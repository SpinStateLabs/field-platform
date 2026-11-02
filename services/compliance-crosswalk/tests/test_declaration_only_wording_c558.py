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
FLAT = " ".join(README.split())     # line breaks in the README are not part of the wording


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
    assert "no retention enforcement" not in FLAT and "no federation events until Phase 4" not in FLAT
    assert "The enforcement exists in the platform" not in FLAT          # no assurance word (C-612 F-C612-1)
    for needle in ("`engine._evidenced`", '"declaration-only control in v0.1"',
                   "`EvidenceSources` has no federation or retention field",
                   "`GET /retention/check`", "`field_core.clients.LedgerClient.retention_check`",
                   "The ledger has retention rotation, apply and check built",
                   "`POST /rotate`", "`POST /retention/apply`", "this crosswalk does not evidence it"):
        assert needle in FLAT, needle


def test_the_string_the_readme_quotes_is_the_one_the_engine_returns():
    engine_src = (Path(__file__).resolve().parents[1] / "src" / "compliance_crosswalk" / "engine.py").read_text(encoding="utf-8")
    assert 'return True, "declaration-only control in v0.1"' in engine_src
    assert 'returns "declaration-only control in v0.1" for both' in FLAT


def test_the_ledger_routes_the_readme_names_exist_in_the_sealed_ledger_source():
    api = (Path(__file__).resolve().parents[2] / "sealed-ledger" / "src" / "sealed_ledger" / "api.py").read_text(encoding="utf-8")
    for route in ('@app.post("/rotate"', '@app.post("/retention/apply"', '@app.get("/retention/check"'):
        assert route in api, route
