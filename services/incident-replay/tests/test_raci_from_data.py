"""C3 — RACI from data: every party read from registry / grant / manifest,
every fallback labeled, log-only shadow verdicts counted, and the C2
earliest-live integrity note (against a stub ledger /health)."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, ManifestResolver, RegistryClient
from field_core.delegation import DelegationToken, TokenStatus
from field_core.validation import validate_manifest_data
from incident_replay.api import create_app as create_replay_app
from incident_replay.engine import (
    AuthorityGrant,
    LedgerQueryClient,
    ReplayEngine,
    ReplayRequest,
    TokenQueryClient,
    render_markdown,
)
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerBusy, LedgerStore

AGENT = "invoicing-agent"
WINDOW = {"since": "2020-01-01T00:00:00+00:00", "until": "2030-01-01T00:00:00+00:00"}
LOG_ONLY = "(log-only, not enforced)"


def manifest_data(**overrides) -> dict:
    """A schema-valid manifest (synthetic values); overrides replace sections."""
    data = {
        "schema_version": "field.spinstatelabs.ca/v1",
        "agent": {"name": AGENT, "version": "0.1.0"},
        "federated": {"isolated": True, "allowed_peers": [], "contracts": []},
        "identity": {"principal": "Controller, Spin State Labs (demo)",
                     "org": "Spin State Labs", "jurisdiction": ["PIPEDA"]},
        "enforcement": {
            "kill_switch": {"endpoint": "http://127.0.0.1:8005/kill/invoicing-agent",
                            "method": "HTTP POST",
                            "authorized_operators": ["Controller (demo)",
                                                     "CISO on-call (demo)"]},
            "irreversible_action_policy": "require_human_approval",
        },
        "ledger": {"cryptographic_seal": True, "seal_algorithm": "sha-256-chain",
                   "retention_days": 2555, "logged_events": ["every action"]},
        "delegation": {"granted_by": "Controller, Spin State Labs (demo)",
                       "scope": ["draft invoices"], "expiry": "2027-06-30"},
    }
    data.update(overrides)
    return data


def grant(token_id, granted_by, scope, issued_at,
          expires_at="2030-01-01T00:00:00+00:00", revoked=False) -> dict:
    """A token exactly as delegation-authority's GET /tokens serialises it."""
    return {"token_id": token_id, "agent_id": AGENT, "granted_by": granted_by,
            "scope": scope, "issued_at": issued_at, "expires_at": expires_at,
            "revoked": revoked, "revocation_id": None, "revoked_at": None}


class StubTokens:
    """delegation-authority stand-in with explicit, controllable issued_at."""

    def __init__(self, tokens: list[dict]):
        self._tokens = tokens

    def tokens(self, agent_id: str) -> list[dict]:
        return [t for t in self._tokens if t["agent_id"] == agent_id]


class _Resp:
    def __init__(self, body: dict, status_code: int = 200):
        self._body, self.status_code = body, status_code

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}", request=httpx.Request("GET", "http://t"),
                response=httpx.Response(self.status_code),
            )


class StubLedgerHttp:
    """Real ledger underneath; ``/health`` and ``/verify`` answers can carry
    the C2 fields (or fail) — a stub for a ledger that does not exist yet."""

    def __init__(self, inner, health_extra=None, verify_extra=None,
                 health_status=200, health_raises=False):
        self.inner = inner
        self.health_extra = health_extra or {}
        self.verify_extra = verify_extra or {}
        self.health_status = health_status
        self.health_raises = health_raises

    def get(self, url, **kwargs):
        if url.endswith("/health"):
            if self.health_raises:
                raise httpx.ConnectError("ledger health down")
            body = {**self.inner.get(url).json(), **self.health_extra}
            return _Resp(body, self.health_status)
        if url.endswith("/verify"):
            return _Resp({**self.inner.get(url).json(), **self.verify_extra})
        return self.inner.get(url, **kwargs)

    def post(self, url, **kwargs):
        return self.inner.post(url, **kwargs)

    def patch(self, url, **kwargs):
        return self.inner.patch(url, **kwargs)


class Estate:
    def __init__(self, tmp_path):
        self.dir = tmp_path
        self.ledger = TestClient(
            create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl"))
        )
        self.registry = TestClient(
            create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3"))
        )

    def write_manifest(self, name: str, data: dict | str) -> str:
        text = data if isinstance(data, str) else yaml.safe_dump(data, sort_keys=False)
        (self.dir / name).write_text(text, encoding="utf-8")
        return name  # relative ref, resolved under manifest_dir

    def register(self, manifest_ref: str | None = None) -> None:
        body = {"agent_id": AGENT, "name": "Invoice Drafting Copilot",
                "owner": "AP Team Lead", "domain": "finance"}
        if manifest_ref is not None:
            body["manifest_ref"] = manifest_ref
        assert self.registry.post("/agents", json=body).status_code == 201

    def append(self, event_type: str, payload: dict) -> None:
        resp = self.ledger.post("/events", json={
            "event_type": event_type, "agent_id": AGENT, "payload": payload})
        assert resp.status_code == 201

    def engine(self, tokens=(), ledger_http=None) -> ReplayEngine:
        return ReplayEngine(
            ledger=LedgerQueryClient(client=ledger_http or self.ledger,
                                     base_url="http://t"),
            registry=RegistryClient(client=self.registry, base_url="http://t"),
            delegation=StubTokens(list(tokens)),
            manifests=ManifestResolver(manifest_dir=self.dir),
        )

    def replay(self, tokens=(), ledger_http=None, **window):
        req = ReplayRequest(agent_id=AGENT, **{**WINDOW, **window})
        return self.engine(tokens, ledger_http).replay(req)


@pytest.fixture()
def estate(tmp_path):
    return Estate(tmp_path)


# ── A: the covering grant, else the earliest overlapping grant ─────────────


def test_covering_grant_beats_earlier_non_covering_grant(estate):
    estate.register()
    estate.append("conformance.escalate",
                  {"action": "transfer funds", "clause_id": "E.irreversible"})
    pm = estate.replay(tokens=[
        grant("t-early", "Controller", ["draft invoices"], "2026-01-01T00:00:00+00:00"),
        grant("t-late", "Treasurer", ["transfer funds"], "2026-03-01T00:00:00+00:00"),
    ])
    assert pm.raci["Accountable"] == "Treasurer (grant covering 'transfer funds')"
    assert pm.raci_sources["Accountable"] == "grant covering 'transfer funds'"


def test_earliest_covering_grant_wins_when_several_cover(estate):
    estate.register()
    estate.append("conformance.block",
                  {"action": "transfer funds", "clause_id": "E.spend_cap"})
    pm = estate.replay(tokens=[  # later grant listed first: order is by instant
        grant("t-2", "CFO", ["transfer funds"], "2026-05-01T00:00:00+00:00"),
        grant("t-1", "Treasurer", ["transfer funds"], "2026-02-01T00:00:00+00:00"),
    ])
    assert pm.raci["Accountable"] == "Treasurer (grant covering 'transfer funds')"


def test_d_scope_failure_falls_back_to_earliest_overlapping_grant(estate):
    """A D.scope block on an action no grant holds has no covering grant."""
    estate.register()
    estate.append("conformance.block",
                  {"action": "transfer funds", "clause_id": "D.scope"})
    pm = estate.replay(tokens=[
        grant("t-late", "CFO", ["read timesheets"], "2026-02-01T00:00:00+00:00"),
        grant("t-early", "Controller", ["draft invoices"], "2026-01-01T00:00:00+00:00"),
    ])
    assert pm.raci["Accountable"] == "Controller (earliest overlapping grant)"
    assert pm.raci_sources["Accountable"] == "earliest overlapping grant"


def test_no_failure_uses_earliest_overlapping_grant(estate):
    estate.register()
    estate.append("conformance.allow", {"action": "draft invoices"})
    pm = estate.replay(tokens=[
        grant("t-late", "CFO", ["draft invoices"], "2026-02-01T00:00:00+00:00"),
        grant("t-early", "Controller", ["draft invoices"], "2026-01-01T00:00:00+00:00"),
    ])
    assert pm.first_failure is None
    assert pm.raci["Accountable"] == "Controller (earliest overlapping grant)"


def test_no_grants_means_no_grantor_found(estate):
    estate.register()
    estate.append("conformance.block",
                  {"action": "transfer funds", "clause_id": "D.scope"})
    for tokens in ([], [grant("t-old", "Controller", ["transfer funds"],
                              "2019-01-01T00:00:00+00:00",
                              expires_at="2019-06-01T00:00:00+00:00")]):
        pm = estate.replay(tokens=tokens)
        assert pm.authority == []
        assert pm.raci["Accountable"] == "<no grantor found>"
        assert pm.raci_sources["Accountable"] == "none"


def test_covers_is_the_delegation_token_rule():
    """Exact membership, same answers as field_core DelegationToken.covers."""
    scope = ["draft invoices", "read timesheets"]
    token = DelegationToken(agent_id=AGENT, granted_by="Controller", scope=scope,
                            issued_at="2026-01-01T00:00:00+00:00",
                            expires_at="2027-01-01T00:00:00+00:00")
    g = AuthorityGrant(**grant("t", "Controller", scope, "2026-01-01T00:00:00+00:00"))
    for action in ("draft invoices", "Draft invoices", "draft invoice",
                   "draft invoices ", "read timesheets", "draft"):
        assert g.covers(action) is token.covers(action), action


def test_grant_window_overlap_compares_instants_not_strings(estate):
    """Mixed offsets mis-order lexically; both directions are checked."""
    estate.register()
    window = {"since": "2026-08-18T00:00:00+00:00",
              "until": "2026-08-18T23:59:59+00:00"}
    # Lexically "2026-08-18T20:00…" <= until, but it is 2026-08-19T01:00Z.
    late = grant("t-late", "CFO", ["x"], "2026-08-18T20:00:00-05:00")
    # Lexically "2026-08-19T01:00…" > until, but it is 2026-08-18T20:00Z.
    inside = grant("t-in", "Controller", ["x"], "2026-08-19T01:00:00+05:00")
    pm = estate.replay(tokens=[late, inside], **window)
    assert [a.token_id for a in pm.authority] == ["t-in"]
    assert pm.raci["Accountable"] == "Controller (earliest overlapping grant)"


def test_non_iso_window_bound_is_refused_422(estate):
    replay = TestClient(create_replay_app(engine=estate.engine()))
    resp = replay.post("/replay", json={"agent_id": AGENT, "since": "yesterday",
                                        "until": WINDOW["until"]})
    assert resp.status_code == 422


# ── C: manifest kill_switch.authorized_operators, else the clause default ──


def test_consulted_from_manifest_operators_when_non_empty(estate):
    estate.register(estate.write_manifest("m.yaml", manifest_data()))
    estate.append("conformance.block",
                  {"action": "transfer funds", "clause_id": "D.scope"})
    pm = estate.replay()
    assert pm.manifest_resolved is True and pm.manifest_detail == "ok"
    assert pm.raci["Consulted"] == (
        "Controller (demo), CISO on-call (demo) "
        "(manifest kill_switch.authorized_operators)"
    )
    assert pm.raci_sources["Consulted"] == "manifest kill_switch.authorized_operators"


@pytest.mark.parametrize("operators", [[], None], ids=["empty-list", "absent"])
def test_empty_or_absent_operators_use_clause_default(estate, operators):
    """Templates ship `authorized_operators: []`: the manifest still resolves
    (Informed reads it), but Consulted is the labeled clause default."""
    data = manifest_data()
    if operators is None:
        del data["enforcement"]["kill_switch"]["authorized_operators"]
    else:
        data["enforcement"]["kill_switch"]["authorized_operators"] = operators
    estate.register(estate.write_manifest("m.yaml", data))
    estate.append("conformance.block",
                  {"action": "transfer funds", "clause_id": "D.scope"})
    pm = estate.replay()
    assert pm.manifest_resolved is True
    assert pm.raci["Consulted"] == "GC (delegation) (default)"
    assert pm.raci_sources["Consulted"] == "default"
    assert pm.raci["Informed"].endswith("(manifest identity)")


def _schema_invalid() -> dict:
    data = manifest_data()
    del data["identity"]["principal"]
    return data


@pytest.mark.parametrize(
    "setup, reason",
    [
        (lambda e: None, "no_ref"),
        (lambda e: "nowhere/absent.yaml", "missing"),
        (lambda e: e.write_manifest("bad.yaml", "identity: [unclosed\n  : :"), "invalid"),
        (lambda e: e.write_manifest("schema.yaml", _schema_invalid()), "invalid"),
    ],
    ids=["no-ref", "missing-file", "unparseable-yaml", "schema-invalid"],
)
def test_unresolvable_manifest_defaults_labeled_no_crash(estate, setup, reason):
    estate.register(setup(estate))
    estate.append("conformance.block",
                  {"action": "transfer funds", "clause_id": "D.scope"})
    pm = estate.replay()
    assert pm.manifest_resolved is False
    assert pm.manifest_detail == reason
    assert pm.raci["Consulted"] == "GC (delegation) (default)"
    assert pm.raci["Informed"] == "CEO / board (attestation-reporter) (default)"
    assert pm.raci_sources["Consulted"] == pm.raci_sources["Informed"] == "default"
    md = render_markdown(pm)
    assert f"not resolved (`{reason}`)" in md
    assert "| Informed | CEO / board (attestation-reporter) (default) |" in md


def test_unregistered_agent_defaults_every_manifest_role(estate):
    pm = estate.replay()
    assert pm.agent_record is None and pm.manifest_detail == "no_ref"
    assert pm.raci_sources == {"Responsible": "none", "Accountable": "none",
                               "Consulted": "default", "Informed": "default"}


# ── I: manifest identity, else the default ─────────────────────────────────


def test_informed_principal_and_org(estate):
    estate.register(estate.write_manifest("m.yaml", manifest_data()))
    pm = estate.replay()
    assert pm.raci["Informed"] == (
        "Controller, Spin State Labs (demo) — Spin State Labs (manifest identity)"
    )
    assert pm.raci_sources["Informed"] == "manifest identity"


def test_informed_principal_only(estate):
    data = manifest_data()
    del data["identity"]["org"]
    estate.register(estate.write_manifest("m.yaml", data))
    pm = estate.replay()
    assert pm.raci["Informed"] == "Controller, Spin State Labs (demo) (manifest identity)"


def test_responsible_is_registry_owner_labeled(estate):
    estate.register()
    pm = estate.replay()
    assert pm.raci["Responsible"] == "AP Team Lead (agent owner)"
    assert pm.raci_sources["Responsible"] == "registry owner"


# ── log-only shadow verdicts (conformance-sentinel engine.py _verdict) ──────


def test_shadow_block_is_first_failure_labeled_log_only(estate):
    estate.register()  # no manifest: Consulted must come from the letter
    estate.append("conformance.allow", {"action": "draft invoices", "clause_id": None})
    estate.append("conformance.shadow_block", {
        "action": "transfer funds", "would_block": "D.scope",
        "reasons": ["'transfer funds' not in token scope"], "mode": "log_only"})
    pm = estate.replay(tokens=[
        grant("t", "Controller", ["draft invoices"], "2026-01-01T00:00:00+00:00")])

    ff = pm.first_failure
    assert ff is not None and ff.event_type == "conformance.shadow_block"
    assert ff.clause_id == "D.scope"
    assert ff.action == "transfer funds"
    assert ff.enforced is False
    assert ff.summary.endswith(LOG_ONLY)
    assert pm.raci["Consulted"] == "GC (delegation) (default)"
    assert pm.raci["Accountable"] == "Controller (earliest overlapping grant)"
    assert [t.enforced for t in pm.timeline] == [True, False]

    md = render_markdown(pm)
    assert f"- `D.scope` at `{ff.ts[:19]}` — SHADOW_BLOCK 'transfer funds' [D.scope] {LOG_ONLY}" in md


def test_shadow_escalate_clause_from_would_block(estate):
    estate.register()
    estate.append("conformance.shadow_escalate", {
        "action": "send invoice", "would_block": "E.escalation_trigger",
        "reasons": ["matched declared trigger"], "mode": "log_only"})
    pm = estate.replay()
    assert pm.first_failure.clause_id == "E.escalation_trigger"
    assert pm.first_failure.enforced is False
    assert pm.raci["Consulted"] == "CISO / CFO (enforcement) (default)"


def test_first_failure_shadow_before_enforced(estate):
    estate.register()
    estate.append("conformance.shadow_block",
                  {"action": "transfer funds", "would_block": "D.scope", "mode": "log_only"})
    estate.append("conformance.block",
                  {"action": "send invoice", "clause_id": "E.escalation_trigger"})
    pm = estate.replay()
    assert pm.first_failure.event_type == "conformance.shadow_block"
    assert pm.first_failure.clause_id == "D.scope"


def test_first_failure_enforced_before_shadow(estate):
    estate.register()
    estate.append("conformance.escalate",
                  {"action": "send invoice", "clause_id": "E.escalation_trigger"})
    estate.append("conformance.shadow_block",
                  {"action": "transfer funds", "would_block": "D.scope", "mode": "log_only"})
    pm = estate.replay()
    assert pm.first_failure.event_type == "conformance.escalate"
    assert pm.first_failure.enforced is True
    assert LOG_ONLY not in pm.first_failure.summary
    assert pm.raci["Consulted"] == "CISO / CFO (enforcement) (default)"


# ── earliest-live integrity note (C2 /health contract, stub ledger) ────────

C2_HEALTH = {"earliest_live_ts": "2026-01-01T00:00:00+00:00",
             "earliest_live_index": 42, "archived_segments": 2}


def test_earliest_live_note_present_when_window_starts_before_it(estate):
    estate.register()
    estate.append("conformance.allow", {"action": "draft invoices"})
    stub = StubLedgerHttp(estate.ledger, health_extra=C2_HEALTH)
    pm = estate.replay(ledger_http=stub)
    assert len(pm.integrity_notes) == 1
    note = pm.integrity_notes[0]
    assert note.startswith(
        "window starts before the earliest live event (segments archived: 2)")
    assert "global index 42" in note
    assert pm.ledger_integrity_ok is True  # a note, not a chain break
    assert f"> **Integrity note:** {note}" in render_markdown(pm)


def test_earliest_live_archived_count_falls_back_to_verify(estate):
    estate.register()
    health = {k: v for k, v in C2_HEALTH.items() if k != "archived_segments"}
    stub = StubLedgerHttp(estate.ledger, health_extra=health,
                          verify_extra={"archived_segments": 3})
    pm = estate.replay(ledger_http=stub)
    assert "(segments archived: 3)" in pm.integrity_notes[0]


@pytest.mark.parametrize("since", [
    "2026-01-01T00:00:00+00:00",   # equal: not before
    "2026-03-01T00:00:00+00:00",   # after
    "2025-12-31T20:00:00-05:00",   # = 2026-01-01T01:00Z; lexically "before"
], ids=["equal", "after", "mixed-offset-after"])
def test_earliest_live_note_absent_when_window_starts_at_or_after_it(estate, since):
    estate.register()
    stub = StubLedgerHttp(estate.ledger, health_extra=C2_HEALTH)
    pm = estate.replay(ledger_http=stub, since=since)
    assert pm.integrity_notes == []


def test_earliest_live_note_absent_on_pre_c2_ledger(estate):
    """The real ledger underneath: pre-C2 its /health has no earliest_live_*
    fields; with C2 and nothing archived it reports index 0. No note."""
    estate.register()
    estate.append("conformance.allow", {"action": "draft invoices"})
    health = estate.ledger.get("/health").json()
    assert "earliest_live_ts" not in health or health.get("earliest_live_index") == 0
    pm = estate.replay()
    assert pm.integrity_notes == []
    assert "Integrity note" not in render_markdown(pm)


def test_earliest_live_note_absent_when_nothing_archived(estate):
    estate.register()
    stub = StubLedgerHttp(estate.ledger, health_extra={
        "earliest_live_ts": "2026-01-01T00:00:00+00:00", "earliest_live_index": 0,
        "archived_segments": 0})
    assert estate.replay(ledger_http=stub).integrity_notes == []


@pytest.mark.parametrize("stub_kwargs", [
    {"health_raises": True},
    {"health_status": 503},
], ids=["unreachable", "http-503"])
def test_unreadable_ledger_health_never_crashes_the_replay(estate, stub_kwargs):
    estate.register()
    estate.append("conformance.block",
                  {"action": "transfer funds", "clause_id": "D.scope"})
    stub = StubLedgerHttp(estate.ledger, **stub_kwargs)
    pm = estate.replay(ledger_http=stub)
    assert pm.first_failure.clause_id == "D.scope"
    assert pm.integrity_notes and pm.integrity_notes[0].startswith(
        "earliest-live check unavailable")


def test_unparseable_earliest_live_ts_never_crashes(estate):
    estate.register()
    stub = StubLedgerHttp(estate.ledger, health_extra={
        "earliest_live_ts": "not-a-time", "earliest_live_index": 5})
    pm = estate.replay(ledger_http=stub)
    assert pm.integrity_notes[0].startswith("earliest-live check unavailable")


# ── served JSON carries the additive fields ────────────────────────────────


def test_served_post_mortem_carries_sources_and_manifest_fields(estate):
    estate.register(estate.write_manifest("m.yaml", manifest_data()))
    estate.append("conformance.block",
                  {"action": "transfer funds", "clause_id": "D.scope"})
    replay = TestClient(create_replay_app(engine=estate.engine(tokens=[
        grant("t", "Controller", ["draft invoices"], "2026-01-01T00:00:00+00:00")])))
    pm = replay.post("/replay", json={"agent_id": AGENT, **WINDOW}).json()
    assert pm["manifest_resolved"] is True and pm["manifest_detail"] == "ok"
    assert pm["raci_sources"] == {
        "Responsible": "registry owner",
        "Accountable": "earliest overlapping grant",
        "Consulted": "manifest kill_switch.authorized_operators",
        "Informed": "manifest identity",
    }
    assert pm["first_failure"]["action"] == "transfer funds"
    assert pm["first_failure"]["enforced"] is True
    assert pm["integrity_notes"] == []


# ── C3 review: Accountable is judged at the failure's ledger timestamp ─────

UTC = timezone.utc
MICRO = timedelta(microseconds=1)
DAY = timedelta(days=1)
HOUR = timedelta(hours=1)


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _around_now() -> dict:
    now = datetime.now(UTC)
    return {"since": (now - DAY).isoformat(), "until": (now + DAY).isoformat()}


def _tick() -> None:
    # Every service stamps datetime.now(); keep the orderings these tests
    # depend on strict even on a coarse clock.
    time.sleep(0.02)


def _real_delegation(estate) -> TestClient:
    """The real delegation-authority over the estate's ledger and registry."""
    return TestClient(create_delegation_app(
        store=TokenStore(estate.dir / "tokens.sqlite3"),
        ledger=LedgerClient(client=estate.ledger, base_url="http://t"),
        registry=RegistryClient(client=estate.registry, base_url="http://t"),
    ))


def _mint(delegation, granted_by: str, scope: list[str], **expiry) -> dict:
    body = {"agent_id": AGENT, "granted_by": granted_by, "scope": scope,
            **(expiry or {"ttl_seconds": 3600})}
    resp = delegation.post("/tokens", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _real_engine(estate, delegation) -> ReplayEngine:
    return ReplayEngine(
        ledger=LedgerQueryClient(client=estate.ledger, base_url="http://t"),
        registry=RegistryClient(client=estate.registry, base_url="http://t"),
        delegation=TokenQueryClient(client=delegation, base_url="http://t"),
        manifests=ManifestResolver(manifest_dir=estate.dir),
    )


def _failure_at(estate, event_type: str, payload: dict) -> datetime:
    """Ledger a verdict and return the timestamp the ledger stamped on it."""
    estate.append(event_type, payload)
    return _ts(estate.ledger.get("/events", params={"agent_id": AGENT}).json()[-1]["ts"])


def test_accountable_is_never_a_grant_revoked_before_the_failure(estate):
    """Real delegation-authority: revoke and reissue, then fail. The revoked
    grant covers the action and is earlier, but was not in force."""
    estate.register()
    delegation = _real_delegation(estate)
    old = _mint(delegation, "Former Controller", ["read timesheets", "draft invoices"])
    _tick()
    assert delegation.post(f"/tokens/{old['token_id']}/revoke").status_code == 200
    _tick()
    new = _mint(delegation, "Current Controller", ["read timesheets", "draft invoices"])
    _tick()
    estate.append("conformance.escalate",
                  {"action": "draft invoices", "clause_id": "E.irreversible"})

    pm = _real_engine(estate, delegation).replay(
        ReplayRequest(agent_id=AGENT, **_around_now()))
    by_id = {a.token_id: a for a in pm.authority}
    assert set(by_id) == {old["token_id"], new["token_id"]}  # the table keeps both
    assert _ts(by_id[old["token_id"]].revoked_at) < _ts(pm.first_failure.ts)
    assert pm.raci["Accountable"] == "Current Controller (grant covering 'draft invoices')"
    assert pm.accountable_grant.token_id == new["token_id"]


def test_accountable_is_never_a_grant_minted_after_the_failure(estate):
    """Real delegation-authority: a D.scope block, then a remediation grant
    that covers the action. It did not exist at the failure."""
    estate.register()
    delegation = _real_delegation(estate)
    _mint(delegation, "Payroll Lead", ["read timesheets"])
    _tick()
    estate.append("conformance.block", {
        "action": "draft invoices", "clause_id": "D.scope",
        "reasons": ["'draft invoices' not in token scope ['read timesheets']"]})
    _tick()
    later = _mint(delegation, "Controller (remediation)", ["read timesheets", "draft invoices"])

    pm = _real_engine(estate, delegation).replay(
        ReplayRequest(agent_id=AGENT, **_around_now()))
    assert _ts(later["issued_at"]) > _ts(pm.first_failure.ts)
    assert later["token_id"] in {a.token_id for a in pm.authority}
    assert pm.raci["Accountable"] == "Payroll Lead (earliest overlapping grant)"
    assert pm.raci_sources["Accountable"] == "earliest overlapping grant"


def test_d_expired_accountable_is_the_lapsed_grant_even_before_the_window(estate):
    """Real delegation-authority: the presented token expired before the
    chosen window starts (C-gate (6)'s shape). Its grantor is still found."""
    estate.register()
    delegation = _real_delegation(estate)
    _mint(delegation, "Payroll Lead", ["read timesheets"])
    vt = _mint(delegation, "vt grantor (Controller)", ["draft invoices"],
               expires_at=(datetime.now(UTC) + timedelta(milliseconds=300)).isoformat())
    expired_at = _ts(vt["expires_at"])
    while datetime.now(UTC) <= expired_at + timedelta(milliseconds=50):
        time.sleep(0.05)
    intro = delegation.post("/introspect", json={"token_id": vt["token_id"]}).json()
    assert intro["status"] == "expired"  # what the sentinel maps to D.expired
    estate.append("conformance.block", {"action": "draft invoices", "clause_id": "D.expired",
                                        "reasons": ["token inactive: token is expired"]})

    window = {"since": (expired_at + MICRO).isoformat(),
              "until": (datetime.now(UTC) + DAY).isoformat()}
    pm = _real_engine(estate, delegation).replay(ReplayRequest(agent_id=AGENT, **window))
    assert pm.first_failure.clause_id == "D.expired"
    assert vt["token_id"] not in {a.token_id for a in pm.authority}
    assert pm.raci["Accountable"] == (
        "vt grantor (Controller) (expired grant covering 'draft invoices')")
    assert pm.raci_sources["Accountable"] == "expired grant covering 'draft invoices'"
    assert f"*Accountable grant:* `{vt['token_id'][:8]}…` by vt grantor (Controller)" in (
        render_markdown(pm))

    served = TestClient(create_replay_app(engine=_real_engine(estate, delegation)))
    body = served.post("/replay", json={"agent_id": AGENT, **window}).json()
    assert body["accountable_grant"]["token_id"] == vt["token_id"]


def test_d_revoked_accountable_is_the_revoked_grant(estate):
    estate.register()
    delegation = _real_delegation(estate)
    _mint(delegation, "Payroll Lead", ["read timesheets", "draft invoices"])
    _tick()
    revoked = _mint(delegation, "Controller", ["draft invoices"])
    assert delegation.post(f"/tokens/{revoked['token_id']}/revoke").status_code == 200
    _tick()
    estate.append("conformance.block", {"action": "draft invoices", "clause_id": "D.revoked",
                                        "reasons": ["token inactive: token is revoked"]})
    pm = _real_engine(estate, delegation).replay(
        ReplayRequest(agent_id=AGENT, **_around_now()))
    assert pm.raci["Accountable"] == "Controller (revoked grant covering 'draft invoices')"
    assert pm.accountable_grant.token_id == revoked["token_id"]


def test_status_at_is_the_delegation_token_rule():
    """AuthorityGrant.status_at(at) == DelegationToken.status(now=at): expired
    once at >= expires_at; revocation wins over expiry."""
    issued = datetime(2026, 1, 1, tzinfo=UTC)
    expires = datetime(2026, 2, 1, tzinfo=UTC)
    token = DelegationToken(agent_id=AGENT, granted_by="Controller", scope=["x"],
                            issued_at=issued, expires_at=expires)
    g = AuthorityGrant(**grant("t", "Controller", ["x"], issued.isoformat(),
                               expires_at=expires.isoformat()))
    for at in (issued, expires - MICRO, expires, expires + MICRO):
        assert g.status_at(at) == token.status(now=at).value, at
    assert g.status_at(issued - MICRO) is None  # not yet issued

    gone = token.revoke(now=expires - DAY)
    rg = AuthorityGrant(**{**grant("t", "Controller", ["x"], issued.isoformat(),
                                   expires_at=expires.isoformat(), revoked=True),
                           "revoked_at": gone.revoked_at.isoformat()})
    for at in (gone.revoked_at, expires, expires + DAY):
        assert rg.status_at(at) == gone.status(now=at).value == "revoked", at
    assert rg.status_at(gone.revoked_at - MICRO) == "active"
    unknown = AuthorityGrant(**grant("t", "Controller", ["x"], issued.isoformat(),
                                     expires_at=expires.isoformat(), revoked=True))
    assert unknown.status_at(issued + DAY) is None  # revoked, but when is unknown


@pytest.mark.parametrize("covering, in_force", [
    ({"issued": 0}, True),
    ({"issued": +MICRO}, False),
    ({"expires": 0}, False),
    ({"expires": +MICRO}, True),
    ({"revoked_at": 0}, False),
    ({"revoked_at": +MICRO}, True),
    ({"revoked_at": None}, False),
], ids=["issued-at-failure", "issued-after-failure", "expires-at-failure",
        "expires-after-failure", "revoked-at-failure", "revoked-after-failure",
        "revoked-time-unknown"])
def test_covering_grant_must_be_in_force_at_the_failure_instant(estate, covering, in_force):
    estate.register()
    at = _failure_at(estate, "conformance.escalate",
                     {"action": "draft invoices", "clause_id": "E.irreversible"})
    shift = {k: (at if v == 0 else None if v is None else at + v) for k, v in covering.items()}
    tok = grant("t-cover", "Treasurer", ["draft invoices"],
                (shift.get("issued") or at - DAY).isoformat(),
                expires_at=(shift.get("expires") or at + DAY).isoformat(),
                revoked="revoked_at" in covering)
    if shift.get("revoked_at") is not None:
        tok["revoked_at"] = shift["revoked_at"].isoformat()
    fallback = grant("t-fallback", "Controller", ["read timesheets"],
                     (at - 2 * DAY).isoformat(), expires_at=(at + DAY).isoformat())
    pm = estate.replay(tokens=[fallback, tok], since=(at - 3 * DAY).isoformat(),
                       until=(at + 3 * DAY).isoformat())
    assert {a.token_id for a in pm.authority} == {"t-cover", "t-fallback"}
    assert pm.raci["Accountable"] == (
        "Treasurer (grant covering 'draft invoices')" if in_force
        else "Controller (earliest overlapping grant)")


# (earlier instant, later instant) whose strings sort the other way round:
# pydantic drops zero microseconds, so both shapes come out of GET /tokens.
MISORDERED = [
    ("2026-02-01T00:00:47Z", "2026-02-01T00:00:47.000001Z"),
    ("2026-02-01T10:00:00+05:00", "2026-02-01T06:00:00+00:00"),
]


@pytest.mark.parametrize("pair", MISORDERED, ids=["fraction", "offset"])
@pytest.mark.parametrize("action, expected", [
    ("transfer funds", "Treasurer (grant covering 'transfer funds')"),
    ("wire funds", "Treasurer (earliest overlapping grant)"),
], ids=["covering", "fallback"])
def test_earliest_grant_is_chosen_by_instant_not_string(estate, pair, action, expected):
    earlier, later = pair
    estate.register()
    at = _failure_at(estate, "conformance.block", {"action": action, "clause_id": "E.spend_cap"})
    until = (at + DAY).isoformat()
    pm = estate.replay(tokens=[  # the later grant listed first
        grant("t-later", "CFO", ["transfer funds"], later, expires_at=until),
        grant("t-earlier", "Treasurer", ["transfer funds"], earlier, expires_at=until),
    ], until=until)
    assert pm.raci["Accountable"] == expected


@pytest.mark.parametrize("pair", MISORDERED, ids=["fraction", "offset"])
@pytest.mark.parametrize("lapsed", ["expired", "revoked"])
def test_lapsed_clause_names_the_most_recent_grant_that_lapsed_that_way(estate, lapsed, pair):
    earlier, later = pair
    estate.register()
    clause = "D.expired" if lapsed == "expired" else "D.revoked"
    at = _failure_at(estate, "conformance.block", {"action": "draft invoices", "clause_id": clause})

    def lapsed_grant(token_id, granted_by, issued, how, since_lapse=HOUR):
        tok = grant(token_id, granted_by, ["draft invoices"], issued,
                    expires_at=(at - since_lapse if how == "expired" else at + DAY).isoformat(),
                    revoked=how == "revoked")
        if how == "revoked":
            tok["revoked_at"] = (at - since_lapse).isoformat()
        return tok

    other = "revoked" if lapsed == "expired" else "expired"
    tokens = [  # earlier listed first: neither list order nor min() gives the answer
        lapsed_grant("t-earlier", "Original Controller", earlier, lapsed),
        lapsed_grant("t-later", "Renewed Controller", later, lapsed),
        # more recent, covering, lapsed the OTHER way: not what the sentinel reported
        lapsed_grant("t-other-way", "Wrong Controller", (at - HOUR).isoformat(), other,
                     since_lapse=timedelta(minutes=30)),
        # in force, covering: loses to the lapsed grant for a lapsed clause
        grant("t-active", "Current Controller", ["draft invoices"],
              (at - DAY).isoformat(), expires_at=(at + DAY).isoformat()),
    ]
    pm = estate.replay(tokens=tokens, since=(at - timedelta(minutes=1)).isoformat(),
                       until=(at + DAY).isoformat())
    assert pm.raci["Accountable"] == (
        f"Renewed Controller ({lapsed} grant covering 'draft invoices')")
    assert pm.accountable_grant.token_id == "t-later"


def test_lapsed_clause_without_a_lapsed_covering_grant_uses_the_general_rule(estate):
    """The sentinel checks expiry before scope, so the presented token need not
    cover the action: an expired grant is named only when it does."""
    estate.register()
    at = _failure_at(estate, "conformance.block",
                     {"action": "draft invoices", "clause_id": "D.expired"})
    pm = estate.replay(tokens=[
        grant("t-expired", "Payroll Lead", ["read timesheets"],
              (at - DAY).isoformat(), expires_at=(at - HOUR).isoformat()),
        grant("t-active", "Controller", ["draft invoices"],
              (at - DAY).isoformat(), expires_at=(at + DAY).isoformat()),
    ], since=(at - 2 * DAY).isoformat(), until=(at + DAY).isoformat())
    assert pm.raci["Accountable"] == "Controller (grant covering 'draft invoices')"


# ── C3 review: window boundaries, instants, naive and date-only bounds ─────


def test_window_overlap_boundaries_match_the_token_status_rule(estate):
    """Issued exactly at `until` overlaps (inclusive); expiring exactly at
    `since` does not — DelegationToken.status calls it expired then."""
    estate.register()
    since = datetime(2026, 8, 18, tzinfo=UTC)
    until = datetime(2026, 8, 19, tzinfo=UTC)
    pm = estate.replay(tokens=[
        grant("issued-at-until", "A", ["x"], until.isoformat(),
              expires_at=(until + DAY).isoformat()),
        grant("issued-after-until", "B", ["x"], (until + MICRO).isoformat(),
              expires_at=(until + DAY).isoformat()),
        grant("expires-at-since", "C", ["x"], (since - DAY).isoformat(),
              expires_at=since.isoformat()),
        grant("expires-after-since", "D", ["x"], (since - DAY).isoformat(),
              expires_at=(since + MICRO).isoformat()),
    ], since=since.isoformat(), until=until.isoformat())
    assert [a.token_id for a in pm.authority] == ["issued-at-until", "expires-after-since"]
    edge = DelegationToken(agent_id=AGENT, granted_by="C", scope=["x"],
                           issued_at=since - DAY, expires_at=since)
    assert edge.status(now=since) is TokenStatus.EXPIRED


def test_grant_expiry_side_compares_instants_not_strings(estate):
    estate.register()
    window = {"since": "2026-08-18T00:00:00+00:00", "until": "2026-08-18T23:59:59+00:00"}
    # Lexically before `since`, but it is 2026-08-18T01:00Z: in force in the window.
    alive = grant("t-alive", "Controller", ["x"], "2026-08-01T00:00:00+00:00",
                  expires_at="2026-08-17T20:00:00-05:00")
    # Lexically after `since`, but it is 2026-08-17T22:00Z: expired before it.
    gone = grant("t-gone", "CFO", ["x"], "2026-08-01T00:00:00+00:00",
                 expires_at="2026-08-18T03:00:00+05:00")
    pm = estate.replay(tokens=[gone, alive], **window)
    assert [a.token_id for a in pm.authority] == ["t-alive"]


def test_naive_window_bounds_are_read_as_utc(estate):
    """Served: a naive bound against aware token times is a 200 (never a
    naive-vs-aware TypeError) and means UTC, the ledger's rule."""
    estate.register()
    tokens = [
        grant("t-1130z", "Controller", ["x"], "2026-08-18T11:30:00+00:00",
              expires_at="2026-08-19T00:00:00+00:00"),
        grant("t-1230z", "CFO", ["x"], "2026-08-18T12:30:00+00:00",
              expires_at="2026-08-19T00:00:00+00:00"),
    ]
    replay = TestClient(create_replay_app(engine=estate.engine(tokens=tokens)))
    resp = replay.post("/replay", json={"agent_id": AGENT, "since": "2026-08-18T00:00:00",
                                        "until": "2026-08-18T12:00:00"})
    assert resp.status_code == 200, resp.text
    assert [a["token_id"] for a in resp.json()["authority"]] == ["t-1130z"]


@pytest.mark.parametrize("shape", ["since-date", "until-date", "both-dates", "basic-date"])
def test_date_only_window_bound_is_refused_422(estate, shape):
    """A date alone would reach the ledger as 00:00:00 UTC: since=until=<the
    incident's day> returned a clean 'no BLOCK or ESCALATE' report."""
    estate.register()
    estate.append("conformance.block", {"action": "transfer funds", "clause_id": "D.scope"})
    day = estate.ledger.get("/events", params={"agent_id": AGENT}).json()[-1]["ts"][:10]
    bounds = {
        "since-date": {"since": day, "until": f"{day}T23:59:59.999999+00:00"},
        "until-date": {"since": f"{day}T00:00:00+00:00", "until": day},
        "both-dates": {"since": day, "until": day},
        "basic-date": {"since": day.replace("-", ""), "until": day.replace("-", "")},
    }[shape]
    replay = TestClient(create_replay_app(engine=estate.engine()))
    for route in ("/replay", "/replay/markdown"):
        resp = replay.post(route, json={"agent_id": AGENT, **bounds})
        assert resp.status_code == 422, (route, resp.status_code, resp.text[:200])
        assert "a date alone is not an instant" in resp.text


# ── C3 review: blank manifest names are not parties ────────────────────────


@pytest.mark.parametrize("operators, principal, org, consulted, informed", [
    (["", "   "], "   ", "  ",
     "GC (delegation) (default)", "CEO / board (attestation-reporter) (default)"),
    (["  Controller (demo)  ", "", " "], " Controller, Spin State Labs (demo) ", "  ",
     "Controller (demo) (manifest kill_switch.authorized_operators)",
     "Controller, Spin State Labs (demo) (manifest identity)"),
], ids=["all-blank", "padded-and-blank"])
def test_blank_manifest_names_are_not_parties(estate, operators, principal, org,
                                              consulted, informed):
    data = manifest_data()
    data["enforcement"]["kill_switch"]["authorized_operators"] = operators
    data["identity"]["principal"] = principal
    data["identity"]["org"] = org
    assert validate_manifest_data(data).ok  # the schema accepts every one of them
    estate.register(estate.write_manifest("m.yaml", data))
    estate.append("conformance.block", {"action": "transfer funds", "clause_id": "D.scope"})
    pm = estate.replay()
    assert pm.manifest_resolved is True
    assert pm.raci["Consulted"] == consulted
    assert pm.raci["Informed"] == informed
    assert pm.raci_sources["Consulted"] == consulted[consulted.rindex("(") + 1:-1]
    assert pm.raci_sources["Informed"] == informed[informed.rindex("(") + 1:-1]


# ── C3 review: a busy ledger is not a broken chain (sealed-ledger contract) ─


def test_busy_ledger_is_unverified_never_a_broken_chain_and_never_ok(estate, monkeypatch):
    """The real ledger store: its first snapshot (the /verify) cannot
    stabilise, so the real /verify answers 200 ok=false "ledger busy: …"."""
    estate.register()
    estate.append("conformance.block", {"action": "transfer funds", "clause_id": "D.scope"})
    store = estate.ledger.app.state.store
    real, calls = store._take_snapshot, []

    def busy_first(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise LedgerBusy("ledger busy: no consistent snapshot after 42 attempts")
        return real(*args, **kwargs)

    monkeypatch.setattr(store, "_take_snapshot", busy_first)
    pm = estate.replay()
    assert len(calls) >= 2  # /verify was busy; /events was then served
    assert pm.ledger_integrity_ok is False
    assert pm.ledger_integrity_status == "unverified"
    assert pm.ledger_integrity_detail.startswith("INTEGRITY NOT VERIFIED: ledger busy: ")
    assert "CHAIN BROKEN" not in pm.ledger_integrity_detail
    assert pm.first_failure.clause_id == "D.scope"
    md = render_markdown(pm)
    assert "> ## ⚠ LEDGER INTEGRITY NOT VERIFIED (ledger busy)" in md
    assert "LEDGER INTEGRITY FAILED" not in md
    assert "OK — " not in md


@pytest.mark.parametrize("reason", [
    "segment 2: link break at index 5",
    "link break at index 3 (not ledger busy: a break)",
    None,
], ids=["break", "busy-not-a-prefix", "no-reason"])
def test_any_other_verify_failure_is_still_a_broken_chain(estate, reason):
    estate.register()
    assert estate.replay().ledger_integrity_status == "intact"
    stub = StubLedgerHttp(estate.ledger, verify_extra={"ok": False, "reason": reason})
    pm = estate.replay(ledger_http=stub)
    assert pm.ledger_integrity_ok is False
    assert pm.ledger_integrity_status == "broken"
    assert pm.ledger_integrity_detail == f"CHAIN BROKEN: {reason}"
    assert "> ## ⚠ LEDGER INTEGRITY FAILED" in render_markdown(pm)


# ── C3 review: the suite ignores the caller's FIELD_MANIFEST_DIR ────────────


def test_default_manifest_resolver_ignores_the_callers_manifest_dir():
    """tests/conftest.py: the default ManifestResolver() — the one the
    reconstruction test's engine gets — never resolves that test's relative
    manifest_ref, whatever FIELD_MANIFEST_DIR the shell exports."""
    assert ManifestResolver().resolve_detail("manifests/invoicing-agent.yaml") == (
        None, "missing")
