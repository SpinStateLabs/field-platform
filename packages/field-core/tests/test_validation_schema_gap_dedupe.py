"""S4-1: validate_manifest_data dropped schema violations with a SUBSTRING test (`prefix in gap`, the first path
segment against every critical-gap text, which grows inside the loop). So only the first violation under each
top-level section was reported, and a section whose name appeared inside another gap's wording lost every violation
(the kill-switch gap text contains 'agent', so every agent.* violation vanished). A violation is now skipped only when
a targeted rule already named that dotted path (or a path under it), or the identical line is already there.
Also: delegation.expiry passes the shape pattern for an impossible date (2026-13-45) yet `_parse_expiry` returns None
and nothing was reported; it now warns (a warning, not a critical gap: a critical gap flips the resolver verdict to
'invalid', which is the owner's decision)."""

from __future__ import annotations

from datetime import datetime, timezone

from field_core.templates_api import template_data
from field_core.validation import ValidationStatus, validate_manifest_data

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def resolved():
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
    data["delegation"]["scope"] = ["read timesheets"]
    data["delegation"]["expiry"] = "2027-06-30"
    data["delegation"]["revocation"] = {"method": "HTTP POST", "endpoint": "http://localhost:8003/tokens/{id}/revoke"}
    return data


def violations(result):
    return [g for g in result.critical_gaps if g.startswith("schema violation")]


def test_the_resolved_baseline_is_valid():
    assert validate_manifest_data(resolved(), now=NOW).status is ValidationStatus.VALID


def test_two_bad_fields_under_one_section_are_both_reported():
    data = resolved()
    data["enforcement"]["protected_paths"] = "not-a-list"                       # enforcement.protected_paths
    data["enforcement"]["kill_switch"]["sentinel_max_age_s"] = 0                # enforcement.kill_switch.sentinel_max_age_s
    result = validate_manifest_data(data, now=NOW)
    got = violations(result)
    assert any("enforcement.protected_paths" in g for g in got), got
    assert any("sentinel_max_age_s" in g for g in got), got
    assert result.status is ValidationStatus.INVALID


def test_an_agent_violation_and_a_missing_kill_switch_are_both_reported():
    data = resolved()
    data["agent"]["version"] = 7                                                # agent.version: not a string
    del data["enforcement"]["kill_switch"]
    result = validate_manifest_data(data, now=NOW)
    assert any("kill_switch" in g and not g.startswith("schema violation") for g in result.critical_gaps)
    assert any("agent.version" in g for g in violations(result)), result.critical_gaps


def test_a_violation_already_named_by_a_targeted_rule_is_not_repeated():
    data = resolved()
    del data["enforcement"]["kill_switch"]
    result = validate_manifest_data(data, now=NOW)
    named = [g for g in result.critical_gaps if "kill_switch" in g]
    assert len(named) == 1 and not named[0].startswith("schema violation"), named        # the targeted line only
    data = resolved()
    data["delegation"]["scope"] = []
    result = validate_manifest_data(data, now=NOW)
    assert [g for g in result.critical_gaps if "delegation.scope" in g and g.startswith("schema violation")] == []
    data = resolved()
    del data["ledger"]
    result = validate_manifest_data(data, now=NOW)
    assert [g for g in result.critical_gaps if g.startswith("schema violation") and g.split("—", 1)[1].strip().startswith("ledger")] == []


def test_every_distinct_schema_violation_in_one_section_is_listed_once():
    data = resolved()
    data["identity"]["jurisdiction"] = "PIPEDA"                                 # identity.jurisdiction
    data["identity"]["model_provider"] = 5                                      # identity.model_provider
    result = validate_manifest_data(data, now=NOW)
    got = violations(result)
    assert any("identity.jurisdiction" in g for g in got) and any("identity.model_provider" in g for g in got), got
    assert len(got) == len(set(got))


def test_status_and_blocking_verdict_are_unchanged_by_the_extra_lines():
    data = resolved()
    data["agent"]["version"] = 7
    assert validate_manifest_data(data, now=NOW).status is ValidationStatus.INVALID


# ---- impossible expiry --------------------------------------------------------------------------------------------


def test_an_impossible_expiry_date_warns_and_is_not_plain_valid():
    data = resolved()
    data["delegation"]["expiry"] = "2026-13-45"
    result = validate_manifest_data(data, now=NOW)
    assert result.status is ValidationStatus.VALID_WITH_WARNINGS, result.model_dump()
    assert result.critical_gaps == []
    assert any("delegation.expiry" in w and "2026-13-45" in w and "not a real" in w for w in result.warnings), result.warnings


def test_a_real_expiry_does_not_get_that_warning():
    for value in ("2027-06-30", "2027-06-30T12:00:00Z", "2024-02-29"):
        data = resolved()
        data["delegation"]["expiry"] = value
        assert not any("not a real" in w for w in validate_manifest_data(data, now=NOW).warnings), value


def test_a_past_and_a_near_term_expiry_still_warn_as_before():
    data = resolved()
    data["delegation"]["expiry"] = "2026-01-01"
    assert any("in the past" in w for w in validate_manifest_data(data, now=NOW).warnings)
    data["delegation"]["expiry"] = "2026-08-20"
    assert any("near-term" in w for w in validate_manifest_data(data, now=NOW).warnings)


def test_an_expiry_that_fails_the_shape_pattern_is_a_schema_violation_not_a_calendar_warning():
    data = resolved()
    data["delegation"]["expiry"] = "next tuesday"
    result = validate_manifest_data(data, now=NOW)
    assert result.status is ValidationStatus.INVALID
    assert any("delegation.expiry" in g for g in violations(result))
    assert not any("not a real" in w for w in result.warnings)


def test_a_violation_under_a_path_a_targeted_rule_named_is_not_repeated():
    data = resolved()
    data["enforcement"]["kill_switch"]["method"] = ""            # the targeted kill-switch rule fires...
    result = validate_manifest_data(data, now=NOW)
    assert any(g.startswith("enforcement.kill_switch (endpoint + method)") for g in result.critical_gaps)
    # ...and pydantic's enforcement.kill_switch.method line, UNDER that path, is not listed a second time
    assert not [g for g in violations(result) if "enforcement.kill_switch" in g], result.critical_gaps
