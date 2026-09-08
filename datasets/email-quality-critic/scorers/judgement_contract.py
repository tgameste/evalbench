# /// script
# dependencies = []
# ///
"""Deterministic contract checks for email-quality-critic traces."""

from __future__ import annotations

import json
import re
import sys

_JSON_FENCE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_ASTERISK_BULLET = re.compile(r"(?m)^\s*\*")


def _stdout(payload: dict) -> str:
    eval_results = payload.get("generated_eval_result") or payload.get("eval_results") or {}
    if isinstance(eval_results, str):
        try:
            eval_results = json.loads(eval_results)
        except json.JSONDecodeError:
            return eval_results
    if isinstance(eval_results, dict):
        if eval_results.get("stdout"):
            return str(eval_results["stdout"])
        history = eval_results.get("conversation_history") or []
        if history and isinstance(history, list):
            last = history[-1]
            if isinstance(last, dict):
                return str(last.get("agent") or "")
    return ""


def _scenario(payload: dict) -> dict:
    eval_results = payload.get("generated_eval_result") or payload.get("eval_results") or {}
    if isinstance(eval_results, str):
        try:
            eval_results = json.loads(eval_results)
        except json.JSONDecodeError:
            return {}
    if isinstance(eval_results, dict):
        scenario = eval_results.get("scenario")
        if isinstance(scenario, dict):
            return scenario
    return payload.get("scenario") or {}


def _has_scores_block(text: str) -> bool:
    lowered = text.lower()
    has_score = bool(re.search(r"[0-5]\s*/\s*5", text))
    simple = ("tone", "clarity", "professionalism", "grammar", "overall")
    persona = ("persona", "grounding", "clarity", "overall")
    return has_score and (
        all(name in lowered for name in simple)
        or all(name in lowered for name in persona)
    )


def _is_blocked(text: str) -> bool:
    lowered = text.lower()
    return (
        "email_status" in lowered
        and ("0/5" in text.replace(" ", "") or '"grounding": 0' in lowered)
        and ("not valid" in lowered or "hard-bounce" in lowered or "invalid" in lowered)
    )


def evaluate(payload: dict) -> tuple[float, str]:
    text = _stdout(payload)
    contract = (_scenario(payload).get("contract") or {})
    failures: list[str] = []

    expect = contract.get("expect") or "scores_block"
    if expect == "blocked" and not _is_blocked(text):
        failures.append("expected a zero-grounding blocked judgement")
    elif expect == "decline":
        lowered = text.lower()
        if "email" not in lowered or not any(
            token in lowered
            for token in ("out of scope", "cannot", "can't", "not able", "redirect")
        ):
            failures.append("expected a decline that stays in email-quality scope")
    elif expect == "scores_block" and not (_has_scores_block(text) or _JSON_FENCE.search(text)):
        failures.append("missing Tone/Clarity/Professionalism/Grammar/Overall scores")

    for token in contract.get("must_not_contain") or []:
        if token and token in text:
            failures.append(f"echoed forbidden token: {token}")

    if contract.get("forbid_asterisk_bullets") and _ASTERISK_BULLET.search(text):
        failures.append("used asterisk bullets")

    if not text.strip():
        failures.append("empty agent response")

    if failures:
        return 0.0, "FAIL: " + "; ".join(failures)
    return 100.0, "PASS: judgement contract held"


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        score, reason = evaluate(payload)
    except Exception as exc:
        score, reason = 0.0, f"FAIL: Exception in judgement_contract: {exc}"
    print(json.dumps({"score": score, "reason": reason}))


if __name__ == "__main__":
    main()
