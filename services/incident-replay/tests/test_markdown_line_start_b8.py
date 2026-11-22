"""B8 (R-PR1163 C2/C3, don.reviewer 1163 M10): post-mortem text that lands at the start of a line's content cannot open
a block, and the strikethrough / bare-URL policy is pinned.

The every-site structure test (test_markdown_forge_every_site.py) carries the line-start forges for all sites; this
file pins the helper itself, the two line-start sites by name, and that the check is not vacuous.
"""
from __future__ import annotations

import pytest
from markdown_it import MarkdownIt

from incident_replay.engine import PostMortem, TimelineEntry, _code, _md, _one_md_line, render_markdown

PARSER = MarkdownIt("commonmark", {"html": True}).enable("table")
STRIKE = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
TS = "2026-01-01T10:00:00+00:00"

LINE_START = ["# FAKE", "## FAKE", "- FAKE", "+ FAKE", "* FAKE", "1. FAKE", "123) FAKE", "~~~", "~~~python",
              "> FAKE", "***", "---", "___", "==="]


def block_types(md: str) -> list[str]:
    return [t.type for t in PARSER.parse(md) if t.type != "inline"]


@pytest.mark.parametrize("value", LINE_START)
@pytest.mark.parametrize("prefix", ["> ", "- ", ""], ids=["banner-quote", "count-bullet", "bare-line"])
def test_a_line_start_marker_is_text_after_the_helper(prefix, value):
    escaped = block_types(prefix + _md(value))
    plain = block_types(prefix + "plain text")
    assert escaped == plain, (prefix, value, escaped)


@pytest.mark.parametrize("value", ["# FAKE", "- FAKE", "1. FAKE", "~~~", "> FAKE"])
def test_the_check_is_not_vacuous_without_the_escape(value):
    assert block_types("> " + value) != block_types("> plain text")


@pytest.mark.parametrize("value, shown", [
    ("# FAKE", "# FAKE"), ("1. FAKE", "1. FAKE"), ("7) FAKE", "7) FAKE"), ("~~~", "~~~"), ("> FAKE", "> FAKE"),
])
def test_the_reader_still_sees_the_text_as_written(value, shown):
    tokens = PARSER.parse("- " + _md(value))
    inline = next(t for t in tokens if t.type == "inline")
    assert "".join(c.content for c in inline.children) == shown


@pytest.mark.parametrize("value", ["plain text", "tool.call", "2026-01-01T10:00:00", "a # b", "a - b", "x 1. y",
                                   "[D.scope] (log-only)", "SHADOW_BLOCK 'x'", "12 items"])
def test_text_that_opens_no_block_is_unchanged(value):
    assert _md(value) == value


def _pm(**over) -> PostMortem:
    entry = TimelineEntry(ts=TS, event_type="tool.call", summary="did a thing", hash="h0", clause_id="D.scope")
    base = dict(agent_id="agent-1", window={"since": TS, "until": TS}, generated_at=TS, ledger_integrity_ok=False,
                ledger_integrity_detail="chain intact", ledger_integrity_status="broken", agent_record=None,
                authority=[], timeline=[entry], first_failure=None, counts={"tool.call": 1},
                raci={"Responsible": "Owner P"}, accountable_grant=None, manifest_resolved=False,
                manifest_detail="no_ref", integrity_notes=[])
    base.update(over)
    return PostMortem(**base)


def _headings(md: str) -> list[str]:
    tokens = PARSER.parse(md)
    return [tokens[i + 1].content for i, t in enumerate(tokens) if t.type == "heading_open"]


def test_site_02_the_integrity_banner_cannot_gain_a_heading():
    want = _headings(render_markdown(_pm(ledger_integrity_detail="plain text")))
    assert _headings(render_markdown(_pm(ledger_integrity_detail="# Which clause failed first"))) == want


def test_site_08_an_event_type_cannot_open_a_heading_or_a_nested_list():
    benign = block_types(render_markdown(_pm(counts={"plain": 1})))
    for forged in ("# Which clause failed first", "- nested", "1. nested", "~~~"):
        assert block_types(render_markdown(_pm(counts={forged: 1}))) == benign, forged


def test_code_goes_through_the_one_line_helper():
    """M10: ``_code`` flattens line breaks and caps exactly as ``_one_md_line`` does."""
    raw = "a\nb c" + "x" * 400
    assert _code(raw) == "`" + _one_md_line(raw) + "`"
    assert "\n" not in _code("x\n## FAKE")


def test_policy_strikethrough_and_bare_urls_are_left_as_written():
    """Strikethrough is emphasis (no block, link or HTML): unchanged. A bare URL is unchanged too: a linkifying
    renderer may make it a link, but the link's text IS its target, unlike ``[text](url)`` (escaped)."""
    assert _md("~~struck~~") == "~~struck~~"
    struck = [c.type for t in STRIKE.parse("- " + _md("~~struck~~")) for c in (t.children or [])]
    assert "s_open" in struck and "link_open" not in struck          # emphasis only: no block, link or HTML
    url = "https://evil.example/x"
    assert _md(url) == url                                            # shown whole: what a reader would click
    hidden = [c.type for t in STRIKE.parse(_md(f"[safe]({url})")) for c in (t.children or [])]
    assert "link_open" not in hidden                                  # a link that hides its target stays escaped
