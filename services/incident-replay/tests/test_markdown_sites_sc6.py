"""PR 521 reviewer condition: one forge test per interpolation site of render_markdown.

The first sc6 file pins the helper plus three ledger-derived sites; the rest were free to lose
their `_md(...)` call unnoticed (8 of 14 mutants survived). Each case below puts forged markdown
into exactly ONE field of a hand-built PostMortem, so removing `_md` at that site fails that case
and no other. A forged line is one that starts a heading or list item of its own."""
from __future__ import annotations

import pytest

from incident_replay.engine import AuthorityGrant, PostMortem, TimelineEntry, render_markdown

FORGED = "x\n\n## FORGED heading\n- FAKE item"
FORGED_ID = "\n# FAKE1\n"          # exactly 8 chars: survives the token_id[:8] slice
FORGED_LINE_STARTS = ("## FORGED", "- FAKE", "# FAKE")


def _grant(**kw) -> AuthorityGrant:
    base = dict(token_id="tok00001", granted_by="gb", scope=["s1"], issued_at="2026-01-01T00:00:00Z",
                expires_at="2026-02-01T00:00:00Z", revoked=False)
    return AuthorityGrant(**{**base, **kw})


def _entry(**kw) -> TimelineEntry:
    base = dict(ts="2026-01-01T00:00:00Z", event_type="kill.agent", clause_id=None, summary="s", hash="h")
    return TimelineEntry(**{**base, **kw})


def _pm(**kw) -> PostMortem:
    base = dict(
        agent_id="ag", window={"since": "a", "until": "b"}, generated_at="g",
        ledger_integrity_ok=True, ledger_integrity_detail="fine", ledger_integrity_status="intact",
        agent_record={"agent_id": "ag", "name": "n", "owner": "o", "domain": "d", "status": "st",
                      "manifest_ref": "m"},
        authority=[_grant()], timeline=[_entry()], first_failure=_entry(clause_id="D.scope"),
        counts={"kill.agent": 1}, raci={"Responsible": "r"}, accountable_grant=_grant(),
    )
    return PostMortem(**{**base, **kw})


def _rec(field):
    r = {"agent_id": "ag", "name": "n", "owner": "o", "domain": "d", "status": "st", "manifest_ref": "m"}
    r[field] = FORGED
    return {"agent_record": r}


SITES = {
    "title_agent_id": lambda: {"agent_id": FORGED},
    "banner_unverified_detail": lambda: {"ledger_integrity_ok": False, "ledger_integrity_status": "unverified",
                                         "ledger_integrity_detail": FORGED},
    "banner_failed_detail": lambda: {"ledger_integrity_ok": False, "ledger_integrity_status": "broken",
                                     "ledger_integrity_detail": FORGED},
    "integrity_line_detail": lambda: {"ledger_integrity_detail": FORGED},
    "integrity_note": lambda: {"integrity_notes": [FORGED]},
    "record_agent_id": lambda: _rec("agent_id"),
    "record_name": lambda: _rec("name"),
    "record_owner": lambda: _rec("owner"),
    "record_domain": lambda: _rec("domain"),
    "record_status": lambda: _rec("status"),
    "record_manifest_ref": lambda: _rec("manifest_ref"),
    "authority_token_id": lambda: {"authority": [_grant(token_id=FORGED_ID)]},
    "authority_granted_by": lambda: {"authority": [_grant(granted_by=FORGED)]},
    "authority_scope": lambda: {"authority": [_grant(scope=[FORGED])]},
    "timeline_event_type": lambda: {"timeline": [_entry(event_type=FORGED)]},
    "timeline_summary": lambda: {"timeline": [_entry(summary=FORGED)]},
    "first_failure_clause_id": lambda: {"first_failure": _entry(clause_id=FORGED)},
    "first_failure_summary": lambda: {"first_failure": _entry(clause_id="D.scope", summary=FORGED)},
    "event_count_key": lambda: {"counts": {FORGED: 1}},
    "manifest_detail": lambda: {"manifest_resolved": False, "manifest_detail": FORGED},
    "raci_role": lambda: {"raci": {FORGED: "r"}},
    "raci_party": lambda: {"raci": {"Responsible": FORGED}},
    "accountable_token_id": lambda: {"accountable_grant": _grant(token_id=FORGED_ID)},
    "accountable_granted_by": lambda: {"accountable_grant": _grant(granted_by=FORGED)},
    "accountable_scope": lambda: {"accountable_grant": _grant(scope=[FORGED])},
}


@pytest.mark.parametrize("site", sorted(SITES))
def test_forged_text_at_one_site_adds_no_markdown_structure(site):
    lines = render_markdown(_pm(**SITES[site]())).splitlines()
    assert not [ln for ln in lines if ln.startswith(FORGED_LINE_STARTS)]
    assert sum(ln.startswith("## ") for ln in lines) == len([ln for ln in render_markdown(_pm()).splitlines()
                                                              if ln.startswith("## ")])


@pytest.mark.parametrize("site,kw,needle", [
    ("authority_granted_by", {"authority": [_grant(granted_by="a|b")]}, "a\\|b"),
    ("authority_scope", {"authority": [_grant(scope=["a|b"])]}, "a\\|b"),
    ("raci_role", {"raci": {"a|b": "r"}}, "| a\\|b |"),
    ("raci_party", {"raci": {"Responsible": "a|b"}}, "| a\\|b |"),
])
def test_table_cells_escape_pipes(site, kw, needle):
    assert needle in render_markdown(_pm(**kw))


def test_a_clean_post_mortem_still_renders_its_sections():
    md = render_markdown(_pm())
    for heading in ("## Agent", "## What ran (timeline)", "## Event counts", "## RACI"):
        assert heading in md.splitlines()
