"""B1 — DOA roster gate on mint.

Every test here is written to FAIL if someone weakens the guard: each refusal
asserts the status code AND the clause id, and the 503 path asserts that
nothing was persisted and nothing was ledgered. The roster-unset path is
covered in test_delegation_authority.py (8 pre-existing tests, unmodified)
plus `test_roster_unset_is_todays_behaviour_with_doa_checked_false` below.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.clients import LedgerClient, RegistryClient
from delegation_authority.doa import DoaRoster, DoaRosterError, load_roster
from delegation_authority.store import TokenStore
from field_core.templates_api import template_data
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

AGENT_ID = "invoicing-agent"
GRANTOR = "Don Hagell, Spin State Labs"
MANIFEST_SCOPE = ["read timesheets", "draft invoices", "send invoice email"]
REPO_ROOT = Path(__file__).resolve().parents[3]


def write_manifest(tmp_path, scope=None, valid=True) -> Path:
    path = tmp_path / "agent-manifest.yaml"
    if not valid:
        path.write_text("delegation: [this is: not a manifest\n", encoding="utf-8")
        return path
    data = template_data("default")
    data["agent"]["name"] = AGENT_ID
    data["identity"]["principal"] = GRANTOR
    data["delegation"]["granted_by"] = GRANTOR
    data["delegation"]["scope"] = list(MANIFEST_SCOPE if scope is None else scope)
    data["delegation"]["expiry"] = "2027-06-30"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def write_roster(tmp_path, **overrides) -> Path:
    row = {
        "grantor": GRANTOR,
        "allowed_scope": list(MANIFEST_SCOPE),
        "max_ttl_days": 30,
        "max_spend_usd": 500.0,
        "active": True,
    }
    row.update(overrides)
    path = tmp_path / "doa-roster.yaml"
    path.write_text(yaml.safe_dump({"grantors": [row]}, sort_keys=False), encoding="utf-8")
    return path


class Spine:
    def __init__(self, tmp_path, manifest_ref):
        self.ledger_store = LedgerStore(tmp_path / "events.jsonl")
        self.registry = TestClient(
            create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3"))
        )
        self.ledger = TestClient(create_ledger_app(store=self.ledger_store))
        self.delegation = TestClient(
            create_delegation_app(
                store=TokenStore(tmp_path / "tokens.sqlite3"),
                ledger=LedgerClient(client=self.ledger, base_url="http://t"),
                registry=RegistryClient(client=self.registry, base_url="http://t"),
            )
        )
        body = {
            "agent_id": AGENT_ID,
            "name": "Invoice Drafting Copilot",
            "owner": GRANTOR,
            "domain": "finance",
        }
        if manifest_ref is not None:
            body["manifest_ref"] = str(manifest_ref)
        assert self.registry.post("/agents", json=body).status_code == 201

    def mint(self, **overrides):
        body = {
            "agent_id": AGENT_ID,
            "granted_by": GRANTOR,
            "scope": ["read timesheets", "draft invoices"],
            "ttl_seconds": 3600,
        }
        body.update(overrides)
        return self.delegation.post("/tokens", json=body)

    def mint_events(self):
        return self.ledger.get(
            "/events", params={"event_type": "delegation.mint"}
        ).json()


@pytest.fixture()
def spine(tmp_path):
    return Spine(tmp_path, write_manifest(tmp_path))


def detail(resp):
    return resp.json()["detail"]


# --- roster UNSET: today's behaviour, explicitly recorded --------------------


def test_roster_unset_is_todays_behaviour_with_doa_checked_false(spine, monkeypatch):
    monkeypatch.delenv("FIELD_DOA_ROSTER", raising=False)
    r = spine.mint()
    assert r.status_code == 201
    events = spine.mint_events()
    assert len(events) == 1
    assert events[0]["payload"]["doa_checked"] is False
    assert events[0]["payload"]["doa_row"] is None


def test_blank_roster_env_is_treated_as_unset(spine, monkeypatch):
    monkeypatch.setenv("FIELD_DOA_ROSTER", "   ")
    assert spine.mint().status_code == 201
    assert spine.mint_events()[0]["payload"]["doa_checked"] is False


# --- roster SET: the gate ----------------------------------------------------


def test_roster_happy_path_records_doa_row(spine, tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    r = spine.mint()
    assert r.status_code == 201
    payload = spine.mint_events()[0]["payload"]
    assert payload["doa_checked"] is True
    assert payload["doa_row"] == {
        "grantor": GRANTOR,
        "max_ttl_days": 30,
        "max_spend_usd": 500.0,
    }


def test_grantor_off_roster_is_403_d_grantor(spine, tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    r = spine.mint(granted_by="Someone Else, Nowhere Inc")
    assert r.status_code == 403
    assert detail(r)["clause_id"] == "D.grantor"
    assert spine.mint_events() == []
    assert spine.delegation.get("/tokens").json() == []


def test_near_miss_grantor_string_is_still_off_roster(spine, tmp_path, monkeypatch):
    """Exact-string membership: no trimming, no case folding, no fuzzy match."""
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    r = spine.mint(granted_by=GRANTOR.lower())
    assert r.status_code == 403
    assert detail(r)["clause_id"] == "D.grantor"


def test_inactive_grantor_is_403_d_grantor(spine, tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path, active=False)))
    r = spine.mint()
    assert r.status_code == 403
    assert detail(r)["clause_id"] == "D.grantor"
    assert "inactive" in detail(r)["message"]
    assert spine.mint_events() == []


def test_scope_beyond_grantor_allowed_scope_is_403_d_grantor(
    spine, tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "FIELD_DOA_ROSTER",
        str(write_roster(tmp_path, allowed_scope=["read timesheets"])),
    )
    r = spine.mint(scope=["read timesheets", "draft invoices"])
    assert r.status_code == 403
    assert detail(r)["clause_id"] == "D.grantor"
    assert "draft invoices" in detail(r)["message"]
    assert spine.mint_events() == []


def test_scope_beyond_agent_manifest_is_422_d_scope(spine, tmp_path, monkeypatch):
    """The roster widens nothing: a scope the grantor may delegate but the
    agent's own manifest does not declare is still refused."""
    monkeypatch.setenv(
        "FIELD_DOA_ROSTER",
        str(write_roster(tmp_path, allowed_scope=[*MANIFEST_SCOPE, "wire funds"])),
    )
    r = spine.mint(scope=["wire funds"])
    assert r.status_code == 422
    assert detail(r)["clause_id"] == "D.scope"
    assert spine.mint_events() == []


def test_ttl_seconds_beyond_max_ttl_days_is_403_d_grantor(spine, tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path, max_ttl_days=1)))
    r = spine.mint(ttl_seconds=2 * 86400)
    assert r.status_code == 403
    assert detail(r)["clause_id"] == "D.grantor"
    assert "max_ttl_days" in detail(r)["message"]
    assert spine.mint_events() == []


def test_expires_at_beyond_max_ttl_days_is_403_d_grantor(spine, tmp_path, monkeypatch):
    """The second expiry form must be gated too — checking only ttl_seconds
    would leave `expires_at` as an unbounded bypass."""
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path, max_ttl_days=1)))
    far = datetime.now(timezone.utc) + timedelta(days=2)
    r = spine.mint(ttl_seconds=None, expires_at=far.isoformat())
    assert r.status_code == 403
    assert detail(r)["clause_id"] == "D.grantor"
    assert spine.mint_events() == []


def test_ttl_inside_max_ttl_days_is_minted_in_both_forms(spine, tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path, max_ttl_days=3)))
    assert spine.mint(ttl_seconds=2 * 86400).status_code == 201
    soon = datetime.now(timezone.utc) + timedelta(days=2)
    assert (
        spine.mint(ttl_seconds=None, expires_at=soon.isoformat()).status_code == 201
    )


# --- fail-closed paths -------------------------------------------------------


def test_roster_set_but_file_missing_is_503_with_nothing_persisted(
    spine, tmp_path, monkeypatch
):
    """A roster that cannot be read must NEVER become a silently unchecked
    mint. 503 lands before any ledger write."""
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(tmp_path / "not-there.yaml"))
    r = spine.mint()
    assert r.status_code == 503
    assert "refusing to mint" in r.json()["detail"]
    assert spine.delegation.get("/tokens").json() == []
    assert spine.ledger.get("/events").json() == []


def test_roster_with_unknown_key_is_503(spine, tmp_path, monkeypatch):
    """extra='forbid': a typo'd roster key is a refusal, not an ignored line."""
    path = tmp_path / "doa-roster.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "grantors": [
                    {
                        "grantor": GRANTOR,
                        "allowed_scope": list(MANIFEST_SCOPE),
                        "max_ttl_days": 30,
                        "active": True,
                        "max_spend_cad": 500,  # typo: not a roster key
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(path))
    r = spine.mint()
    assert r.status_code == 503
    assert spine.ledger.get("/events").json() == []


def test_roster_that_is_not_yaml_is_503(spine, tmp_path, monkeypatch):
    path = tmp_path / "doa-roster.yaml"
    path.write_text("grantors: [unclosed\n", encoding="utf-8")
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(path))
    assert spine.mint().status_code == 503
    assert spine.ledger.get("/events").json() == []


def test_agent_without_manifest_ref_under_roster_is_422_d_scope(
    tmp_path, monkeypatch
):
    """Fail closed: with no manifest there is nothing to check scope against,
    so the mint is refused rather than allowed on the roster alone."""
    spine = Spine(tmp_path, manifest_ref=None)
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    r = spine.mint()
    assert r.status_code == 422
    assert detail(r)["clause_id"] == "D.scope"
    assert "no_ref" in detail(r)["message"]
    assert spine.mint_events() == []


def test_agent_with_missing_manifest_file_under_roster_is_422(tmp_path, monkeypatch):
    # v1.2 D3b refuses an unresolvable manifest_ref at POST /agents, so the
    # agent registers with a valid manifest that is removed afterwards — the
    # post-registration state D3b does not prevent.
    manifest = write_manifest(tmp_path)
    spine = Spine(tmp_path, manifest_ref=manifest)
    manifest.unlink()
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    r = spine.mint()
    assert r.status_code == 422
    assert detail(r)["clause_id"] == "D.scope"
    assert "missing" in detail(r)["message"]


def test_agent_with_invalid_manifest_under_roster_is_422(tmp_path, monkeypatch):
    # As above: registered valid (D3b), broken after registration. The later
    # edit gets a later mtime, so the shared resolver's mtime cache (holding
    # the valid file from registration) cannot serve the old parse.
    manifest = write_manifest(tmp_path)
    spine = Spine(tmp_path, manifest_ref=manifest)
    registered = manifest.stat()
    write_manifest(tmp_path, valid=False)
    os.utime(manifest, ns=(registered.st_atime_ns, registered.st_mtime_ns + 2_000_000_000))
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    r = spine.mint()
    assert r.status_code == 422
    assert detail(r)["clause_id"] == "D.scope"
    assert "invalid" in detail(r)["message"]


def test_roster_gate_runs_after_the_registry_check(spine, tmp_path, monkeypatch):
    """An unregistered agent is still 404, not a roster error — the registry
    check stays first so the pre-existing contract is unchanged."""
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(tmp_path / "not-there.yaml"))
    assert spine.mint(agent_id="ghost-agent").status_code == 404


# --- the shipped example roster ---------------------------------------------


def test_shipped_example_roster_parses_and_matches_the_ssl_manifests():
    """The example roster is the one Don copies; if it drifts from the two
    shipped manifests it hands out an envelope that mints nothing."""
    example = REPO_ROOT / "manifests" / "doa-roster.example.yaml"
    roster = load_roster(example)
    assert isinstance(roster, DoaRoster)
    assert [r.grantor for r in roster.grantors] == ["Don Hagell, Spin State Labs"]
    row = roster.grantors[0]
    assert row.active is True
    assert row.max_ttl_days == 30

    union: list[str] = []
    for name in ("ssl-invoicing-agent.yaml", "ssl-timekeeping-agent.yaml"):
        data = yaml.safe_load(
            (REPO_ROOT / "manifests" / name).read_text(encoding="utf-8")
        )
        assert data["delegation"]["granted_by"] == row.grantor
        for scope in data["delegation"]["scope"]:
            if scope not in union:
                union.append(scope)
    assert row.allowed_scope == union


# --- guards that were correct but unpinned (Phase B review) -------------------


def test_an_empty_roster_file_is_refused_by_name(tmp_path):
    """An empty file collapses to zero grantors, which already fails closed —
    but "roster is empty" and "you are not on the roster" send an operator to
    two different places. The message is the guard."""
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(DoaRosterError) as exc:
        load_roster(path)
    assert "empty" in str(exc.value)


def test_a_roster_that_is_not_a_mapping_is_refused_by_name(tmp_path):
    """`- grantor: X` at the top level is a LIST — the commonest hand-edit
    slip. Without the isinstance check pydantic reports a type error against
    an internal model name instead of naming the file's shape."""
    path = tmp_path / "list.yaml"
    path.write_text("- grantor: Don Hagell\n", encoding="utf-8")
    with pytest.raises(DoaRosterError) as exc:
        load_roster(path)
    assert "mapping" in str(exc.value)


@pytest.mark.parametrize("bad_ttl", [0, -1])
def test_a_nonpositive_max_ttl_days_is_refused(tmp_path, bad_ttl):
    """`max_ttl_days: 0` reads as "this grantor may mint nothing". It is far
    more likely to be a typo, and a roster that silently refuses every mint is
    indistinguishable from an outage — so the load fails loudly instead."""
    path = tmp_path / "ttl.yaml"
    path.write_text(yaml.safe_dump({"grantors": [{
        "grantor": "Don Hagell", "allowed_scope": ["read timesheets"],
        "max_ttl_days": bad_ttl, "active": True,
    }]}), encoding="utf-8")
    with pytest.raises(DoaRosterError) as exc:
        load_roster(path)
    assert "max_ttl_days" in str(exc.value)


def test_a_naive_stored_expiry_is_read_as_utc_not_local_time():
    """`_epoch` on a naive datetime. Mint normalises everything it writes, so
    this branch is defensive — but a database written by an older build, or by
    hand, holds naive values, and reading one in the server's local zone would
    shift the introspected `exp` by the UTC offset. On a UTC-0 machine the bug
    is invisible, which is exactly why it needs a test rather than a comment."""
    from delegation_authority.api import _epoch

    naive = datetime(2026, 9, 12, 12, 0, 0)
    aware = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    assert _epoch(naive) == _epoch(aware)
    assert _epoch(naive) == int(aware.timestamp())
