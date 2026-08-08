"""federation-broker tests: contract gating, manifest checks, adversarial."""

import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore
from field_core.clients import LedgerClient
from field_core.templates_api import template_data
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

COUNTERPARTY = "Borealis Example Corp"


def counterparty_manifest(**overrides):
    """A VALID manifest for the counterparty's agent that federates with us."""
    data = template_data("client-facing-agent")
    data["agent"]["name"] = "borealis-billing-agent"
    data["identity"]["principal"] = "VP Finance, Borealis (demo)"
    data["identity"]["org"] = COUNTERPARTY
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = "https://borealis.example/kill"
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["enforcement"]["kill_switch"]["authorized_operators"] = ["VP Finance"]
    data["ledger"]["store"] = "borealis WORM store (demo)"
    data["delegation"]["granted_by"] = "VP Finance, Borealis (demo)"
    data["delegation"]["scope"] = ["exchange invoice status"]
    data["delegation"]["revocation"] = {"method": "HTTP POST",
                                        "endpoint": "https://borealis.example/revoke"}
    data["federated"] = {
        "isolated": False,
        "allowed_peers": [
            {"agent_id": "invoicing-agent", "org": "Spin State Labs",
             "trust_basis": "federation contract FED-2026-001 (demo)"}
        ],
        "contracts": [
            {"peer": "invoicing-agent", "contract_ref": "FED-2026-001",
             "scope": "exchange invoice status"}
        ],
    }
    data.update(overrides)
    return data


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_ORG_NAME", "Spin State Labs")
    ledger_client = TestClient(
        create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl"))
    )
    broker = TestClient(
        create_app(
            engine=BrokerEngine(
                store=ContractStore(tmp_path / "contracts.sqlite3"),
                ledger=LedgerClient(client=ledger_client, base_url="http://t"),
            )
        )
    )
    broker.put(
        "/contracts/FED-2026-001",
        json={"contract_id": "FED-2026-001", "counterparty_org": COUNTERPARTY,
              "allowed_scopes": ["exchange invoice status"],
              "allowed_data_classes": ["invoice metadata"],
              "contract_ref": "gc-vault/FED-2026-001 (demo)", "active": True},
    )
    return broker, ledger_client


def crossing(broker, manifest=None, **overrides):
    body = {
        "counterparty_org": COUNTERPARTY,
        "counterparty_agent_id": "borealis-billing-agent",
        "counterparty_manifest": manifest or counterparty_manifest(),
        "scope": "exchange invoice status",
        "data_class": "invoice metadata",
    }
    body.update(overrides)
    return broker.post("/crossing", json=body)


def test_governed_crossing_allowed(stack):
    broker, ledger_client = stack
    verdict = crossing(broker).json()
    assert verdict["decision"] == "ALLOW"
    assert "FED-2026-001" in verdict["reasons"][0]

    events = ledger_client.get(
        "/events", params={"event_type": "federation.allow"}
    ).json()
    assert len(events) == 1
    assert events[0]["payload"]["counterparty_org"] == COUNTERPARTY


def test_isolated_counterparty_blocked(stack):
    broker, _ = stack
    manifest = counterparty_manifest()
    manifest["federated"] = {"isolated": True, "allowed_peers": [], "contracts": []}
    verdict = crossing(broker, manifest=manifest).json()
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "F.isolated"


def test_counterparty_not_naming_us_blocked(stack):
    broker, _ = stack
    manifest = counterparty_manifest()
    manifest["federated"]["allowed_peers"] = [
        {"agent_id": "other", "org": "Some Other Org", "trust_basis": "mTLS"}
    ]
    verdict = crossing(broker, manifest=manifest).json()
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "F.peer"


def test_no_contract_blocked(stack):
    broker, _ = stack
    manifest = counterparty_manifest()
    manifest["identity"]["org"] = "Unknown Org"
    verdict = crossing(
        broker, manifest=manifest, counterparty_org="Unknown Org"
    ).json()
    assert verdict["decision"] == "BLOCK"
    assert "no active federation contract" in verdict["reasons"][0]


def test_out_of_contract_scope_blocked(stack):
    broker, ledger_client = stack
    verdict = crossing(broker, scope="pull full customer ledger").json()
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "F.peer"
    blocks = ledger_client.get(
        "/events", params={"event_type": "federation.block"}
    ).json()
    assert len(blocks) == 1


def test_out_of_contract_data_class_blocked(stack):
    broker, _ = stack
    verdict = crossing(broker, data_class="customer PII").json()
    assert verdict["decision"] == "BLOCK"
    assert "customer PII" in verdict["reasons"][0]


def test_adversarial_invalid_manifest_blocked(stack):
    """Adversarial: counterparty presents a manifest with an unsealed ledger
    but a perfectly-formed peer declaration. Manifest validity is checked
    FIRST — the flattering peer entry never gets read."""
    broker, _ = stack
    manifest = counterparty_manifest()
    manifest["ledger"]["cryptographic_seal"] = False
    verdict = crossing(broker, manifest=manifest).json()
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "I.manifest"


# --- Manifest signing (hardening: authenticity, not just consistency) ---

from field_core.signing import generate_keypair, sign_manifest  # noqa: E402


def register_signed_contract(broker, public_pem):
    # Replaces the fixture contract (same id): one active contract per org.
    broker.put(
        "/contracts/FED-2026-001",
        json={"contract_id": "FED-2026-001", "counterparty_org": COUNTERPARTY,
              "allowed_scopes": ["exchange invoice status"],
              "allowed_data_classes": ["invoice metadata"],
              "counterparty_pubkey_pem": public_pem, "active": True},
    )


def test_signed_crossing_allowed(stack):
    broker, _ = stack
    private_pem, public_pem = generate_keypair()
    register_signed_contract(broker, public_pem)
    manifest = counterparty_manifest()
    verdict = crossing(
        broker, manifest=manifest,
        manifest_signature=sign_manifest(manifest, private_pem),
    ).json()
    assert verdict["decision"] == "ALLOW"


def test_adversarial_unsigned_crossing_blocked_when_key_registered(stack):
    broker, _ = stack
    _, public_pem = generate_keypair()
    register_signed_contract(broker, public_pem)
    verdict = crossing(broker).json()  # no signature presented
    assert verdict["decision"] == "BLOCK"
    assert "requires a signed manifest" in verdict["reasons"][0]


def test_adversarial_tampered_manifest_after_signing_blocked(stack):
    """Sign one manifest, present a quietly-broadened one."""
    broker, _ = stack
    private_pem, public_pem = generate_keypair()
    register_signed_contract(broker, public_pem)
    signed = counterparty_manifest()
    signature = sign_manifest(signed, private_pem)
    tampered = counterparty_manifest()
    tampered["delegation"]["scope"] = ["exchange invoice status",
                                      "pull full customer ledger"]
    verdict = crossing(broker, manifest=tampered, manifest_signature=signature).json()
    assert verdict["decision"] == "BLOCK"
    assert "signature invalid" in verdict["reasons"][0]


def test_adversarial_wrong_key_blocked(stack):
    broker, _ = stack
    _, public_pem = generate_keypair()          # registered key
    attacker_private, _ = generate_keypair()    # attacker signs with own key
    register_signed_contract(broker, public_pem)
    manifest = counterparty_manifest()
    verdict = crossing(
        broker, manifest=manifest,
        manifest_signature=sign_manifest(manifest, attacker_private),
    ).json()
    assert verdict["decision"] == "BLOCK"
    assert "signature invalid" in verdict["reasons"][0]


def test_keyless_contract_stays_compatible(stack):
    """Contracts without a registered key behave exactly as before."""
    broker, _ = stack
    assert crossing(broker).json()["decision"] == "ALLOW"
