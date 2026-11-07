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


# ---- R-PR737-f579ff3 conditions (findings 1 to 3) --------------------------------------------------------------
# One injection per registry-derived field of every section: the value carries a newline and a heading, and the line
# must stay one line. Dropping `_inline` at any one call site leaves a line that starts with "## FORGED".

from lifecycle_manager.engine import RetentionFinding, WitnessFinding, _inline  # noqa: E402

import pytest  # noqa: E402


def _bad(n: int) -> str:
    return f"T{n}\n## FORGED{n}"


def _flat(n: int) -> str:
    return f"T{n} ## FORGED{n}"


def _assert_one_line(text: str, ns) -> None:
    assert not any(line.startswith("## FORGED") for line in text.split("\n")), text
    for n in ns:
        assert _flat(n) in text, f"field {n} is not on one line"


def test_expiring_fields_stay_on_one_line():
    e = ExpiringAuthority(token_id="abcdef0123456789", agent_id=_bad(1), granted_by=_bad(2), expires_at="x",
                          days_left=5, scope=[_bad(3), "write"])
    _assert_one_line(render_markdown(_report(expiring=[e])), (1, 2, 3))


def test_reattestation_fields_stay_on_one_line():
    a = ReattestationDue(agent_id=_bad(1), owner=_bad(2), last_updated="t", days_stale=91, basis=_bad(3),
                         attested_by=_bad(4))
    _assert_one_line(render_markdown(_report(reattestation_due=[a])), (1, 2, 3, 4))


def test_orphan_fields_stay_on_one_line():
    o = Orphan(agent_id=_bad(1), owner="x", status=_bad(2), reason=_bad(3))
    _assert_one_line(render_markdown(_report(orphans=[o])), (1, 2, 3))


def test_retention_fields_stay_on_one_line():
    f = RetentionFinding(status="violation", estate_retention_days=10, max_manifest_retention_days=20,
                         offending=[{"agent_id": _bad(1), "retention_days": _bad(2)}],
                         unresolvable=[{"agent_id": _bad(3), "manifest_ref": _bad(4), "reason": _bad(5)}],
                         detail=_bad(6))
    _assert_one_line(render_markdown(_report(retention_policy=f)), (1, 2, 3, 4, 5, 6))


def test_witness_detail_stays_on_one_line():
    w = WitnessFinding(status="stale", estate_watched="e", detail=_bad(1))
    _assert_one_line(render_markdown(_report(witness=w)), (1,))


@pytest.mark.parametrize("raw,want", [
    ("a\x00b", "a b"), ("a\x1bb", "a b"),                       # Cc: NUL, ESC
    ("a​b", "a b"), ("a‮b", "a b"),                   # Cf: zero-width space, right-to-left override
    ("a b", "a b"), ("a b", "a b"),                   # Zl, Zp
    ("a   b", "a b"), ("  a \t b  ", "a b"),                    # whitespace runs collapse, ends trimmed
])
def test_inline_collapses_control_format_and_whitespace(raw, want):
    assert _inline(raw) == want


@pytest.mark.parametrize("marker", list("#-`*>+"))
def test_inline_escapes_each_leading_block_marker_once_and_only_leading(marker):
    assert _inline(f"{marker}x") == f"\{marker}x"
    assert _inline(f"x{marker}y") == f"x{marker}y"
    assert _inline(f" {marker}x") == f"\{marker}x"               # the collapse runs first, so this is leading
