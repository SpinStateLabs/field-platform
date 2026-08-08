"""Manifest model tests: the four shipped templates must parse; invariants hold."""

import pytest
from pydantic import ValidationError

from field_core.manifest import FieldManifest
from field_core.templates_api import TEMPLATE_NAMES, template_data


@pytest.mark.parametrize("name", TEMPLATE_NAMES)
def test_all_shipped_templates_parse(name):
    manifest = FieldManifest.from_dict(template_data(name))
    assert manifest.schema_version == "field.spinstatelabs.ca/v1"
    assert manifest.ledger.cryptographic_seal is True


def test_financial_template_specifics():
    m = FieldManifest.from_dict(template_data("financial-agent"))
    assert m.ledger.retention_days == 2555  # 7 years
    assert m.ledger.seal_algorithm == "ed25519-signed-chain"
    assert m.enforcement.spend_cap is not None
    assert m.enforcement.spend_cap.on_breach == "halt"
    assert m.runtime_protocol.preset == "audit"


def test_read_only_template_forbids_irreversible():
    m = FieldManifest.from_dict(template_data("read-only-agent"))
    assert m.enforcement.irreversible_action_policy == "forbid"
    assert m.identity.data_scope.may_transmit == []


def test_seal_false_rejected():
    data = template_data("default")
    data["ledger"]["cryptographic_seal"] = False
    with pytest.raises(ValidationError):
        FieldManifest.from_dict(data)


def test_seal_algorithm_none_rejected():
    data = template_data("default")
    data["ledger"]["seal_algorithm"] = "none"
    with pytest.raises(ValidationError):
        FieldManifest.from_dict(data)


def test_not_isolated_without_peers_rejected():
    data = template_data("default")
    data["federated"]["isolated"] = False
    data["federated"]["allowed_peers"] = []
    with pytest.raises(ValidationError):
        FieldManifest.from_dict(data)


def test_not_isolated_with_peer_accepted():
    data = template_data("default")
    data["federated"]["isolated"] = False
    data["federated"]["allowed_peers"] = [
        {"agent_id": "peer-1", "org": "CounterpartyCo", "trust_basis": "mTLS cert"}
    ]
    m = FieldManifest.from_dict(data)
    assert m.federated.allowed_peers[0].agent_id == "peer-1"


def test_unknown_top_level_key_rejected():
    data = template_data("default")
    data["surprise"] = {"x": 1}
    with pytest.raises(ValidationError):
        FieldManifest.from_dict(data)


def test_bad_expiry_format_rejected():
    data = template_data("default")
    data["delegation"]["expiry"] = "next year sometime"
    with pytest.raises(ValidationError):
        FieldManifest.from_dict(data)


def test_bad_preset_rejected():
    data = template_data("default")
    data["runtime_protocol"]["preset"] = "vibes"
    with pytest.raises(ValidationError):
        FieldManifest.from_dict(data)
