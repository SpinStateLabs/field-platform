"""S7-26: a wrong-shaped registry answer is `unavailable`, never an exception, in `retention_check`.

The module promises "a check that could not run is unavailable, never ok" and its broad excepts say "the check reports, it
never 500s", but the loop after them did not honour it: a list holding a non-object raised AttributeError on `.get`
(GET /retention/check was a 500), and a non-string manifest_ref (list, dict, number) reached resolve_manifest_detail.
(`ledger.retention_days` needs no guard: the manifest model already types it `int` with `ge=1`.)"""

import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import field_core.clients as clients
from sealed_ledger.api import create_app
from sealed_ledger.cli import app as cli_app
from sealed_ledger.retention import retention_check
from sealed_ledger.store import LedgerStore


class Registry:
    def __init__(self, listed):
        self.listed = listed

    def list_agents(self, *a, **k):
        return self.listed


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    for name in ("FIELD_LEDGER_URL", "FIELD_SHARED_SECRET", "FIELD_LEDGER_ARCHIVE_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FIELD_LEDGER_RETENTION_DAYS", "365")
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    path = tmp_path / "data" / "ledger" / "events.jsonl"
    path.parent.mkdir(parents=True)
    store = LedgerStore(path)
    store.append("action", {"n": 1})
    return store, path


NOT_RECORDS = [[1], [None, {"agent_id": "a", "manifest_ref": None}], ["x"], [[{"agent_id": "a"}]],
               [{"agent_id": "a"}, 5.5], [True]]


@pytest.mark.parametrize("listed", NOT_RECORDS, ids=["int", "null-and-dict", "str", "nested", "dict-and-float", "bool"])
def test_a_list_holding_a_non_record_is_unavailable_with_a_fixed_detail(ledger, listed):
    store, _ = ledger
    check = retention_check(store, Registry(listed))
    assert check.status == "unavailable" and check.ok is False
    assert "registry unavailable: TypeError: registry returned a list holding" in check.detail
    assert "not agent records" in check.detail
    assert check.offending == [] and check.unresolvable == []


def test_the_detail_names_the_type_not_the_value(ledger):
    store, _ = ledger
    check = retention_check(store, Registry([{"agent_id": "a"}, "SECRET-VALUE-xyz", 7]))
    assert "SECRET-VALUE-xyz" not in check.detail
    assert "int" in check.detail and "str" in check.detail


@pytest.mark.parametrize("ref", [["x"], {"a": 1}, 7, 1.5, True], ids=["list", "dict", "int", "float", "bool"])
def test_a_non_string_manifest_ref_is_listed_unresolvable_as_invalid(ledger, ref):
    store, _ = ledger
    check = retention_check(store, Registry([{"agent_id": "a", "manifest_ref": ref}]))
    assert check.status == "unresolvable" and check.ok is False
    assert check.unresolvable == [{"agent_id": "a", "manifest_ref": f"<{type(ref).__name__}>", "reason": "invalid"}]
    assert check.manifests_checked == 0


def test_an_empty_or_missing_ref_is_still_just_without_a_manifest(ledger):
    store, _ = ledger
    check = retention_check(store, Registry([{"agent_id": "a", "manifest_ref": ""}, {"agent_id": "b"}]))
    assert check.agents_without_manifest == 2 and check.unresolvable == []


@pytest.mark.parametrize("listed", [[1], [None, {"agent_id": "a"}]], ids=["int", "null-and-dict"])
def test_get_retention_check_is_200_with_status_unavailable_not_a_500(ledger, listed):
    store, _ = ledger
    r = TestClient(create_app(store=store, registry=Registry(listed)), raise_server_exceptions=False).get(
        "/retention/check")
    assert r.status_code == 200 and r.json()["status"] == "unavailable"


@pytest.mark.parametrize("listed", [[1], [None, {"agent_id": "a"}]], ids=["int", "null-and-dict"])
def test_the_offline_cli_check_prints_unavailable_and_exits_3(ledger, monkeypatch, listed):
    _, path = ledger
    monkeypatch.setattr(clients, "RegistryClient", lambda *a, **k: Registry(listed))
    r = CliRunner().invoke(cli_app, ["retention", "check", "--offline", "--path", str(path)])
    assert r.exit_code == 3, r.output
    assert json.loads(r.stdout)["status"] == "unavailable"
