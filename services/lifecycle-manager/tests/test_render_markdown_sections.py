"""S7-12 — render_markdown: exact lines for the expiring / re-attestation / orphan
sections, and registry-derived text stays on one line and cannot forge a heading."""

from __future__ import annotations

from lifecycle_manager.engine import (
    ExpiringAuthority, Orphan, ReattestationDue, SweepConfig, SweepReport, render_markdown,
)


def _report(**kw) -> SweepReport:
    base = dict(
        swept_at="2026-01-01T00:00:00Z", config=SweepConfig(), agents_scanned=3,
        tokens_scanned=2, roster_size=4, expiring=[], reattestation_due=[], orphans=[],
        escalations_written=0,
    )
    base.update(kw)
    return SweepReport(**base)


def _lines(r: SweepReport) -> list[str]:
    return render_markdown(r).split("\n")


def test_empty_sections_use_none_fallbacks_and_footer():
    ls = _lines(_report())
    assert "## Expiring authorities (0)" in ls
    assert "- none within horizon" in ls
    assert "## Re-attestation due (0)" in ls
    assert "## Orphans (0)" in ls
    assert ls.count("- none") == 2
    assert "*Escalations written to ledger:* 0" in ls
    assert "auto-kill orphans: off" in render_markdown(_report())


def test_auto_kill_on_header():
    r = _report(config=SweepConfig(auto_kill_orphans=True))
    assert "auto-kill orphans: ON" in render_markdown(r)


def test_expiring_line_exact():
    e = ExpiringAuthority(token_id="abcdef0123456789", agent_id="a1", granted_by="don",
                          expires_at="x", days_left=5, scope=["read", "write"])
    assert "- `abcdef01…` a1 — 5 d left (granted by don; scope read, write)" in _lines(
        _report(expiring=[e]))


def test_reattestation_with_and_without_attester():
    a = ReattestationDue(agent_id="a1", owner="o", last_updated="t", days_stale=91,
                         basis="attested_at", attested_by="bob")
    b = ReattestationDue(agent_id="a2", owner="o", last_updated="t", days_stale=95)
    ls = _lines(_report(reattestation_due=[a, b]))
    assert "- a1 — owner o, 91 d since attested_at, last attested by bob" in ls
    assert "- a2 — owner o, 95 d since created_at" in ls


def test_orphans_with_and_without_autokill():
    k = Orphan(agent_id="a1", owner="gone", status="active", reason="no owner", auto_killed=True)
    n = Orphan(agent_id="a2", owner="gone", status="active", reason="no owner")
    ls = _lines(_report(orphans=[k, n]))
    assert "- a1 (active) — no owner → AUTO-KILLED" in ls
    assert "- a2 (active) — no owner" in ls


def test_forged_heading_and_newline_stay_on_one_line():
    o = Orphan(agent_id="a1", owner="x", status="active",
               reason="gone\n## Forged - fake item")
    ls = _lines(_report(orphans=[o]))
    assert not any(l.startswith("## Forged") or l.startswith("- fake") for l in ls)
    assert "- a1 (active) — gone ## Forged - fake item" in ls


def test_leading_marker_escaped():
    r = ReattestationDue(agent_id="# boss", owner="-o", last_updated="t", days_stale=1)
    ls = _lines(_report(reattestation_due=[r]))
    assert "- \\# boss — owner \\-o, 1 d since created_at" in ls
