"""ADK / Agent Engine generator for free-text agents (not NL2SQL).

Unlike :class:`AgentRuntimeGenerator`, this keeps the full model text so
EvalBench can score critiques, judgements, and other non-SQL outputs.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from google.api_core.exceptions import ResourceExhausted
from google.cloud.aiplatform_v1.types import (
    reasoning_engine_execution_service as aip_types,
)
import vertexai
from vertexai import agent_engines

from generators.models.agent_cli import AgentCliGenerator
from generators.models.agent_runtime import _parse_stream_response
from util.gcp import get_gcp_project, get_gcp_region
from util.rate_limit import ResourceExhaustedError


def _is_placeholder_resource(name: str) -> bool:
    return "..." in name or "YOUR_" in name or "<" in name


class _AdkCommand:
    def __init__(self, prompt: str):
        self.prompt = prompt


class AdkAgentGenerator(AgentCliGenerator):
    """Query a deployed ADK Agent Engine or a local ADK FastAPI app."""

    def __init__(self, querygenerator_config):
        super().__init__(querygenerator_config)
        self.name = "adk_agent"
        self.fake_home = None
        self.resource_name = (
            querygenerator_config.get("resource_name")
            or os.environ.get("AGENT_ENGINE_RESOURCE")
            or ""
        )
        self.url = (
            querygenerator_config.get("url")
            or os.environ.get("ADK_AGENT_URL")
            or ""
        )
        self.app_name = querygenerator_config.get("app_name") or "app"
        # AdkApp engines register streaming as async_stream_query. stream_query
        # is accepted by the API but returns an empty HttpBody on those engines.
        self.class_method = (
            querygenerator_config.get("class_method") or "async_stream_query"
        )
        self.remote_app = None

        if self.url:
            self._validate_url(self.url)
            return

        if not self.resource_name:
            raise ValueError(
                "AdkAgentGenerator requires `resource_name` / "
                "AGENT_ENGINE_RESOURCE or `url` / ADK_AGENT_URL."
            )
        if _is_placeholder_resource(self.resource_name):
            raise ValueError(
                "AGENT_ENGINE_RESOURCE is a placeholder "
                f"({self.resource_name!r}). Export the full Agent Engine id, "
                "e.g. projects/689632009240/locations/us-east1/"
                "reasoningEngines/7997777211698446336"
            )

        project_id = get_gcp_project(querygenerator_config.get("gcp_project_id"))
        location = get_gcp_region(querygenerator_config.get("gcp_region"))
        logging.info(
            "Initializing Vertex AI (Project: %s, Location: %s)",
            project_id,
            location,
        )
        vertexai.init(project=project_id, location=location)
        logging.info("Connecting to ADK Agent Engine: %s", self.resource_name)
        self.remote_app = agent_engines.AgentEngine(self.resource_name)

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        local = host in ("127.0.0.1", "localhost", "::1")
        if parsed.scheme not in ("http", "https"):
            raise ValueError("ADK agent url must be http(s)")
        if not local and parsed.scheme != "https":
            raise ValueError(
                "ADK_AGENT_URL must use https:// unless it targets localhost"
            )

    @property
    def version(self) -> str:
        return "adk_agent"

    def create_command(
        self, cli, prompt, env=None, resume=False, session_id=None, cwd=None
    ):
        return _AdkCommand(prompt)

    def generate_internal(self, prompt: str) -> str:
        if self.url:
            return self._query_http(prompt)
        try:
            client = self.remote_app.execution_api_client
            response = client.stream_query_reasoning_engine(
                request=aip_types.StreamQueryReasoningEngineRequest(
                    name=self.resource_name,
                    input={
                        "message": prompt,
                        "user_id": "evalbench_user",
                    },
                    class_method=self.class_method,
                ),
            )
            text = _parse_stream_response(response)
            if not text:
                raise RuntimeError(
                    f"ADK Agent Engine returned no text via {self.class_method}"
                )
            return text
        except ResourceExhausted as exc:
            raise ResourceExhaustedError(exc)

    def safe_generate(
        self, cli_cmd, timeout_seconds: Optional[float] = None
    ) -> subprocess.CompletedProcess:
        prompt = getattr(cli_cmd, "prompt", "")
        try:
            stdout = self.generate(prompt) or ""
            return subprocess.CompletedProcess(
                args=["adk_agent"],
                returncode=0 if stdout else 1,
                stdout=stdout,
                stderr="" if stdout else "ADK Agent Engine returned empty text",
            )
        except Exception as exc:
            logging.exception("Error querying ADK Agent Engine: %s", exc)
            return subprocess.CompletedProcess(
                args=["adk_agent"],
                returncode=1,
                stdout="",
                stderr=f"{type(exc).__name__}: {exc}",
            )

    def parse_response(self, stdout: str) -> dict:
        return {}

    def extract_tools(self, stdout: str) -> list:
        return []

    def extract_skills(self, stdout: str) -> list:
        return []

    def _query_http(self, prompt: str) -> str:
        payload = {
            "appName": self.app_name,
            "userId": "evalbench_user",
            "sessionId": "evalbench",
            "newMessage": {
                "role": "user",
                "parts": [{"text": prompt}],
            },
        }
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            self.url.rstrip("/") + "/run",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=120) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
        return _text_from_adk_http(raw)


def _text_from_adk_http(raw: str) -> str:
    """Collect model text from an ADK `/run` JSON (object or NDJSON)."""
    chunks: list[str] = []
    for line in raw.splitlines() or [raw]:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        chunks.extend(_walk_text(parsed))
    if chunks:
        return "".join(chunks)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    return "".join(_walk_text(parsed)) or raw


def _walk_text(node) -> list[str]:
    texts: list[str] = []
    if isinstance(node, dict):
        text = node.get("text")
        if isinstance(text, str) and "parts" not in node:
            texts.append(text)
        for key, value in node.items():
            if key == "text":
                continue
            if isinstance(value, (dict, list)):
                texts.extend(_walk_text(value))
    elif isinstance(node, list):
        for item in node:
            texts.extend(_walk_text(item))
    return texts
