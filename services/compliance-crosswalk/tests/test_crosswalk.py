"""compliance-crosswalk tests — incl. the anti-fabrication guard."""

from fastapi.testclient import TestClient

from compliance_crosswalk.api import create_app
from compliance_crosswalk.engine import EvidenceSources, evaluate, render_markdown
from compliance_crosswalk.mapping import CONTROLS, FRAMEWORKS, TODO_CITATION
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


def test_adversarial_no_fabricated_citations():
    """THE guard: every citation in every control for every framework must be
    the TODO stub until official texts are ingested. A real-looking citation
    appearing here means someone fabricated regulation references."""
    for control in CONTROLS:
        assert set(control.citations.keys()) == set(FRAMEWORKS.keys())
        for framework, citation in control.citations.items():
            assert citation == TODO_CITATION, (
                f"{control.control_id}/{framework} carries citation "
                f"{citation!r} — citations must stay TODO until ingestion"
            )


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
    assert TODO_CITATION in md
    assert "have not been ingested" in md


def test_api_roundtrip():
    client = TestClient(create_app())
    assert client.get("/frameworks").json() == FRAMEWORKS
    r = client.post("/crosswalk", json={"manifest": resolved_manifest()})
    assert r.status_code == 200
    assert r.json()["manifest_valid"] is True
