"""v1.2 D1 (verifier open item D1-R3) — ``lifecycle provision`` loads a
manifest's ``enforcement.rate_limits`` into the governor after the cap.

Before this, provision PUT ``/caps`` only, so an agent provisioned the way
the runbook provisions the canaries had NO rate limit: the D-gate's
``canary.throttle`` check (3 ALLOW, the 4th BLOCK ``E.rate_limit``) could not
pass, and a re-provision left a stale set in place. Every test below fails
against the provision that skipped the step:

* a declared set is loaded (and a ``session`` entry reported as declared,
  not enforced), and the governor's window then throttles after ``max``;
* a re-provision whose manifest no longer declares rate limits clears the
  stale set, and a provision with nothing declared and nothing held adds no
  step (the four-step report is unchanged);
* a set the governor would refuse stops provision before any side effect;
* a governor that refuses the set (a pre-D1 governor has no route) or is
  unreachable at that step fails the step and mints nothing.

In-process apps behind TestClients, no network, no sleeps.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, RegistryClient
from lifecycle_manager.engine import LifecycleEngine, LifecycleError
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore

AGENT = "throttled-agent"
ACTION = "draft invoices"
GRANTOR = "Controller, Spin State Labs (test)"

MANIFEST = """\
schema_version: field.spinstatelabs.ca/v1

agent:
  name: throttled-agent
  description: Drafts invoices for human review. SYNTHETIC test agent.
  version: "0.1.0"

federated:
  isolated: true
  allowed_peers: []
  contracts: []

identity:
  principal: Controller, Spin State Labs (test)
  org: Spin State Labs
  jurisdiction:
    - PIPEDA
  data_scope:
    may_access:
      - timesheet CSV (read)
    may_retain:
      - draft invoices pending review
    may_transmit: []
  model_provider: Anthropic

enforcement:
  kill_switch:
    endpoint: http://127.0.0.1:8005/kill/throttled-agent
    method: HTTP POST
    authorized_operators:
      - Controller, Spin State Labs (test)
  spend_cap:
    currency: USD
    limit: 5
    period: daily
    on_breach: halt
__RATE_LIMITS__  irreversible_action_policy: require_human_approval
  escalation_triggers:
    - send invoice

ledger:
  cryptographic_seal: true
  seal_algorithm: sha-256-merkle
  retention_days: 2555
  logged_events:
    - every action
    - every escalation
    - every delegation use
    - every spend
  store: sealed-ledger service (hash-chained JSONL)

delegation:
  granted_by: Controller, Spin State Labs (test)
  scope:
    - read timesheets
    - draft invoices
  expiry: "2030-06-30"
  revocation:
    method: HTTP POST
    endpoint: http://127.0.0.1:8003/tokens/{id}/revoke

runtime_protocol:
  name: FORCE
  version: "1.0"
  preset: audit
"""

DECLARED = (
    "  rate_limits:\n"
    "    - action: draft invoices\n"
    "      max: 3\n"
    "      period: hourly\n"
    "    - action: tool_call\n"
    "      max: 50\n"
    "      period: session\n"
)


def _manifest(tmp_path: Path, name: str, rate_limits: str = "") -> Path:
    path = tmp_path / name
    path.write_text(MANIFEST.replace("__RATE_LIMITS__", rate_limits), encoding="utf-8")
    return path


class Stack:
    def __init__(self, tmp_path: Path):
        self.registry_store = RegistryStore(tmp_path / "agents.sqlite3")
        self.registry = TestClient(create_registry_app(store=self.registry_store))
        self.ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
        self.delegation = TestClient(create_delegation_app(
            store=TokenStore(tmp_path / "tokens.sqlite3"),
            ledger=LedgerClient(client=self.ledger, base_url="http://t"),
            registry=RegistryClient(client=self.registry, base_url="http://t"),
        ))
        self.governor = TestClient(create_governor_app(store=GovernorStore(tmp_path / "spend.sqlite3")))
        self.engine = LifecycleEngine(
            registry=RegistryClient(client=self.registry, base_url="http://t"),
            delegation=self.delegation,
            ledger=LedgerClient(client=self.ledger, base_url="http://t"),
            registry_http=self.registry,
            governor=self.governor,
        )

    def provision(self, manifest: Path):
        return self.engine.provision(manifest_path=manifest, owner="AP Team Lead", domain="finance",
                                     grantor=GRANTOR, ttl_days=30)

    def rate_limits(self) -> list[dict]:
        resp = self.governor.get(f"/rate-limits/{AGENT}")
        assert resp.status_code == 200, resp.text
        return resp.json()["rate_limits"]


@pytest.fixture()
def stack(tmp_path):
    s = Stack(tmp_path)
    yield s
    s.registry_store.close()


def _step(report, name: str):
    found = [s for s in report.steps if s.step == name]
    assert len(found) == 1, [s.step for s in report.steps]
    return found[0]


def test_provision_loads_the_declared_set_and_the_window_throttles_after_max(stack, tmp_path):
    report = stack.provision(_manifest(tmp_path, "declared.yaml", DECLARED))
    assert report.ok is True
    assert [s.step for s in report.steps] == ["validate", "register", "cap", "rate_limits", "mint"]
    step = _step(report, "rate_limits")
    assert step.outcome == "ok" and step.http_status == 200
    assert step.detail.startswith("1 enforced, 1 declared-unenforced")
    assert "DECLARED, NOT ENFORCED by the governor (gate-only): 'tool_call' max 50 per 'session'" in step.detail

    rows = {r["action"]: r for r in stack.rate_limits()}
    assert rows[ACTION]["status"] == "enforced" and rows[ACTION]["max"] == 3
    assert rows[ACTION]["period_seconds"] == 3600
    assert rows["tool_call"]["status"] == "declared_unenforced"

    def status() -> dict:
        resp = stack.governor.get(f"/status/{AGENT}", params={"action": ACTION})
        assert resp.status_code == 200, resp.text
        return resp.json()

    for _ in range(3):
        assert status()["state"] == "OK"
        spend = stack.governor.post("/spend", json={"agent_id": AGENT, "actions": 1, "action": ACTION,
                                                    "source": "sentinel", "shadowed": False})
        assert spend.status_code == 201, spend.text
    throttled = status()
    assert throttled["state"] == "THROTTLED"
    assert throttled["retry_after_seconds"] > 0
    assert throttled["spent_actions_metered"] == 3 and throttled["spent_actions_self"] == 0


def test_reprovision_without_rate_limits_clears_the_stale_set(stack, tmp_path):
    assert stack.provision(_manifest(tmp_path, "declared.yaml", DECLARED)).ok is True
    assert len(stack.rate_limits()) == 2

    second = stack.provision(_manifest(tmp_path, "none.yaml"))
    assert second.ok is True and second.registry_outcome == "updated"
    step = _step(second, "rate_limits")
    assert step.outcome == "ok" and step.detail == "0 enforced, 0 declared-unenforced"
    assert stack.rate_limits() == []

    # nothing declared and nothing held: no call result worth a step, the four-step report stands
    third = stack.provision(_manifest(tmp_path, "none-again.yaml"))
    assert third.ok is True
    assert [s.step for s in third.steps] == ["validate", "register", "cap", "mint"]


@pytest.mark.parametrize("bad, why", [
    ("  rate_limits:\n    - action: draft invoices\n      max: 3\n      period: per-run\n", "per-run"),
    ("  rate_limits:\n    - action: draft invoices\n      max: 3\n      period: hourly\n"
     "    - action: draft invoices\n      max: 5\n      period: hourly\n", "duplicate"),
], ids=["unknown-period", "duplicate-entry"])
def test_a_set_the_governor_would_refuse_stops_provision_before_any_side_effect(stack, tmp_path, bad, why):
    with pytest.raises(LifecycleError) as exc:
        stack.provision(_manifest(tmp_path, "bad.yaml", bad))
    assert "enforcement.rate_limits refused" in str(exc.value) and why in str(exc.value)
    assert "Nothing was provisioned" in str(exc.value)
    assert stack.registry.get("/agents").json() == []
    assert stack.governor.get(f"/caps/{AGENT}").status_code == 404
    assert stack.delegation.get("/tokens").json() == []
    assert stack.ledger.get("/events").json() == []


class PreD1Governor:
    """A governor image from before D1: /caps works, /rate-limits is a 404."""

    def __init__(self, real):
        self.real = real

    def get(self, path, **kw):
        if path.startswith("/rate-limits/"):
            return self.real.get("/no-such-route-before-d1", **kw)
        return self.real.get(path, **kw)

    def put(self, path, **kw):
        if path.startswith("/rate-limits/"):
            return self.real.put("/no-such-route-before-d1", **kw)
        return self.real.put(path, **kw)


def test_a_governor_that_refuses_the_set_fails_the_step_and_mints_nothing(stack, tmp_path):
    stack.engine.governor = PreD1Governor(stack.governor)
    report = stack.provision(_manifest(tmp_path, "declared.yaml", DECLARED))
    assert report.ok is False
    assert [(s.step, s.outcome) for s in report.steps] == [
        ("validate", "ok"), ("register", "ok"), ("cap", "ok"), ("rate_limits", "failed")]
    step = _step(report, "rate_limits")
    assert step.http_status == 404 and "rate limits NOT loaded (404)" in step.detail
    assert report.token_id is None and stack.delegation.get("/tokens").json() == []
    # the earlier steps stand, reported, not rolled back
    assert stack.governor.get(f"/caps/{AGENT}").status_code == 200


def test_nothing_declared_against_a_pre_d1_governor_still_provisions(stack, tmp_path):
    stack.engine.governor = PreD1Governor(stack.governor)
    report = stack.provision(_manifest(tmp_path, "none.yaml"))
    assert report.ok is True
    assert [s.step for s in report.steps] == ["validate", "register", "cap", "mint"]


class RateLimitsDown(PreD1Governor):
    def get(self, path, **kw):
        if path.startswith("/rate-limits/"):
            raise ConnectionError("down")
        return self.real.get(path, **kw)

    def put(self, path, **kw):
        if path.startswith("/rate-limits/"):
            raise ConnectionError("down")
        return self.real.put(path, **kw)


def test_a_governor_outage_at_the_rate_limit_step_is_a_reported_failed_step(stack, tmp_path):
    stack.engine.governor = RateLimitsDown(stack.governor)
    report = stack.provision(_manifest(tmp_path, "declared.yaml", DECLARED))
    assert report.ok is False
    step = _step(report, "rate_limits")
    assert step.outcome == "failed" and "transport error" in step.detail
    assert stack.delegation.get("/tokens").json() == []


def test_doc_drift_no_governor_or_lifecycle_text_says_provision_skips_rate_limits():
    """Integration review R4: once provision loads rate limits, no README,
    docstring or comment may still say it PUTs /caps only, and both READMEs
    carry an Enforced row citing this file."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    stale = ("does not call it yet", "does NOT call it yet", "lifecycle provision does not call",
             "PUTs `/caps` only today", "validate -> register -> cap -> mint**")
    texts = {rel: (root / rel).read_text(encoding="utf-8") for rel in (
        "services/spend-governor/README.md", "services/spend-governor/src/spend_governor/provisioning.py",
        "services/spend-governor/src/spend_governor/cli.py", "services/lifecycle-manager/README.md")}
    for rel, text in texts.items():
        assert not [s for s in stale if s in text], rel
    gov = [l for l in texts["services/spend-governor/README.md"].splitlines()
           if "`rate_limits` are loaded by both manifest-driven provisioning paths" in l]
    assert len(gov) == 1 and "**Enforced in code**" in gov[0] and "test_provision_rate_limits.py" in gov[0]
    lc = texts["services/lifecycle-manager/README.md"]
    assert "validate -> register -> cap -> rate limits -> mint" in lc
    assert any("a failed rate-limit step mints nothing" in l and "**Enforced in code**" in l
               and "test_provision_rate_limits.py" in l for l in lc.splitlines())
