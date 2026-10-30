"""C-101 (reviewer C-91 on PR 25): the fly-image-smoke "no external URL" grep covers the spellings it missed.

The guard in `.github/workflows/ci.yml` (step "The estate root serves the branded ops console, air-gapped") greps the
served console page for an external reference. It is an accident guard, NOT a proof of an air gap: review is. This
test takes the grep exactly as shipped (its flags and its pattern, parsed with shlex from the step's `run:` script) and
runs the real `grep` over sample pages:

* must match: a double-quoted, single-quoted and unquoted attribute, a protocol-relative url, a meta refresh, a css
  `url(` and `@import`, a JavaScript `fetch` of an absolute url, the font hosts, any case, spaces around `=`;
* must not match: relative paths, fragments, `data:` URIs, a `fetch` of a relative path, prose that mentions https.
The shipped console page itself must have no hit. Each check is also run on mutants of the pattern that must fail it.

C-546 (Lane 10): the step flattens the page to one line with `tr` before the grep, so an attribute split across lines is
seen; `srcset`, `imagesrcset`, `ping` and `formaction` are in the list; and the step tells grep status 1 (no hit) from
status 2 (a broken pattern): the shipped tail of the step is run in bash for a clean page, a hit and a broken pattern.
`formaction` is redundant with `action`, and `imagesrcset` with `srcset` (both are substring matches), so they are listed
for readability only and no mutant removes either alone (it would be equivalent).
"""
from __future__ import annotations

import os
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
    "srcset, first entry external": '<img srcset="https://evil.example/a.png 1x, b.png 2x">',
    "srcset, second entry external": '<img srcset="a.png 1x, https://evil.example/b.png 2x">',
    "imagesrcset": "<link rel=preload imagesrcset='a.png 1x, //evil.example/b.png 2x'>",
    "ping": '<a href="/x" ping="https://evil.example/p">x</a>',
    "attribute split across two lines": '<script src=\n"https://evil.example/x.js"></script>',
    "attribute value on the next line, tabs": '<img\n\tsrc\t=\t\n  //evil.example/p.png>',
    "css url split across lines": "<style>.a{background:url(\n'https://evil.example/b.png')}</style>",
    "fetch split across lines": "<script>fetch(\n  'https://evil.example/x')</script>",
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
    "srcset, relative only": '<img srcset="a.png 1x, b.png 2x">',
    "ping to a relative path": '<a href="/x" ping="/beacon">x</a>',
    "two lines, nothing external": '<script>\nfetch(\n  "/api/x")\n</script>',
    "plain asset": '<link rel="icon" href="icon.svg">',
}


def guard_script(ci_text: str) -> str:
    steps = yaml.safe_load(ci_text)["jobs"]["fly-image-smoke"]["steps"]
    (script,) = [st["run"] for st in steps if STEP in st.get("name", "")]
    return script


def shipped_grep(ci_text: str) -> list[str]:
    """argv of the `grep ... root.flat` of the guard, from the step's run script as shipped."""
    lines = [ln.strip() for ln in guard_script(ci_text).splitlines() if re.match(r"\s*grep -o -E\b", ln)]
    assert len(lines) == 1, lines
    words = shlex.split(lines[0].removesuffix("|| rc=$?"))
    return words[:-1]          # drop the "$RUNNER_TEMP/root.flat" file operand


TR_LINE = re.compile(r"\s*tr '\\n' ' ' <")


def flattens(ci_text: str) -> bool:
    return any(TR_LINE.match(ln) for ln in guard_script(ci_text).splitlines())


def hits(argv: list[str], page: str, tmp: Path, flatten: bool = True) -> bool:
    f = tmp / "page.html"
    f.write_text(page.replace("\n", " ") if flatten else page, encoding="utf-8")
    p = subprocess.run([GREP, *argv[1:], str(f)], capture_output=True, text=True)
    assert p.returncode in (0, 1), p.stderr
    return p.returncode == 0


def failures(ci_text: str, tmp: Path) -> list[str]:
    argv, flat = shipped_grep(ci_text), flattens(ci_text)
    out = [f"missed: {n}" for n, page in MUST_MATCH.items() if not hits(argv, page, tmp, flat)]
    out += [f"false positive: {n}" for n, page in MUST_NOT_MATCH.items() if hits(argv, page, tmp, flat)]
    return out


def run_tail(ci_text: str, page: str, tmp: Path) -> subprocess.CompletedProcess:
    """Run the shipped tail of the step (from the `tr` line on) in bash -e, as GitHub runs it, on `page`."""
    lines = guard_script(ci_text).splitlines()
    start = next(i for i, ln in enumerate(lines) if TR_LINE.match(ln))
    (tmp / "root.html").write_text(page, encoding="utf-8")
    env = {**os.environ, "RUNNER_TEMP": str(tmp)}
    return subprocess.run(["bash", "-e", "-o", "pipefail", "-c", "\n".join(lines[start:])], capture_output=True, text=True, env=env)


def test_the_shipped_guard_matches_every_spelling_and_no_clean_page(tmp_path):
    assert failures(CI.read_text(encoding="utf-8"), tmp_path) == []


def test_the_shipped_console_page_has_no_external_reference(tmp_path):
    assert run_tail(CI.read_text(encoding="utf-8"), CONSOLE.read_text(encoding="utf-8"), tmp_path).returncode == 0


def tail_problems(ci_text: str, tmp: Path) -> list[str]:
    """The step must exit 0 on a clean page, 1 with the external-reference message on a hit, and 1 with the failure
    message when grep itself fails (a broken pattern): rc 0, 1 and 2 are three different outcomes."""
    out = []
    ok = run_tail(ci_text, "<p>nothing external</p>\n", tmp)
    if ok.returncode != 0:
        out.append(f"a clean page failed the step: {ok.stdout}{ok.stderr}")
    hit = run_tail(ci_text, '<script src="https://evil.example/x.js"></script>\n', tmp)
    if hit.returncode != 1 or "references an external URL" not in hit.stdout:
        out.append(f"a hit did not fail the step with the external-URL message: rc={hit.returncode} {hit.stdout}")
    bad = ci_text.replace("grep -o -E -i '(src|", "grep -o -E -i '((src|", 1)      # an unbalanced group: grep exits 2
    broken = run_tail(bad, "<p>nothing external</p>\n", tmp)
    if broken.returncode != 1 or "grep failed with status 2" not in broken.stdout:
        out.append(f"a broken pattern did not fail the step with the grep-failed message: rc={broken.returncode} {broken.stdout}")
    return out


def test_the_step_tells_no_hit_from_a_hit_from_a_grep_error(tmp_path):
    assert tail_problems(CI.read_text(encoding="utf-8"), tmp_path) == []


def test_the_guard_is_still_an_accident_guard_in_its_own_words():
    assert "accident guard" in CI.read_text(encoding="utf-8")


MUTANTS = {
    "case-insensitivity dropped": ("grep -o -E -i '(src|", "grep -o -E '(src|"),
    "attribute spaces dropped": ("(src|href|action|formaction|poster|data|ping)[[:space:]]*=[[:space:]]*", "(src|href|action|formaction|poster|data|ping)="),
    "single and no quote dropped": ("""=[[:space:]]*["'"'"']?(https?:)?//|(srcset""", """=[[:space:]]*"(https?:)?//|(srcset"""),
    "meta refresh dropped": ("http-equiv[[:space:]]*=[[:space:]]*[\"'\"'\"']?refresh|", ""),
    "fetch dropped": ("fetch[[:space:]]*\\([[:space:]]*[\"'\"'\"'`]?(https?:)?//|", ""),
    "fetch backtick dropped": ("""["'"'"'`]?(https?:)?//|fonts""", """["'"'"']?(https?:)?//|fonts"""),
    "css url dropped": ("url\\([[:space:]]*[\"'\"'\"']?(https?:)?//|", ""),
    "css import dropped": ("@import|", ""),
    "font hosts dropped": ("|fonts\\.(googleapis|gstatic)", ""),
    "action dropped": ("|action|formaction|", "|formaction|"),
    "poster dropped": ("|poster|", "|"),
    "data dropped": ("|data|ping)", "|ping)"),
    "ping dropped": ("|data|ping)", "|data)"),
    "srcset branch dropped": ("|(srcset|imagesrcset)[[:space:]]*=[[:space:]]*[\"'\"'\"']?[^\"'\"'\"'>]*//", ""),
    "srcset only the first entry": ("[^\"'\"'\"'>]*//|http-equiv", "(https?:)?//|http-equiv"),
    "lines not flattened": ("tr '\\n' ' ' < \"$RUNNER_TEMP/root.html\" > \"$RUNNER_TEMP/root.flat\"", "cp \"$RUNNER_TEMP/root.html\" \"$RUNNER_TEMP/root.flat\""),
    "everything matches": ("(src|href|action|formaction|poster|data|ping)[[:space:]]*=", "(src|href|action|formaction|poster|data|ping|a)[[:space:]]*"),
}


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_each_pattern_mutant_is_caught(name, tmp_path):
    old, new = MUTANTS[name]
    text = CI.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"mutation anchor not found exactly once: {old!r}"
    assert failures(text.replace(old, new), tmp_path) != [], "the mutant survived"


TAIL_MUTANTS = {
    "a grep error passes": ('          if [ "$rc" -ne 1 ]; then\n            echo "::error::the external-reference grep failed with status $rc"; exit 1\n          fi\n', ""),
    "a hit passes": ('          if [ "$rc" -eq 0 ]; then\n            echo "::error::console page references an external URL"; exit 1\n          fi\n', ""),
    "grep errors are swallowed": ('root.flat" || rc=$?', 'root.flat" || true'),
}


@pytest.mark.parametrize("name", sorted(TAIL_MUTANTS))
def test_each_status_handling_mutant_is_caught(name, tmp_path):
    old, new = TAIL_MUTANTS[name]
    text = CI.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"mutation anchor not found exactly once: {old!r}"
    assert tail_problems(text.replace(old, new), tmp_path) != [], "the mutant survived"


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
