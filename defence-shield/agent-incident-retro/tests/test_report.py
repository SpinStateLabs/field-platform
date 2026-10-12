"""The report is SIGNED, so attacker-controlled log text must not be able to
inject Markdown structure or raw HTML into it, and the notice must never read
as an accusation."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import re

from agent_incident_retro.engine import run_retro
from agent_incident_retro.report import _scrub, code, render_markdown, safe
from agent_incident_retro.synth import _clf

_RUN = re.compile(r"`+")


def _outside_code_spans(md: str) -> str:
    """Strip inline code spans the way CommonMark delimits them: a run of N
    backticks closes at the next run of EXACTLY N backticks (an unmatched run
    is literal text). What's left is what a renderer treats as prose/HTML; text
    inside a span is rendered literally, so it is safe and does not count."""
    out: list[str] = []
    i = 0
    while (m := _RUN.search(md, i)) is not None:
        out.append(md[i : m.start()])
        n = len(m.group())
        close = re.compile(rf"(?<!`)`{{{n}}}(?!`)").search(md, m.end())
        if close is None:
            out.append(m.group())
            i = m.end()
        else:
            out.append(" ")
            i = close.end()
    out.append(md[i:])
    return "".join(out)


def _unescaped(construct: str, text: str) -> bool:
    """True if ``construct`` appears in ``text`` with no backslash before it."""
    return re.search(r"(?<!\\)" + re.escape(construct), text) is not None


def test_scrub_removes_newlines_and_controls():
    assert "\n" not in _scrub("a\nb")
    assert _scrub("a\r\n\t\x00b c") == "a b c"


def test_scrub_removes_bidi_and_zero_width_controls():
    # U+202E (RTL override) would display the rest of a table cell reversed to
    # a human reader; the isolates and zero-width characters are the same class
    for ch in ("\u202e", "\u202d", "\u202a", "\u2066", "\u2067", "\u2068", "\u2069", "\u200b", "\u200f", "\ufeff"):
        assert ch not in _scrub(f"Mozilla {ch}evil.example{ch} ok"), hex(ord(ch))


def test_safe_neutralises_markdown_and_html():
    assert safe("### Verdict: CLEAR").startswith("\\#")
    assert "<" not in safe("<img src=x onerror=alert(1)>")
    # '>' is HTML-escaped to &gt; (so it cannot start a blockquote) and the
    # result is additionally backslash-guarded on its new leading char
    out = safe("> blockquote")
    assert not out.lstrip("\\").startswith(">") and "&gt;" in out


def test_safe_escapes_inline_markdown_everywhere_not_just_leading():
    out = safe("ip ![t](https://evil.example/p.png) [x](https://phish.example) *b* _c_ `d` ~e~ f|g")
    for construct in ("![", "](", "[x", "*b*", "_c_", "`d`", "~e~", "|"):
        assert not _unescaped(construct, out), (construct, out)
    # an attacker backslash cannot cancel the escape that follows it:
    # "\[x](u)" must not come out as "\\[x](u)" (literal backslash + live link)
    out = safe("\\[x](https://phish.example)")
    assert out.startswith("\\\\\\[") and not _unescaped("](", out)


def test_code_cannot_break_out_of_span():
    rendered = code("a`b` c")
    assert rendered.startswith("``") and rendered.endswith("``")
    assert "\n" not in code("a\nb")


def test_code_fence_is_one_longer_than_the_longest_backtick_run():
    """CommonMark closes a span at the first run of exactly the opening length,
    so a fence that is only one longer than ONE backtick is closed by a run of
    two. The fence must exceed the longest run in the text, for any run."""
    for n in range(1, 7):
        text = f"a{'`' * n}b{'`' * (n - 1)}c"
        rendered = code(text)
        fence = _RUN.match(rendered).group()
        assert len(fence) == n + 1, (n, rendered)
        assert rendered.endswith(fence)
        inner = rendered[len(fence) : -len(fence)]
        # no run inside the span is as long as the fence -> nothing closes it early
        assert max(len(r) for r in _RUN.findall(inner)) < len(fence)
        assert _outside_code_spans(rendered).strip() == ""
    # a run at either end gets the CommonMark space padding
    assert code("``x").startswith("``` ``x ```")


def _report_for(targets: list[str], ua: str = "python-requests/2.32.3", ip: str = "203.0.113.5") -> str:
    t0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
    lines = []
    # a benign then a payload on the same param so the session is reported
    lines.append(_clf(ip, t0, "GET", "/search?q=books", 200, 100, ua))
    for i, tgt in enumerate(targets, start=1):
        lines.append(_clf(ip, t0 + timedelta(seconds=20 * i), "GET", tgt, 200, 100, ua))
    return lines


def _render(tmp_path: Path, rows: list[str]) -> str:
    log = tmp_path / "e.log"
    log.write_text("\n".join(rows) + "\n", encoding="utf-8")
    result = run_retro([log], fmt="clf")
    assert result.findings  # the session was flagged, so the payload reached the report
    return render_markdown(result, "2026-10-11T00:00:00+00:00")


def test_injected_heading_in_path_does_not_become_a_heading(tmp_path: Path):
    # a debug-probe path carrying encoded newlines + a fake heading
    evil = "/admin/%0a%0a%23%23%23%20INJECTED%20HEADING%0a%0aall%20clear"
    md = _render(tmp_path, _report_for([evil]))
    # the injected text must never START a line (where it would become a heading,
    # blockquote or list item); scrub collapsed its embedded newlines to spaces,
    # so it can only appear mid-cell.
    assert not any(
        ln.lstrip().startswith(("#", ">", "-", "*", "+")) and "INJECTED" in ln
        for ln in md.splitlines()
    )


def test_injected_html_img_is_escaped(tmp_path: Path):
    evil = "/admin/%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E"
    md = _render(tmp_path, _report_for([evil]))
    # no live <img> outside a code span (inside a span it renders literally)
    assert "<img" not in _outside_code_spans(md)


def test_injected_html_in_client_ip_notice_is_escaped(tmp_path: Path):
    # some logs put an XFF-style value in the client field; treat it as hostile
    # text. (The CLF client field is \S+, so the tag must carry no space —
    # the v0.1 version of this test used "<a href=x>", which never parsed and
    # so asserted against an empty report.)
    evil_ip = "203.0.113.5<svg/onload=alert(1)>"
    md = _render(tmp_path, _report_for(["/search?q=%27%20OR%20%271%27%3D%271%20--%20"], ip=evil_ip))
    assert "<svg" not in _outside_code_spans(md)


# second independent review (2026-10-12), HIGH-1 and MEDIUM-2 payloads

UA_DOUBLE_BACKTICK = (
    "Mozilla/5.0``**CONFIRMED: operated by ACME Corp, admitted in writing**"
    "![](https://evil.example/px.png)``x"
)


def test_double_backtick_run_in_user_agent_cannot_close_the_code_span(tmp_path: Path):
    """HIGH-1: ``code()`` used a 2-backtick fence whenever the text had a
    backtick, so a 2-backtick run in the user-agent closed it and the bold
    'CONFIRMED' claim plus a tracking image went live in the SIGNED report."""
    md = _render(tmp_path, _report_for(["/search?q=%27%20OR%20%271%27%3D%271"], ua=UA_DOUBLE_BACKTICK))
    prose = _outside_code_spans(md)
    assert "CONFIRMED" not in prose
    assert "![](" not in prose and "evil.example" not in prose
    ua_row = next(ln for ln in md.splitlines() if ln.startswith("| User-agent |"))
    assert ua_row.count("```") == 2  # a 3-backtick fence around a text whose longest run is 2


def test_inline_image_and_link_in_probe_path_are_not_live(tmp_path: Path):
    """MEDIUM-2 (reviewer case 2): the S.debug-probe detail carries the probed
    path; a mid-string ``![t](url)`` / ``[x](url)`` used to survive ``safe()``,
    which escaped only a LEADING Markdown character."""
    from urllib.parse import quote

    evil = "/admin/" + quote("![tracker](https://evil.example/p.png) [click here](https://phish.example)", safe="")
    rows = _report_for([evil])
    rows.insert(1, _clf("203.0.113.5", datetime(2026, 9, 1, 0, 0, 10, tzinfo=timezone.utc), "GET", evil, 404, 1, "python-requests/2.32.3"))
    md = _render(tmp_path, rows)
    prose = _outside_code_spans(md)
    assert not _unescaped("](", prose) and not _unescaped("![", prose)
    assert "evil.example" not in prose and "phish.example" not in prose
    assert "evil.example" in md  # still shown to the reviewer, literally


def test_inline_image_and_link_in_client_ip_notice_are_not_live(tmp_path: Path):
    """MEDIUM-2 (reviewer case 3): the DRAFT notice line rendered the client
    field through ``safe()``; an XFF-style value with an inline link survived."""
    evil_ip = "203.0.113.5![](https://evil.example/px.png)[operator:ACME](https://phish.example)"
    md = _render(tmp_path, _report_for(["/search?q=%27%20OR%20%271%27%3D%271"], ip=evil_ip))
    notice = "\n".join(ln for ln in md.splitlines() if ln.startswith("> - "))
    assert notice  # the notice was rendered for this ESCALATE/REVIEW session
    prose = _outside_code_spans(notice)
    assert not _unescaped("](", prose) and not _unescaped("![", prose)
    assert "phish.example" not in prose


def test_notice_is_not_an_accusation(tmp_path: Path):
    md = _render(tmp_path, _report_for(["/search?q=%27%20OR%20%271%27%3D%271%20--%20"]))
    assert "consistent with" in md
    assert "clause matches for review, not confirmed findings" in md
    # no bare factual accusation
    assert "showed hostile, automated, goal-seeking behaviour" not in md
