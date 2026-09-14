"""D5 — outbound crossings (our agent asks to cross into a counterparty org).

The mirror of the inbound sequence, run against OUR manifest: VALID
(``I.manifest``) → ``isolated is False`` (``F.isolated``) → counterparty in
OUR ``allowed_peers`` (``F.peer``) → the same contract, by counterparty org
→ scope and data class inside it. The signature step is SKIPPED outbound
(documented asymmetry). Every fixture here is synthetic: Borealis Example
Corp is a demo org and every key is generated per test.
"""

import pytest
from fastapi.testclient import TestClient

from federation_broker import engine as engine_mod
from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore, CrossingRequest
from field_core.clients import LedgerClient
from field_core.signing import generate_keypair, sign_manifest
from field_core.templates_api import template_data
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

HOME = "Spin State Labs"
COUNTERPARTY = "Borealis Example Corp"
OUR_AGENT = "invoicing-agent"
SCOPE = "exchange invoice status"
DATA_CLASS = "invoice metadata"


def our_manifest():
    """A VALID manifest for OUR agent that federates with the counterparty."""
    data = template_data("client-facing-agent")
    data["agent"]["name"] = OUR_AGENT
    data["identity"]["principal"] = "Controller, Spin State Labs (demo)"
    data["identity"]["org"] = HOME
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = "https://spinstate.example/kill"
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["enforcement"]["kill_switch"]["authorized_operators"] = ["Controller"]
    data["ledger"]["store"] = "sealed-ledger (demo)"
    data["delegation"]["granted_by"] = "Controller, Spin State Labs (demo)"
    data["delegation"]["scope"] = [SCOPE]
    data["delegation"]["revocation"] = {"method": "HTTP POST",
                                        "endpoint": "https://spinstate.example/revoke"}
    data["federated"] = {
        "isolated": False,
        "allowed_peers": [
            {"agent_id": "borealis-billing-agent", "org": COUNTERPARTY,
             "trust_basis": "federation contract FED-2026-001 (demo)"}
        ],
        "contracts": [
            {"peer": "borealis-billing-agent", "contract_ref": "FED-2026-001",
             "scope": SCOPE}
        ],
    }
    return data


def contract_body(**overrides):
    body = {"contract_id": "FED-2026-001", "counterparty_org": COUNTERPARTY,
            "allowed_scopes": [SCOPE], "allowed_data_classes": [DATA_CLASS],
            "contract_ref": "gc-vault/FED-2026-001 (demo)", "active": True}
    body.update(overrides)
    return body


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_ORG_NAME", HOME)
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    broker = TestClient(
        create_app(
            engine=BrokerEngine(
                store=ContractStore(tmp_path / "contracts.sqlite3"),
                ledger=LedgerClient(client=ledger, base_url="http://t"),
            )
        )
    )
    r = broker.put("/contracts/FED-2026-001", json=contract_body())
    assert r.status_code == 200, r.text
    return broker, ledger


def outbound(broker, manifest=None, **overrides):
    body = {
        "direction": "outbound",
        "counterparty_org": COUNTERPARTY,
        "agent_id": OUR_AGENT,
        "manifest": manifest if manifest is not None else our_manifest(),
        "scope": SCOPE,
        "data_class": DATA_CLASS,
    }
    body.update(overrides)
    return broker.post("/crossing", json=body)


def events(ledger, event_type):
    r = ledger.get("/events", params={"event_type": event_type})
    assert r.status_code == 200, r.text
    return r.json()


def test_outbound_in_contract_allowed_with_direction_in_context_and_ledger(stack):
    broker, ledger = stack
    r = outbound(broker, counterparty_agent_id="borealis-billing-agent")
    assert r.status_code == 200, r.text
    verdict = r.json()
    assert verdict["decision"] == "ALLOW"
    assert verdict["clause_id"] is None
    assert verdict["agent_id"] == f"{HOME}/{OUR_AGENT}"
    assert verdict["context"]["direction"] == "outbound"
    assert verdict["context"]["counterparty_org"] == COUNTERPARTY
    assert verdict["context"]["counterparty_agent_id"] == "borealis-billing-agent"
    assert "FED-2026-001" in verdict["reasons"][0]

    allows = events(ledger, "federation.allow")
    assert len(allows) == 1
    assert allows[0]["payload"]["direction"] == "outbound"
    assert allows[0]["payload"]["counterparty_org"] == COUNTERPARTY
    assert allows[0]["agent_id"] == f"{HOME}/{OUR_AGENT}"


def test_inbound_verdict_and_ledger_carry_direction_inbound(stack):
    """The default direction is inbound, and it is now in the ledger payload
    too (it was only in the verdict context before D5)."""
    broker, ledger = stack
    counterparty = our_manifest()
    counterparty["identity"]["org"] = COUNTERPARTY
    counterparty["federated"]["allowed_peers"] = [
        {"agent_id": OUR_AGENT, "org": HOME, "trust_basis": "FED-2026-001 (demo)"}
    ]
    r = broker.post("/crossing", json={
        "counterparty_org": COUNTERPARTY,
        "counterparty_agent_id": "borealis-billing-agent",
        "counterparty_manifest": counterparty,
        "scope": SCOPE, "data_class": DATA_CLASS,
    })
    verdict = r.json()
    assert verdict["decision"] == "ALLOW", verdict
    assert verdict["context"]["direction"] == "inbound"
    assert verdict["agent_id"] == f"{COUNTERPARTY}/borealis-billing-agent"
    assert events(ledger, "federation.allow")[0]["payload"]["direction"] == "inbound"


def test_outbound_isolated_blocked_f_isolated(stack):
    broker, ledger = stack
    manifest = our_manifest()
    manifest["federated"] = {"isolated": True, "allowed_peers": [], "contracts": []}
    verdict = outbound(broker, manifest=manifest).json()
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "F.isolated"
    assert events(ledger, "federation.block")[0]["payload"]["direction"] == "outbound"


def test_outbound_counterparty_not_in_our_peers_blocked_f_peer(stack):
    broker, _ = stack
    manifest = our_manifest()
    manifest["federated"]["allowed_peers"] = [
        {"agent_id": "other", "org": "Some Other Org", "trust_basis": "mTLS"}
    ]
    verdict = outbound(broker, manifest=manifest).json()
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "F.peer"
    assert "allowed peer" in verdict["reasons"][0]


def test_outbound_peer_rule_is_the_lenient_substring_rule(stack):
    """Same rule as the inbound home-org match: the counterparty org need only
    appear (case-insensitively) inside a peer's org string."""
    broker, _ = stack
    manifest = our_manifest()
    manifest["federated"]["allowed_peers"][0]["org"] = "BOREALIS EXAMPLE CORP (Canada)"
    assert outbound(broker, manifest=manifest).json()["decision"] == "ALLOW"


def test_outbound_no_contract_blocked(stack):
    broker, _ = stack
    manifest = our_manifest()
    manifest["federated"]["allowed_peers"][0]["org"] = "Unknown Org"
    verdict = outbound(broker, manifest=manifest, counterparty_org="Unknown Org").json()
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "F.peer"
    assert "no active federation contract" in verdict["reasons"][0]


def test_outbound_out_of_contract_scope_blocked(stack):
    broker, _ = stack
    verdict = outbound(broker, scope="pull full customer ledger").json()
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "F.peer"
    assert "allowed_scopes" in verdict["reasons"][0]


def test_outbound_out_of_contract_data_class_blocked(stack):
    broker, _ = stack
    verdict = outbound(broker, data_class="customer PII").json()
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "F.peer"
    assert "customer PII" in verdict["reasons"][0]


def test_adversarial_outbound_invalid_manifest_blocked_before_peer_read(stack, monkeypatch):
    """An unsealed-ledger manifest with a perfectly-formed peer entry: validity
    is checked FIRST, so neither the peer list nor the contract store is read."""
    broker, _ = stack

    def must_not_run(*a, **k):
        raise AssertionError("peer list / contract store read before validity")

    monkeypatch.setattr(engine_mod, "_lists_org", must_not_run)
    monkeypatch.setattr(broker.app.state.engine.store, "for_org", must_not_run)
    manifest = our_manifest()
    manifest["ledger"]["cryptographic_seal"] = False
    verdict = outbound(broker, manifest=manifest).json()
    assert verdict["decision"] == "BLOCK"
    assert verdict["clause_id"] == "I.manifest"
    assert verdict["reasons"][0].startswith("our manifest INVALID")


def test_outbound_keyed_contract_needs_no_signature_documented_asymmetry(stack):
    """A keyed contract refuses an UNSIGNED inbound crossing, but the same
    contract does not ask for a signature outbound: its key is the
    counterparty's and cannot verify our own manifest. The verdict says so."""
    broker, _ = stack
    _, public_pem = generate_keypair()
    r = broker.put("/contracts/FED-2026-001",
                   json=contract_body(counterparty_pubkey_pem=public_pem))
    assert r.status_code == 200, r.text

    verdict = outbound(broker).json()
    assert verdict["decision"] == "ALLOW"
    assert any("signature step skipped outbound" in x for x in verdict["reasons"])

    counterparty = our_manifest()
    counterparty["identity"]["org"] = COUNTERPARTY
    counterparty["federated"]["allowed_peers"][0]["org"] = HOME
    inbound = broker.post("/crossing", json={
        "counterparty_org": COUNTERPARTY, "counterparty_agent_id": "borealis-billing-agent",
        "counterparty_manifest": counterparty, "scope": SCOPE, "data_class": DATA_CLASS,
    }).json()
    assert inbound["decision"] == "BLOCK"
    assert "requires a signed manifest" in inbound["reasons"][0]


def test_outbound_refuses_a_signature_it_would_not_check(stack):
    """Accepting and silently ignoring a signature would let a caller believe it
    was verified. Outbound refuses the field (422)."""
    broker, _ = stack
    private_pem, _ = generate_keypair()
    manifest = our_manifest()
    r = outbound(broker, manifest=manifest,
                 manifest_signature=sign_manifest(manifest, private_pem))
    assert r.status_code == 422
    assert "manifest_signature not accepted on an outbound crossing" in r.text


@pytest.mark.parametrize(
    "body, needle",
    [
        # inbound (default) with the outbound names
        ({"counterparty_org": COUNTERPARTY, "agent_id": OUR_AGENT, "manifest": {},
          "scope": SCOPE, "data_class": DATA_CLASS},
         "an inbound crossing requires counterparty_agent_id, counterparty_manifest"),
        # inbound carrying an outbound name alongside the inbound ones
        ({"counterparty_org": COUNTERPARTY, "counterparty_agent_id": "b",
          "counterparty_manifest": {}, "manifest": {},
          "scope": SCOPE, "data_class": DATA_CLASS},
         "manifest not accepted on an inbound crossing"),
        # outbound missing our manifest
        ({"direction": "outbound", "counterparty_org": COUNTERPARTY,
          "agent_id": OUR_AGENT, "scope": SCOPE, "data_class": DATA_CLASS},
         "an outbound crossing requires manifest"),
        # outbound carrying the counterparty's manifest name
        ({"direction": "outbound", "counterparty_org": COUNTERPARTY,
          "agent_id": OUR_AGENT, "manifest": {}, "counterparty_manifest": {},
          "scope": SCOPE, "data_class": DATA_CLASS},
         "counterparty_manifest not accepted on an outbound crossing"),
        # unknown direction
        ({"direction": "sideways", "counterparty_org": COUNTERPARTY,
          "agent_id": OUR_AGENT, "manifest": {},
          "scope": SCOPE, "data_class": DATA_CLASS},
         "Input should be 'inbound' or 'outbound'"),
    ],
)
def test_request_names_must_match_the_direction(stack, body, needle):
    broker, ledger = stack
    r = broker.post("/crossing", json=body)
    assert r.status_code == 422, r.text
    assert needle in r.text
    assert events(ledger, "federation.allow") == []
    assert events(ledger, "federation.block") == []


def test_peer_rule_ignores_malformed_peer_entries_instead_of_crashing():
    """Validity is checked before the peer list, so a schema-valid manifest
    never reaches this with non-dict peers; the helper still answers False
    rather than raising if it ever does."""
    assert engine_mod._lists_org(["Borealis Example Corp", None, 7], COUNTERPARTY) is False
    assert engine_mod._lists_org("Borealis Example Corp", COUNTERPARTY) is False
    assert engine_mod._lists_org([{"org": "borealis example corp"}], COUNTERPARTY) is True


def test_outbound_dispatch_is_on_direction_not_on_field_presence():
    """Engine-level: an outbound request is never decided by the inbound path
    (which would read counterparty_manifest — None here)."""
    req = CrossingRequest(direction="outbound", counterparty_org=COUNTERPARTY,
                          agent_id=OUR_AGENT, manifest=our_manifest(),
                          scope=SCOPE, data_class=DATA_CLASS)

    class NoContracts:
        def for_org(self, org):
            return None

    verdict = BrokerEngine(store=NoContracts()).decide(req)
    assert verdict.decision.value == "BLOCK"
    assert verdict.context["direction"] == "outbound"
    assert verdict.agent_id.endswith(f"/{OUR_AGENT}")
