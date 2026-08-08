"""force-gateway tests: preset fidelity, injection, telemetry, adversarial."""

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import create_app, inject_force_block, mock_upstream
from force_gateway.presets import PRESETS, preset_block
from force_gateway.telemetry import analyze


# --- preset fidelity: blocks come verbatim from the shipped protocol ---

def test_preset_letter_composition():
    assert PRESETS == {"analysis": "FORCE", "brainstorm": "FCE",
                       "draft": "FC", "audit": "FRCE"}


def test_analysis_contains_all_five_verbatim_lines():
    block = preset_block("analysis")
    # one distinctive verbatim line per component, from protocol.md
    assert "No sycophancy" in block                                # F
    assert "strongest objections" in block                         # O
    assert "Do not invent citations" in block                      # R
    assert "ASSUMPTIONS:" in block                                 # C
    assert "Prefer \"I don't know\" over a guess" in block         # E
    assert "No filler openings" in block                           # OUTPUT RULES


def test_audit_skips_objections():
    block = preset_block("audit")
    assert "strongest objections" not in block   # no O
    assert "Do not invent citations" in block    # R present


def test_draft_is_minimal():
    block = preset_block("draft")
    assert "ASSUMPTIONS:" in block
    assert "confidence level" not in block       # no E
    assert "strongest objections" not in block   # no O


def test_unknown_preset_raises():
    with pytest.raises(KeyError):
        preset_block("vibes")


# --- injection preserves the caller's system prompt ---

def test_inject_into_absent_system():
    body = inject_force_block({"model": "m", "messages": []}, "draft")
    assert body["system"].startswith("# FORCE Runtime Protocol")


def test_inject_preserves_string_system():
    body = inject_force_block(
        {"system": "You are the invoicing agent.", "messages": []}, "analysis"
    )
    assert "# FORCE Runtime Protocol" in body["system"]
    assert "You are the invoicing agent." in body["system"]
    assert body["system"].index("FORCE") < body["system"].index("invoicing agent")


def test_inject_preserves_block_list_system():
    original = [{"type": "text", "text": "You are the invoicing agent."}]
    body = inject_force_block({"system": original, "messages": []}, "audit")
    assert body["system"][0]["text"].startswith("# FORCE Runtime Protocol")
    assert body["system"][1]["text"] == "You are the invoicing agent."


# --- telemetry heuristics ---

def test_telemetry_detects_force_markers():
    report = analyze(
        "Correction: the premise is flawed.\n"
        "ASSUMPTIONS:\n1. X. [HIGH]\nREASONING:\n1. Y. [LOW]\nCONCLUSION:\nZ."
    )
    assert report.has_confidence_tags and report.confidence_tags == 2
    assert report.corrections >= 1
    assert report.cot_structure is True
    assert report.clean_of_flattery is True
    assert "heuristic" in report.method


def test_adversarial_flattery_is_flagged():
    report = analyze("Great question! I'd be happy to help. Hope this helps!")
    assert report.flattery_hits == 3
    assert report.clean_of_flattery is False


# --- end-to-end through the mock upstream ---

@pytest.fixture()
def client():
    return TestClient(create_app(upstream=mock_upstream))


def test_proxy_roundtrip_records_telemetry(client):
    r = client.post(
        "/v1/messages",
        json={"model": "claude-x", "max_tokens": 512,
              "system": "You are the invoicing agent.",
              "messages": [{"role": "user", "content": "Draft the invoice."}]},
        headers={"x-force-preset": "audit", "x-field-agent-id": "invoicing-agent"},
    )
    assert r.status_code == 200
    assert r.json()["usage"]["output_tokens"] == 118

    summary = client.get("/telemetry").json()
    assert summary["total_requests"] == 1
    assert summary["by_preset"] == {"audit": 1}
    assert summary["responses_with_confidence_tags"] == 1
    assert summary["responses_with_cot_structure"] == 1
    assert summary["responses_clean_of_flattery"] == 1
    assert summary["total_output_tokens"] == 118
    assert "heuristic" in summary["method"]
    assert summary["recent"][0]["agent_id"] == "invoicing-agent"


def test_unknown_preset_rejected(client):
    r = client.post(
        "/v1/messages",
        json={"model": "m", "messages": []},
        headers={"x-force-preset": "vibes"},
    )
    assert r.status_code == 422


def test_governor_gets_token_spend(tmp_path):
    class FakeGovernor:
        def __init__(self):
            self.calls = []

        def post(self, url, json=None, **kw):
            self.calls.append((url, json))

    gov = FakeGovernor()
    client = TestClient(create_app(upstream=mock_upstream, governor_client=gov))
    client.post(
        "/v1/messages",
        json={"model": "m", "messages": []},
        headers={"x-field-agent-id": "invoicing-agent"},
    )
    assert gov.calls == [
        ("/spend", {"agent_id": "invoicing-agent", "tokens": 358,
                    "note": "force-gateway LLM call"})
    ]
