"""field-agent SDK tests — the three hooks, adversarial paths, re-export identity."""

import conformance_sentinel.governed as governed_mod

import field_agent
from field_agent import (
    ActionBlocked,
    ActionEscalated,
    AgentKilled,
    HeartbeatUnreachable,
    NoSpendCapError,
)
from tests.conftest import AGENT_ID, DownClient


# -- re-export identity ------------------------------------------------------

def test_reexports_are_the_sentinels_own_classes():
    """Catching field_agent.ActionBlocked catches the sentinel's exception."""
    assert field_agent.ActionBlocked is governed_mod.ActionBlocked
    assert field_agent.ActionEscalated is governed_mod.ActionEscalated
    assert field_agent.Governor is governed_mod.Governor
    assert field_agent.governed is governed_mod.governed


# -- hook 1: ACTIONS ---------------------------------------------------------

def test_check_allow_passes_and_ledgers(stack):
    token = stack.mint_token()
    stack.set_cap()  # manifest declares a spend cap; an unmetered one ESCALATEs
    agent = stack.make_agent(token_id=token)
    verdict = agent.check("draft invoices")
    assert verdict["decision"] == "ALLOW"
    allows = stack.events("conformance.allow")
    assert allows and allows[-1]["payload"]["action"] == "draft invoices"
    assert allows[-1]["agent_id"] == AGENT_ID


def test_check_block_raises_with_clause(stack):
    token = stack.mint_token()
    agent = stack.make_agent(token_id=token)
    calls = []

    @agent.governed("transfer funds")
    def rogue():
        calls.append("ran")

    try:
        rogue()
        assert False, "expected ActionBlocked"
    except ActionBlocked as exc:
        assert exc.verdict["clause_id"] == "D.scope"
    assert calls == []  # the blocked function body never executed
    blocks = stack.events("conformance.block")
    assert blocks and blocks[-1]["payload"]["clause_id"] == "D.scope"


def test_check_escalate_raises(stack):
    token = stack.mint_token()
    agent = stack.make_agent(token_id=token)
    try:
        agent.check("send invoice email")
        assert False, "expected ActionEscalated"
    except ActionEscalated as exc:
        assert exc.verdict["clause_id"] == "E.escalation_trigger"


def test_adversarial_sentinel_down_blocks(stack):
    """Fail closed: sentinel unreachable ⇒ no action runs."""
    agent = stack.make_agent(sentinel_client=DownClient())
    calls = []

    @agent.governed("draft invoices")
    def draft():
        calls.append("ran")

    try:
        draft()
        assert False, "expected ActionBlocked"
    except ActionBlocked as exc:
        assert exc.verdict["clause_id"] == "E.kill_switch"
        assert "failing closed" in "; ".join(exc.verdict["reasons"])
    assert calls == []


# -- hook 2: USAGE -----------------------------------------------------------

def test_report_usage_priced_and_ledgered(stack):
    stack.set_cap()
    agent = stack.make_agent()
    report = agent.report_usage("haiku-4.5", input_tokens=40_000, output_tokens=8_000)
    # haiku: $1/MTok in + $5/MTok out ⇒ 40k*10 + 8k*50 = 800_000 units = $0.08
    assert report.record.priced and report.record.cost_units == 800_000
    assert report.record.model == "claude-haiku-4-5"  # alias canonicalized
    assert report.rogue == []
    recorded = stack.events("usage.recorded")
    assert recorded and recorded[-1]["payload"]["model"] == "claude-haiku-4-5"


def test_adversarial_rogue_model_flagged(stack):
    """A model off the allow-list is a finding, an escalation, and a ledger event."""
    stack.set_cap()
    stack.set_policy(allowed_models=["claude-haiku-4-5"])
    agent = stack.make_agent()
    report = agent.report_usage(
        "claude-opus-4-8", input_tokens=1_000, output_tokens=200
    )
    assert "rogue_model" in [f.kind for f in report.rogue]
    escs = stack.governor.get("/escalations", params={"agent_id": AGENT_ID}).json()
    assert any(e["kind"] == "usage:rogue_model" for e in escs)
    assert stack.events("usage.rogue_model")


def test_adversarial_rogue_burst_flagged(stack):
    """A token burst past the rate ceiling is flagged even below the cap."""
    stack.set_cap()
    stack.set_policy(token_rate_limit=10_000)
    agent = stack.make_agent()
    # 9k + 3k = 12k tokens in one window >= the 10k ceiling
    report = agent.report_usage(
        "claude-haiku-4-5", input_tokens=9_000, output_tokens=3_000
    )
    assert "rogue_burst" in [f.kind for f in report.rogue]
    assert stack.events("usage.rogue_burst")


def test_report_spend_metered(stack):
    stack.set_cap()
    agent = stack.make_agent()
    status = agent.report_spend(cents=12_000, actions=1, note="draft INV-001")
    assert status.state == "OK" and status.spent_cents == 12_000


def test_adversarial_usage_without_cap_raises(stack):
    """Ungoverned spend is refused, not silently dropped."""
    agent = stack.make_agent()
    try:
        agent.report_usage("claude-haiku-4-5", input_tokens=10, output_tokens=10)
        assert False, "expected NoSpendCapError"
    except NoSpendCapError as exc:
        assert "no spend cap" in str(exc)


# -- hook 3: LIVENESS --------------------------------------------------------

def test_heartbeat_alive(stack):
    agent = stack.make_agent()
    hb = agent.ensure_alive()
    assert hb.killed is False and hb.status == "active"


def test_adversarial_killed_heartbeat_halts(stack):
    """killed=true means stop; the SDK enforces the halt."""
    stack.kill()
    agent = stack.make_agent()
    try:
        agent.ensure_alive()
        assert False, "expected AgentKilled"
    except AgentKilled as exc:
        assert exc.heartbeat is not None and exc.heartbeat.killed
    assert stack.events("kill.agent")


def test_adversarial_unknown_agent_halts(stack):
    """Unknown agents are told to stop (registry fail-closed)."""
    agent = stack.make_agent(agent_id="ghost-agent")
    try:
        agent.ensure_alive()
        assert False, "expected AgentKilled"
    except AgentKilled as exc:
        assert exc.heartbeat.status == "unregistered"


def test_adversarial_killswitch_down_halts(stack):
    """Liveness unknown ⇒ assume killed; `except AgentKilled` cannot fail open."""
    agent = stack.make_agent(killswitch_client=DownClient())
    try:
        agent.ensure_alive()
        assert False, "expected HeartbeatUnreachable"
    except AgentKilled as exc:
        assert isinstance(exc, HeartbeatUnreachable)


def test_heartbeat_max_age_gates_check(stack):
    """With heartbeat_max_age set, a killed agent halts at its next check()."""
    token = stack.mint_token()
    stack.kill()
    agent = stack.make_agent(token_id=token, heartbeat_max_age=0.0)
    try:
        agent.check("draft invoices")
        assert False, "expected AgentKilled"
    except AgentKilled:
        pass


# -- cross-cutting -----------------------------------------------------------

def test_adversarial_secret_estate_sdk_succeeds_bare_client_401s(stack, monkeypatch):
    """The SDK attaches x-field-auth per request; a bare client does not."""
    from field_core.authn import ENV_VAR

    token = stack.mint_token()
    stack.set_cap()
    monkeypatch.setenv(ENV_VAR, "s3cret-demo-only")

    bare = stack.sentinel.post(
        "/check", json={"agent_id": AGENT_ID, "action": "draft invoices"}
    )
    assert bare.status_code == 401
    assert stack.governor.get(f"/status/{AGENT_ID}").status_code == 401

    agent = stack.make_agent(token_id=token)
    assert agent.check("draft invoices")["decision"] == "ALLOW"
    report = agent.report_usage("claude-haiku-4-5", input_tokens=100, output_tokens=10)
    assert report.record.priced
    assert agent.ensure_alive().killed is False


def test_facade_end_to_end(stack):
    """One governed working loop: check → act → meter → heartbeat; chain intact."""
    token = stack.mint_token()
    stack.set_cap()
    agent = stack.make_agent(token_id=token)

    drafted = []

    @agent.governed("draft invoices")
    def draft(n):
        drafted.append(n)

    agent.ensure_alive()
    draft(1)
    agent.report_usage(
        "claude-haiku-4-5", input_tokens=2_000, output_tokens=500, note="INV-001"
    )
    assert drafted == [1]
    types = [e["event_type"] for e in stack.events()]
    assert "conformance.allow" in types and "usage.recorded" in types
    assert stack.ledger.get("/verify").json()["ok"] is True


# -- hook 3: LIVENESS check-ins (v1.2) ---------------------------------------

def test_checkin_records_last_seen_server_side(stack):
    """`heartbeat()` reads; `checkin()` writes. Nothing else in the SDK makes
    an agent visible to the kill-switch's GET /liveness."""
    agent = stack.make_agent()

    agent.heartbeat()
    assert stack.heartbeats.get(AGENT_ID) is None, "a poll must not check in"

    hb = agent.checkin()
    assert hb.killed is False and hb.last_seen is not None
    row = stack.heartbeats.get(AGENT_ID)
    assert row is not None and row["checkins"] == 1 and row["status"] == "active"

    liveness = stack.killswitch.get("/liveness", params={"stale_after": 300}).json()
    assert [r["agent_id"] for r in liveness["live"]] == [AGENT_ID]


def test_adversarial_killed_agent_checkin_still_says_killed(stack):
    """A check-in is not a resurrection: the verdict comes from the registry."""
    stack.kill()
    hb = stack.make_agent().checkin()
    assert hb.killed is True and hb.status == "killed"


def test_adversarial_unknown_agent_checkin_says_killed(stack):
    hb = stack.make_agent(agent_id="ghost-agent").checkin()
    assert hb.killed is True and hb.status == "unregistered"
    assert stack.heartbeats.get("ghost-agent")["status"] == "unregistered"


def test_adversarial_checkin_with_killswitch_down_halts(stack):
    """Liveness unknown ⇒ halt, same fail-closed contract as heartbeat()."""
    agent = stack.make_agent(killswitch_client=DownClient())
    try:
        agent.checkin()
        assert False, "expected HeartbeatUnreachable"
    except AgentKilled as exc:
        assert isinstance(exc, HeartbeatUnreachable)
