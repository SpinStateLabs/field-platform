"""The report is SIGNED, so attacker-controlled log text must not be able to
inject Markdown structure or raw HTML into it, and the notice must never read
as an accusation."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import re

from agent_incident_retro.engine import run_retro
from agent_incident_retro.report import _scrub, code, render_markdown, safe
from agent_incident_retro.synth import _clf


def _outside_code_spans(md: str) -> str:
    """Strip inline code spans; what's left is what a Markdown renderer treats
    as prose/HTML. HTML inside a code span is rendered literally, so it is safe
    and does not count."""
    md = re.sub(r"``.*?``", " ", md)
    md = re.sub(r"`[^`]*`", " ", md)
    return md


def test_scrub_removes_newlines_and_controls():
    assert "\n" not in _scrub("a\nb")
    assert _scrub("a\r\n\t\x00b c") == "a b c"


def test_safe_neutralises_markdown_and_html():
    assert safe("### Verdict: CLEAR").startswith("\\#")
    assert "<" not in safe("<img src=x onerror=alert(1)>")
    # '>' is HTML-escaped to &gt; (so it cannot start a blockquote) and the
    # result is additionally backslash-guarded on its new leading char
    out = safe("> blockquote")
    assert not out.lstrip("\\").startswith(">") and "&gt;" in out


def test_code_cannot_break_out_of_span():
    rendered = code("a`b` c")
    assert rendered.startswith("``") and rendered.endswith("``")
    assert "\n" not in code("a\nb")


def _report_for(targets: list[str], ua: str = "python-requests/2.32.3", ip: str = "203.0.113.5") -> str:
    t0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
    lines = []
    # a benign then a payload on the same param so the session is reported
    lines.append(_clf(ip, t0, "GET", "/search?q=books", 200, 100, ua))
    for i, tgt in enumerate(targets, start=1):
        lines.append(_clf(ip, t0 + timedelta(seconds=20 * i), "GET", tgt, 200, 100, ua))
    return lines


def test_injected_heading_in_path_does_not_become_a_heading(tmp_path: Path):
    # a debug-probe path carrying encoded newlines + a fake heading
    evil = "/admin/%0a%0a%23%23%23%20INJECTED%20HEADING%0a%0aall%20clear"
    log = tmp_path / "e.log"
    log.write_text("\n".join(_report_for([evil])) + "\n", encoding="utf-8")
    result = run_retro([log], fmt="clf")
    md = render_markdown(result, "2026-10-11T00:00:00+00:00")
    assert result.findings  # it was flagged
    # the injected text must never START a line (where it would become a heading,
    # blockquote or list item); scrub collapsed its embedded newlines to spaces,
    # so it can only appear mid-cell.
    assert not any(
        ln.lstrip().startswith(("#", ">", "-", "*", "+")) and "INJECTED" in ln
        for ln in md.splitlines()
    )


def test_injected_html_img_is_escaped(tmp_path: Path):
    evil = "/admin/%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E"
    log = tmp_path / "e.log"
    log.write_text("\n".join(_report_for([evil])) + "\n", encoding="utf-8")
    md = render_markdown(run_retro([log], fmt="clf"), "2026-10-11T00:00:00+00:00")
    # no live <img> outside a code span (inside a span it renders literally)
    assert "<img" not in _outside_code_spans(md)


def test_injected_html_in_client_ip_notice_is_escaped(tmp_path: Path):
    # some logs put an XFF-style value in the client field; treat it as hostile text
    evil_ip = "203.0.113.5<a href=x>"
    log = tmp_path / "e.log"
    rows = _report_for(["/search?q=%27%20OR%20%271%27%3D%271%20--%20"], ip=evil_ip)
    log.write_text("\n".join(rows) + "\n", encoding="utf-8")
    md = render_markdown(run_retro([log], fmt="clf"), "2026-10-11T00:00:00+00:00")
    assert "<a href" not in md


def test_notice_is_not_an_accusation(tmp_path: Path):
    log = tmp_path / "e.log"
    log.write_text("\n".join(_report_for(["/search?q=%27%20OR%20%271%27%3D%271%20--%20"])) + "\n", encoding="utf-8")
    md = render_markdown(run_retro([log], fmt="clf"), "2026-10-11T00:00:00+00:00")
    assert "consistent with" in md
    assert "clause matches for review, not confirmed findings" in md
    # no bare factual accusation
    assert "showed hostile, automated, goal-seeking behaviour" not in md
