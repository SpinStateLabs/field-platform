"""C-483 (reviewer PR 300, F-PR300-1..4): one active contract per NORMALISED org, atomic across processes, with a loud
warning on a database that already holds duplicates.

* `normalize_org` is the one spelling an org is compared by (NFKC, case-folded, whitespace collapsed); `save`,
  `for_org` and `_lists_org` use it, so a spelling variant is the same org;
* `save` is one `BEGIN IMMEDIATE` transaction and a partial unique index on the normalised key backs it: two stores on
  one file cannot both win, and an IntegrityError is a 409-shaped ContractConflict;
* a database that already holds two active rows for one org opens (never refused), logs a warning naming the ids,
  skips the index, still resolves to the lowest contract id (as text) and still refuses a third.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from federation_broker import engine as engine_module
from federation_broker.api import create_app
from federation_broker.engine import (BrokerEngine, ContractConflict, ContractStore, FederationContract, _lists_org,
                                      normalize_org)

DEMO = Path(engine_module.__file__).resolve().parents[2] / "demo.sh"
README = Path(engine_module.__file__).resolve().parents[2] / "README.md"
BASE = dict(allowed_scopes=["exchange invoice status"], allowed_data_classes=["invoice metadata"])


def contract(cid, org="Acme Corp", active=True):
    return FederationContract(contract_id=cid, counterparty_org=org, active=active, **BASE)


@pytest.fixture()
def store(tmp_path):
    s = ContractStore(tmp_path / "c.sqlite3")
    yield s
    s.close()


def index_exists(path) -> bool:
    c = sqlite3.connect(str(path))
    try:
        return c.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='contracts_one_active_per_org'").fetchone() is not None
    finally:
        c.close()


# ---- the helper -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("a,b", [
    ("Acme Corp", "ACME CORP"),
    ("Acme Corp", "  acme corp  "),
    ("Acme Corp", "Acme    Corp"),
    ("Acme Corp", "Acme\tCorp"),
    ("Acme Corp", "Acme Corp"),                    # no-break space
    ("Acme Corp", "Ａcme Corp"),                    # fullwidth A (NFKC)
    ("Straße AG", "STRASSE AG"),                   # casefold, not lower()
])
def test_spelling_variants_are_one_org(a, b):
    assert normalize_org(a) == normalize_org(b)


@pytest.mark.parametrize("a,b", [("Acme Corp", "Acme Corporation"), ("Acme Corp", "Acme-Corp"), ("Acme Corp", "Acne Corp")])
def test_different_orgs_stay_different(a, b):
    assert normalize_org(a) != normalize_org(b)


def test_a_whitespace_only_name_normalises_to_nothing_and_matches_nothing(store):
    assert normalize_org("  \t ") == ""
    store.save(contract("FED-1", org="Acme Corp"))
    store.save(contract("FED-BLANK", org="   "))           # accepted as before; it can never be looked up
    assert store.for_org("   ") is None
    assert _lists_org([{"org": "Acme Corp"}], "   ") is False


# ---- save, for_org and the peer rule use it -------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_ORG_NAME", "Spin State Labs")
    s = ContractStore(tmp_path / "api.sqlite3")
    yield TestClient(create_app(engine=BrokerEngine(store=s)))
    s.close()


def put(client, cid, org, active=True):
    return client.put(f"/contracts/{cid}", json={"contract_id": cid, "counterparty_org": org, "allowed_scopes": ["s"],
                                                 "allowed_data_classes": ["d"], "active": active})


@pytest.mark.parametrize("variant", ["ACME CORP", " acme  corp ", "Ａcme Corp"])
def test_a_spelling_variant_cannot_hold_a_second_active_contract(client, variant):
    assert put(client, "FED-1", "Acme Corp").status_code == 200
    r = put(client, "FED-2", variant)
    assert r.status_code == 409, r.text
    assert "FED-1" in r.text


def test_the_same_id_may_change_its_spelling(client):
    assert put(client, "FED-1", "Acme Corp").status_code == 200
    assert put(client, "FED-1", "ACME  CORP").status_code == 200


def test_for_org_finds_the_contract_by_any_spelling(store):
    store.save(contract("FED-1", org="Acme Corp"))
    for spelling in ("ACME CORP", " acme   corp", "Ａcme Corp"):
        assert store.for_org(spelling).contract_id == "FED-1"
    assert store.for_org("Acme Corporation") is None


def test_the_peer_rule_compares_normalised_names():
    assert _lists_org([{"org": "ACME   CORP Holdings"}], "acme corp")
    assert not _lists_org([{"org": "Other Co"}], "acme corp")


# ---- atomic across processes ----------------------------------------------------------------------------------------

def test_two_stores_on_one_file_cannot_both_register_an_active_contract(tmp_path):
    path = tmp_path / "race.sqlite3"
    a, b = ContractStore(path), ContractStore(path)
    try:
        for rnd in range(15):
            for s in (a, b):                                 # start each round with the org free
                for c in s.list():
                    s.save(contract(c.contract_id, org=c.counterparty_org, active=False))
            barrier, results = threading.Barrier(2), {}

            def run(name, s, cid, org):
                barrier.wait()
                try:
                    s.save(contract(cid, org=org))
                    results[name] = "ok"
                except ContractConflict:
                    results[name] = "conflict"

            ts = [threading.Thread(target=run, args=("a", a, f"FED-A{rnd}", "Acme Corp")),
                  threading.Thread(target=run, args=("b", b, f"FED-B{rnd}", "ACME  CORP"))]
            [t.start() for t in ts]
            [t.join() for t in ts]
            assert sorted(results.values()) == ["conflict", "ok"], (rnd, results)
            assert len([c for c in a.list() if c.active]) == 1
    finally:
        a.close()
        b.close()


def test_the_unique_index_exists_and_refuses_a_second_active_row_for_one_key(tmp_path):
    path = tmp_path / "idx.sqlite3"
    ContractStore(path).close()
    assert index_exists(path)
    c = sqlite3.connect(str(path))
    ins = ("INSERT INTO contracts (contract_id, counterparty_org, allowed_scopes, allowed_data_classes, active, org_key) "
           "VALUES (?, 'x', '[]', '[]', ?, 'acme corp')")
    c.execute(ins, ("FED-1", 1))
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(ins, ("FED-2", 1))
    c.execute(ins, ("FED-3", 0))                              # an inactive row is not covered by the index
    c.close()


def test_an_integrity_error_from_the_index_is_a_contract_conflict(store, tmp_path):
    # a row the application check cannot see (its text normalises differently from its key) but the index catches
    with store._lock, store._conn:
        store._conn.execute(
            "INSERT INTO contracts (contract_id, counterparty_org, allowed_scopes, allowed_data_classes, active, org_key) "
            "VALUES ('FED-HIDDEN', 'Something Else', ?, ?, 1, 'acme corp')", (json.dumps(["s"]), json.dumps(["d"])))
    with pytest.raises(ContractConflict, match="one active contract per org"):
        store.save(contract("FED-2", org="Acme Corp"))
    assert [c.contract_id for c in store.list()] == ["FED-HIDDEN"]          # the failed save left nothing behind


# ---- a database from before the rule --------------------------------------------------------------------------------

def old_database(path, rows):
    c = sqlite3.connect(str(path))
    c.executescript("CREATE TABLE contracts (contract_id TEXT PRIMARY KEY, counterparty_org TEXT NOT NULL, "
                    "allowed_scopes TEXT NOT NULL, allowed_data_classes TEXT NOT NULL, contract_ref TEXT, active INTEGER NOT NULL DEFAULT 1);")
    for cid, org in rows:
        c.execute("INSERT INTO contracts VALUES (?,?,?,?,NULL,1)", (cid, org, json.dumps(["s"]), json.dumps(["d"])))
    c.commit()
    c.close()


def test_a_clean_old_database_is_upgraded_in_place_and_gets_the_index(tmp_path):
    path = tmp_path / "old.sqlite3"
    old_database(path, [("FED-1", "Acme Corp"), ("FED-2", "Other Co")])
    s = ContractStore(path)
    try:
        assert index_exists(path)
        assert s.for_org("ACME CORP").contract_id == "FED-1"
    finally:
        s.close()


def test_a_database_with_duplicate_active_rows_opens_warns_and_skips_the_index(tmp_path, caplog):
    path = tmp_path / "dupes.sqlite3"
    old_database(path, [("FED-B", "Acme Corp"), ("FED-A", "ACME  CORP"), ("FED-C", "Other Co")])
    with caplog.at_level(logging.WARNING, logger="federation_broker.engine"):
        s = ContractStore(path)
    try:
        text = " ".join(r.getMessage() for r in caplog.records)
        assert "FED-A" in text and "FED-B" in text and "NOT created" in text
        assert not index_exists(path)
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="federation_broker.engine"):
            assert s.for_org("acme corp").contract_id == "FED-A"          # the lowest id, as text
        assert "lowest contract id" in " ".join(r.getMessage() for r in caplog.records)
        with pytest.raises(ContractConflict):                                # a third is still refused
            s.save(contract("FED-D", org="Acme Corp"))
    finally:
        s.close()


def test_a_single_active_contract_logs_no_warning(store, caplog):
    store.save(contract("FED-1"))
    with caplog.at_level(logging.WARNING, logger="federation_broker.engine"):
        assert store.for_org("Acme Corp").contract_id == "FED-1"
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


# ---- wording (F-PR300-3, F-PR300-4) ---------------------------------------------------------------------------------

def test_the_readme_says_what_a_legacy_database_resolves_to():
    text = README.read_text(encoding="utf-8")
    assert "lowest contract id" in text and "as text" in text


def test_the_demo_does_not_claim_nothing_is_masked():
    text = DEMO.read_text(encoding="utf-8")
    assert "nothing is masked" not in text
    assert "`|| true`" in text and "assertion that follows" in text
