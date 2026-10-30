"""C-101 (reviewer C-91 on PR 25): the fly-image-smoke "no external URL" grep covers the spellings it missed.

The guard in `.github/workflows/ci.yml` (step "The estate root serves the branded ops console, air-gapped") greps the
served console page for an external reference. It is an accident guard, NOT a proof of an air gap: review is. This
test takes the grep exactly as shipped (its flags and its pattern, parsed with shlex from the step's `run:` script) and
runs the real `grep` over sample pages:

* must match: a double-quoted, single-quoted and unquoted attribute, a protocol-relative url, a meta refresh, a css
  `url(` and `@import`, a JavaScript `fetch` of an absolute url, the font hosts, any case, spaces around `=`;
* must not match: relative paths, fragments, `data:` URIs, a `fetch` of a relative path, prose that mentions https.
The shipped console page itself must have no hit. Each check is also run on mutants of the pattern that must fail it.
"""
from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
CONSOLE = ROOT / "services" / "ops-console" / "src" / "ops_console" / "static" / "console.html"
GREP = shutil.which("grep")
pytestmark = pytest.mark.skipif(GREP is None, reason="grep is not installed")

STEP = "air-gapped"

MUST_MATCH = {
    "double-quoted href (the control)": '<a href="https://ok.example/">x</a>',
    "single-quoted script src": "<script src='https://evil.example/x.js'></script>",
    "unquoted link href": "<link rel=stylesheet href=https://evil.example/s.css>",
    "unquoted protocol-relative img": "<img src=//evil.example/p.png>",
    "meta refresh": "<meta http-equiv=refresh content='0;url=https://evil.example/'>",
    "javascript fetch": "<script>fetch('https://evil.example/x')</script>",
    "javascript fetch, double quotes and spaces": '<script>fetch( "//evil.example/x" )</script>',
    "upper-case attribute": '<IMG SRC="HTTP://evil.example/p.png">',
    "spaces around the equals sign": '<script src = "https://evil.example/x.js"></script>',
    "form action": '<form action="https://evil.example/post">',
    "button formaction": "<button formaction=//evil.example/post>",
    "poster": "<video poster='//evil.example/p.jpg'></video>",
    "object data": "<object data=//evil.example/x.swf></object>",
    "css url, single quote": "<style>.a{background:url('https://evil.example/b.png')}</style>",
    "css url, bare": "<style>.a{background:url(//evil.example/b.png)}</style>",
    "css import": "<style>@import url(x.css);</style>",
    "google fonts host": "<style>/* fonts.googleapis.com */</style>",
    "gstatic host": "<link href='/x' data-f=fonts.gstatic.com>",
    "fetch with a template literal": "<script>fetch(`https://evil.example/${x}`)</script>",
}
MUST_NOT_MATCH = {
    "relative href": '<a href="/path/page">x</a>',
    "fragment": '<a href="#top">x</a>',
    "data uri": '<img src="data:image/svg+xml;base64,AAAA">',
    "same-origin fetch": "<script>fetch('/api/overview')</script>",
    "fetch of a variable": "<script>fetch(path, {headers: h})</script>",
    "prose": "<p>See https://example.org for the docs; the data-id=3 attribute stays.</p>",
    "plain asset": '<link rel="icon" href="icon.svg">',
}


def shipped_grep(ci_text: str) -> list[str]:
    """argv of the `grep ... root.html` of the guard, from the step's run script as shipped."""
    steps = yaml.safe_load(ci_text)["jobs"]["fly-image-smoke"]["steps"]
    (script,) = [s["run"] for s in steps if STEP in s.get("name", "")]
    lines = [ln.strip() for ln in script.splitlines() if re.match(r"\s*if grep -n -E\b", ln)]
    assert len(lines) == 1, lines
    words = shlex.split(lines[0].removeprefix("if ").removesuffix("; then"))
    return words[:-1]          # drop the "$RUNNER_TEMP/root.html" file operand


def hits(argv: list[str], page: str, tmp: Path) -> bool:
    f = tmp / "page.html"
    f.write_text(page, encoding="utf-8")
    p = subprocess.run([GREP, *argv[1:], str(f)], capture_output=True, text=True)
    assert p.returncode in (0, 1), p.stderr
    return p.returncode == 0


def failures(ci_text: str, tmp: Path) -> list[str]:
    argv = shipped_grep(ci_text)
    out = [f"missed: {n}" for n, page in MUST_MATCH.items() if not hits(argv, page, tmp)]
    out += [f"false positive: {n}" for n, page in MUST_NOT_MATCH.items() if hits(argv, page, tmp)]
    return out


def test_the_shipped_guard_matches_every_spelling_and_no_clean_page(tmp_path):
    assert failures(CI.read_text(encoding="utf-8"), tmp_path) == []


def test_the_shipped_console_page_has_no_external_reference(tmp_path):
    assert not hits(shipped_grep(CI.read_text(encoding="utf-8")), CONSOLE.read_text(encoding="utf-8"), tmp_path)


def test_the_guard_is_still_an_accident_guard_in_its_own_words():
    assert "accident guard" in CI.read_text(encoding="utf-8")


MUTANTS = {
    "case-insensitivity dropped": ("grep -n -E -i '(src|", "grep -n -E '(src|"),
    "attribute spaces dropped": ("(src|href|action|poster|data)[[:space:]]*=[[:space:]]*", "(src|href|action|poster|data)="),
    "single and no quote dropped": ("""=[[:space:]]*["'"'"']?(https?:)?//|http-equiv""", """=[[:space:]]*"(https?:)?//|http-equiv"""),
    "meta refresh dropped": ("http-equiv[[:space:]]*=[[:space:]]*[\"'\"'\"']?refresh|", ""),
    "fetch dropped": ("fetch[[:space:]]*\\([[:space:]]*[\"'\"'\"'`]?(https?:)?//|", ""),
    "fetch backtick dropped": ("""["'"'"'`]?(https?:)?//|fonts""", """["'"'"']?(https?:)?//|fonts"""),
    "css url dropped": ("url\\([[:space:]]*[\"'\"'\"']?(https?:)?//|", ""),
    "css import dropped": ("@import|", ""),
    "font hosts dropped": ("|fonts\\.(googleapis|gstatic)", ""),
    "action dropped": ("|action|", "|"),
    "poster dropped": ("|poster|", "|"),
    "data dropped": ("|poster|data)", "|poster)"),
    "everything matches": ("(src|href|action|poster|data)[[:space:]]*=", "(src|href|action|formaction|poster|data|a)[[:space:]]*"),
}


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_each_pattern_mutant_is_caught(name, tmp_path):
    old, new = MUTANTS[name]
    text = CI.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"mutation anchor not found exactly once: {old!r}"
    assert failures(text.replace(old, new), tmp_path) != [], "the mutant survived"


def test_the_old_pattern_missed_what_the_report_said(tmp_path):
    # the pre-C-101 pattern (C-91): five of the six samples of the report slipped through
    text = CI.read_text(encoding="utf-8")
    argv = shipped_grep(text)
    old = ["grep", "-n", "-E", """(src|href|action)="(https?:)?//|url\\((["']?)(https?:)?//|@import|fonts\\.(googleapis|gstatic)"""]
    report = ["double-quoted href (the control)", "single-quoted script src", "unquoted link href",
              "unquoted protocol-relative img", "meta refresh", "javascript fetch"]
    missed = [n for n in report if not hits(old, MUST_MATCH[n], tmp_path)]
    assert missed == report[1:], missed
    assert all(hits(argv, MUST_MATCH[n], tmp_path) for n in report)
