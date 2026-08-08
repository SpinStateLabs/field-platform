"""``field validate`` parity tests against the vendored plugin schema."""

import json
from datetime import datetime, timezone

from field_core.manifest import SEAL_ALGORITHMS
from field_core.templates_api import schema_json, template_data
from field_core.validation import (
    ValidationStatus,
    render_validation_report,
    validate_manifest_data,
)

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def test_vendored_schema_agrees_on_seal_algorithms():
    schema = json.loads(schema_json())
    schema_algos = tuple(
        schema["properties"]["ledger"]["properties"]["seal_algorithm"]["enum"]
    )
    assert schema_algos == SEAL_ALGORITHMS
    assert "none" not in schema_algos


def test_vendored_schema_seal_is_const_true():
    schema = json.loads(schema_json())
    seal = schema["properties"]["ledger"]["properties"]["cryptographic_seal"]
    assert seal["const"] is True


def test_template_validates_with_placeholder_warnings():
    result = validate_manifest_data(template_data("default"), now=NOW)
    assert result.status is ValidationStatus.VALID_WITH_WARNINGS
    assert result.critical_gaps == []
    assert any("REPLACE-ME" in w for w in result.warnings)


def test_fully_resolved_manifest_is_valid():
    data = template_data("default")
    data["agent"]["name"] = "invoicing-agent"
    data["agent"]["description"] = "Drafts invoices from timesheets"
    data["identity"]["principal"] = "Controller, Spin State Labs"
    data["identity"]["org"] = "Spin State Labs"
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = "http://localhost:8005/kill/invoicing-agent"
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["ledger"]["store"] = "hash-chained JSONL (sealed-ledger service)"
    data["delegation"]["granted_by"] = "Controller, Spin State Labs"
    data["delegation"]["scope"] = ["read timesheets", "draft invoices"]
    data["delegation"]["expiry"] = "2027-06-30"
    data["delegation"]["revocation"] = {
        "method": "HTTP POST",
        "endpoint": "http://localhost:8003/tokens/{id}/revoke",
    }
    result = validate_manifest_data(data, now=NOW)
    assert result.status is ValidationStatus.VALID, result.model_dump()


def test_missing_kill_switch_is_critical_gap():
    data = template_data("default")
    del data["enforcement"]["kill_switch"]
    result = validate_manifest_data(data, now=NOW)
    assert result.status is ValidationStatus.INVALID
    assert any("kill_switch" in g for g in result.critical_gaps)


def test_missing_grantor_is_critical_gap():
    data = template_data("default")
    del data["delegation"]["granted_by"]
    result = validate_manifest_data(data, now=NOW)
    assert result.status is ValidationStatus.INVALID
    assert any("granted_by" in g for g in result.critical_gaps)


def test_unsealed_ledger_is_critical_gap():
    data = template_data("default")
    data["ledger"]["cryptographic_seal"] = False
    result = validate_manifest_data(data, now=NOW)
    assert result.status is ValidationStatus.INVALID
    assert any("cryptographic_seal" in g for g in result.critical_gaps)


def test_seal_algorithm_none_is_critical_gap():
    data = template_data("default")
    data["ledger"]["seal_algorithm"] = "none"
    result = validate_manifest_data(data, now=NOW)
    assert result.status is ValidationStatus.INVALID
    assert any("seal_algorithm" in g for g in result.critical_gaps)


def test_missing_section_reported_not_crashed():
    data = template_data("default")
    del data["ledger"]
    result = validate_manifest_data(data, now=NOW)
    assert result.status is ValidationStatus.INVALID
    assert result.sections_present["ledger"] is False
    assert any("'ledger' is missing" in g for g in result.critical_gaps)


def test_past_expiry_warns_but_does_not_block():
    data = template_data("default")
    data["delegation"]["expiry"] = "2020-01-01"
    result = validate_manifest_data(data, now=NOW)
    assert result.status is ValidationStatus.VALID_WITH_WARNINGS
    assert any("in the past" in w for w in result.warnings)


def test_near_term_expiry_warns():
    data = template_data("default")
    data["delegation"]["expiry"] = "2026-08-20"  # 12 days from NOW
    result = validate_manifest_data(data, now=NOW)
    assert any("near-term" in w for w in result.warnings)


def test_missing_runtime_protocol_warns():
    data = template_data("default")
    del data["runtime_protocol"]
    result = validate_manifest_data(data, now=NOW)
    assert any("runtime_protocol absent" in w for w in result.warnings)


def test_report_renders_skill_format():
    result = validate_manifest_data(template_data("default"), now=NOW)
    report = render_validation_report(result)
    assert "FIELD manifest validation" in report
    assert "Status: VALID_WITH_WARNINGS" in report
    assert "Critical gaps (blocking):" in report
    assert "Runtime protocol: FORCE — preset analysis" in report


def test_adversarial_garbage_manifest_reports_all_gaps():
    """Adversarial: near-empty dict must produce a gap report, not a crash."""
    result = validate_manifest_data({"schema_version": "wrong/v9"}, now=NOW)
    assert result.status is ValidationStatus.INVALID
    assert all(not present for present in result.sections_present.values())
    # every one of the five sections is called out
    for section in ("federated", "identity", "enforcement", "ledger", "delegation"):
        assert any(section in g for g in result.critical_gaps)
