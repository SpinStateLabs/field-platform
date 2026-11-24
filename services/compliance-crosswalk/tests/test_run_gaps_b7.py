"""B7 (roley.reviewer 1181 C2): ``crosswalk run --agent-id`` shows an unanswered /verify as "✗" (not verified), never
the "—" of an offline run, and its Markdown carries a Gaps section: the same list the evidence pack prints.
"""

from __future__ import annotations

import yaml
from typer.testing import CliRunner

from compliance_crosswalk import api as api_module
from compliance_crosswalk.cli import app
from compliance_crosswalk.engine import (
    GAP_LABELS,
    LEDGER_NOT_CHECKED_GAP,
    EvidenceSources,
    coverage_gaps,
    evaluate,
    render_markdown,
)
from test_crosswalk import resolved_manifest

runner = CliRunner()
COLLECTED = dict(registry_record={"agent_id": "a", "owner": "AP Team Lead"},
                 ledger_event_types={"kill.drill.complete": 1})


def _md(sources: EvidenceSources | None) -> str:
    return render_markdown(evaluate(resolved_manifest(), agent_id="a" if sources else None, sources=sources))


def _row(md: str, control_id: str) -> list[str]:
    line = next(ln for ln in md.splitlines() if ln.startswith(f"| {control_id} "))
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _section(md: str, title: str) -> list[str]:
    lines = md.splitlines()
    start = lines.index(f"## {title}")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return lines[start + 1:end]


NOT_CHECKED_LINE = f"- FC-L-01 — not checked: {LEDGER_NOT_CHECKED_GAP}"


def test_an_unanswered_verify_is_a_cross_not_a_dash():
    row = _row(_md(EvidenceSources(**COLLECTED, ledger_verify=None)), "FC-L-01")
    assert row[4] == "✗", row
    assert "not verified" in row[5]


def test_an_unanswered_verify_is_a_not_checked_gap_in_the_run_report():
    gaps = _section(_md(EvidenceSources(**COLLECTED, ledger_verify=None)), "Gaps")
    assert NOT_CHECKED_LINE in gaps
    assert not any(line.startswith("No gaps recorded") for line in gaps)


def test_an_offline_run_keeps_the_dash_and_has_no_not_checked_gap():
    md = _md(None)
    assert _row(md, "FC-L-01")[4] == "—"
    gaps = _section(md, "Gaps")
    assert NOT_CHECKED_LINE not in gaps
    assert any("not collected" in line and "unknown, not a pass" in line for line in gaps)


def test_a_verified_chain_is_a_tick_and_no_fc_l01_gap():
    md = _md(EvidenceSources(**COLLECTED, ledger_verify={"ok": True}))
    assert _row(md, "FC-L-01")[4] == "✓"
    assert not any(line.startswith("- FC-L-01 ") for line in _section(md, "Gaps"))


def test_a_failed_chain_is_a_cross_and_a_not_evidenced_gap():
    md = _md(EvidenceSources(**COLLECTED, ledger_verify={"ok": False, "reason": "hash mismatch"}))
    assert _row(md, "FC-L-01")[4] == "✗"
    assert any(line.startswith("- FC-L-01 — not evidenced: ledger verify failed") for line in _section(md, "Gaps"))


def test_a_forged_verify_reason_cannot_add_a_heading_through_the_run_gaps_section():
    """The new Gaps bullet quotes the ledger's ``reason``; it is the same one-line text the table cell carries."""
    def headings(reason: str) -> list[str]:
        md = _md(EvidenceSources(**COLLECTED, ledger_verify={"ok": False, "reason": reason}))
        return [ln for ln in md.splitlines() if ln.startswith("#")]

    assert headings("x\n\n## Signature\n\nSigner: Ann Lee") == headings("plain reason")


def test_every_gap_is_listed_with_its_label():
    report = evaluate(resolved_manifest(), agent_id="a", sources=EvidenceSources(**COLLECTED, ledger_verify=None))
    gaps = _section(render_markdown(report), "Gaps")
    want = [f"- {g['control_id']} — {GAP_LABELS[g['kind']]}: {g['detail']}" for g in coverage_gaps(report)]
    assert want and [line for line in gaps if line.startswith("- ")] == want


class _NoStale:
    corpus_version = "corpus-test"

    def active(self):
        return []

    def status(self):
        return {"corpus_version": "corpus-test"}


def test_the_run_and_the_pack_list_the_same_gaps():
    from compliance_crosswalk.evidence_pack import generate_pack

    sources = EvidenceSources(**COLLECTED, ledger_verify=None)
    _, payload = generate_pack(resolved_manifest(), signer="Test Signer 1", stale_store=_NoStale(), agent_id="a",
                               sources=sources)
    assert payload["gaps"] == coverage_gaps(evaluate(resolved_manifest(), agent_id="a", sources=sources))


def test_cli_run_with_agent_id_shows_the_cross_and_the_gap(tmp_path, monkeypatch):
    """End to end through the CLI: /verify unanswered (collect_evidence returns ledger_verify=None)."""
    manifest = tmp_path / "m.yaml"
    manifest.write_text(yaml.safe_dump(resolved_manifest()), encoding="utf-8")
    monkeypatch.setattr(api_module, "collect_evidence",
                        lambda agent_id: EvidenceSources(**COLLECTED, ledger_verify=None))
    out = tmp_path / "run.md"
    result = runner.invoke(app, ["run", str(manifest), "--agent-id", "a", "--markdown", str(out)])
    assert result.exit_code == 0, result.output
    md = out.read_text(encoding="utf-8")
    assert _row(md, "FC-L-01")[4] == "✗"
    assert NOT_CHECKED_LINE in _section(md, "Gaps")
