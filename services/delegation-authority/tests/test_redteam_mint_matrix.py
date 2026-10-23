"""Red-team CI plan M8 / T9: HTTP mint matrix on ``POST /tokens``.

Runs the real delegation-authority, agent-registry and sealed-ledger apps in
process (FastAPI ``TestClient``, the harness every other test in this service
uses), with ephemeral tmp_path stores, an ephemeral roster and manifest, and a
throwaway shared secret. No estate, no real secret.

Method: one valid baseline mint (the positive control). Every refusal changes
exactly ONE dimension of that baseline, so a refusal is attributable to that
dimension. Oracles are deterministic: HTTP status, ``detail.clause_id`` and
the absence of side effects (no token persisted, no ``delegation.mint`` ledger
event). No LLM judge.

Where the plan's wording and the code differ, the test pins the CODE's
documented behaviour; the differences are listed in the PR body. Findings RT-MINT-1 (expired/overrun manifest expiry) and RT-MINT-2
(ttl_seconds=2**63 -> 500) were found by this matrix and are fixed in api.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.clients import LedgerClient, RegistryClient
from delegation_authority.store import TokenStore
from field_core.templates_api import template_data
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

AGENT_ID = "rt-mint-agent"
GRANTOR = "Red Team Grantor, Test Org"
MANIFEST_SCOPE = ["read timesheets", "draft invoices", "send invoice email"]
ROSTER_SCOPE = ["read timesheets", "draft invoices"]  # NARROWER than the manifest
SECRET = "rt-ephemeral-secret"  # throwaway, test-only; never an estate secret
HDR = "x-field-auth"
DAY = 86400


def write_manifest(tmp_path: Path, expiry: str = "2099-06-30", scope=None) -> Path:
    path = tmp_path / "agent-manifest.yaml"
    data = template_data("default")
    data["agent"]["name"] = AGENT_ID
    data["identity"]["principal"] = GRANTOR
    data["delegation"]["granted_by"] = GRANTOR
    data["delegation"]["scope"] = list(MANIFEST_SCOPE if scope is None else scope)
    data["delegation"]["expiry"] = expiry
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def write_roster(tmp_path: Path, **overrides) -> Path:
    row = {
        "grantor": GRANTOR,
        "allowed_scope": list(ROSTER_SCOPE),
        "max_ttl_days": 30,
        "max_spend_usd": 500.0,
        "active": True,
    }
    row.update(overrides)
    path = tmp_path / "doa-roster.yaml"
    path.write_text(yaml.safe_dump({"grantors": [row]}, sort_keys=False), encoding="utf-8")
    return path


class Spine:
    def __init__(self, tmp_path: Path, manifest_ref: Path | None, secret: str | None = None):
        inner = {HDR: secret} if secret else {}
        self.registry = TestClient(
            create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")),
            headers=inner,
        )
        self.ledger = TestClient(
            create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")), headers=inner
        )
        self.delegation = TestClient(
            create_delegation_app(
                store=TokenStore(tmp_path / "tokens.sqlite3"),
                ledger=LedgerClient(client=self.ledger, base_url="http://t"),
                registry=RegistryClient(client=self.registry, base_url="http://t"),
            ),
            # an unhandled server error must surface as a 500 response we can
            # assert on, not as an exception inside the test
            raise_server_exceptions=False,
        )
        body = {"agent_id": AGENT_ID, "name": "Mint Matrix Agent", "owner": GRANTOR,
                "domain": "finance"}
        if manifest_ref is not None:
            body["manifest_ref"] = str(manifest_ref)
        assert self.registry.post("/agents", json=body).status_code == 201

    def mint(self, headers=None, **overrides):
        body = {
            "agent_id": AGENT_ID,
            "granted_by": GRANTOR,
            "scope": list(ROSTER_SCOPE),
            "ttl_seconds": 3600,
        }
        body.update(overrides)
        body = {k: v for k, v in body.items() if v is not None}
        return self.delegation.post("/tokens", json=body, headers=headers or {})

    def mint_events(self) -> list[dict]:
        return self.ledger.get("/events", params={"event_type": "delegation.mint"}).json()

    def tokens(self) -> list[dict]:
        return self.delegation.get("/tokens").json()

    def assert_no_side_effects(self):
        assert self.mint_events() == []
        assert self.tokens() == []


@pytest.fixture()
def armed(tmp_path, monkeypatch):
    """Roster ARMED, no perimeter secret, valid manifest. The baseline world."""
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    return Spine(tmp_path, write_manifest(tmp_path))


def detail(resp):
    return resp.json()["detail"]


def clause(resp) -> str:
    d = detail(resp)
    assert isinstance(d, dict), d
    return d["clause_id"]


# --- positive control: exactly one valid combination ----------------------------


def test_positive_control_valid_combination_mints_and_is_ledgered(armed):
    r = armed.mint()
    assert r.status_code == 201, r.text
    token = r.json()
    assert token["agent_id"] == AGENT_ID and token["granted_by"] == GRANTOR
    assert token["scope"] == ROSTER_SCOPE
    events = armed.mint_events()
    assert len(events) == 1
    assert events[0]["payload"]["token_id"] == token["token_id"]
    assert events[0]["payload"]["doa_checked"] is True
    assert len(armed.tokens()) == 1


# --- one dimension at a time ---------------------------------------------------------

# (id, overrides, status, clause_id or None for a plain-string detail)
REFUSALS = [
    ("grantor-not-in-roster", {"granted_by": "Mallory Stranger"}, 403, "D.grantor"),
    ("grantor-case-variant", {"granted_by": GRANTOR.upper()}, 403, "D.grantor"),
    ("grantor-trailing-space", {"granted_by": GRANTOR + " "}, 403, "D.grantor"),
    ("grantor-fullwidth-lookalike", {"granted_by": GRANTOR.replace("R", "Ｒ", 1)}, 403, "D.grantor"),
    ("scope-outside-roster-row", {"scope": ["read timesheets", "send invoice email"]}, 403, "D.grantor"),
    ("scope-outside-manifest", {"scope": ["read timesheets", "wire money"]}, 403, "D.grantor"),
    ("ttl-over-grantor-cap-by-one-second", {"ttl_seconds": 30 * DAY + 1}, 403, "D.grantor"),
    ("ttl-far-over-cap", {"ttl_seconds": 3650 * DAY}, 403, "D.grantor"),
    # RT-MINT-2 (fixed): the unbounded int used to overflow timedelta() in api.py
    # -> unhandled OverflowError -> 500. Now a clean 422, like the other bad TTLs.
    ("ttl-2-pow-63", {"ttl_seconds": 2**63}, 422, None),
    ("ttl-beyond-datetime-range", {"ttl_seconds": 10**13}, 422, None),
    ("expires-at-in-the-past", {"ttl_seconds": None,
                                "expires_at": "2000-01-01T00:00:00+00:00"}, 422, None),
    ("empty-scope", {"scope": []}, 422, None),
    ("empty-grantor", {"granted_by": ""}, 422, None),
    ("zero-ttl", {"ttl_seconds": 0}, 422, None),
    ("negative-ttl", {"ttl_seconds": -5}, 422, None),
    ("both-expiry-fields", {"expires_at": "2099-01-01T00:00:00+00:00"}, 422, None),
    ("neither-expiry-field", {"ttl_seconds": None}, 422, None),
    ("unknown-body-field", {"max_spend_usd": 10**9}, 422, None),
]


@pytest.mark.parametrize("name,overrides,status,clause_id",
                         REFUSALS, ids=[r[0] for r in REFUSALS])
def test_single_dimension_refusals_persist_and_ledger_nothing(
    armed, name, overrides, status, clause_id
):
    r = armed.mint(**overrides)
    assert r.status_code == status, (name, r.status_code, r.text)
    if clause_id:
        assert clause(r) == clause_id
    armed.assert_no_side_effects()


def test_scope_outside_manifest_and_roster_row_is_attributed_to_the_right_gate(
    tmp_path, monkeypatch
):
    """The two scope gates are separable. Roster allows MORE than the manifest
    declares: the manifest gate (422 D.scope) must fire. Manifest declares
    MORE than the roster row allows: the grantor gate (403 D.grantor) fires."""
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    extra = "approve payments"

    wide_roster = write_roster(tmp_path, allowed_scope=[*MANIFEST_SCOPE, extra])
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(wide_roster))
    s1 = Spine(tmp_path, write_manifest(tmp_path))
    r = s1.mint(scope=[extra])
    assert (r.status_code, clause(r)) == (422, "D.scope")
    s1.assert_no_side_effects()

    sub = tmp_path / "wide-manifest"
    sub.mkdir()
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(sub)))
    s2 = Spine(sub, write_manifest(sub, scope=[*MANIFEST_SCOPE, extra]))
    r = s2.mint(scope=[extra])
    assert (r.status_code, clause(r)) == (403, "D.grantor")
    s2.assert_no_side_effects()


def test_inactive_grantor_is_refused(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path, active=False)))
    s = Spine(tmp_path, write_manifest(tmp_path))
    r = s.mint()
    assert (r.status_code, clause(r)) == (403, "D.grantor")
    s.assert_no_side_effects()


def test_ttl_boundary_exactly_at_cap_is_allowed_and_one_second_over_is_not(armed):
    assert armed.mint(ttl_seconds=30 * DAY + 1).status_code == 403
    assert armed.mint(ttl_seconds=30 * DAY).status_code == 201
    assert len(armed.tokens()) == 1


def test_expires_at_beyond_cap_naive_far_future_and_year_9999_are_refused(armed):
    far = datetime.now(timezone.utc) + timedelta(days=31)
    for value in (far.isoformat(), far.replace(tzinfo=None).isoformat(),
                  "2099-01-01T00:00:00", "9999-12-31T23:59:59+00:00"):
        r = armed.mint(ttl_seconds=None, expires_at=value)
        assert r.status_code == 403 and clause(r) == "D.grantor", (value, r.status_code, r.text)
    armed.assert_no_side_effects()


def test_unregistered_agent_is_404(armed):
    r = armed.mint(agent_id="never-registered-agent")
    assert r.status_code == 404
    armed.assert_no_side_effects()


@pytest.mark.parametrize("status", ["retired", "killed"])
def test_retired_or_killed_agent_is_409(armed, status):
    assert armed.registry.patch(f"/agents/{AGENT_ID}", json={"status": status}).status_code == 200
    r = armed.mint()
    assert r.status_code == 409, r.text
    armed.assert_no_side_effects()


def test_agent_reactivated_after_retirement_mints_again(armed):
    armed.registry.patch(f"/agents/{AGENT_ID}", json={"status": "retired"})
    assert armed.mint().status_code == 409
    armed.registry.patch(f"/agents/{AGENT_ID}", json={"status": "active"})
    assert armed.mint().status_code == 201


# --- expired manifest --------------------------------------------------------------------


def _tomorrow() -> str:
    """A date-only manifest expiry is 00:00 UTC of that date, so "tomorrow's
    date" is less than an hour away late in the evening and made these tests
    clock-dependent (red between 22:00 and 24:00 UTC). Three days ahead keeps
    every in-test offset (hours) and the 30-day refusal meaningful at any time
    of day. (Name kept for the call sites.)"""
    return (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d")


def test_mint_refuses_when_the_agent_manifest_delegation_has_expired(tmp_path, monkeypatch):
    """RT-MINT-1 (fixed). 422 D.manifest_expired (PROVISIONAL id), no token, no
    ledger event (refusals do not ledger, like every other D.* refusal)."""
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    s = Spine(tmp_path, write_manifest(tmp_path, expiry="2020-01-01"))
    r = s.mint()
    assert (r.status_code, clause(r)) == (422, "D.manifest_expired"), r.text
    assert "in the past" in detail(r)["message"]
    s.assert_no_side_effects()


def test_mint_refuses_a_token_that_would_outlive_the_manifest_expiry(tmp_path, monkeypatch):
    """A 30-day token under a manifest expiring tomorrow is REFUSED, not clamped
    (the code base refuses over-cap lifetimes elsewhere: max_ttl_days is a 403)."""
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    s = Spine(tmp_path, write_manifest(tmp_path, expiry=_tomorrow()))
    r = s.mint(ttl_seconds=30 * DAY)
    assert (r.status_code, clause(r)) == (422, "D.manifest_expired"), r.text
    s.assert_no_side_effects()
    # the same manifest still mints a token that ends before it does
    ok = s.mint(ttl_seconds=3600)
    assert ok.status_code == 201
    assert len(s.tokens()) == 1 and len(s.mint_events()) == 1


def test_manifest_expiry_bounds_the_expires_at_form_too(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    s = Spine(tmp_path, write_manifest(tmp_path, expiry=_tomorrow()))
    over = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    r = s.mint(ttl_seconds=None, expires_at=over)
    assert (r.status_code, clause(r)) == (422, "D.manifest_expired")
    s.assert_no_side_effects()
    within = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    assert s.mint(ttl_seconds=None, expires_at=within).status_code == 201


def test_manifest_expiry_boundary_is_exact(tmp_path, monkeypatch):
    """Expiry given as a full UTC datetime: a token ending at or before it is
    allowed, one second after is refused."""
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    edge = (datetime.now(timezone.utc) + timedelta(hours=10)).replace(microsecond=0)
    s = Spine(tmp_path, write_manifest(tmp_path, expiry=edge.isoformat()))
    over = edge + timedelta(seconds=1)
    assert s.mint(ttl_seconds=None, expires_at=over.isoformat()).status_code == 422
    assert s.mint(ttl_seconds=None, expires_at=edge.isoformat()).status_code == 201


def test_roster_unset_ignores_the_manifest_expiry_documented_unchecked_mint(
    tmp_path, monkeypatch
):
    """Roster-unset behaviour is unchanged (doa_checked: false): the manifest is
    never resolved, so a lapsed manifest does not stop the mint. The expiry
    control lives behind the same gate as the other manifest checks."""
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.delenv("FIELD_DOA_ROSTER", raising=False)
    s = Spine(tmp_path, write_manifest(tmp_path, expiry="2020-01-01"))
    assert s.mint().status_code == 201
    ev = s.mint_events()
    assert len(ev) == 1 and ev[0]["payload"]["doa_checked"] is False


def test_huge_ttl_is_422_with_the_roster_unset_too(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.delenv("FIELD_DOA_ROSTER", raising=False)
    s = Spine(tmp_path, write_manifest(tmp_path))
    r = s.mint(ttl_seconds=2**63)
    assert r.status_code == 422 and detail(r) == "ttl_seconds is out of range"
    s.assert_no_side_effects()


def test_unparseable_manifest_expiry_is_refused_not_ignored(tmp_path, monkeypatch):
    """A syntactically plausible but impossible date (month 13) matches the
    manifest's expiry pattern yet cannot be read: refuse, never skip the check."""
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    s = Spine(tmp_path, write_manifest(tmp_path, expiry="2026-13-45"))
    r = s.mint()
    assert (r.status_code, clause(r)) == (422, "D.manifest_expired"), r.text
    assert "unparseable" in detail(r)["message"]
    s.assert_no_side_effects()


def test_date_only_manifest_expiry_is_midnight_utc_not_end_of_day(tmp_path, monkeypatch):
    """Date-only means 00:00:00 UTC of that day. A token ending just before that
    midnight is accepted; one ending just after (still 'that day') is refused."""
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    day = (datetime.now(timezone.utc) + timedelta(days=3)).date()
    midnight = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    s = Spine(tmp_path, write_manifest(tmp_path, expiry=day.isoformat()))
    before = (midnight - timedelta(seconds=1)).isoformat()
    after = (midnight + timedelta(seconds=1)).isoformat()
    noon = (midnight + timedelta(hours=12)).isoformat()  # same calendar day: NOT allowed
    for late in (after, noon):
        r = s.mint(ttl_seconds=None, expires_at=late)
        assert (r.status_code, clause(r)) == (422, "D.manifest_expired"), late
    s.assert_no_side_effects()
    assert s.mint(ttl_seconds=None, expires_at=before).status_code == 201
    assert s.mint(ttl_seconds=None, expires_at=midnight.isoformat()).status_code == 201


def test_lapsed_manifest_with_over_cap_ttl_is_422_manifest_expired_not_403(tmp_path, monkeypatch):
    """Order is pinned: the lapsed-manifest check runs BEFORE the grantor TTL
    cap, so a lapsed manifest answers 422 D.manifest_expired whatever the TTL.
    (Under a LIVE manifest an over-cap TTL is still 403 D.grantor.)"""
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    s = Spine(tmp_path, write_manifest(tmp_path, expiry="2020-01-01"))
    r = s.mint(ttl_seconds=30 * DAY + 1)
    assert (r.status_code, clause(r)) == (422, "D.manifest_expired")
    s.assert_no_side_effects()


# --- roster-level failures ---------------------------------------------------------------------


def test_roster_missing_or_unreadable_is_503_and_mints_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(tmp_path / "no-such-roster.yaml"))
    s = Spine(tmp_path, write_manifest(tmp_path))
    assert s.mint().status_code == 503
    s.assert_no_side_effects()


def test_roster_swapped_mid_run_takes_effect_on_the_next_mint(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    roster = write_roster(tmp_path)
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(roster))
    s = Spine(tmp_path, write_manifest(tmp_path))
    assert s.mint().status_code == 201
    write_roster(tmp_path, active=False)  # same path, grantor now inactive
    r = s.mint()
    assert (r.status_code, clause(r)) == (403, "D.grantor")
    assert len(s.tokens()) == 1 and len(s.mint_events()) == 1


def test_roster_unset_means_no_grantor_scope_or_ttl_check_documented_unset_is_open(
    tmp_path, monkeypatch
):
    """PINNED documented behaviour (api.py docstring: 'unset is today's
    behaviour exactly, recorded as doa_checked: false'). With no roster an
    unknown grantor can mint any scope for any lifetime. This is the plan's
    T9 gap 1: it is only safe where the deployment arms the roster."""
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.delenv("FIELD_DOA_ROSTER", raising=False)
    s = Spine(tmp_path, write_manifest(tmp_path))
    r = s.mint(granted_by="Mallory Stranger", scope=["anything at all"],
               ttl_seconds=3650 * DAY)
    assert r.status_code == 201
    ev = s.mint_events()
    assert len(ev) == 1 and ev[0]["payload"]["doa_checked"] is False


# --- perimeter secret --------------------------------------------------------------------------------


@pytest.fixture()
def secured(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    return Spine(tmp_path, write_manifest(tmp_path), secret=SECRET)


@pytest.mark.parametrize("headers", [
    {},
    {HDR: ""},
    {HDR: "wrong-secret"},
    {HDR: SECRET + "x"},
    {HDR: SECRET[:-1]},
    {HDR: SECRET.upper()},
    {"authorization": "Bearer " + SECRET},
    {"x-field-auth-extra": SECRET},
], ids=["missing", "empty", "wrong", "suffixed", "truncated", "wrong-case", "bearer-instead", "wrong-header-name"])
def test_missing_or_incorrect_shared_secret_is_401_and_mints_nothing(secured, headers):
    r = secured.mint(headers=headers)
    assert r.status_code == 401, r.text
    # the data must be read with the secret: nothing was persisted or ledgered
    assert secured.mint_events() == []
    assert secured.delegation.get("/tokens", headers={HDR: SECRET}).json() == []


def test_correct_shared_secret_is_the_one_valid_combination(secured):
    r = secured.mint(headers={HDR: SECRET})
    assert r.status_code == 201, r.text
    assert len(secured.mint_events()) == 1
    assert len(secured.delegation.get("/tokens", headers={HDR: SECRET}).json()) == 1


def test_secret_does_not_bypass_roster_or_scope_gates(secured):
    h = {HDR: SECRET}
    r = secured.mint(headers=h, granted_by="Mallory Stranger")
    assert (r.status_code, clause(r)) == (403, "D.grantor")
    r = secured.mint(headers=h, scope=["wire money"])
    assert r.status_code == 403
    assert secured.mint_events() == []


def test_health_stays_open_but_tokens_do_not(secured):
    assert secured.delegation.get("/health").status_code == 200
    assert secured.delegation.get("/tokens").status_code == 401


# --- the whole matrix against ONE service: exactly one success ---------------------------------------


def test_exactly_one_valid_combination_succeeds_across_the_matrix(armed):
    outcomes = {}
    for name, overrides, _status, _clause in REFUSALS:
        outcomes[name] = armed.mint(**overrides).status_code
    outcomes["unregistered"] = armed.mint(agent_id="ghost").status_code
    outcomes["VALID"] = armed.mint().status_code

    successes = [k for k, v in outcomes.items() if v == 201]
    assert successes == ["VALID"], outcomes
    assert len(armed.tokens()) == 1
    assert len(armed.mint_events()) == 1
