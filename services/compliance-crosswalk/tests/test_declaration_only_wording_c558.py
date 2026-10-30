"""C-558 (Lane 10 C-542): the wording about the declaration-only controls FC-F-01 and FC-L-02 is true of the code.

Ledger retention (700301d) and the federation broker are built elsewhere in the platform; what is true of THIS service
is that its evidence sources carry neither, so both controls are evidenced as declaration-only. These tests pin the
facts the README and the mapping rest on: if evidence collection for either is ever added, the wording must be
revisited together with it. Nothing here claims compliance; the crosswalk never does.
"""
from __future__ import annotations

from pathlib import Path

from compliance_crosswalk.engine import EvidenceSources, evaluate
from compliance_crosswalk.mapping import CONTROLS

README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


def _control(control_id):
    return next(c for c in CONTROLS if c.control_id == control_id)


def test_the_evidence_sources_hold_no_federation_or_retention_field():
    fields = set(EvidenceSources.model_fields)
    assert not {f for f in fields if "federation" in f or "retention" in f}, fields


def test_both_controls_are_evidenced_as_declaration_only_even_with_every_source_present():
    sources = EvidenceSources(registry_record={"owner": "x"}, ledger_verify={"ok": True},
                              ledger_event_types={"federation.allow": 3, "federation.block": 1},
                              tokens=[], governor_cap={"limit": 1})
    report = evaluate({}, sources=sources)
    rows = {c.control_id: c for c in report.controls}
    for control_id in ("FC-F-01", "FC-L-02"):
        assert rows[control_id].evidence_detail == "declaration-only control in v0.1", control_id


def test_the_mapping_says_declaration_only_and_no_longer_says_enforcement_is_not_built():
    assert _control("FC-L-02").evidence_kind.startswith("manifest declaration only")
    assert _control("FC-F-01").evidence_kind.startswith("manifest declaration only")
    for control_id in ("FC-F-01", "FC-L-02"):
        kind = _control(control_id).evidence_kind
        assert "not built" not in kind and "+ federation-broker crossing events" not in kind


def test_the_readme_names_the_code_behind_the_statement_and_drops_the_stale_phrases():
    assert "no retention enforcement" not in README and "no federation events\n  until Phase 4" not in README
    for needle in ("`engine._evidenced`", "`EvidenceSources` has no federation or retention field",
                   "`GET /retention/check`", "`field_core.clients.LedgerClient.retention_check`",
                   "this crosswalk does not evidence it"):
        assert needle in README, needle
