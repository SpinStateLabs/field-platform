"""compliance-crosswalk tests — incl. the anti-fabrication guard."""

from fastapi.testclient import TestClient

from compliance_crosswalk.api import create_app
from compliance_crosswalk.engine import EvidenceSources, evaluate, render_markdown
from compliance_crosswalk.mapping import CONTROLS, FRAMEWORKS, INGESTION_LOG
from field_core.templates_api import template_data


def resolved_manifest():
    data = template_data("financial-agent")
    data["agent"]["name"] = "invoicing-agent"
    data["identity"]["principal"] = "Controller, Spin State Labs"
    data["identity"]["org"] = "Spin State Labs"
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = "http://127.0.0.1:8005/kill/x"
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["enforcement"]["kill_switch"]["authorized_operators"] = ["Controller"]
    data["ledger"]["store"] = "sealed-ledger service"
    data["delegation"]["granted_by"] = "Controller, Spin State Labs"
    data["delegation"]["revocation"] = {"method": "HTTP POST", "endpoint": "http://x"}
    return data


def test_adversarial_no_ungrounded_citations():
    """THE guard, post-ingestion form: a citation may exist ONLY with a
    verified reference + source URL + retrieval date; pending entries must
    carry NO reference (a reference without a source is a fabrication).
    ISO/IEC 42001 must remain pending-purchase until the text is bought."""
    for control in CONTROLS:
        assert set(control.citations.keys()) == set(FRAMEWORKS.keys())
        for framework, citation in control.citations.items():
            where = f"{control.control_id}/{framework}"
            if citation.status == "cited":
                assert citation.reference and citation.source_url and \
                    citation.retrieved, f"{where}: cited but not grounded"
            else:
                assert citation.reference is None, (
                    f"{where}: {citation.status} entry carries a reference — "
                    "that is an ungrounded citation"
                )
            if framework == "iso-42001":
                assert citation.status == "pending-purchase", (
                    f"{where}: ISO 42001 text has not been purchased; "
                    "it can never be 'cited' from memory"
                )


def test_ingestion_log_covers_all_cited_frameworks():
    logged = {entry["framework"] for entry in INGESTION_LOG}
    cited = {
        framework
        for control in CONTROLS
        for framework, citation in control.citations.items()
        if citation.status == "cited"
    }
    assert cited <= logged, "cited framework missing from INGESTION_LOG"


def test_kill_switch_control_carries_stop_button_citations():
    """FC-E-01 is the flagship mapping: EU stop button + NIST MANAGE 2.4."""
    fc_e01 = next(c for c in CONTROLS if c.control_id == "FC-E-01")
    assert "stop" in fc_e01.citations["eu-ai-act"].reference.lower()
    assert "MANAGE 2.4" in fc_e01.citations["nist-ai-rmf"].reference


def test_coverage_declared_only():
    report = evaluate(resolved_manifest(), agent_id=None, sources=None)
    assert report.manifest_valid
    assert report.evidence_collected is False
    assert report.declared_count == len(CONTROLS)
    for c in report.controls:
        assert c.evidenced is None


def test_placeholder_manifest_shows_gaps():
    report = evaluate(template_data("default"))
    gaps = {c.control_id for c in report.controls if not c.declared}
    assert "FC-I-01" in gaps  # principal is REPLACE-ME in the raw template
    assert "FC-E-01" in gaps  # kill switch endpoint is REPLACE-ME
    assert "FC-E-02" in gaps  # default template has no spend_cap


def test_evidence_changes_verdicts():
    sources = EvidenceSources(
        registry_record={"agent_id": "a", "owner": "AP Team Lead"},
        ledger_verify={"ok": True, "length": 10},
        ledger_event_types={"kill.drill.complete": 1, "delegation.revoke": 1},
        tokens=[{"token_id": "t", "revoked": True}],
        governor_cap={"agent_id": "a", "limit_cents": 50000},
    )
    report = evaluate(resolved_manifest(), agent_id="a", sources=sources)
    by_id = {c.control_id: c for c in report.controls}
    assert by_id["FC-L-01"].evidenced is True
    assert by_id["FC-E-01"].evidenced is True
    assert by_id["FC-E-02"].evidenced is True
    assert by_id["FC-D-01"].evidenced is True
    assert by_id["FC-D-02"].evidenced is True
    assert by_id["FC-R-01"].evidenced is True


def test_shadow_escalations_evidence_fc_e_03_distinctly():
    """S2-R: a log-only estate writes conformance.shadow_escalate, not
    conformance.escalate. FC-E-03's evidence counts both but keeps them
    labeled apart — a shadow escalate proves the trigger fires, not that a
    human was actually paused."""
    sources = EvidenceSources(
        ledger_verify={"ok": True, "length": 5},
        ledger_event_types={"conformance.shadow_escalate": 2},
    )
    report = evaluate(resolved_manifest(), agent_id="a", sources=sources)
    fc_e03 = next(c for c in report.controls if c.control_id == "FC-E-03")
    assert "0 enforced + 2 shadow (log-only)" in fc_e03.evidence_detail


def test_broken_ledger_fails_evidence():
    sources = EvidenceSources(
        ledger_verify={"ok": False, "reason": "hash mismatch at index 2"},
    )
    report = evaluate(resolved_manifest(), agent_id="a", sources=sources)
    fc_l01 = next(c for c in report.controls if c.control_id == "FC-L-01")
    assert fc_l01.evidenced is False
    assert "hash mismatch" in fc_l01.evidence_detail


def test_markdown_report_carries_citation_status():
    md = render_markdown(evaluate(resolved_manifest()))
    assert "Citation status" in md
    assert "source-grounded" in md
    assert "pending-purchase" in md            # ISO column stays honest
    assert "Article 12 (Record-Keeping)" in md  # a real, verified citation
    assert "MANAGE 2.4" in md


def test_api_roundtrip():
    client = TestClient(create_app())
    assert client.get("/frameworks").json() == FRAMEWORKS
    r = client.post("/crosswalk", json={"manifest": resolved_manifest()})
    assert r.status_code == 200
    assert r.json()["manifest_valid"] is True
