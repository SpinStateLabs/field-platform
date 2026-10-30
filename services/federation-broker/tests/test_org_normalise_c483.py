"""C-483 (reviewer PR 300 F-PR300-1..3): the one-active-contract rule is spelling-blind, enforced by the database,
and a database that already holds two active rows says so."""

from __future__ import annotations

import json
import logging
import sqlite3

import pytest

from federation_broker.engine import ContractConflict, ContractStore, FederationContract, _lists_org, normalise_org

ORG = "Borealis Example Corp"


def contract(contract_id, org=ORG, active=True):
    return FederationContract(contract_id=contract_id, counterparty_org=org, allowed_scopes=["s"],
                              allowed_data_classes=["d"], active=active)


@pytest.mark.parametrize("variant", [
    "borealis example corp", "BOREALIS EXAMPLE CORP", " Borealis Example Corp ", "Borealis  Example\tCorp",
    "Borealis Example Corp​", "Borealis Example Corp", "Ｂorealis Example Corp",    # NBSP, fullwidth B
])
def test_a_spelling_variant_of_the_org_is_the_same_org(tmp_path, variant):
    store = ContractStore(tmp_path / "c.sqlite3")
    store.save(contract("FED-A"))
    with pytest.raises(ContractConflict):
        store.save(contract("FED-B", org=variant))
    assert store.for_org(variant).contract_id == "FED-A"
    assert [c.contract_id for c in store.list()] == ["FED-A"]


def test_a_different_org_is_still_a_different_org(tmp_path):
    store = ContractStore(tmp_path / "c.sqlite3")
    store.save(contract("FED-A"))
    store.save(contract("FED-B", org="Borealis Example Corporation"))
    assert store.for_org(ORG).contract_id == "FED-A"


def test_the_helper_and_the_peer_check_agree():
    assert normalise_org("  Ａ b​\n C ") == "a b c"
    assert _lists_org([{"org": "BOREALIS  Example Corp (EU)"}], "borealis example corp")
    assert not _lists_org([{"org": "Other Corp"}], ORG)


def test_two_stores_on_one_file_cannot_both_win(tmp_path):
    """F-PR300-2: two processes. The second writer's check runs after the first's insert is visible or is refused by
    the write lock / the unique index; either way the table never holds two active rows."""
    path = tmp_path / "c.sqlite3"
    a, b = ContractStore(path), ContractStore(path)
    a.save(contract("FED-A"))
    with pytest.raises(ContractConflict):
        b.save(contract("FED-B"))
    # the window itself: a check that saw no row, then an insert, is stopped by the index
    with b._lock, b._conn, pytest.raises(sqlite3.IntegrityError):
        b._conn.execute(
            "INSERT INTO contracts (contract_id, counterparty_org, allowed_scopes, allowed_data_classes, active, org_key)"
            " VALUES ('FED-C', ?, '[]', '[]', 1, ?)", (ORG, normalise_org(ORG)))
    assert [c.contract_id for c in a.list()] == ["FED-A"]


def test_the_write_lock_is_taken_before_the_check(tmp_path):
    path = tmp_path / "c.sqlite3"
    a, b = ContractStore(path), ContractStore(path)
    with a._lock, a._conn:
        a._conn.execute("BEGIN IMMEDIATE")
        b._conn.execute("PRAGMA busy_timeout=0")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            b.save(contract("FED-B"))


def _old_database(path, rows):
    """A file as an earlier release left it: no org_key column, no index."""
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE contracts (contract_id TEXT PRIMARY KEY, counterparty_org TEXT NOT NULL, "
        "allowed_scopes TEXT NOT NULL, allowed_data_classes TEXT NOT NULL, contract_ref TEXT, pubkey TEXT, "
        "active INTEGER NOT NULL DEFAULT 1);")
    for cid, org in rows:
        con.execute("INSERT INTO contracts VALUES (?,?,?,?,NULL,NULL,1)", (cid, org, json.dumps(["s"]), json.dumps(["d"])))
    con.commit()
    con.close()


def test_an_old_database_is_upgraded_and_gets_the_index(tmp_path):
    path = tmp_path / "old.sqlite3"
    _old_database(path, [("FED-A", ORG)])
    store = ContractStore(path)
    assert store.for_org("borealis EXAMPLE corp").contract_id == "FED-A"
    with pytest.raises(ContractConflict):
        store.save(contract("FED-B"))


def test_an_old_database_with_duplicates_warns_at_open_and_at_lookup(tmp_path, caplog):
    path = tmp_path / "old.sqlite3"
    _old_database(path, [("FED-9", ORG), ("FED-10", "borealis example corp")])
    with caplog.at_level(logging.WARNING, logger="federation_broker.engine"):
        store = ContractStore(path)
    assert "more than one active contract" in caplog.text
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="federation_broker.engine"):
        assert store.for_org(ORG).contract_id == "FED-10"                 # lowest TEXT id, as the README says
    assert "holds 2 active contracts" in caplog.text and "FED-10" in caplog.text
    store.save(contract("FED-10", active=False))                          # deactivating still works (no index to trip)


def test_a_single_active_row_logs_nothing(tmp_path, caplog):
    store = ContractStore(tmp_path / "c.sqlite3")
    store.save(contract("FED-A"))
    with caplog.at_level(logging.WARNING, logger="federation_broker.engine"):
        store.for_org(ORG)
    assert caplog.text == ""
