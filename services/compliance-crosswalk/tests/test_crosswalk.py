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
    # the Claude Code Enforcement Gate keys FC-E-04..06 read (ADR-0074)
    data["enforcement"]["irreversible_actions"] = {"deny_patterns": [r"\brm\s+-rf\b"]}
    data["enforcement"]["protected_paths"] = [r"\.env$"]
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


GATE_IDS = ("FC-E-04", "FC-E-05", "FC-E-06")
GATE_NOTE = "declared, enforced locally by the Claude Code gate, no estate evidence"


def _by_id(report):
    return {c.control_id: c for c in report.controls}


def test_gate_controls_exist_with_honest_citations():
    """ADR-0074: three declaration-only controls for the keys the gate enforces."""
    by_id = {c.control_id: c for c in CONTROLS}
    assert [c for c in by_id if c.startswith("FC-E-")] == ["FC-E-01", "FC-E-02", "FC-E-03", *GATE_IDS]
    assert by_id["FC-E-04"].manifest_path == "enforcement.irreversible_actions"
    assert by_id["FC-E-05"].manifest_path == "enforcement.protected_paths"
    assert by_id["FC-E-06"].manifest_path == "enforcement.rate_limits"
    for cid in GATE_IDS:
        assert by_id[cid].letter == "E"
        assert by_id[cid].citations["iso-42001"].status == "pending-purchase"
    # only already-verified text may be cited: EU Art. 14 para 1 as a PARTIAL mapping on FC-E-04
    cited = {(cid, fw) for cid in GATE_IDS for fw, c in by_id[cid].citations.items() if c.status == "cited"}
    assert cited == {("FC-E-04", "eu-ai-act")}
    eu = by_id["FC-E-04"].citations["eu-ai-act"]
    assert "Article 14" in eu.reference and "partial" in (eu.note or "")
    assert eu.source_url == by_id["FC-E-03"].citations["eu-ai-act"].source_url


def test_gate_controls_declared_from_gate_keys():
    by_id = _by_id(evaluate(resolved_manifest()))
    for cid in GATE_IDS:
        assert by_id[cid].declared, cid
    # absent / empty keys are not a declaration
    bare = resolved_manifest()
    del bare["enforcement"]["irreversible_actions"]
    del bare["enforcement"]["protected_paths"]
    bare["enforcement"]["rate_limits"] = [{"action": "send_email", "max": 5, "period": "hour"}]
    by_id = _by_id(evaluate(bare))
    assert not by_id["FC-E-04"].declared and not by_id["FC-E-05"].declared and not by_id["FC-E-06"].declared
    empty = resolved_manifest()
    empty["enforcement"]["irreversible_actions"] = {"deny_patterns": []}
    assert not _by_id(evaluate(empty))["FC-E-04"].declared
    e5_only = resolved_manifest()
    e5_only["enforcement"]["irreversible_actions"] = {"deny_patterns": [], "session_written_exec": "deny"}
    assert _by_id(evaluate(e5_only))["FC-E-04"].declared
    wrong_period = resolved_manifest()
    wrong_period["enforcement"]["rate_limits"] = [{"action": "tool_call", "max": 5, "period": "hour"}]
    assert not _by_id(evaluate(wrong_period))["FC-E-06"].declared


def test_gate_controls_never_claim_estate_evidence():
    """A declaration is not evidence of enforcement: evidenced stays None (not True, not False),
    offline or with every estate artifact present, and the detail says so."""
    offline = _by_id(evaluate(resolved_manifest()))
    sources = EvidenceSources(
        registry_record={"agent_id": "a", "owner": "AP Team Lead"},
        ledger_verify={"ok": True, "length": 10},
        ledger_event_types={"kill.drill.complete": 1, "delegation.revoke": 1},
        tokens=[{"token_id": "t", "revoked": True}],
        governor_cap={"agent_id": "a", "limit_cents": 50000},
    )
    live_report = evaluate(resolved_manifest(), agent_id="a", sources=sources)
    live = _by_id(live_report)
    for cid in GATE_IDS:
        assert offline[cid].evidenced is None and live[cid].evidenced is None, cid
        assert GATE_NOTE in offline[cid].evidence_detail and GATE_NOTE in live[cid].evidence_detail
    # the evidenced count is the pre-existing controls only
    assert live_report.evidenced_count == sum(1 for c in live_report.controls if c.evidenced) == 10


def test_gate_controls_add_no_evidence_pack_gap_when_declared():
    report = evaluate(resolved_manifest(), agent_id="a", sources=EvidenceSources(ledger_verify={"ok": True, "length": 1}))
    assert not [c for c in report.controls if c.control_id in GATE_IDS and c.evidenced is False]


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
