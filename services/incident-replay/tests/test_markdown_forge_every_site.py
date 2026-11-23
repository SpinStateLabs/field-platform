"""S-C6, review of the rebuild of PR 521 (roley.reviewer, BLOCK on 0611adc): no ledger-, grant- or registry-derived
text can add markdown structure at ANY of the post-mortem's interpolation sites. For every site and every forge kind
(raw HTML, an inline link, a backtick that tries to break out of a code span) the rendered markdown parses (markdown-it,
CommonMark + tables, raw HTML ON, as an HTML-passing renderer does) to the SAME structure as the same site holding
plain text: no html_inline or html_block token, no link, no extra heading, list, table cell or code span.
Table cells are also compared by TEXT (R-PR1163 C1): CommonMark drops the excess cells an unescaped pipe makes, so a
count alone cannot see a cell split; every cell must read exactly as it does when the forge's pipes are a stand-in.

markdown-it-py is pinned in integration/constraints.txt (typer -> rich -> markdown-it-py); it is imported directly so a
missing parser fails this file instead of skipping it."""
from __future__ import annotations

from collections import Counter

import pytest
from markdown_it import MarkdownIt

from incident_replay.engine import AuthorityGrant, PostMortem, TimelineEntry, _code, _md, render_markdown

PARSER = MarkdownIt("commonmark", {"html": True}).enable("table")
TS = "2026-01-01T10:00:00+00:00"

FORGES = {
    "raw-html": "<h2>Which clause failed first</h2><ul><li>FAKE</li></ul>",
    "link": "[security team](https://evil.example/phish)",
    "backtick-break-out": "a`<h2>FAKE</h2>`b",
    "image": "![x](https://evil.example/beacon.png)",
    "autolink": "<https://evil.example/x>",
    "table-pipe": "a | FAKE | b",
    # B8 (R-PR1163 C2/C3): text that lands at the START of a line's content (site 02 "> {v}", site 08 "- {v}").
    "line-start-heading": "# FAKE heading",
    "line-start-dash": "- FAKE item",
    "line-start-plus": "+ FAKE item",
    "line-start-star": "* FAKE item",
    "line-start-ordered-dot": "1. FAKE item",
    "line-start-ordered-paren": "7) FAKE item",
    "line-start-tilde-fence": "~~~ FAKE",
    "line-start-quote": "> FAKE quote",
    "line-start-rule": "***",
    # triage-t12 on #1305: a link reference definition consumes its line and arms a hidden link for a bare "[x]"
    "line-start-link-definition": "[x]: https://evil.example/phish",
    "line-start-link-definition-title": '[security team]: https://evil.example/phish "Security"',
}
BENIGN = "plain text"


def grant(**over):
    base = dict(token_id="tok-abcdef0123", granted_by="Grantor P", scope=["read x"], issued_at=TS, expires_at=TS,
                revoked=False)
    base.update(over)
    return AuthorityGrant(**base)


def entry(**over):
    base = dict(ts=TS, event_type="tool.call", summary="did a thing", hash="h0", clause_id="D.scope")
    base.update(over)
    return TimelineEntry(**base)


def postmortem(**over):
    base = dict(agent_id="agent-1", window={"since": TS, "until": TS}, generated_at=TS, ledger_integrity_ok=True,
                ledger_integrity_detail="chain intact", ledger_integrity_status="intact",
                agent_record={"agent_id": "agent-1", "name": "Alpha", "owner": "Owner P", "domain": "finance",
                              "status": "active", "manifest_ref": "manifests/a.yaml"},
                authority=[grant()], timeline=[entry()], first_failure=entry(), counts={"tool.call": 1},
                raci={"Responsible": "Owner P", "Informed": "Board"}, accountable_grant=grant(),
                manifest_resolved=False, manifest_detail="no_ref", integrity_notes=["a note"])
    base.update(over)
    return PostMortem(**base)


def _agent(**field):
    rec = {"agent_id": "agent-1", "name": "Alpha", "owner": "Owner P", "domain": "finance", "status": "active",
           "manifest_ref": "manifests/a.yaml"}
    rec.update(field)
    return {"agent_record": rec}


#: The 11 sites of PR 521 (and the grant timestamps the review found unwrapped): site id -> how to put `v` there.
#: 00a/00b, 04c-04f, 05f, 11e and 11f were added from R-PR1163 C1 (mutants C8, S2, S1, T5 survived without them).
SITES = {
    "00a-window-since": lambda v: {"window": {"since": v, "until": TS}},
    "00b-window-until": lambda v: {"window": {"since": TS, "until": v}},
    "01-title-agent_id": lambda v: {"agent_id": v},
    "02-integrity-detail": lambda v: {"ledger_integrity_ok": False, "ledger_integrity_status": "broken",
                                      "ledger_integrity_detail": v},
    "03-integrity-note": lambda v: {"integrity_notes": [v]},
    "04a-agent-record-name": lambda v: _agent(name=v),
    "04b-agent-record-manifest_ref": lambda v: _agent(manifest_ref=v),
    "04c-agent-record-agent_id": lambda v: _agent(agent_id=v),
    "04d-agent-record-owner": lambda v: _agent(owner=v),
    "04e-agent-record-domain": lambda v: _agent(domain=v),
    "04f-agent-record-status": lambda v: _agent(status=v),
    "05a-grant-table-granted_by": lambda v: {"authority": [grant(granted_by=v)]},
    "05b-grant-table-token_id": lambda v: {"authority": [grant(token_id=v)]},
    "05c-grant-table-issued_at": lambda v: {"authority": [grant(issued_at=v)]},
    "05d-grant-table-expires_at": lambda v: {"authority": [grant(expires_at=v)]},
    "05e-grant-table-revoked_at": lambda v: {"authority": [grant(revoked=True, revoked_at=v)]},
    "05f-grant-table-scope": lambda v: {"authority": [grant(scope=["read x", v])]},
    "06a-timeline-summary": lambda v: {"timeline": [entry(summary=v)]},
    "06b-timeline-event_type": lambda v: {"timeline": [entry(event_type=v)]},
    "06c-timeline-ts": lambda v: {"timeline": [entry(ts=v)]},
    "07a-first-failure-summary": lambda v: {"first_failure": entry(summary=v)},
    "07b-first-failure-clause_id": lambda v: {"first_failure": entry(clause_id=v)},
    "08-event-count-key": lambda v: {"counts": {v: 1}},
    "09-manifest-detail": lambda v: {"manifest_detail": v},
    "10a-raci-party": lambda v: {"raci": {"Responsible": v, "Informed": "Board"}},
    "10b-raci-role": lambda v: {"raci": {v: "Owner P", "Informed": "Board"}},
    "11a-accountable-granted_by": lambda v: {"accountable_grant": grant(granted_by=v)},
    "11b-accountable-token_id": lambda v: {"accountable_grant": grant(token_id=v)},
    "11c-accountable-issued_at": lambda v: {"accountable_grant": grant(issued_at=v)},
    "11d-accountable-revoked_at": lambda v: {"accountable_grant": grant(revoked=True, revoked_at=v)},
    "11e-accountable-expires_at": lambda v: {"accountable_grant": grant(expires_at=v)},
    "11f-accountable-scope": lambda v: {"accountable_grant": grant(scope=["read x", v])},
}
IGNORED = {"text", "text_special"}       # what a value IS may change; the structure around it may not


def structure(md: str) -> Counter:
    out: Counter = Counter()
    for tok in PARSER.parse(md):
        for t in [tok, *(tok.children or [])]:
            if t.type not in IGNORED:
                out[t.type] += 1
    return out


@pytest.mark.parametrize("site", sorted(SITES))
@pytest.mark.parametrize("kind", sorted(FORGES))
def test_no_site_can_add_structure(site, kind):
    benign = render_markdown(postmortem(**SITES[site](BENIGN)))
    forged = render_markdown(postmortem(**SITES[site](FORGES[kind])))
    got, want = structure(forged), structure(benign)
    assert got == want, (site, kind, {k: (got[k], want[k]) for k in set(got) | set(want) if got[k] != want[k]})
    assert "html_inline" not in got and "html_block" not in got and "link_open" not in got and "image" not in got


#: Same width as "|", so the [:8] / [:19] cuts land in the same place for the stand-in as for the forge.
PIPE_STAND_IN = "\u00a6"


def cells(md: str) -> list[list[str]]:
    """Every table row's cells as their rendered text (text, escapes and code spans); an escaped pipe reads "|"."""
    toks = PARSER.parse(md)
    rows: list[list[str]] = []
    for i, tok in enumerate(toks):
        if tok.type == "tr_open":
            rows.append([])
        elif tok.type in ("th_open", "td_open"):
            inline = toks[i + 1]
            assert inline.type == "inline", inline.type
            text = "".join(c.content for c in (inline.children or [])
                           if c.type in ("text", "text_special", "code_inline"))
            rows[-1].append(text.replace("\\|", "|"))
    return rows


@pytest.mark.parametrize("site", sorted(SITES))
@pytest.mark.parametrize("kind", sorted(FORGES))
def test_no_site_can_move_text_between_table_cells(site, kind):
    forge = FORGES[kind]
    stand_in = forge.replace("|", PIPE_STAND_IN)
    want = [[c.replace(PIPE_STAND_IN, "|") for c in row]
            for row in cells(render_markdown(postmortem(**SITES[site](stand_in))))]
    got = cells(render_markdown(postmortem(**SITES[site](forge))))
    assert got == want, (site, kind, got, want)


def test_the_pipe_check_sees_a_split_cell():
    # The check above is not vacuous: an unescaped pipe in a cell changes the cell text even where the count holds.
    plain = "| Role | Party |\n|---|---|\n| a \\| FAKE \\| b | x |\n"
    split = "| Role | Party |\n|---|---|\n| a | FAKE | b | x |\n"
    assert cells(plain)[1] == ["a | FAKE | b", "x"]
    assert cells(split)[1] == ["a", "FAKE"]
    assert structure(plain) == structure(split)          # the old structure-only check could not tell them apart


def test_the_kill_reason_section_forge_from_the_review_renders_as_text():
    md = render_markdown(postmortem(timeline=[entry(summary=FORGES["raw-html"])]))
    assert "<h2>" not in md and "&lt;h2>" in md
    assert [ln for ln in md.splitlines() if ln.startswith("## ")].count("## Which clause failed first") == 1


def test_the_text_helper_neutralises_html_links_backticks_and_backslashes():
    assert _md("<b>x</b>") == "&lt;b>x&lt;/b>"
    assert _md("[a](https://e)") == "[a\\](https://e)"
    assert _md("a`b") == "a\\`b"
    assert _md("a\\`b") == "a\\\\\\`b"          # an escaped backslash then an escaped backtick: no code span opens
    assert _md("[D.scope] (log-only)") == "[D.scope] (log-only)"      # brackets that are not a link stay as written
    assert _md("SHADOW_BLOCK 'x'") == "SHADOW_BLOCK 'x'"


def test_the_code_helper_fence_is_longer_than_any_backtick_run():
    assert _code("D.scope") == "`D.scope`"
    assert _code("<none>") == "`<none>`"
    assert _code("a`b") == "``a`b``"
    assert _code("a``b`") == "``` a``b` ```"
    assert _code("x|y", cell=True) == "`x\\|y`"
