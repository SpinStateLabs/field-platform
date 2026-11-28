"""B3: FC-E-03, FC-F-01 and FC-L-02 rest on the manifest declaration. No run reports them evidenced, no headline
counts them as evidence or as gaps, and every report and pack names them as declared only."""
from __future__ import annotations

import pytest

from compliance_crosswalk.engine import (
    DECLARED_ONLY_DETAIL,
    DECLARED_ONLY_UNDECLARED,
    EvidenceSources,
    coverage_gaps,
    evaluate,
    render_markdown,
)
from compliance_crosswalk.evidence_pack import generate_pack
from field_core.templates_api import template_data

IDS = ["FC-E-03", "FC-F-01", "FC-L-02"]
SIGNER = "Controller, Spin State Labs"
FULL = EvidenceSources(
    registry_record={"owner": "Controller"},
    ledger_verify={"ok": True, "length": 9},
    ledger_event_types={"kill.drill.complete": 1, "delegation.revoke": 1, "conformance.escalate": 2,
                        "conformance.shadow_escalate": 3, "federation.allow": 1},
    tokens=[{"token_id": "t1", "revoked": True}],
    governor_cap={"cap": 10},
)


class _NoStale:
    def active(self):
        return []

    def status(self):
        return {"active": [], "corpus_version": "test"}


def declared_manifest():
    data = template_data("default")
    data.setdefault("enforcement", {})["irreversible_action_policy"] = "forbidden without a named human"
    data.setdefault("federated", {})["isolated"] = True
    data.setdefault("ledger", {})["retention_days"] = 365
    return data


def rows(report):
    return {c.control_id: c for c in report.controls}


@pytest.mark.parametrize("sources", [None, FULL, EvidenceSources(ledger_verify={"ok": True})],
                         ids=["offline", "everything", "ledger-only"])
def test_the_three_are_never_evidenced_and_never_a_gap_when_declared(sources):
    report = evaluate(declared_manifest(), agent_id="a", sources=sources)
    assert report.declared_only == IDS
    for cid in IDS:
        assert rows(report)[cid].declared and rows(report)[cid].evidenced is None, cid
    assert not [g for g in coverage_gaps(report) if g["control_id"] in IDS]
    assert report.evidenced_count == sum(1 for c in report.controls if c.evidenced is True and c.control_id not in IDS)


def test_the_detail_is_fixed_and_escalation_counts_are_information_only():
    full = rows(evaluate(declared_manifest(), agent_id="a", sources=FULL))
    assert full["FC-F-01"].evidence_detail == full["FC-L-02"].evidence_detail == DECLARED_ONLY_DETAIL
    assert full["FC-E-03"].evidence_detail == (
        "declared only; 2 enforced + 3 shadow (log-only) escalation event(s) observed; "
        "no evidence artifact shows the policy holds")
    unread = rows(evaluate(declared_manifest(), agent_id="a", sources=EvidenceSources(ledger_verify={"ok": True})))
    assert unread["FC-E-03"].evidence_detail == DECLARED_ONLY_DETAIL      # unread event counts are not printed as zero


def test_an_undeclared_one_is_a_not_declared_gap_and_is_not_called_declared_only():
    data = declared_manifest()
    del data["federated"]["isolated"]
    report = evaluate(data, agent_id="a", sources=FULL)
    assert report.declared_only == ["FC-E-03", "FC-L-02"]
    row = rows(report)["FC-F-01"]
    assert row.evidenced is None and row.evidence_detail == DECLARED_ONLY_UNDECLARED
    assert ("FC-F-01", "not-declared") in {(g["control_id"], g["kind"]) for g in coverage_gaps(report)}


def test_the_markdown_report_shows_declared_only_in_the_count_the_table_and_under_gaps():
    report = evaluate(declared_manifest(), agent_id="a", sources=FULL)
    md = render_markdown(report)
    assert "3/13 declared only" in md
    for cid in IDS:
        line = next(l for l in md.splitlines() if l.startswith(f"| {cid} |") and "declared only" in l)
        assert "| declared only |" in line and "| ✓ | declared only |" in line, cid
    assert "so it is neither evidenced nor a gap): FC-E-03, FC-F-01, FC-L-02." in md


def test_the_pack_shows_declared_only_in_the_table_the_json_and_beside_the_headline():
    md, payload = generate_pack(declared_manifest(), signer=SIGNER, stale_store=_NoStale(), agent_id="a",
                                sources=FULL)
    assert payload["declared_only"] == IDS
    for cid in IDS:
        assert any(l.startswith(f"| {cid} |") and l.endswith("| yes | declared-only |") for l in md.splitlines()), cid
        assert next(c for c in payload["controls"] if c["control_id"] == cid)["evidenced"] is None
        assert cid not in {g["control_id"] for g in payload["gaps"]}
    assert "so it is neither evidenced nor a gap): FC-E-03, FC-F-01, FC-L-02." in md


def test_a_callers_word_does_not_turn_a_declared_only_control_into_a_claim():
    md, payload = generate_pack(declared_manifest(), signer=SIGNER, stale_store=_NoStale(), caller_sources=FULL)
    assert payload["declared_only"] == IDS
    assert not [g for g in payload["gaps"] if g["control_id"] in IDS]
    for cid in IDS:
        assert any(l.startswith(f"| {cid} |") and l.endswith("| declared-only |") for l in md.splitlines()), cid
