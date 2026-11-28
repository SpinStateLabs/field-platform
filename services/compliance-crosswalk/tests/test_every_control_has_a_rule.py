"""Every crosswalk control is evaluated by a rule of its own. A control id that no rule names reads as such, never as
"declared only" or as evidenced, so a control added to the matrix without a rule cannot pass unnoticed."""
from __future__ import annotations

import pytest

from compliance_crosswalk.engine import (
    DECLARED_ONLY_CONTROL_IDS,
    DECLARED_ONLY_DETAIL,
    NO_EVIDENCE_RULE,
    EvidenceSources,
    _evidenced,
    evaluate,
)
from compliance_crosswalk.mapping import CONTROLS
from field_core.templates_api import template_data

FULL = EvidenceSources(
    registry_record={"owner": "Controller"},
    ledger_verify={"ok": True, "length": 9},
    ledger_event_types={"kill.drill.complete": 1, "delegation.revoke": 1, "conformance.escalate": 2},
    tokens=[{"token_id": "t1", "revoked": True}],
    governor_cap={"cap": 10},
)
EMPTY_ANSWERS = EvidenceSources(registry_record=None, ledger_verify={"ok": False, "reason": "x"},
                                ledger_event_types={}, tokens=[], governor_cap=None)


@pytest.mark.parametrize("sources", [FULL, EMPTY_ANSWERS], ids=["full", "empty-answers"])
@pytest.mark.parametrize("control", CONTROLS, ids=lambda c: c.control_id)
def test_every_control_has_a_rule(control, sources):
    _, detail = _evidenced(control, sources, "agent-1")
    assert detail != NO_EVIDENCE_RULE, control.control_id


@pytest.mark.parametrize("control", CONTROLS, ids=lambda c: c.control_id)
def test_only_the_declared_only_controls_read_declared_only(control):
    _, detail = _evidenced(control, FULL, "agent-1")
    assert (detail == DECLARED_ONLY_DETAIL) == (control.control_id in DECLARED_ONLY_CONTROL_IDS
                                                and control.control_id != "FC-E-03"), control.control_id


def test_an_unknown_control_id_is_never_evidenced_and_says_no_rule_exists():
    unknown = CONTROLS[0].model_copy(update={"control_id": "FC-X-99"})
    for sources in (FULL, EMPTY_ANSWERS):
        evidenced, detail = _evidenced(unknown, sources, "agent-1")
        assert evidenced is None and detail == NO_EVIDENCE_RULE


def test_no_report_row_carries_the_no_rule_detail():
    report = evaluate(template_data("default"), agent_id="agent-1", sources=FULL)
    assert [c.control_id for c in report.controls if c.evidence_detail == NO_EVIDENCE_RULE] == []
