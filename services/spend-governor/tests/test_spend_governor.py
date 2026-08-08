"""spend-governor tests: metering, thresholds, hard caps, adversarial arithmetic."""

import pytest
from fastapi.testclient import TestClient

from field_core.manifest import FieldManifest
from field_core.templates_api import template_data
from spend_governor.api import create_app
from spend_governor.core import GovernorStore, SpendCapConfig, evaluate


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=GovernorStore(tmp_path / "spend.sqlite3")))


def set_cap(client, **overrides):
    body = {
        "agent_id": "invoicing-agent",
        "currency": "USD",
        "limit_cents": 50_000,  # $500 daily, per the financial-agent template
        "period": "daily",
        "escalate_at_pct": 80,
    }
    body.update(overrides)
    r = client.put(f"/caps/{body['agent_id']}", json=body)
    assert r.status_code == 200
    return r.json()


def spend(client, cents=0, tokens=0, actions=0):
    return client.post(
        "/spend",
        json={"agent_id": "invoicing-agent", "cents": cents, "tokens": tokens,
              "actions": actions},
    )


def test_cap_from_financial_manifest():
    manifest = FieldManifest.from_dict(template_data("financial-agent"))
    cap = SpendCapConfig.from_manifest(manifest, "fin-agent")
    assert cap.limit_cents == 50_000  # USD 500 -> cents, integer
    assert cap.period == "daily"
    assert cap.on_breach == "halt"


def test_spend_within_limits_ok(client):
    set_cap(client)
    status = spend(client, cents=10_000).json()
    assert status["state"] == "OK"
    assert status["spent_cents"] == 10_000


def test_threshold_escalates_before_cap(client):
    set_cap(client)
    status = spend(client, cents=40_000).json()  # exactly 80%
    assert status["state"] == "ESCALATE"
    escs = client.get("/escalations").json()
    assert len(escs) == 1
    assert escs[0]["kind"] == "cents"
    assert escs[0]["spent"] == 40_000

    # More spend below the cap does not duplicate the escalation.
    spend(client, cents=1_000)
    assert len(client.get("/escalations").json()) == 1


def test_hard_cap_blocks(client):
    set_cap(client)
    spend(client, cents=49_999)
    status = spend(client, cents=1).json()  # exactly at cap
    assert status["state"] == "BLOCK"
    assert "cap reached" in status["detail"]


def test_resolving_escalation_returns_to_ok(client):
    set_cap(client)
    spend(client, cents=40_000)
    esc_id = client.get("/escalations").json()[0]["escalation_id"]
    r = client.post(
        f"/escalations/{esc_id}/resolve", json={"resolved_by": "Controller"}
    )
    assert r.status_code == 200
    # Still >= threshold, so a fresh escalation would re-fire on next spend —
    # but pure status reads now show the arithmetic state, not a stale queue.
    status = client.get("/status/invoicing-agent").json()
    assert status["open_escalations"] == 0


def test_action_and_token_limits(client):
    set_cap(client, limit_cents=None, token_limit=1000, action_limit=10)
    assert spend(client, tokens=500, actions=2).json()["state"] == "OK"
    assert spend(client, tokens=300).json()["state"] == "ESCALATE"  # 800 = 80%
    status = spend(client, actions=8).json()  # actions hit 10 = cap
    assert status["state"] == "BLOCK"
    assert "actions cap" in status["detail"]


def test_spend_without_cap_refused(client):
    r = client.post("/spend", json={"agent_id": "ghost", "cents": 1})
    assert r.status_code == 404
    assert "ungoverned" in r.json()["detail"]


def test_adversarial_negative_spend_rejected(client):
    """Adversarial: negative amounts must not reduce the running total."""
    set_cap(client)
    r = client.post("/spend", json={"agent_id": "invoicing-agent", "cents": -500})
    assert r.status_code == 422


def test_adversarial_integer_threshold_no_float_drift():
    """evaluate() uses pure integer comparisons — no float rounding escape.

    599_999 cents of a 600_000 cap at 99% threshold: 599_999*100 < 600_000*99
    is False (59_999_900 >= 59_400_000) -> ESCALATE, and at the cap -> BLOCK.
    """
    cap = SpendCapConfig(
        agent_id="a", limit_cents=600_000, period="total", escalate_at_pct=99
    )
    state, _ = evaluate(cap, 599_999, 0, 0, 0)
    assert state.value == "ESCALATE"
    state, _ = evaluate(cap, 600_000, 0, 0, 0)
    assert state.value == "BLOCK"
    state, _ = evaluate(cap, 594_000, 0, 0, 0)  # exactly 99%
    assert state.value == "ESCALATE"
    state, _ = evaluate(cap, 593_999, 0, 0, 0)  # one cent under 99%
    assert state.value == "OK"


def test_sub_cent_manifest_limit_refused():
    manifest_data = template_data("financial-agent")
    manifest_data["enforcement"]["spend_cap"]["limit"] = 0.001
    manifest = FieldManifest.from_dict(manifest_data)
    with pytest.raises(ValueError, match="sub-cent"):
        SpendCapConfig.from_manifest(manifest, "fin-agent")
