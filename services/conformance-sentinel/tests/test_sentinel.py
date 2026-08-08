"""Sentinel decision tests — every clause, adversarial paths, decorator."""

import conformance_sentinel.governed as governed_mod
from conformance_sentinel.governed import ActionBlocked, ActionEscalated, Governor, governed
from tests.conftest import AGENT_ID


def test_allow_path_logs_to_ledger(stack):
    stack.set_cap()
    token = stack.mint_token()
    verdict = stack.check("draft invoices", token_id=token)
    assert verdict["decision"] == "ALLOW"
    assert verdict["clause_id"] is None

    allows = stack.ledger.get(
        "/events", params={"event_type": "conformance.allow"}
    ).json()
    assert len(allows) == 1
    assert allows[0]["payload"]["action"] == "draft invoices"


def test_killed_agent_blocks_instantly(stack):
    stack.set_cap()
    token = stack.mint_token()
    assert stack.check("draft invoices", token_id=token)["decision"] == "ALLOW"

    stack.registry.patch(f"/agents/{AGENT_ID}", json={"status": "killed"})
    verdict = stack.check("draft invoices", token_id=token)
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "E.kill_switch"


def test_unregistered_agent_blocks(stack):
    r = stack.sentinel.post(
        "/check", json={"agent_id": "ghost", "action": "anything", "token_id": "x"}
    )
    verdict = r.json()
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "R.unregistered"


def test_missing_manifest_blocks(stack):
    stack.manifest_path.unlink()
    token = stack.mint_token()
    verdict = stack.check("draft invoices", token_id=token)
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "I.manifest"


def test_adversarial_invalid_manifest_blocks(stack):
    """Adversarial: someone unseals the ledger clause in the manifest on disk.
    The manifest is now INVALID; the agent loses all authority."""
    stack.set_cap()
    token = stack.mint_token()
    text = stack.manifest_path.read_text(encoding="utf-8")
    stack.manifest_path.write_text(
        text.replace("cryptographic_seal: true", "cryptographic_seal: false"),
        encoding="utf-8",
    )
    verdict = stack.check("draft invoices", token_id=token)
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "I.manifest"


def test_no_token_blocks(stack):
    stack.set_cap()
    verdict = stack.check("draft invoices", token_id=None)
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "D.token"


def test_revoked_token_blocks_with_clause(stack):
    stack.set_cap()
    token = stack.mint_token()
    stack.delegation.post(f"/tokens/{token}/revoke")
    verdict = stack.check("draft invoices", token_id=token)
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "D.revoked"


def test_adversarial_out_of_scope_blocks(stack):
    """The invoicing agent tries to 'transfer funds' — not in any scope."""
    stack.set_cap()
    token = stack.mint_token()
    verdict = stack.check("transfer funds", token_id=token)
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "D.scope"

    blocks = stack.ledger.get(
        "/events", params={"event_type": "conformance.block"}
    ).json()
    assert blocks[-1]["payload"]["clause_id"] == "D.scope"


def test_adversarial_token_narrower_than_manifest(stack):
    """Token minted for reading only; manifest allows drafting too.
    The narrower grant wins — drafting blocks on token scope."""
    stack.set_cap()
    token = stack.mint_token(scope=["read timesheets"])
    assert stack.check("read timesheets", token_id=token)["decision"] == "ALLOW"
    verdict = stack.check("draft invoices", token_id=token)
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "D.scope"


def test_irreversible_escalates_per_policy(stack):
    stack.set_cap()
    token = stack.mint_token()
    verdict = stack.check("draft invoices", token_id=token, irreversible=True)
    assert verdict["decision"] == "ESCALATE"
    assert verdict["clause_id"] == "E.irreversible"


def test_escalation_trigger_matches(stack):
    stack.set_cap()
    token = stack.mint_token()
    verdict = stack.check("send invoice email", token_id=token)
    assert verdict["decision"] == "ESCALATE"
    assert verdict["clause_id"] == "E.escalation_trigger"


def test_spend_threshold_and_cap(stack):
    stack.set_cap(limit_cents=50_000)
    token = stack.mint_token()

    stack.governor.post("/spend", json={"agent_id": AGENT_ID, "cents": 40_000})
    verdict = stack.check("draft invoices", token_id=token)
    assert verdict["decision"] == "ESCALATE"
    assert verdict["clause_id"] == "E.spend_threshold"

    stack.governor.post("/spend", json={"agent_id": AGENT_ID, "cents": 10_000})
    verdict = stack.check("draft invoices", token_id=token)
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "E.spend_cap"


def test_declared_cap_without_governor_config_escalates(stack):
    """Manifest declares a spend_cap; nobody configured the governor.
    That metering gap goes to a human, not silently ALLOW."""
    token = stack.mint_token()
    verdict = stack.check("draft invoices", token_id=token)
    assert verdict["decision"] == "ESCALATE"
    assert verdict["clause_id"] == "E.spend_cap"
    assert "metering gap" in verdict["reasons"][0]


def test_adversarial_ledger_down_blocks_everything(stack):
    """Fail closed: no audit trail, no actions."""
    stack.set_cap()
    token = stack.mint_token()
    stack.ledger_up = False
    verdict = stack.check("draft invoices", token_id=token)
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "L.unreachable"


def test_governed_decorator_allows_and_blocks(stack, monkeypatch):
    stack.set_cap()
    token = stack.mint_token()
    monkeypatch.setattr(
        governed_mod.httpx, "Client", lambda timeout=None: stack.sentinel
    )

    calls = []

    @governed(agent_id=AGENT_ID, action="draft invoices", token_id=lambda: token)
    def draft():
        calls.append("ran")
        return "INV-001"

    assert draft() == "INV-001"
    assert calls == ["ran"]

    @governed(agent_id=AGENT_ID, action="transfer funds", token_id=lambda: token)
    def rogue():
        calls.append("must never run")

    try:
        rogue()
        assert False, "expected ActionBlocked"
    except ActionBlocked as exc:
        assert exc.verdict["clause_id"] == "D.scope"
    assert calls == ["ran"]  # the blocked function body never executed

    guard = Governor(agent_id=AGENT_ID, token_id=token, client=stack.sentinel)
    try:
        guard.check("send invoice email")
        assert False, "expected ActionEscalated"
    except ActionEscalated as exc:
        assert exc.verdict["clause_id"] == "E.escalation_trigger"
