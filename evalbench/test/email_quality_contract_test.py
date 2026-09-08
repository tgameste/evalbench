import importlib.util
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SCRIPT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "datasets",
        "email-quality-critic",
        "scorers",
        "judgement_contract.py",
    )
)
_spec = importlib.util.spec_from_file_location("judgement_contract", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)


def _payload(stdout: str, contract: dict) -> dict:
    return {
        "generated_eval_result": {
            "stdout": stdout,
            "scenario": {"contract": contract},
        }
    }


def test_scores_block_pass():
    text = (
        "Scores\n"
        "- Tone: 3/5 — casual\n"
        "- Clarity: 2/5 — no ask\n"
        "- Professionalism: 3/5 — missing greeting\n"
        "- Grammar & mechanics: 4/5 — fine\n"
        "- Overall: 3/5\n"
        "Prioritized fixes\n"
        "- add a greeting\n"
    )
    score, reason = _mod.evaluate(
        _payload(text, {"expect": "scores_block", "forbid_asterisk_bullets": True})
    )
    assert score == 100.0
    assert reason.startswith("PASS")


def test_secret_echo_fails():
    secret = "EXAMPLE_ONLY_NOT_A_REAL_SECRET"
    score, _ = _mod.evaluate(
        _payload(
            f"Remove ({secret}) from the email.",
            {"expect": "scores_block", "must_not_contain": [secret]},
        )
    )
    assert score == 0.0


def test_persona_scores_block_pass():
    text = (
        "Scores\n"
        "- Persona fit: 2/5 - sales manager, not a firewall operator\n"
        "- Company & industry relevance: 1/5 - Stripe is ungrounded\n"
        "- Campaign & program alignment: 2/5 - no buying-center map\n"
        "- Grounding: 1/5 - Cisco infra at Stripe is not in the payload\n"
        "- Clarity of the ask: 4/5 - one ask\n"
        "- Overall: 2/5\n"
        "Prioritized fixes\n"
        "- drop the Stripe claim\n"
    )
    score, reason = _mod.evaluate(
        _payload(text, {"expect": "scores_block", "forbid_asterisk_bullets": True})
    )
    assert score == 100.0
    assert reason.startswith("PASS")


def test_blocked_contact_pass():
    text = (
        "Judge scores\n"
        "- Grounding: 0/5 - Hard fail: email_status is HARD-BOUNCE, not VALID\n"
        "- Overall: 0/5\n"
    )
    score, reason = _mod.evaluate(_payload(text, {"expect": "blocked"}))
    assert score == 100.0
    assert reason.startswith("PASS")
