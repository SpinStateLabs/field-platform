"""S7-13 — scan_service_accounts gets the D3 input hardening the other CSV readers have:
a BOM is not a header character, 1 MiB is enforced, and a header with neither
``account`` nor ``name`` is refused by name instead of scanning nothing."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_registry import cli
from agent_registry.api import create_app
from agent_registry.discover import scan_service_accounts
from agent_registry.models import AgentCreate
from agent_registry.redaction import MAX_SCAN_BYTES, ScanInputError
from agent_registry.store import RegistryStore


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "agents.sqlite3"
    store = RegistryStore(path)
    store.add(AgentCreate(agent_id="svc-known", name="Known", owner="Controller, SSL",
                         domain="finance"))
    store.close()
    return path


@pytest.fixture()
def client(db, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    store = RegistryStore(db)
    yield TestClient(create_app(store=store), raise_server_exceptions=False)
    store.close()


BOM_CSV = "﻿account,type\nsvc-known,service\nsvc-shadow,service\n"
_ROW = "svc-a,service\n"
BIG = "account,type\n" + _ROW * (MAX_SCAN_BYTES // len(_ROW) + 1)  # many small rows, > 1 MiB


def _registered(db):
    s = RegistryStore(db)
    try:
        return s.list()
    finally:
        s.close()


def test_bom_prefixed_file_is_scanned(db):
    cands, scanned = scan_service_accounts(BOM_CSV, _registered(db))
    assert scanned == 2
    assert [c.identifier for c in cands] == ["svc-shadow"]


def test_bom_prefixed_file_via_api(client):
    r = client.post("/discover", json={"accounts_csv": BOM_CSV})
    assert r.status_code == 200, r.text
    assert r.json()["scanned_accounts"] == 2


def test_oversize_csv_is_422_and_exit_2(client, tmp_path, db):
    r = client.post("/discover", json={"accounts_csv": BIG})
    assert r.status_code == 422 and "1 MiB" in r.json()["detail"]
    f = tmp_path / "big.csv"
    f.write_text(BIG, encoding="utf-8")
    res = CliRunner().invoke(cli.app, ["scan", "--accounts", str(f), "--path", str(db)])
    assert res.exit_code == 2, res.output
    assert "1 MiB" in res.output


@pytest.mark.parametrize("header", ["identity,type", "Identity", "owner,notes"])
def test_header_without_account_or_name_is_refused(client, tmp_path, db, header):
    csv_text = f"{header}\nsvc-a,service\n"
    with pytest.raises(ScanInputError, match="accounts_csv.*account.*name"):
        scan_service_accounts(csv_text, [])
    r = client.post("/discover", json={"accounts_csv": csv_text})
    assert r.status_code == 422 and "account" in r.json()["detail"]
    f = tmp_path / "a.csv"
    f.write_text(csv_text, encoding="utf-8")
    res = CliRunner().invoke(cli.app, ["scan", "--accounts", str(f), "--path", str(db)])
    assert res.exit_code == 2 and "accounts_csv" in res.output


@pytest.mark.parametrize("header", ["account,type", "name,type", " Account ,type"])
def test_either_column_name_still_scans(header):
    cands, scanned = scan_service_accounts(f"{header}\nsvc-a,service\n", [])
    assert scanned == 1 and len(cands) == 1


def test_header_only_file_is_not_refused():
    assert scan_service_accounts("account,type\n", []) == ([], 0)
