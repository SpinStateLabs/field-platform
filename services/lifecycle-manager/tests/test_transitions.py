"""v1.2 B4 — re-attestation basis, provision, decommission.

Every test here is written so that it FAILS if the guard it covers is
weakened. The three that matter most:

* an INVALID manifest must leave zero side effects (a half-provisioned agent
  is worse than none);
* decommissioning an unknown agent must fail loud — no registry change, no
  ledger event, kill spy at zero;
* a second decommission must be a recorded no-op with NO second
  ``kill.agent``.

The whole stack is in-process (registry, ledger, delegation, governor,
kill-switch apps behind TestClients) and every clock is injected, so there
is no network and no sleep anywhere.
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from lifecycle_manager.engine import (
    LifecycleEngine,
    LifecycleError,
    SweepConfig,
    render_markdown,
)
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)
ROSTER = "owner,department\nAP Team Lead,finance\n"

#: A fully resolved, VALID manifest. `limit: 500` daily is 50000 cents — the
#: number the happy-path provision test asserts, derived with `round`, which
#: is what SpendCapConfig.from_manifest uses.
VALID_MANIFEST = """\
schema_version: field.spinstatelabs.ca/v1

agent:
  name: invoicing-agent
  description: Reads a timesheet CSV and drafts invoices for human review. SYNTHETIC test agent.
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
    endpoint: http://127.0.0.1:8005/kill/invoicing-agent
    method: HTTP POST
    authorized_operators:
      - Controller, Spin State Labs (test)
  spend_cap:
    currency: USD
    limit: 500
    period: daily
    on_breach: halt
  irreversible_action_policy: require_human_approval
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

#: INVALID: every required section is missing but `agent`. `field validate`
#: reports INVALID, so provision must stop before it touches anything.
INVALID_MANIFEST = """\
schema_version: field.spinstatelabs.ca/v1

agent:
  name: invoicing-agent
  description: Missing every other required FIELD section.
  version: "0.1.0"
"""


class KillSpy:
    """Counts kill calls and forwards them to the real kill-switch app.

    `calls` is the assertion that matters in the adversarial tests: zero
    means the code never even reached the halt."""

    def __init__(self, client):
        self.client = client
        self.calls: list[tuple[str, dict]] = []

    def post(self, path, json=None, **kw):
        self.calls.append((path, json or {}))
        return self.client.post(path, json=json, **kw)


class Down:
    """A client whose every call raises — an outage, not a refusal."""

    def get(self, *a, **k):
        raise ConnectionError("down")

    def post(self, *a, **k):
        raise ConnectionError("down")

    def patch(self, *a, **k):
        raise ConnectionError("down")

    def put(self, *a, **k):
        raise ConnectionError("down")


@pytest.fixture()
def stack(tmp_path):
    store = RegistryStore(tmp_path / "agents.sqlite3")
    registry = TestClient(create_registry_app(store=store))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    delegation = TestClient(
        create_delegation_app(
            store=TokenStore(tmp_path / "tokens.sqlite3"),
            ledger=LedgerClient(client=ledger, base_url="http://t"),
            registry=RegistryClient(client=registry, base_url="http://t"),
        )
    )
    governor = TestClient(
        create_governor_app(store=GovernorStore(tmp_path / "spend.sqlite3"))
    )
    kill_app = TestClient(
        create_kill_app(
            registry=RegistryClient(client=registry, base_url="http://t"),
            ledger=LedgerClient(client=ledger, base_url="http://t"),
        )
    )
    kill_spy = KillSpy(kill_app)
    engine = LifecycleEngine(
        registry=RegistryClient(client=registry, base_url="http://t"),
        delegation=delegation,
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        killswitch=kill_spy,
        registry_http=registry,
        governor=governor,
    )
    yield engine, registry, ledger, delegation, governor, kill_spy
    store.close()


@pytest.fixture()
def valid_manifest(tmp_path) -> pathlib.Path:
    path = tmp_path / "invoicing-agent.yaml"
    path.write_text(VALID_MANIFEST, encoding="utf-8")
    return path


@pytest.fixture()
def estate_ref(tmp_path) -> str:
    """An absolute, estate-shaped manifest_ref (.../data/manifests/NAME.yaml)
    that RESOLVES. v1.2 D3b: POST /agents refuses a set manifest_ref that does
    not resolve, and the literal "/data/manifests/invoicing-agent.yaml" exists
    on an estate but not on a dev box or CI runner. It is a different file from
    ``valid_manifest`` (the --manifest path), so the "recorded verbatim, not
    rewritten from --manifest" assertions keep their meaning."""
    path = tmp_path / "data" / "manifests" / "invoicing-agent.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(VALID_MANIFEST, encoding="utf-8")
    return str(path)


@pytest.fixture()
def invalid_manifest(tmp_path) -> pathlib.Path:
    path = tmp_path / "broken.yaml"
    path.write_text(INVALID_MANIFEST, encoding="utf-8")
    return path


def _events(ledger, event_type=None):
    params = {"event_type": event_type} if event_type else None
    return ledger.get("/events", params=params).json()


# ---------------------------------------------------------------------------
# Re-attestation basis
# ---------------------------------------------------------------------------

def test_grep_guard_engine_never_reads_the_record_edit_timestamp():
    """The regression this whole change exists to prevent.

    The old basis was the registry record's edit timestamp, which ANY patch
    resets — so a kill/revive cycle zeroed the staleness clock. If someone
    reintroduces a read of it, this fails."""
    import lifecycle_manager.engine as engine_module

    source = pathlib.Path(engine_module.__file__).read_text(encoding="utf-8")
    assert "updated_at" not in source, (
        "engine.py must not read the registry record's edit timestamp — "
        "the re-attestation basis is attested_at, else created_at"
    )


def test_reattestation_basis_is_created_at_when_nobody_has_attested(stack):
    engine, registry, _, _, _, _ = stack
    registry.post("/agents", json={"agent_id": "invoicing-agent", "name": "I",
                                   "owner": "AP Team Lead", "domain": "finance"})
    report = engine.sweep(ROSTER, config=SweepConfig(), now=NOW + timedelta(days=120))
    (finding,) = report.reattestation_due
    assert finding.basis == "created_at"
    assert finding.attested_by is None
    assert finding.days_stale >= 119


def test_attesting_moves_the_basis_and_names_the_attester(stack):
    """After an attestation the clock runs from attested_at, and both the
    finding and the ledger payload say who attested."""
    engine, registry, ledger, _, _, _ = stack
    registry.post("/agents", json={"agent_id": "invoicing-agent", "name": "I",
                                   "owner": "AP Team Lead", "domain": "finance"})
    stale = NOW + timedelta(days=120)
    fresh = NOW + timedelta(days=89)

    before = engine.sweep(ROSTER, config=SweepConfig(), now=stale).reattestation_due
    assert [f.basis for f in before] == ["created_at"]

    registry.post("/agents/invoicing-agent/attest", json={"attested_by": "Don Hagell"})

    # Inside the 90-day window on the new basis: nothing due.
    assert engine.sweep(ROSTER, config=SweepConfig(), now=fresh).reattestation_due == []

    # Past it: due again, and the finding says which clock it ran.
    (finding,) = engine.sweep(
        ROSTER, config=SweepConfig(), now=stale
    ).reattestation_due
    assert finding.basis == "attested_at"
    assert finding.attested_by == "Don Hagell"

    payload = _events(ledger, "lifecycle.reattestation_due")[-1]["payload"]
    assert payload["basis"] == "attested_at"
    assert payload["attested_by"] == "Don Hagell"
    # Additive: the pre-v1.2 keys still mean what they meant.
    assert set(payload) >= {"owner", "days_stale", "operator"}


def test_adversarial_kill_revive_cycle_does_not_hide_staleness(stack):
    """The exact bug: two PATCHes used to reset the re-attestation clock."""
    engine, registry, _, _, _, _ = stack
    registry.post("/agents", json={"agent_id": "invoicing-agent", "name": "I",
                                   "owner": "AP Team Lead", "domain": "finance"})
    later = NOW + timedelta(days=120)
    registry.patch("/agents/invoicing-agent", json={"status": "killed"})
    registry.patch("/agents/invoicing-agent", json={"status": "active"})
    registry.patch("/agents/invoicing-agent", json={"owner": "AP Team Lead"})

    report = engine.sweep(ROSTER, config=SweepConfig(), now=later)
    assert [f.agent_id for f in report.reattestation_due] == ["invoicing-agent"]


def test_markdown_names_the_basis(stack):
    engine, registry, _, _, _, _ = stack
    registry.post("/agents", json={"agent_id": "invoicing-agent", "name": "I",
                                   "owner": "AP Team Lead", "domain": "finance"})
    md = render_markdown(
        engine.sweep(ROSTER, config=SweepConfig(), now=NOW + timedelta(days=120))
    )
    assert "since created_at" in md


# ---------------------------------------------------------------------------
# provision
# ---------------------------------------------------------------------------

def test_adversarial_invalid_manifest_leaves_zero_side_effects(
    stack, invalid_manifest
):
    engine, registry, ledger, delegation, governor, kill_spy = stack
    with pytest.raises(LifecycleError) as exc:
        engine.provision(
            manifest_path=invalid_manifest, owner="AP Team Lead",
            domain="finance", grantor="Controller", ttl_days=30,
        )
    assert "INVALID" in str(exc.value)

    assert registry.get("/agents").json() == []
    assert delegation.get("/tokens").json() == []
    assert governor.get("/caps/invoicing-agent").status_code == 404
    assert _events(ledger) == []
    assert kill_spy.calls == []


def test_happy_path_provision_registers_caps_and_mints(stack, valid_manifest, estate_ref):
    engine, registry, ledger, delegation, governor, _ = stack
    report = engine.provision(
        manifest_path=valid_manifest, owner="AP Team Lead", domain="finance",
        grantor="Controller, Spin State Labs (test)", ttl_days=30,
        name="Invoicing", manifest_ref=estate_ref,
    )
    assert report.ok is True
    assert report.registry_outcome == "registered"
    assert [s.step for s in report.steps] == ["validate", "register", "cap", "mint"]
    assert {s.outcome for s in report.steps} == {"ok"}

    record = registry.get("/agents/invoicing-agent").json()
    assert record["owner"] == "AP Team Lead" and record["domain"] == "finance"
    assert record["manifest_ref"] == estate_ref
    assert record["name"] == "Invoicing"

    cap = governor.get("/caps/invoicing-agent").json()
    assert cap["limit_cents"] == 50_000 and cap["period"] == "daily"
    assert report.cap_cents == 50_000

    tokens = delegation.get("/tokens").json()
    assert len(tokens) == 1
    assert tokens[0]["scope"] == ["read timesheets", "draft invoices"]
    assert report.token_id == tokens[0]["token_id"]


def test_provision_cents_use_round_not_truncation(stack, tmp_path):
    """$0.29 is 29 cents, and binary floating point is why this matters:
    `0.29 * 100` is 28.999999999999996, so `int()` truncates to 28 while
    `round()` gives 29. The cap written here and the cap the governor derives
    must not differ by a cent.

    The value is load-bearing. An earlier version of this test used 0.07,
    where `0.07 * 100` is 7.000000000000001 — `int()` and `round()` BOTH
    return 7, so the test passed against the truncating implementation it was
    named after and proved nothing."""
    assert int(0.29 * 100) == 28 and round(0.29 * 100) == 29, (
        "pick a value where the two functions disagree, or this test is decoration"
    )
    engine, _, _, _, governor, _ = stack
    path = tmp_path / "cents.yaml"
    path.write_text(VALID_MANIFEST.replace("limit: 500", "limit: 0.29"), encoding="utf-8")
    report = engine.provision(
        manifest_path=path, owner="AP Team Lead", domain="finance",
        grantor="Controller", ttl_days=30,
    )
    assert report.cap_cents == 29
    assert governor.get("/caps/invoicing-agent").json()["limit_cents"] == 29


def test_provision_of_an_existing_agent_is_reported_as_updated(stack, valid_manifest,
                                                             estate_ref):
    engine, registry, _, _, _, _ = stack
    registry.post("/agents", json={"agent_id": "invoicing-agent", "name": "Old",
                                   "owner": "Someone Else", "domain": "finance"})
    report = engine.provision(
        manifest_path=valid_manifest, owner="AP Team Lead", domain="finance",
        grantor="Controller", ttl_days=30,
        manifest_ref=estate_ref,
    )
    assert report.ok is True
    assert report.registry_outcome == "updated"
    record = registry.get("/agents/invoicing-agent").json()
    assert record["owner"] == "AP Team Lead"
    assert record["manifest_ref"] == estate_ref


def test_provision_passes_a_mint_refusal_through_verbatim(stack, valid_manifest,
                                                          monkeypatch, tmp_path):
    """B1's roster gate refuses off-roster grantors with 403 D.grantor. The
    provision report must carry that status and body, not a paraphrase."""
    roster = tmp_path / "doa.yaml"
    roster.write_text(
        "grantors:\n"
        "  - grantor: Controller, Spin State Labs (test)\n"
        "    allowed_scope: [read timesheets, draft invoices]\n"
        "    max_ttl_days: 30\n"
        "    active: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(roster))
    engine, registry, _, delegation, governor, _ = stack
    report = engine.provision(
        manifest_path=valid_manifest, owner="AP Team Lead", domain="finance",
        grantor="Somebody Not On The Roster", ttl_days=30,
    )
    assert report.ok is False
    mint = [s for s in report.steps if s.step == "mint"][0]
    assert mint.outcome == "failed" and mint.http_status == 403
    assert "D.grantor" in (mint.detail or "")
    # ...and the earlier steps are reported as done, not silently undone.
    assert registry.get("/agents/invoicing-agent").status_code == 200
    assert governor.get("/caps/invoicing-agent").status_code == 200
    assert delegation.get("/tokens").json() == []


def test_provision_reports_a_mid_sequence_failure_step_by_step(stack, valid_manifest):
    """The governor is down: register succeeded, cap failed, mint never ran.

    A transport fault becomes a reported STEP, not a traceback — the operator
    has to be told which step died and that the earlier ones stand."""
    engine, registry, _, delegation, _, _ = stack
    engine.governor = Down()
    report = engine.provision(
        manifest_path=valid_manifest, owner="AP Team Lead", domain="finance",
        grantor="Controller", ttl_days=30,
    )
    assert report.ok is False
    outcomes = {s.step: s.outcome for s in report.steps}
    assert outcomes == {"validate": "ok", "register": "ok", "cap": "failed"}
    assert "transport error" in [s for s in report.steps if s.step == "cap"][0].detail
    assert report.cap_cents is None and report.token_id is None

    # The registration really happened — no rollback, and no pretending.
    assert registry.get("/agents/invoicing-agent").status_code == 200
    assert delegation.get("/tokens").json() == []


# ---------------------------------------------------------------------------
# decommission
# ---------------------------------------------------------------------------

def _provisioned(engine, manifest):
    return engine.provision(
        manifest_path=manifest, owner="AP Team Lead", domain="finance",
        grantor="Controller, Spin State Labs (test)", ttl_days=30,
    )


def test_adversarial_decommission_of_an_unknown_agent_fails_loud(stack):
    engine, registry, ledger, _, _, kill_spy = stack
    before = registry.get("/agents").json()
    with pytest.raises(LifecycleError) as exc:
        engine.decommission("ghost-agent", by="Don", reason="typo")
    assert "not registered" in str(exc.value)
    assert registry.get("/agents").json() == before
    assert _events(ledger) == []
    assert kill_spy.calls == []


def test_decommission_revokes_kills_retires_and_records(stack, valid_manifest):
    engine, registry, ledger, delegation, _, kill_spy = stack
    provisioned = _provisioned(engine, valid_manifest)

    report = engine.decommission("invoicing-agent", by="Don Hagell",
                                 reason="project ended")
    assert report.ok is True and report.noop is False
    assert report.tokens_revoked == [provisioned.token_id]
    assert report.killed is True and report.retired is True

    assert delegation.get(f"/tokens/{provisioned.token_id}").json()["revoked"] is True
    assert registry.get("/agents/invoicing-agent").json()["status"] == "retired"
    assert len(kill_spy.calls) == 1

    recorded = _events(ledger, "lifecycle.decommissioned")
    assert len(recorded) == 1
    payload = recorded[0]["payload"]
    assert payload["by"] == "Don Hagell" and payload["reason"] == "project ended"
    assert payload["tokens_revoked"] == 1 and payload["killed"] is True
    assert payload["noop"] is False


def test_adversarial_second_decommission_is_a_noop_with_no_second_kill(
    stack, valid_manifest
):
    engine, registry, ledger, _, _, kill_spy = stack
    _provisioned(engine, valid_manifest)
    engine.decommission("invoicing-agent", by="Don", reason="first")
    kills_after_first = len(_events(ledger, "kill.agent"))
    assert kills_after_first == 1

    second = engine.decommission("invoicing-agent", by="Don", reason="again")
    assert second.noop is True and second.ok is True
    assert second.killed is False and second.tokens_revoked == []
    assert len(kill_spy.calls) == 1                      # no second kill call
    assert len(_events(ledger, "kill.agent")) == 1       # and no second event

    recorded = _events(ledger, "lifecycle.decommissioned")
    assert len(recorded) == 2
    assert recorded[-1]["payload"]["noop"] is True
    assert registry.get("/agents/invoicing-agent").json()["status"] == "retired"


def test_decommission_of_an_already_killed_agent_sends_no_second_kill(
    stack, valid_manifest
):
    engine, registry, ledger, _, _, kill_spy = stack
    _provisioned(engine, valid_manifest)
    registry.patch("/agents/invoicing-agent", json={"status": "killed"})

    report = engine.decommission("invoicing-agent", by="Don", reason="cleanup")
    assert report.ok is True
    assert report.killed is False
    assert kill_spy.calls == []
    assert _events(ledger, "kill.agent") == []
    assert [s.outcome for s in report.steps if s.step == "kill"] == ["skipped"]
    assert registry.get("/agents/invoicing-agent").json()["status"] == "retired"


def test_decommission_continues_act_first_when_a_revoke_answers_502(
    stack, valid_manifest
):
    """delegation revoke is ledger-first, so an audit outage answers 502. The
    halt must still happen; the run reports the failure and exits non-zero."""
    engine, registry, _, _, _, kill_spy = stack
    _provisioned(engine, valid_manifest)

    real_get = engine.delegation.get
    real_post = engine.delegation.post

    class RevokeIs502:
        def get(self, *a, **k):
            return real_get(*a, **k)

        def post(self, path, *a, **k):
            if path.endswith("/revoke"):
                class R:
                    status_code = 502
                    text = "ledger unreachable — refusing to revoke"
                return R()
            return real_post(path, *a, **k)

    engine.delegation = RevokeIs502()
    report = engine.decommission("invoicing-agent", by="Don", reason="incident")

    assert report.ok is False                     # exit code will be non-zero
    assert report.tokens_revoked == []
    assert len(report.revoke_failures) == 1
    assert report.revoke_failures[0].http_status == 502
    # ...and the agent was still halted and retired.
    assert report.killed is True and len(kill_spy.calls) == 1
    assert registry.get("/agents/invoicing-agent").json()["status"] == "retired"


def test_decommissioned_agent_cannot_be_killed_or_revived(stack, valid_manifest):
    """The cross-package guard, exercised from this side: one decommission,
    then the kill-switch refuses both ways back."""
    engine, registry, _, _, _, kill_spy = stack
    _provisioned(engine, valid_manifest)
    engine.decommission("invoicing-agent", by="Don", reason="ended")

    op = {"operator": "CISO", "reason": "curious"}
    assert kill_spy.client.post("/kill/invoicing-agent", json=op).status_code == 409
    assert kill_spy.client.post("/revive/invoicing-agent", json=op).status_code == 409
    assert registry.get("/agents/invoicing-agent").json()["status"] == "retired"


def test_decommission_reports_a_ledger_outage_instead_of_hiding_it(
    stack, valid_manifest
):
    engine, registry, _, _, _, _ = stack
    _provisioned(engine, valid_manifest)
    engine.ledger = LedgerClient(client=Down(), base_url="http://t")

    report = engine.decommission("invoicing-agent", by="Don", reason="ended")
    assert report.ok is False
    assert [s.outcome for s in report.steps if s.step == "ledger"] == ["failed"]
    # Act-first: the agent is retired even though the record could not be made.
    assert report.retired is True
    assert registry.get("/agents/invoicing-agent").json()["status"] == "retired"


def test_decommission_when_the_registry_is_unreachable_creates_nothing(tmp_path):
    engine = LifecycleEngine(
        registry=RegistryClient(client=Down(), base_url="http://t"),
        delegation=Down(),
        ledger=LedgerClient(client=Down(), base_url="http://t"),
        killswitch=Down(),
    )
    with pytest.raises(LifecycleError) as exc:
        engine.decommission("invoicing-agent", by="Don", reason="x")
    assert "registry unreachable" in str(exc.value)


def test_spend_governor_is_a_declared_runtime_dependency():
    """`provision` imports the governor's own cap arithmetic at module level,
    so it must be a RUNTIME dependency (not a dev one) and the requirement
    string must equal the dist name the governor publishes — otherwise the
    Docker images install a lifecycle-manager that cannot import."""
    import tomllib

    service = pathlib.Path(__file__).resolve().parents[1]
    services = service.parent
    mine = tomllib.loads((service / "pyproject.toml").read_text(encoding="utf-8"))
    theirs = tomllib.loads(
        (services / "spend-governor" / "pyproject.toml").read_text(encoding="utf-8")
    )
    dist = theirs["project"]["name"]
    assert dist in mine["project"]["dependencies"], (
        f"lifecycle-manager must depend on '{dist}' at runtime"
    )
    assert dist not in mine["project"].get("optional-dependencies", {}).get("dev", [])


def test_decommission_still_halts_when_the_token_listing_is_unreachable(
    stack, valid_manifest
):
    """Act-first, the hardest case: we cannot even enumerate the authority.
    The agent is still killed and retired, and the failure is on the report."""
    engine, registry, _, _, _, kill_spy = stack
    _provisioned(engine, valid_manifest)

    class NoListing:
        def get(self, *a, **k):
            raise ConnectionError("delegation down")

        def post(self, *a, **k):
            raise ConnectionError("delegation down")

    engine.delegation = NoListing()
    report = engine.decommission("invoicing-agent", by="Don", reason="incident")

    assert report.ok is False
    assert any("could not list tokens" in (f.detail or "")
               for f in report.revoke_failures)
    assert report.killed is True and len(kill_spy.calls) == 1
    assert registry.get("/agents/invoicing-agent").json()["status"] == "retired"


def test_adversarial_reprovisioning_a_retired_agent_changes_nothing(
    stack, valid_manifest, estate_ref
):
    """A decommission is final. `provision` was the fifth writer to touch a
    registry record and the only one with no `retired` guard.

    It could never resurrect the agent — the mint refuses a non-active one —
    but that made it look harmless. It is not: the 409-then-PATCH branch
    rewrote `owner` (the audit attribution for a decommissioned agent) and
    `manifest_ref` (which the kill-switch resolves its halt endpoint from,
    on every kill), and the cap step then installed a live spend cap on the
    dead record. Every one of those must not happen.
    """
    engine, registry, _, _, governor, _ = stack
    # Both setup writes are asserted: with the unresolvable estate literal, D3b
    # 422'd this POST silently, the PATCH 404'd, and provision registered a
    # fresh agent (report.ok True) — a setup that must never fail quietly.
    assert registry.post("/agents", json={
        "agent_id": "invoicing-agent", "name": "Invoicing",
        "owner": "AP Team Lead", "domain": "finance",
        "manifest_ref": estate_ref,
    }).status_code == 201
    assert registry.patch("/agents/invoicing-agent",
                          json={"status": "retired"}).status_code == 200

    report = engine.provision(
        manifest_path=valid_manifest, owner="Someone Else", domain="finance",
        grantor="Controller", ttl_days=30,
    )

    assert report.ok is False
    stopped = [s for s in report.steps if s.outcome == "failed"]
    assert [s.step for s in stopped] == ["register"]
    assert stopped[0].http_status == 409
    assert "retired" in stopped[0].detail

    record = registry.get("/agents/invoicing-agent").json()
    assert record["status"] == "retired"
    assert record["owner"] == "AP Team Lead"                       # not rewritten
    assert record["manifest_ref"] == estate_ref                    # not rewritten
    assert governor.get("/caps/invoicing-agent").status_code == 404  # no cap


def test_provisioning_an_existing_ACTIVE_agent_still_updates_it(
    stack, valid_manifest
):
    """The guard must be about `retired`, not about re-provisioning: the
    409-then-PATCH branch is how a manifest_ref or owner correction lands."""
    engine, registry, _, _, _, _ = stack
    registry.post("/agents", json={"agent_id": "invoicing-agent", "name": "Old",
                                   "owner": "Someone Else", "domain": "finance"})
    report = engine.provision(
        manifest_path=valid_manifest, owner="AP Team Lead", domain="finance",
        grantor="Controller", ttl_days=30,
    )
    assert report.registry_outcome == "updated"
    assert registry.get("/agents/invoicing-agent").json()["owner"] == "AP Team Lead"
