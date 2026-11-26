"""Backlog B10: POST /export with the operator layer OFF (unarmed) confines out_dir to FIELD_EXPORT_ROOT, as the armed
modes already did. Before: with operator auth off, out_dir was any absolute path the ledger process could write (only
NUL and over-long values were refused), reachable by any perimeter-secret holder. Nothing here is armed: no operator
registry, no FIELD_OPERATOR_REQUIRE. Every value is made up."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore

REFUSAL = "out_dir must be inside the export root"


@pytest.fixture(autouse=True)
def _unarmed(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, "FIELD_EXPORT_ROOT",
              "FIELD_SHARED_SECRET"):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def store(tmp_path):
    s = LedgerStore(tmp_path / "ledger" / "events.jsonl")
    s.append("x.event", {"i": 1})
    return s


@pytest.fixture()
def client(store):
    c = TestClient(create_app(store=store), raise_server_exceptions=False)
    assert oa.mode() == oa.OFF          # the point of this file: the unarmed path
    return c


def _bundles(root: Path) -> list[Path]:
    return [p for p in root.rglob("summary.json")] if root.exists() else []


def test_an_absolute_out_dir_outside_the_default_root_is_refused(client, tmp_path):
    outside = tmp_path / "elsewhere"
    r = client.post("/export", params={"out_dir": str(outside)})
    assert r.status_code == 422 and REFUSAL in r.json()["detail"]
    assert not outside.exists()
    assert str(tmp_path) not in r.text                       # the path is not echoed


@pytest.mark.parametrize("rel", ["..", "../..", "../../etc", "sub/../../x", "./../escape"])
def test_traversal_out_of_the_root_is_refused(client, tmp_path, rel):
    r = client.post("/export", params={"out_dir": rel})
    assert r.status_code == 422 and REFUSAL in r.json()["detail"]
    assert not (tmp_path / "escape").exists() and not (tmp_path / "x").exists()


def test_a_system_path_is_refused(client):
    r = client.post("/export", params={"out_dir": "/etc/field-b10-should-not-exist"})
    assert r.status_code == 422 and REFUSAL in r.json()["detail"]
    assert not Path("/etc/field-b10-should-not-exist").exists()


def test_no_out_dir_writes_under_the_default_root(client, store):
    r = client.post("/export")
    assert r.status_code == 200, r.text
    root = (store.path.parent / "exports").resolve()
    assert root in Path(r.json()["bundle_dir"]).resolve().parents
    assert len(_bundles(root)) == 1


def test_a_relative_out_dir_is_joined_to_the_default_root(client, store):
    r = client.post("/export", params={"out_dir": "audit/q4"})
    assert r.status_code == 200, r.text
    assert (store.path.parent / "exports" / "audit" / "q4").is_dir()


def test_an_absolute_out_dir_inside_the_root_is_accepted(client, store):
    inside = store.path.parent / "exports" / "abs"
    r = client.post("/export", params={"out_dir": str(inside)})
    assert r.status_code == 200, r.text
    assert inside.is_dir()


def test_field_export_root_moves_the_root_when_unarmed(client, tmp_path, monkeypatch):
    root = tmp_path / "custom-root"
    monkeypatch.setenv("FIELD_EXPORT_ROOT", str(root))
    assert client.post("/export", params={"out_dir": "a"}).status_code == 200
    assert (root / "a").is_dir()
    assert client.post("/export").status_code == 200        # no out_dir = the root itself
    assert len(_bundles(root)) == 2
    # the old default is now outside the root
    old_default = tmp_path / "ledger" / "exports"
    r = client.post("/export", params={"out_dir": str(old_default)})
    assert r.status_code == 422 and not old_default.exists()


def test_a_blank_field_export_root_is_the_default(client, store, monkeypatch):
    monkeypatch.setenv("FIELD_EXPORT_ROOT", "   ")
    assert client.post("/export", params={"out_dir": "b"}).status_code == 200
    assert (store.path.parent / "exports" / "b").is_dir()


def test_a_prefix_sibling_of_the_root_is_not_inside_it(client, store):
    """`.../exports-evil` shares the root's string prefix but is not below it."""
    sibling = store.path.parent / "exports-evil"
    r = client.post("/export", params={"out_dir": str(sibling)})
    assert r.status_code == 422 and not sibling.exists()


def test_the_nul_and_length_checks_still_come_first(client):
    r = client.post("/export", params={"out_dir": "a\x00b"})
    assert r.status_code == 422 and "out_dir must be a path" in r.json()["detail"]
