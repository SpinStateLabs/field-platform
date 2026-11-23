"""S5-11: one stored contract row that cannot be rebuilt must not take down GET /contracts or a crossing.

list() shows it as a degraded INACTIVE entry (id visible, nothing allowed, no key); a crossing that resolves to it is
a ledgered BLOCK F.peer naming the id; other orgs' crossings are unaffected; it is never read as keyless or allowing."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from federation_broker.engine import (
    LIST_MAX, BrokerEngine, ContractStore, ContractUnreadable, NAME_MAX, UNREADABLE_MARK, _contract_from_row,
)
from field_core.clients import LedgerClient
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from test_federation_broker import COUNTERPARTY, counterparty_manifest
from test_federation_outbound import DATA_CLASS, OUR_AGENT, SCOPE, our_manifest

OTHER = "Other Example Corp"


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_ORG_NAME", "Spin State Labs")
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    store = ContractStore(tmp_path / "contracts.sqlite3")
    engine = BrokerEngine(store=store, ledger=LedgerClient(client=ledger, base_url="http://t"))
    return TestClient(create_app(engine=engine)), store, ledger


def row(store, contract_id, org=COUNTERPARTY, scopes=None, classes=None, key=None, active=1):
    scopes = json.dumps([SCOPE]) if scopes is None else scopes
    classes = json.dumps([DATA_CLASS]) if classes is None else classes
    with store._lock, store._conn:
        store._conn.execute(
            "INSERT INTO contracts (contract_id, counterparty_org, allowed_scopes, allowed_data_classes, contract_ref, "
            "pubkey, active) VALUES (?,?,?,?,?,?,?)", (contract_id, org, scopes, classes, None, key, active))


def inbound(client, org=COUNTERPARTY):
    return client.post("/crossing", json={
        "counterparty_org": org, "counterparty_agent_id": "borealis-billing-agent",
        "counterparty_manifest": counterparty_manifest(), "scope": SCOPE, "data_class": DATA_CLASS})


def outbound(client, org=COUNTERPARTY):
    return client.post("/crossing", json={
        "direction": "outbound", "counterparty_org": org, "agent_id": OUR_AGENT,
        "manifest": our_manifest(), "scope": SCOPE, "data_class": DATA_CLASS})


BAD = [
    pytest.param(dict(scopes="not json"), id="scopes-not-json"),
    pytest.param(dict(scopes="[]"), id="scopes-empty-list"),
    pytest.param(dict(scopes='{"a": 1}'), id="scopes-an-object"),
    pytest.param(dict(scopes='[1, 2]'), id="scopes-not-strings"),
    pytest.param(dict(classes="not json"), id="classes-not-json"),
    pytest.param(dict(classes="[]"), id="classes-empty-list"),
    pytest.param(dict(scopes="[" * 100_000), id="scopes-deeply-nested"),
]


@pytest.mark.parametrize("bad", BAD)
def test_get_contracts_is_200_and_names_the_bad_id_inactive(stack, bad):
    client, store, _ = stack
    row(store, "FED-GOOD", org=OTHER)
    row(store, "FED-BAD", **bad)
    r = client.get("/contracts")
    assert r.status_code == 200, r.text
    by = {c["contract_id"]: c for c in r.json()}
    assert set(by) == {"FED-BAD", "FED-GOOD"}
    assert by["FED-GOOD"]["allowed_scopes"] == [SCOPE] and by["FED-GOOD"]["active"] is True
    b = by["FED-BAD"]
    assert b["active"] is False and b["counterparty_pubkey_pem"] is None
    assert b["allowed_scopes"] == [UNREADABLE_MARK] and b["allowed_data_classes"] == [UNREADABLE_MARK]
    assert "re-register" in b["contract_ref"]


@pytest.mark.parametrize("bad", BAD)
@pytest.mark.parametrize("direction", ["inbound", "outbound"])
def test_a_crossing_on_the_bad_contract_is_a_ledgered_block_not_a_500(stack, bad, direction):
    client, store, ledger = stack
    row(store, "FED-BAD", **bad)
    r = (inbound if direction == "inbound" else outbound)(client)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "F.peer"
    assert "FED-BAD" in v["reasons"][0] and "unreadable" in v["reasons"][0] and "re-register" in v["reasons"][0]
    assert len(ledger.get("/events", params={"event_type": "federation.block"}).json()) == 1


def test_the_unreadable_row_is_never_keyless_or_allowing(stack):
    """A bad row with NO key must not reach the keyless branch (which would still block, but for the wrong reason),
    and must never ALLOW outbound (where a keyless contract is valid)."""
    client, store, _ = stack
    row(store, "FED-BAD", scopes="not json", key=None)
    for call in (inbound, outbound):
        v = call(client).json()
        assert v["decision"] == "BLOCK" and "holds no counterparty key" not in v["reasons"][0]


def test_other_orgs_are_unaffected(stack):
    """The bad row belongs to ANOTHER org: the counterparty's own crossing still ALLOWs, and GET /contracts lists both."""
    client, store, _ = stack
    row(store, "FED-BAD", org=OTHER, scopes="not json")
    row(store, "FED-OK")
    assert outbound(client).json()["decision"] == "ALLOW"
    assert client.get("/contracts").status_code == 200


def test_an_unreadable_winner_does_not_fall_through_to_a_readable_second_row(stack):
    client, store, _ = stack
    row(store, "FED-A", scopes="not json")           # sorts first: the row for_org resolves to
    row(store, "FED-B")
    assert outbound(client).json()["decision"] == "BLOCK"


@pytest.mark.parametrize("old_id,new_id", [("FED-OLD", "FED-NEW"), ("FED-A", "FED-Z")],
                         ids=["bad-sorts-last", "bad-sorts-first"])
def test_an_inactive_unreadable_row_does_not_block_the_orgs_active_contract(stack, old_id, new_id):
    """Order-independent: the inactive unreadable row sorts both after and before the active one, so only the
    ``active = 1`` filter (not the sort order) lets the crossing ALLOW."""
    client, store, _ = stack
    row(store, old_id, scopes="not json", active=0)
    row(store, new_id)
    assert outbound(client).json()["decision"] == "ALLOW"


@pytest.mark.parametrize("key", [
    "-----BEGIN PUBLIC KEY-----" + chr(10) + "MCowBQYDK2VwAyEAabc" + chr(10) + "-----END PUBLIC KEY-----" + chr(10),
    "-----BEGIN PRIVATE KEY-----" + chr(10) + "MC4CAQAwBQYDK2VwBCIEIsecretsecret" + chr(10) + "-----END PRIVATE KEY-----" + chr(10),
], ids=["public-key", "private-key"])
def test_the_degraded_entry_never_serves_a_stored_key(stack, key):
    """A bad row WITH a stored key is listed keyless: a regression to pubkey=row["pubkey"] would serve a public key
    and, for private-key material, bypass the WITHHELD_KEY protection."""
    client, store, _ = stack
    row(store, "FED-BAD", scopes="not json", key=key)
    r = client.get("/contracts")
    assert r.status_code == 200, r.text
    assert r.json()[0]["counterparty_pubkey_pem"] is None
    assert "secretsecret" not in r.text and "MCowBQYDK2VwAyEAabc" not in r.text


@pytest.mark.parametrize("which", ["id", "org", "both"])
def test_an_unreadable_legacy_row_with_an_over_long_id_or_org_lists_in_full_and_blocks(stack, which):
    """F1: a row stored before the NAME_MAX bound AND unreadable (bad JSON) must not make GET /contracts a 500 on
    current main. The degraded entry is built with the read model, so the long id / org is shown in full (never cut:
    a cut id is not the row's id and could equal another contract's), inactive, nothing allowed, no key."""
    client, store, _ = stack
    long_id = "I" * 300 if which in ("id", "both") else "FED-LONG"
    long_org = "O" * 300 if which in ("org", "both") else COUNTERPARTY
    row(store, long_id, org=long_org, scopes="not json")
    r = client.get("/contracts")
    assert r.status_code == 200, r.text
    (c,) = r.json()
    assert c["active"] is False and c["allowed_scopes"] == [UNREADABLE_MARK] and c["counterparty_pubkey_pem"] is None
    assert c["contract_id"] == long_id and c["counterparty_org"] == long_org
    if which == "id":
        # a crossing for the unreadable row's org is a ledgered BLOCK, never a 500 and never an ALLOW
        v = outbound(client).json()
        assert v["decision"] == "BLOCK" and v["clause_id"] == "F.peer"


def test_a_readable_legacy_row_with_an_over_long_id_lists_in_full_and_still_works(stack):
    """B12 (ported from PR 1299): a well-formed legacy row with a long id is read with the read model: listed whole,
    active, and its crossings decided as before (not degraded)."""
    client, store, _ = stack
    long_id = "I" * (NAME_MAX + 44)
    row(store, long_id)
    (c,) = client.get("/contracts").json()
    assert c["contract_id"] == long_id and c["active"] is True and c["allowed_scopes"] == [SCOPE]
    assert outbound(client).json()["decision"] == "ALLOW"


def test_store_for_org_raises_and_from_row_raises_a_named_error(stack):
    _, store, _ = stack
    row(store, "FED-BAD", scopes="not json")
    with pytest.raises(ContractUnreadable) as e:
        store.for_org(COUNTERPARTY)
    assert e.value.contract_id == "FED-BAD"
    with store._lock:
        r = store._conn.execute("SELECT * FROM contracts").fetchone()
    with pytest.raises(ContractUnreadable):
        _contract_from_row(r)


def test_the_degraded_entry_for_a_blank_id_and_org_still_serves(stack):
    client, store, _ = stack
    row(store, "", org=" ", scopes="not json")
    r = client.get("/contracts")
    assert r.status_code == 200 and r.json()[0]["contract_id"] == "(unreadable)"


def test_a_readable_store_is_unchanged(stack):
    client, store, _ = stack
    row(store, "FED-1")
    assert [c["allowed_scopes"] for c in client.get("/contracts").json()] == [[SCOPE]]
    assert outbound(client).json()["decision"] == "ALLOW"


# ---- PENDING DON'S RULING: the read model drops LIST_MAX -------------------------------------------------------------
# StoredFederationContract (B12) lifts the list-length caps on read as well as the name-length caps, so a legacy row
# stored before LIST_MAX existed with more than LIST_MAX scopes (or data classes) lists AND its crossings are decided as
# before (ALLOW when in scope). Writes keep the cap. Don is deciding whether reads should keep that; this test pins the
# CURRENT behaviour so the ruling is one visible flip: if reads must refuse it, invert the two ALLOW/list assertions
# (expect the degraded inactive entry and a BLOCK F.peer) and restore max_length=LIST_MAX on the read model.

def test_PENDING_RULING_a_stored_row_with_more_than_LIST_MAX_scopes_lists_and_allows(stack):
    client, store, _ = stack
    assert LIST_MAX == 100
    scopes = [SCOPE] + [f"extra-scope-{i}" for i in range(LIST_MAX)]          # LIST_MAX + 1 entries
    classes = [DATA_CLASS] + [f"extra-class-{i}" for i in range(LIST_MAX)]
    row(store, "FED-WIDE", scopes=json.dumps(scopes), classes=json.dumps(classes))
    r = client.get("/contracts")
    assert r.status_code == 200, r.text
    (c,) = r.json()
    assert c["active"] is True and len(c["allowed_scopes"]) == LIST_MAX + 1 and len(c["allowed_data_classes"]) == LIST_MAX + 1
    assert outbound(client).json()["decision"] == "ALLOW"


def test_a_write_with_more_than_LIST_MAX_scopes_is_still_refused(stack):
    client, _, _ = stack
    body = {"contract_id": "FED-WIDE", "counterparty_org": COUNTERPARTY,
            "allowed_scopes": [SCOPE] + [f"extra-scope-{i}" for i in range(LIST_MAX)],
            "allowed_data_classes": [DATA_CLASS], "active": True}
    assert client.put("/contracts/FED-WIDE", json=body).status_code == 422
    assert client.get("/contracts").json() == []

