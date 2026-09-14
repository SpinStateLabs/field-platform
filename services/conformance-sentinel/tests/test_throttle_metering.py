"""D1 sentinel half: step 8 maps THROTTLED to BLOCK ``E.rate_limit``, option A
metering of every ALLOW, and D1e's token spend ceiling.

The governor in these stacks runs on a frozen clock (``create_app(clock=)``)
so ``retry_after_seconds`` is exact. Everything else is the real in-process
spine from ``conftest.Stack``."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

from conformance_sentinel.engine import SpendStatusClient
from conformance_sentinel.governed import ActionBlocked
from conformance_sentinel.judge import MockJudgeClient
from conformance_sentinel.mode import SentinelMode
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore
from tests.conftest import AGENT_ID

SENTINEL_ID = "conformance-sentinel"
T0 = datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def at(self, seconds: float) -> None:
        self.now = T0 + timedelta(seconds=seconds)


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def gstack(stack, tmp_path, clock):
    """The conftest stack with its governor rebuilt on the frozen clock."""
    store = GovernorStore(tmp_path / "spend-frozen.sqlite3")
    stack.governor = TestClient(create_governor_app(store=store, clock=clock))
    engine = stack.sentinel.app.state.engine
    engine.governor = SpendStatusClient(client=stack.governor, base_url="http://t")
    yield stack
    store.close()


def _limit(stack, action="draft invoices", max_=3, period="hourly", agent=AGENT_ID):
    r = stack.governor.put(f"/rate-limits/{agent}", json={
        "agent_id": agent, "rate_limits": [{"action": action, "max": max_, "period": period}]})
    assert r.status_code == 200, r.text


def _status(stack, action=None, agent=AGENT_ID):
    params = {"action": action} if action else {}
    return stack.governor.get(f"/status/{agent}", params=params).json()


# -- THROTTLED ⇒ BLOCK E.rate_limit ----------------------------------------------

def test_exhausted_window_blocks_with_rate_limit_context_and_ledger(gstack, clock):
    gstack.set_cap()
    _limit(gstack)
    token = gstack.mint_token()

    for _ in range(3):  # N allowed — each ALLOW is metered by the sentinel
        v = gstack.check("draft invoices", token_id=token)
        assert v["decision"] == "ALLOW" and v["context"]["metered"] is True
    v = gstack.check("draft invoices", token_id=token)  # N+1
    assert v["decision"] == "BLOCK" and v["clause_id"] == "E.rate_limit"
    assert v["context"]["retry_after_seconds"] == 3600
    assert "rate limit" in v["reasons"][0]
    assert "metered" not in v["context"]  # a BLOCK is never metered

    blocks = gstack.ledger.get("/events", params={"event_type": "conformance.block"}).json()
    assert blocks[-1]["payload"]["clause_id"] == "E.rate_limit"
    assert blocks[-1]["payload"]["retry_after_seconds"] == 3600
    assert _status(gstack, "draft invoices")["spent_actions_metered"] == 3

    clock.at(3599)
    v = gstack.check("draft invoices", token_id=token)
    assert (v["clause_id"], v["context"]["retry_after_seconds"]) == ("E.rate_limit", 1)
    clock.at(3600)
    assert gstack.check("draft invoices", token_id=token)["decision"] == "ALLOW"


def test_log_only_shadows_rate_limit_and_keeps_filling_the_window(gstack, monkeypatch):
    gstack.set_cap()
    _limit(gstack, max_=2)
    token = gstack.mint_token()
    engine = gstack.sentinel.app.state.engine
    engine.mode = SentinelMode.LOG_ONLY
    posted = []
    real_record = engine.governor.record_action

    def spy(agent_id, action, *, shadowed):
        posted.append((action, shadowed))
        return real_record(agent_id, action, shadowed=shadowed)

    monkeypatch.setattr(engine.governor, "record_action", spy)

    for _ in range(2):
        assert gstack.check("draft invoices", token_id=token)["decision"] == "ALLOW"
    assert posted == [("draft invoices", False), ("draft invoices", False)]
    v = gstack.check("draft invoices", token_id=token)
    assert posted[-1] == ("draft invoices", True)  # the shadowed ALLOW says so
    assert v["decision"] == "ALLOW" and v["context"]["shadowed"] is True
    assert v["context"]["would_be"] == {"decision": "BLOCK", "clause_id": "E.rate_limit"}
    assert v["context"]["retry_after_seconds"] == 3600
    assert v["context"]["metered"] is True  # the action ran, so it is counted

    shadows = gstack.ledger.get(
        "/events", params={"event_type": "conformance.shadow_block"}).json()
    assert shadows[-1]["payload"]["would_block"] == "E.rate_limit"
    assert shadows[-1]["payload"]["retry_after_seconds"] == 3600
    assert gstack.ledger.get("/events", params={"event_type": "conformance.block"}).json() == []
    status = _status(gstack, "draft invoices")
    assert status["spent_actions_metered"] == 3 and status["throttled"]["count"] == 3


def test_per_action_isolation(gstack):
    gstack.set_cap()
    _limit(gstack, max_=1)
    token = gstack.mint_token()
    assert gstack.check("draft invoices", token_id=token)["decision"] == "ALLOW"
    assert gstack.check("draft invoices", token_id=token)["clause_id"] == "E.rate_limit"
    assert gstack.check("read timesheets", token_id=token)["decision"] == "ALLOW"
    assert gstack.check("read timesheets", token_id=token)["decision"] == "ALLOW"


def test_cap_block_outranks_rate_limit(gstack):
    gstack.set_cap(limit_cents=1_000)
    _limit(gstack, max_=1)
    token = gstack.mint_token()
    assert gstack.check("draft invoices", token_id=token)["decision"] == "ALLOW"
    gstack.governor.post("/spend", json={"agent_id": AGENT_ID, "cents": 1_000})
    v = gstack.check("draft invoices", token_id=token)
    assert (v["decision"], v["clause_id"]) == ("BLOCK", "E.spend_cap")
    assert "retry_after_seconds" not in v["context"]


def test_retry_after_reaches_action_blocked(gstack):
    from conformance_sentinel.governed import Governor

    gstack.set_cap()
    _limit(gstack, max_=1)
    token = gstack.mint_token()
    guard = Governor(agent_id=AGENT_ID, token_id=token, client=gstack.sentinel)
    guard.check("draft invoices")
    with pytest.raises(ActionBlocked) as caught:
        guard.check("draft invoices")
    assert caught.value.retry_after == _status(gstack, "draft invoices")["retry_after_seconds"]
    assert caught.value.retry_after == 3600
    with pytest.raises(ActionBlocked) as other:
        guard.check("transfer funds")
    assert other.value.retry_after is None  # D.scope carries no retry time


def test_throttled_sentinel_budget_does_not_pause_judgments(gstack):
    """The judge gate keeps ``== "BLOCK"``: THROTTLED on the sentinel's own
    budget (here its token window) does not stop a judgment."""
    gstack.set_cap()
    r = gstack.governor.put(f"/caps/{SENTINEL_ID}", json={
        "agent_id": SENTINEL_ID, "limit_cents": 10_000, "period": "daily",
        "escalate_at_pct": 80})
    assert r.status_code == 200
    gstack.governor.put(f"/policies/{SENTINEL_ID}", json={
        "agent_id": SENTINEL_ID, "allowed_models": [], "token_rate_limit": 1,
        "rate_window_seconds": 3600})
    gstack.governor.post("/usage", json={"agent_id": SENTINEL_ID, "model": "claude-haiku-4-5",
                                         "input_tokens": 10, "output_tokens": 0})
    assert _status(gstack, agent=SENTINEL_ID)["state"] == "THROTTLED"
    mock = MockJudgeClient(rules={"draft the march invoices": (True, 0.95, "paraphrase")})
    gstack.sentinel.app.state.engine.judge = mock
    token = gstack.mint_token()
    v = gstack.check("draft the march invoices", token_id=token)
    assert v["decision"] == "ALLOW" and len(mock.calls) == 1


def test_an_agents_token_burst_blocks_every_checked_action(gstack, clock):
    """A usage policy's ``token_rate_limit`` (the plugin bootstrap installs one)
    throttles every status read. Before D1 the burst's open ``rogue_burst``
    escalation ESCALATEd every check until a human resolved it; now every
    checked action is BLOCKed ``E.rate_limit`` while the window is exhausted,
    and resolving the escalation does not lift that — only the window
    ageing out does."""
    gstack.set_cap()
    gstack.governor.put(f"/policies/{AGENT_ID}", json={
        "agent_id": AGENT_ID, "allowed_models": [], "token_rate_limit": 200_000,
        "rate_window_seconds": 3600})
    token = gstack.mint_token()
    assert gstack.check("draft invoices", token_id=token)["decision"] == "ALLOW"
    gstack.governor.post("/usage", json={"agent_id": AGENT_ID, "model": "claude-haiku-4-5",
                                         "input_tokens": 200_000, "output_tokens": 0})
    for action in ("draft invoices", "read timesheets"):
        v = gstack.check(action, token_id=token)
        assert (v["decision"], v["clause_id"]) == ("BLOCK", "E.rate_limit"), action
        assert v["context"]["retry_after_seconds"] == 3600
    (esc,) = gstack.governor.get("/escalations").json()
    assert esc["kind"] == "usage:rogue_burst"
    r = gstack.governor.post(f"/escalations/{esc['escalation_id']}/resolve",
                             json={"resolved_by": "Controller, Spin State Labs"})
    assert r.status_code == 200
    v = gstack.check("draft invoices", token_id=token)
    assert (v["decision"], v["clause_id"]) == ("BLOCK", "E.rate_limit")  # still
    clock.at(3600)
    assert gstack.check("read timesheets", token_id=token)["decision"] == "ALLOW"


# -- option A metering ---------------------------------------------------------------

def test_one_allow_meters_exactly_one_and_self_stays_zero(gstack):
    gstack.set_cap()
    token = gstack.mint_token()
    before = _status(gstack)
    assert gstack.check("draft invoices", token_id=token)["context"]["metered"] is True
    after = _status(gstack)
    assert after["spent_actions_metered"] - before["spent_actions_metered"] == 1
    assert after["spent_actions_self"] - before["spent_actions_self"] == 0
    # the metered row is not re-ledgered as spend.recorded
    assert gstack.ledger.get("/events", params={"event_type": "spend.recorded"}).json() == []


def test_block_and_escalate_are_never_metered(gstack):
    gstack.set_cap()
    token = gstack.mint_token()
    assert gstack.check("transfer funds", token_id=token)["decision"] == "BLOCK"
    assert gstack.check("send invoice email", token_id=token)["decision"] == "ESCALATE"
    gstack.governor.post("/spend", json={"agent_id": AGENT_ID, "cents": 40_000})
    assert gstack.check("draft invoices", token_id=token)["clause_id"] == "E.spend_threshold"
    assert _status(gstack)["spent_actions_metered"] == 0


def test_uncapped_agent_is_not_posted_and_says_no_cap(gstack, monkeypatch, tmp_path):
    """No cap ⇒ ``/spend`` would 404: the post is skipped outright."""
    # a manifest WITHOUT spend_cap, so the uncapped agent is ALLOWed at step 8
    data = yaml.safe_load(gstack.manifest_path.read_text(encoding="utf-8"))
    del data["enforcement"]["spend_cap"]
    gstack.manifest_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    engine = gstack.sentinel.app.state.engine
    calls = []
    monkeypatch.setattr(engine.governor, "record_action",
                        lambda *a, **k: calls.append((a, k)) or "metered")
    token = gstack.mint_token()
    v = gstack.check("draft invoices", token_id=token)
    assert v["decision"] == "ALLOW"
    assert (v["context"]["metered"], v["context"]["reason"]) == (False, "no_cap")
    assert calls == []


def test_shadowed_allow_before_step_8_posts_and_reads_404_as_no_cap(gstack):
    """Log-only D.scope shadow: step 8 never ran, the post goes out, and the
    uncapped agent's 404 is ``no_cap`` — not a metering gap."""
    token = gstack.mint_token()
    gstack.sentinel.app.state.engine.mode = SentinelMode.LOG_ONLY
    v = gstack.check("transfer funds", token_id=token)
    assert v["context"]["shadowed"] is True
    assert (v["context"]["metered"], v["context"]["reason"]) == (False, "no_cap")
    assert gstack.ledger.get(
        "/events", params={"event_type": "sentinel.metering_gap"}).json() == []


def test_governor_post_failure_is_ledgered_and_never_flips_the_verdict(gstack, monkeypatch):
    gstack.set_cap()
    engine = gstack.sentinel.app.state.engine

    def boom(*args, **kwargs):
        raise ConnectionError("governor /spend returned 500")

    monkeypatch.setattr(engine.governor, "record_action", boom)
    token = gstack.mint_token()
    v = gstack.check("draft invoices", token_id=token)
    assert v["decision"] == "ALLOW" and v["clause_id"] is None
    assert (v["context"]["metered"], v["context"]["reason"]) == (False, "metering_gap")
    gaps = gstack.ledger.get("/events", params={"event_type": "sentinel.metering_gap"}).json()
    assert len(gaps) == 1
    assert gaps[0]["payload"]["action"] == "draft invoices"
    assert "500" in gaps[0]["payload"]["error"]


def test_metering_gap_with_ledger_down_still_allows(gstack, monkeypatch):
    gstack.set_cap()
    engine = gstack.sentinel.app.state.engine
    token = gstack.mint_token()
    monkeypatch.setattr(engine.governor, "record_action",
                        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down")))
    real_append = engine.ledger.append

    def append(event_type, **kwargs):
        if event_type == "sentinel.metering_gap":
            raise ConnectionError("ledger down")
        return real_append(event_type, **kwargs)

    monkeypatch.setattr(engine.ledger, "append", append)
    v = gstack.check("draft invoices", token_id=token)
    assert v["decision"] == "ALLOW" and v["context"]["reason"] == "metering_gap"


def test_metered_a_and_self_reported_b_count_one_each_end_to_end(gstack):
    gstack.set_cap()
    token = gstack.mint_token()
    gstack.check("draft invoices", token_id=token)                      # metered A
    gstack.governor.post("/spend", json={"agent_id": AGENT_ID, "actions": 1,
                                         "action": "read timesheets"})  # self B
    s = _status(gstack)
    assert (s["spent_actions"], s["spent_actions_self"], s["spent_actions_metered"]) == (2, 1, 1)
    gstack.governor.post("/spend", json={"agent_id": AGENT_ID, "actions": 1,
                                         "action": "draft invoices"})   # self A too
    s = _status(gstack)
    assert (s["spent_actions"], s["spent_actions_self"], s["spent_actions_metered"]) == (2, 2, 1)


class PreD1SpendRequest(BaseModel):
    """``SpendRequest`` verbatim from spend_governor/api.py at 88e44aa (pre-D1):
    ``extra='forbid'`` and no ``action`` / ``source`` / ``shadowed``."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    cents: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    actions: int = Field(default=0, ge=0)
    note: str | None = None


_pre_d1_app = FastAPI()


@_pre_d1_app.post("/spend", status_code=201)
def _pre_d1_spend(req: PreD1SpendRequest) -> dict:
    return {"agent_id": req.agent_id, "state": "OK"}


class _GovernorFront:
    """The real frozen-clock governor for every GET; ``POST /spend`` answered
    by ``spend(body)`` instead — so the real ``SpendStatusClient`` sees it."""

    def __init__(self, real, spend):
        self.real, self.spend = real, spend

    def get(self, url, **kwargs):
        return self.real.get(url, **kwargs)

    def post(self, url, json=None, **kwargs):
        if url.endswith("/spend"):
            return self.spend(json)
        return self.real.post(url, json=json, **kwargs)


def _pre_d1_governor_422(body):
    return TestClient(_pre_d1_app).post("/spend", json=body)


def _governor_500(body):
    return httpx.Response(500, json={"detail": "internal error"})


def test_the_pre_d1_fake_is_faithful():
    pre = TestClient(_pre_d1_app)
    assert pre.post("/spend", json={"agent_id": AGENT_ID, "actions": 1}).status_code == 201
    d1_body = {"agent_id": AGENT_ID, "actions": 1, "action": "draft invoices",
               "source": "sentinel", "shadowed": False}
    r = pre.post("/spend", json=d1_body)
    assert r.status_code == 422
    assert {e["loc"][-1] for e in r.json()["detail"]} == {"action", "source", "shadowed"}


@pytest.mark.parametrize("reply", [_pre_d1_governor_422, _governor_500],
                         ids=["pre-d1-governor-422", "governor-500"])
def test_a_non_201_metering_reply_through_the_real_client_is_a_gap(gstack, reply):
    """Deploy order (LIMITS): a D1 sentinel in front of a pre-D1 governor gets a
    real 422 for the new keys. Through the REAL ``SpendStatusClient`` that is a
    metering gap on EVERY ALLOW — never ``metered: true`` — and the verdict
    stays ALLOW."""
    gstack.set_cap()
    engine = gstack.sentinel.app.state.engine
    engine.governor = SpendStatusClient(
        client=_GovernorFront(gstack.governor, reply), base_url="http://t")
    token = gstack.mint_token()
    for _ in range(2):
        v = gstack.check("draft invoices", token_id=token)
        assert (v["decision"], v["clause_id"]) == ("ALLOW", None)
        assert (v["context"]["metered"], v["context"]["reason"]) == (False, "metering_gap")
    gaps = gstack.ledger.get("/events", params={"event_type": "sentinel.metering_gap"}).json()
    assert len(gaps) == 2
    code = "422" if reply is _pre_d1_governor_422 else "500"
    assert all(code in g["payload"]["error"] for g in gaps)
    assert _status(gstack)["spent_actions_metered"] == 0  # nothing reached the governor


def _metered(stack, agent=AGENT_ID):
    return _status(stack, agent=agent)["spent_actions_metered"]


def test_log_only_meters_every_shadow_allow_including_steps_1_to_4(gstack):
    """Don's decision (2026-09-13), the plan text made literal: EVERY ALLOW in
    EITHER mode is metered, including a log-only shadow decided at steps 1-4
    where identity was never established — ledger down (1), killed or
    non-active record (2), manifest missing (3), no token / another agent's
    token (4). Each is one ``source=sentinel, shadowed=true`` row against the
    NAMED agent, so an unauthenticated caller fills that agent's window (the
    pollution README LIMITS states). A shadow after step 4 is metered too."""
    gstack.set_cap()
    _limit(gstack, max_=2)
    engine = gstack.sentinel.app.state.engine
    engine.mode = SentinelMode.LOG_ONLY

    # step 4: no token, three times. The window (max 2) fills and THROTTLEs.
    for n in range(1, 4):
        v = gstack.check("draft invoices", token_id=None)
        assert v["decision"] == "ALLOW"
        assert v["context"]["would_be"] == {"decision": "BLOCK", "clause_id": "D.token"}
        assert v["context"]["metered"] is True and "reason" not in v["context"]
        assert _metered(gstack) == n
    status = _status(gstack, "draft invoices")
    assert (status["state"], status["spent_actions_metered"], status["spent_actions_self"]) == (
        "THROTTLED", 3, 0)

    # step 4: a live token bound to ANOTHER registered agent.
    other = "other-agent"
    r = gstack.registry.post("/agents", json={
        "agent_id": other, "name": "Other", "owner": "Controller, Spin State Labs",
        "domain": "finance", "manifest_ref": str(gstack.manifest_path)})
    assert r.status_code in (200, 201), r.text
    r = gstack.delegation.post("/tokens", json={
        "agent_id": other, "granted_by": "Controller, Spin State Labs",
        "scope": ["draft invoices"], "ttl_seconds": 3600})
    assert r.status_code == 201, r.text
    v = gstack.check("draft invoices", token_id=r.json()["token_id"])
    assert v["context"]["would_be"]["clause_id"] == "D.token"
    assert v["context"]["metered"] is True
    assert _metered(gstack) == 4

    token = gstack.mint_token()

    # step 1: ledger unreachable (the shadow record itself is lost; the meter is not).
    gstack.ledger_up = False
    v = gstack.check("read timesheets", token_id=token)
    gstack.ledger_up = True
    assert v["decision"] == "ALLOW"
    assert v["context"]["would_be"]["clause_id"] == "L.unreachable"
    assert v["context"]["metered"] is True
    assert _metered(gstack) == 5

    # step 3: the registry record's manifest no longer resolves.
    good_ref = str(gstack.manifest_path)
    r = gstack.registry.patch(f"/agents/{AGENT_ID}",
                              json={"manifest_ref": str(gstack.manifest_path.with_name("gone.yaml"))})
    assert r.status_code == 200, r.text
    v = gstack.check("read timesheets", token_id=token)
    assert v["context"]["would_be"]["clause_id"] == "I.manifest"
    assert v["context"]["metered"] is True
    assert _metered(gstack) == 6
    assert gstack.registry.patch(f"/agents/{AGENT_ID}", json={"manifest_ref": good_ref}).status_code == 200

    # step 2: a killed record.
    r = gstack.registry.patch(f"/agents/{AGENT_ID}", json={"status": "killed"})
    assert r.status_code == 200, r.text
    v = gstack.check("read timesheets", token_id=token)
    assert v["context"]["would_be"]["clause_id"] == "E.kill_switch"
    assert v["context"]["metered"] is True
    assert _metered(gstack) == 7
    assert gstack.registry.patch(f"/agents/{AGENT_ID}", json={"status": "active"}).status_code == 200

    # after step 4 (D.scope shadow at step 5): metered, as before.
    v = gstack.check("transfer funds", token_id=token)
    assert v["context"]["would_be"]["clause_id"] == "D.scope"
    assert v["context"]["metered"] is True
    assert _metered(gstack) == 8
    assert gstack.ledger.get(
        "/events", params={"event_type": "sentinel.metering_gap"}).json() == []


def test_log_only_step_2_unregistered_agent_posts_and_reads_404_as_no_cap(gstack):
    """Step 2's other branch: an agent the registry does not know. The post
    still goes out (every ALLOW is metered); the governor holds no cap for it,
    so its 404 is ``no_cap`` — never a gap, never ``metered: true``."""
    engine = gstack.sentinel.app.state.engine
    engine.mode = SentinelMode.LOG_ONLY
    calls = []
    real = engine.governor.record_action

    def spy(agent_id, action, *, shadowed):
        calls.append((agent_id, action, shadowed))
        return real(agent_id, action, shadowed=shadowed)

    engine.governor.record_action = spy
    r = gstack.sentinel.post("/check", json={"agent_id": "ghost-agent", "action": "draft invoices"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["context"]["would_be"]["clause_id"] == "R.unregistered"
    assert (v["context"]["metered"], v["context"]["reason"]) == (False, "no_cap")
    assert calls == [("ghost-agent", "draft invoices", True)]


# -- D1e: the token's max_spend_usd --------------------------------------------------------

def _with_token_ceiling(stack, monkeypatch, max_spend_usd, issued_at=None):
    """Override the ceiling on the REAL introspection result, to drive values a
    DOA roster cannot hold (unreadable ones) and the frozen governor clock.
    Since D1e the authority itself returns ``max_spend_usd`` and a wall-clock
    ``issued_at`` (end to end, no override:
    ``test_a_rostered_tokens_max_spend_usd_blocks_spend_cap_end_to_end``).
    These tests record spend on the governor's frozen clock, so ``issued_at``
    is either given on that clock or, when None, removed: the sentinel's
    all-recorded-spend fallback, which these tests were written against."""
    engine = stack.sentinel.app.state.engine
    real = engine.delegation.introspect

    def introspect(token_id):
        intro = dict(real(token_id))
        intro["max_spend_usd"] = max_spend_usd
        if issued_at is None:
            intro.pop("issued_at", None)
        else:
            intro["issued_at"] = issued_at
        return intro

    monkeypatch.setattr(engine.delegation, "introspect", introspect)


def test_spend_at_the_token_ceiling_blocks_spend_cap(gstack, monkeypatch, clock):
    gstack.set_cap()  # $500/day agent cap, far above the $1 token ceiling
    _with_token_ceiling(gstack, monkeypatch, 1.0, issued_at=T0.isoformat())
    token = gstack.mint_token()
    clock.at(-60)
    gstack.governor.post("/spend", json={"agent_id": AGENT_ID, "cents": 5_000})  # before issue
    clock.at(60)
    gstack.governor.post("/spend", json={"agent_id": AGENT_ID, "cents": 99})
    assert gstack.check("draft invoices", token_id=token)["decision"] == "ALLOW"
    gstack.governor.post("/spend", json={"agent_id": AGENT_ID, "cents": 1})
    v = gstack.check("draft invoices", token_id=token)
    assert (v["decision"], v["clause_id"]) == ("BLOCK", "E.spend_cap")
    assert v["context"]["token_max_spend_cents"] == 100
    assert v["context"]["token_spent_cents"] == 100
    assert "token spend ceiling" in v["reasons"][0]


def test_token_ceiling_outranks_rate_limit(gstack, monkeypatch):
    gstack.set_cap()
    _limit(gstack, max_=1)
    _with_token_ceiling(gstack, monkeypatch, 0.5)
    token = gstack.mint_token()
    assert gstack.check("draft invoices", token_id=token)["decision"] == "ALLOW"
    gstack.governor.post("/spend", json={"agent_id": AGENT_ID, "cents": 50})
    assert gstack.check("draft invoices", token_id=token)["clause_id"] == "E.spend_cap"


def test_sub_cent_ceiling_floors_and_unreadable_ceilings_block(gstack, monkeypatch):
    gstack.set_cap()
    token = gstack.mint_token()
    gstack.governor.post("/spend", json={"agent_id": AGENT_ID, "cents": 1})
    _with_token_ceiling(gstack, monkeypatch, 0.019)  # floors to 1 cent
    assert gstack.check("draft invoices", token_id=token)["clause_id"] == "E.spend_cap"
    for bad in ("abc", True, -1, "NaN", "Infinity"):
        monkeypatch.undo()
        _with_token_ceiling(gstack, monkeypatch, bad)
        v = gstack.check("draft invoices", token_id=token)
        assert (v["decision"], v["clause_id"]) == ("BLOCK", "E.spend_cap"), bad
        assert "unreadable" in v["reasons"][0]


def test_token_ceiling_unverifiable_total_blocks(gstack, monkeypatch):
    gstack.set_cap()
    _with_token_ceiling(gstack, monkeypatch, 5)
    engine = gstack.sentinel.app.state.engine

    def boom(*args, **kwargs):
        raise ConnectionError("governor /totals returned 500")

    monkeypatch.setattr(engine.governor, "totals_since", boom)
    token = gstack.mint_token()
    v = gstack.check("draft invoices", token_id=token)
    assert (v["decision"], v["clause_id"]) == ("BLOCK", "E.spend_cap")


def test_token_ceiling_without_any_cap_escalates(gstack, monkeypatch):
    data = yaml.safe_load(gstack.manifest_path.read_text(encoding="utf-8"))
    del data["enforcement"]["spend_cap"]
    gstack.manifest_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    _with_token_ceiling(gstack, monkeypatch, 5)
    token = gstack.mint_token()
    v = gstack.check("draft invoices", token_id=token)
    assert (v["decision"], v["clause_id"]) == ("ESCALATE", "E.spend_cap")
    assert "token carries max_spend_usd" in v["reasons"][0]


def test_token_ceiling_refuses_a_cap_in_another_currency(gstack, monkeypatch):
    """``max_spend_usd`` is USD; ``/totals`` cents are in the cap's currency.
    A CAD cap is never compared cent-for-cent against a USD ceiling: BLOCK
    ``E.spend_cap`` naming the currency, even with nothing spent. A total
    that names no currency is refused the same way; ``usd`` is USD."""
    r = gstack.governor.put(f"/caps/{AGENT_ID}", json={
        "agent_id": AGENT_ID, "currency": "CAD", "limit_cents": 50_000,
        "period": "daily", "escalate_at_pct": 80})
    assert r.status_code == 200, r.text
    _with_token_ceiling(gstack, monkeypatch, 5.0)
    token = gstack.mint_token()
    v = gstack.check("draft invoices", token_id=token)
    assert (v["decision"], v["clause_id"]) == ("BLOCK", "E.spend_cap")
    assert "'CAD'" in v["reasons"][0] and "USD" in v["reasons"][0]
    assert v["context"]["cap_currency"] == "CAD"

    engine = gstack.sentinel.app.state.engine
    real_totals = engine.governor.totals_since

    def without_currency(agent_id, since):
        totals = dict(real_totals(agent_id, since))
        totals.pop("currency")
        return totals

    monkeypatch.setattr(engine.governor, "totals_since", without_currency)
    v = gstack.check("draft invoices", token_id=token)
    assert (v["decision"], v["clause_id"]) == ("BLOCK", "E.spend_cap")
    assert "None" in v["reasons"][0]

    monkeypatch.setattr(engine.governor, "totals_since",
                        lambda a, s: {**real_totals(a, s), "currency": "usd"})
    assert gstack.check("draft invoices", token_id=token)["decision"] == "ALLOW"


def test_no_ceiling_on_the_token_changes_nothing(gstack):
    gstack.set_cap()
    token = gstack.mint_token()
    gstack.governor.post("/spend", json={"agent_id": AGENT_ID, "cents": 30_000})
    v = gstack.check("draft invoices", token_id=token)
    assert v["decision"] == "ALLOW" and "token_spent_cents" not in v["context"]


def test_a_rostered_tokens_max_spend_usd_blocks_spend_cap_end_to_end(stack, tmp_path, monkeypatch):
    """D1e end to end, no monkeypatch of introspection: the DOA roster row's
    ``max_spend_usd`` is stamped at mint by the real delegation-authority,
    returned by its ``/introspect`` with ``issued_at``, and the sentinel BLOCKs
    ``E.spend_cap`` once governor-metered spend since issue reaches it. Spend
    recorded before the token was issued does not count against it."""
    import time

    roster = tmp_path / "doa-roster.yaml"
    roster.write_text(yaml.safe_dump({"grantors": [{
        "grantor": "Controller, Spin State Labs", "allowed_scope": ["read timesheets", "draft invoices"],
        "max_ttl_days": 1, "max_spend_usd": 1.0, "active": True}]}), encoding="utf-8")
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(roster))
    stack.set_cap()  # $500/day agent cap, far above the $1 token ceiling
    stack.governor.post("/spend", json={"agent_id": AGENT_ID, "cents": 5_000})  # before issue
    time.sleep(0.05)
    token = stack.mint_token(scope=["read timesheets", "draft invoices"])
    intro = stack.delegation.post("/introspect", json={"token_id": token}).json()
    assert intro["max_spend_usd"] == 1.0 and intro["issued_at"]
    time.sleep(0.05)

    stack.governor.post("/spend", json={"agent_id": AGENT_ID, "cents": 99})
    v = stack.check("draft invoices", token_id=token)
    assert v["decision"] == "ALLOW", v
    stack.governor.post("/spend", json={"agent_id": AGENT_ID, "cents": 1})
    v = stack.check("draft invoices", token_id=token)
    assert (v["decision"], v["clause_id"]) == ("BLOCK", "E.spend_cap"), v
    assert (v["context"]["token_max_spend_cents"], v["context"]["token_spent_cents"]) == (100, 100)
    assert "token spend ceiling" in v["reasons"][0]

    # a token minted with the roster unset carries no ceiling: same agent, same spend, ALLOW
    monkeypatch.delenv("FIELD_DOA_ROSTER")
    plain = stack.mint_token(scope=["read timesheets", "draft invoices"])
    v = stack.check("draft invoices", token_id=plain)
    assert v["decision"] == "ALLOW" and "token_spent_cents" not in v["context"], v
