import os
import sys
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generators.models.adk_agent import (  # noqa: E402
    AdkAgentGenerator,
    _text_from_adk_http,
)


def test_text_from_adk_http_collects_parts():
    raw = (
        '{"content": {"parts": [{"text": "Scores\\n"}]}}\n'
        '{"content": {"parts": [{"text": "- Tone: 4/5"}]}}'
    )
    assert _text_from_adk_http(raw) == "Scores\n- Tone: 4/5"


@patch("generators.models.adk_agent.vertexai.init")
@patch("generators.models.adk_agent.agent_engines.AgentEngine")
def test_generator_initialization(mock_agent_engine, mock_vertexai_init):
    config = {
        "resource_name": "projects/p/locations/l/reasoningEngines/r",
        "gcp_project_id": "test-project",
        "gcp_region": "us-central1",
    }
    generator = AdkAgentGenerator(config)
    mock_vertexai_init.assert_called_once_with(
        project="test-project", location="us-central1"
    )
    mock_agent_engine.assert_called_once_with(
        "projects/p/locations/l/reasoningEngines/r"
    )
    assert generator.name == "adk_agent"
    assert generator.remote_app == mock_agent_engine.return_value


@patch("generators.models.adk_agent.vertexai.init")
@patch("generators.models.adk_agent.agent_engines.AgentEngine")
def test_generate_internal_keeps_full_text(mock_agent_engine, mock_vertexai_init):
    config = {
        "resource_name": "projects/p/locations/l/reasoningEngines/r",
        "gcp_project_id": "test-project",
        "gcp_region": "us-central1",
    }
    mock_client = MagicMock()
    mock_agent_engine.return_value.execution_api_client = mock_client
    mock_chunk = MagicMock()
    mock_chunk.data = (
        b'{"content": {"parts": [{"text": "Scores\\n- Tone: 3/5"}]}}'
    )
    mock_client.stream_query_reasoning_engine.return_value = [mock_chunk]

    generator = AdkAgentGenerator(config)
    text = generator.generate_internal("critique this")
    assert "Tone: 3/5" in text
    assert "SELECT" not in text
    request = mock_client.stream_query_reasoning_engine.call_args[1]["request"]
    assert request.class_method == "async_stream_query"


def test_localhost_url_skips_agent_engine():
    generator = AdkAgentGenerator({"url": "http://127.0.0.1:8000"})
    assert generator.remote_app is None
    assert generator.url == "http://127.0.0.1:8000"


def test_rejects_placeholder_resource():
    try:
        AdkAgentGenerator({
            "resource_name": "projects/.../reasoningEngines/...",
            "gcp_project_id": "test-project",
            "gcp_region": "us-east1",
        })
    except ValueError as exc:
        assert "placeholder" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_rejects_plain_http_remote():
    try:
        AdkAgentGenerator({"url": "http://example.com:8000"})
    except ValueError as exc:
        assert "https" in str(exc)
    else:
        raise AssertionError("expected ValueError")
