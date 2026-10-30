"""C-470 (reviewer C-355 F-C355-2/-3): one active contract per counterparty org, the keyless guard before the scope
check, and a deterministic reading of legacy rows that hold two active contracts for one org."""

import sqlite3

import pytest

from federation_broker.engine import ContractStore
from test_federation_broker import COUNTERPARTY, counterparty_manifest, crossing, stack  # noqa: F401

BODY = {"counterparty_org": COUNTERPARTY, "allowed_scopes": ["exchange invoice status"],
        "allowed_data_classes": ["invoice metadata"], "contract_ref": "gc-vault/x (demo)", "active": True}


def put(broker, cid, **over):
    return broker.put(f"/contracts/{cid}", json={**BODY, "contract_id": cid, **over})


def pem():
    from field_core.signing import generate_keypair

    return generate_keypair()


# --- F-C355-2: one active contract per org ------------------------------------------------------------------


def test_a_second_active_contract_for_one_org_is_409_and_names_the_first(stack):
    broker, _ = stack
    r = put(broker, "FED-2026-002")
    assert r.status_code == 409 and "FED-2026-001" in r.json()["detail"]
    assert [c["contract_id"] for c in broker.get("/contracts").json()] == ["FED-2026-001"]


def test_a_keyless_contract_next_to_a_keyed_one_is_refused(stack):
    broker, _ = stack
    _, public = pem()
    assert put(broker, "FED-2026-001", counterparty_pubkey_pem=public).status_code == 200
    assert put(broker, "FED-2026-002").status_code == 409


def test_a_keyed_contract_next_to_a_keyless_one_is_refused(stack):
    broker, _ = stack
    _, public = pem()
    assert put(broker, "FED-2026-002", counterparty_pubkey_pem=public).status_code == 409


def test_replacing_a_contract_under_its_own_id_is_still_allowed(stack):
    broker, _ = stack
    assert put(broker, "FED-2026-001", contract_ref="gc-vault/new (demo)").status_code == 200
    assert broker.get("/contracts").json()[0]["contract_ref"] == "gc-vault/new (demo)"


def test_after_deactivating_the_first_a_second_active_contract_is_allowed(stack):
    broker, _ = stack
    assert put(broker, "FED-2026-001", active=False).status_code == 200
    assert put(broker, "FED-2026-002").status_code == 200


def test_a_second_contract_that_is_itself_inactive_is_allowed(stack):
    broker, _ = stack
    assert put(broker, "FED-2026-002", active=False).status_code == 200


def test_a_contract_for_another_org_is_allowed(stack):
    broker, _ = stack
    assert put(broker, "FED-2026-009", counterparty_org="Other Example Corp").status_code == 200


def test_the_refused_write_changes_nothing(stack):
    broker, _ = stack
    before = broker.get("/contracts").json()
    put(broker, "FED-2026-002", allowed_scopes=["everything"])
    assert broker.get("/contracts").json() == before


def _legacy_store(tmp_path, rows):
    """A database written before the rule: two ACTIVE rows for one org, inserted in the given order."""
    path = tmp_path / "legacy.sqlite3"
    store = ContractStore(path)
    conn = sqlite3.connect(str(path))
    for cid, pub in rows:
        conn.execute(
            "INSERT INTO contracts (contract_id, counterparty_org, allowed_scopes, allowed_data_classes, contract_ref, pubkey, active)"
            " VALUES (?,?,?,?,?,?,1)",
            (cid, COUNTERPARTY, '["exchange invoice status"]', '["invoice metadata"]', "ref", pub))
    conn.commit()
    conn.close()
    return store


@pytest.mark.parametrize("order", [("A-1", "B-2"), ("B-2", "A-1")])
def test_two_legacy_active_rows_resolve_to_the_lowest_contract_id_whatever_the_insert_order(tmp_path, order):
    _, public = pem()
    pubs = {"A-1": public, "B-2": None}
    store = _legacy_store(tmp_path, [(cid, pubs[cid]) for cid in order])
    assert store.for_org(COUNTERPARTY).contract_id == "A-1"


def test_a_legacy_keyless_row_that_sorts_first_blocks_inbound_even_with_a_keyed_row_beside_it(tmp_path):
    from field_core.clients import LedgerClient  # noqa: F401  (the engine needs a ledger only to record)
    from federation_broker.engine import BrokerEngine, CrossingRequest

    _, public = pem()
    store = _legacy_store(tmp_path, [("B-keyed", public), ("A-keyless", None)])
    assert store.for_org(COUNTERPARTY).contract_id == "A-keyless"
    engine = BrokerEngine(store=store, ledger=None)
    verdict = engine.decide(CrossingRequest(
        counterparty_org=COUNTERPARTY, counterparty_agent_id="borealis-billing-agent",
        counterparty_manifest=counterparty_manifest(), scope="exchange invoice status", data_class="invoice metadata"))
    assert verdict.decision.value == "BLOCK" and "require a contract key" in verdict.reasons[0]


# --- F-C355-3: the keyless guard comes before the scope check ----------------------------------------------------


@pytest.mark.parametrize("over", [{"scope": "something else"}, {"data_class": "customer PII"},
                                  {"scope": "something else", "data_class": "customer PII"}])
def test_a_keyless_contract_is_refused_for_its_missing_key_even_when_the_request_is_out_of_scope(stack, over):
    broker, _ = stack
    v = crossing(broker, **over).json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "F.peer"
    assert "require a contract key" in v["reasons"][0]


def test_a_keyed_contract_with_an_out_of_scope_request_is_refused_for_the_scope(stack):
    from field_core.signing import sign_manifest

    broker, _ = stack
    private_pem, public = pem()
    put(broker, "FED-2026-001", counterparty_pubkey_pem=public)
    manifest = counterparty_manifest()
    v = crossing(broker, manifest=manifest, manifest_signature=sign_manifest(manifest, private_pem),
                 data_class="customer PII").json()
    assert v["decision"] == "BLOCK" and "require a contract key" not in " ".join(v["reasons"])


# --- F-C355-4: the sequence demo.sh steps 2, 3 and 3b walk, as a test (the demo itself is not run in CI) ----------------


def test_the_demo_sequence_keyed_allow_over_reach_block_keyless_block_keyed_allow_again(stack):
    from field_core.signing import sign_manifest

    broker, _ = stack
    private_pem, public = pem()
    manifest = counterparty_manifest()
    sig = sign_manifest(manifest, private_pem)
    assert put(broker, "FED-2026-001", counterparty_pubkey_pem=public).status_code == 200
    ok = crossing(broker, manifest=manifest, manifest_signature=sig).json()
    assert ok["decision"] == "ALLOW"                                                      # step 2
    pii = crossing(broker, manifest=manifest, manifest_signature=sig, data_class="customer PII").json()
    assert pii["decision"] == "BLOCK" and pii["clause_id"] == "F.peer"                    # step 3
    assert put(broker, "FED-2026-001").status_code == 200                                 # 3b: same id, keyless
    keyless = crossing(broker, manifest=manifest, manifest_signature=sig).json()
    assert keyless["decision"] == "BLOCK" and "contract key" in " ".join(keyless["reasons"])
    assert put(broker, "FED-2026-001", counterparty_pubkey_pem=public).status_code == 200  # restored
    assert crossing(broker, manifest=manifest, manifest_signature=sig).json()["decision"] == "ALLOW"
