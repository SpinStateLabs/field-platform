"""C-412 (reviewer C-405 F-C405-2, F-C405-3): the order of the operator guard and the retired check under ENFORCE, and
the stream of the CLI refusal.

F-C405-2: under ENFORCE the operator guard runs before the retired check, so a caller the guard refuses gets its
refusal (401 / 403) and a caller it lets through gets 409 for a retired agent. The README says "for any caller the
operator guard lets through"; the table is pinned both ways here. F-C405-3: the CLI refusal is an `error:` line on
stderr, never on stdout (a script that pipes the stdout of `registry attest` as JSON must not get the message)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_registry import cli
from agent_registry.api import create_app
from agent_registry.models import AgentStatus
from agent_registry.store import RegistryStore
from field_core import operator_auth as oa

KEY_DON = "fok_don-key-0123456789abcdef"
KEY_SVC = "fok_svc-key-0123456789abcdef"
ATT = {"attested_by": "Don Hagell"}
RETIRED = "agent 'a1' is retired - a retired agent has no re-attestation"


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture(autouse=True)
def _manifests_live_in_tmp_path(tmp_path, monkeypatch, _manifest_dir_holds_the_suites_manifest):
    """C-635 (F-C528-4): a manifest_ref must resolve INSIDE FIELD_MANIFEST_DIR; this file writes its manifests
    under tmp_path and names them by absolute path, so that is the directory."""
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(tmp_path))


@pytest.fixture()
def enforce(tmp_path, monkeypatch):
    rows = [
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active", "scopes": ["*"]},
        {"operator_id": "svc", "key_sha256": oa.key_sha256(KEY_SVC), "status": "active", "scopes": ["kill"]},
    ]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


@pytest.fixture()
def retired(tmp_path, enforce):
    store = RegistryStore(tmp_path / "a.sqlite3")
    c = TestClient(create_app(store=store, ledger=None))
    assert c.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O", "domain": "finance"},
                  headers=hdr("don", KEY_DON)).status_code == 201
    assert c.patch("/agents/a1", json={"status": "retired"}, headers=hdr("don", KEY_DON)).status_code == 200
    return c


# --- F-C405-2 -------------------------------------------------------------------------------------------------------


def test_under_enforce_a_caller_with_no_credentials_gets_401_not_409_for_a_retired_agent(retired):
    r = retired.post("/agents/a1/attest", json=ATT)
    assert r.status_code == 401


@pytest.mark.parametrize("who", [("don", "fok_wrong"), ("don", KEY_SVC), ("svc", KEY_SVC)])
def test_under_enforce_a_refused_caller_gets_403_not_409_for_a_retired_agent(retired, who):
    r = retired.post("/agents/a1/attest", json=ATT, headers=hdr(*who))
    assert r.status_code == 403 and RETIRED not in json.dumps(r.json())


def test_under_enforce_an_authorised_caller_gets_409_for_a_retired_agent_and_nothing_is_written(retired):
    before = retired.get("/agents/a1").json()
    r = retired.post("/agents/a1/attest", json=ATT, headers=hdr("don", KEY_DON))
    assert r.status_code == 409 and r.json()["detail"] == RETIRED
    assert retired.get("/agents/a1").json() == before and before["attested_at"] is None


# --- F-C405-3 -------------------------------------------------------------------------------------------------------


def _runner() -> CliRunner:
    try:
        return CliRunner(mix_stderr=False)                 # click < 8.2
    except TypeError:
        return CliRunner()                                 # click >= 8.2 always keeps the streams apart


def test_the_cli_refusal_for_a_retired_agent_is_on_stderr_and_stdout_is_empty(tmp_path):
    db = tmp_path / "agents.sqlite3"
    store = RegistryStore(db)
    TestClient(create_app(store=store)).post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O"})
    store.set_status("a1", AgentStatus.RETIRED)
    store.close()
    r = _runner().invoke(cli.app, ["attest", "a1", "--by", "Don", "--path", str(db)])
    assert r.exit_code == 4
    assert f"error: {RETIRED}" in r.stderr and r.stdout == ""


def test_the_cli_refusal_for_an_unknown_agent_is_on_stderr_and_stdout_is_empty(tmp_path):
    db = tmp_path / "agents.sqlite3"
    RegistryStore(db).close()
    r = _runner().invoke(cli.app, ["attest", "nobody", "--by", "Don", "--path", str(db)])
    assert r.exit_code == 1
    assert "error: agent 'nobody' not registered" in r.stderr and r.stdout == ""


# --- C-417 (reviewer C-416 F-C416-1): the manifest-authorisation step against the retired check ------------------------

KEY_ATT = "tkv-c417att-key-0123456789abcdef"
KEY_BYP = "tkv-c417byp-key-0123456789abcdef"


@pytest.fixture()
def retired_with_manifest(tmp_path, monkeypatch):
    """An agent whose manifest names only `don`, retired. Operators: `don` (all scopes), `att` (attest, NOT on the
    manifest's list), `byp` (attest + bypass_operator_list)."""
    import yaml
    from field_core.templates_api import template_data

    rows = [
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active", "scopes": ["*"]},
        {"operator_id": "att", "key_sha256": oa.key_sha256(KEY_ATT), "status": "active", "scopes": ["attest"]},
        {"operator_id": "byp", "key_sha256": oa.key_sha256(KEY_BYP), "status": "active",
         "scopes": ["attest", "bypass_operator_list"]},
    ]
    ops = tmp_path / "operators.json"
    ops.write_text(json.dumps(rows), encoding="utf-8")
    data = template_data("default")
    data["agent"]["name"] = "g1"
    data["enforcement"]["kill_switch"]["authorized_operators"] = ["don"]
    manifest = tmp_path / "g1.yaml"
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    c = TestClient(create_app(store=RegistryStore(tmp_path / "a.sqlite3"), ledger=None))
    assert c.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O", "domain": "finance",
                                   "manifest_ref": str(manifest)}).status_code == 201
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    assert c.patch("/agents/a1", json={"status": "retired"}, headers=hdr("don", KEY_DON)).status_code == 200
    return c


def test_an_operator_with_the_attest_scope_who_is_not_on_the_manifest_gets_403_not_409_for_a_retired_agent(
        retired_with_manifest):
    c = retired_with_manifest
    before = c.get("/agents/a1").json()
    r = c.post("/agents/a1/attest", json=ATT, headers=hdr("att", KEY_ATT))
    assert r.status_code == 403 and RETIRED not in json.dumps(r.json())
    assert c.get("/agents/a1").json() == before


def test_the_operator_the_manifest_names_gets_409_for_a_retired_agent(retired_with_manifest):
    r = retired_with_manifest.post("/agents/a1/attest", json=ATT, headers=hdr("don", KEY_DON))
    assert r.status_code == 409 and r.json()["detail"] == RETIRED


def test_an_identity_that_bypasses_the_operator_list_gets_409_for_a_retired_agent(retired_with_manifest):
    r = retired_with_manifest.post("/agents/a1/attest", json=ATT, headers=hdr("byp", KEY_BYP))
    assert r.status_code == 409 and r.json()["detail"] == RETIRED
