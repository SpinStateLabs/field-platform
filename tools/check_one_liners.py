#!/usr/bin/env python3
"""check_one_liners - the E-gate input for ``docs/capstone-evidence/v2-one-liners.md`` (Phase E, E1).

    python tools/check_one_liners.py [--file PATH] [--repo DIR]

The one-liners file is only worth reading if every word it calls Enforced is backed by a test that exists and that
is about the word. This script reads the file and checks, with git, at the commit each citation pins:

* the citation names a file and a test function (``path::test_name @ <commit>``), and the commit exists;
* that file exists at that commit, and defines that test function (``def test_name``, at module level or in a class, never nested in a function; when the
  name is defined twice in one scope the LAST definition is the one Python runs and the one checked);
* the word's KEY (a short token the author gives with the citation) occurs, case-insensitively, in that test
  function's source at that commit (its name, docstring or body: the "assertion names the word" check). The KEY is
  required and at least 3 non-space characters, so a citation cannot pass by pointing at an unrelated test or by
  naming a letter;
* the file has the global line first, twelve system rows numbered 1 to 12, every REQUIRED QUALIFIER verbatim, an
  old-wording provenance line, and every keyless row carrying "not live-verified - needs ANTHROPIC_API_KEY".

Citation grammar (one per line, anywhere in the file; ``|`` separates fields)::

    - ENFORCED: <word or phrase> | CITE: <path>::<test_name> @ <commit> | KEY: <token>

It proves that the test exists at the commit and mentions the word. It does NOT run the test and cannot judge whether
the test proves the word: that is the independent adversarial review the E-gate also requires. Standard library only.
Exit status: 0 every check passed, 1 a check failed, 2 usage error or a pinned commit that is not in the clone (fetch main).
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILE = ROOT / "docs" / "capstone-evidence" / "v2-one-liners.md"
GLOBAL_LINE = ("estate status is recorded outside this repository; every Enforced word is test/CI-proven; any live "
               "status is Declared")
KEYLESS_TEXT = "not live-verified - needs ANTHROPIC_API_KEY"
SYSTEMS = 12
#: A KEY shorter than this matches almost any test (a letter is in nearly every function): it is a FAIL, not a pass.
MIN_KEY_CHARS = 3

#: The qualifiers the plan (tasks/todo.md, E1) says must survive verbatim. A qualifier that the code does not
#: support is removed from this list only by a reviewed change that says why.
REQUIRED_QUALIFIERS = (
    "API-key scans (file-based, heuristic)",
    "at the agent's action boundary (SDK/@governed; cooperative perimeter)",
    "when FIELD_DOA_ROSTER is set (unset by default); grantor name recorded, not authenticated",
    "OAuth-style",
    "allowlisted, best-effort; only the GB10 canary manifest declares an agent-side endpoint",
    "for agents that check in; check-ins are not made by default",
    "hash-chained, Ed25519-anchored; estate-level retention by segment rotation (mechanism; rotation is not armed by "
    "default - key custody undecided)",
    "R/A/C/I from registry, grant, manifest with labeled defaults",
    "Continuous (content-change detection; semantics by named review; live fetch verified manually, not in CI)",
    "ISO/IEC 42001 (pending text purchase)",
    "crossing-decision service",
    "throttle (per-action windows over self-reported action counts",
    "on-report metering (gateway-metered tokens, self-reported spend",
    "org-wide when deployed as the LLM egress proxy (not the default deployment; platform judge traffic "
    "deliberately passthrough - excluded from hygiene telemetry)",
    "hygiene telemetry rates + sycophancy drift (mechanism; judge off by default)",
    "provision -> decommission, named re-attestation (name recorded, not authenticated)",
    "quarterly (UTC-quarter window), Ed25519-signed by a named signer (CLI; served packs unsigned drafts unless F4)",
)

CITE_RE = re.compile(
    r"^\s*-\s*ENFORCED:\s*(?P<word>.+?)\s*\|\s*CITE:\s*(?P<path>[\w./-]+)::(?P<test>\w+)\s*@\s*(?P<commit>[0-9a-f]{7,40})"
    r"\s*\|\s*KEY:\s*(?P<key>[^|\n]+?)\s*$", re.M)
ROW_RE = re.compile(r"^##\s+(\d+)\s+[-—]\s+\S", re.M)


class Report:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, ok: bool, text: str) -> bool:
        print(f"[{'PASS' if ok else 'FAIL'}] {text}")
        self.passed += ok
        self.failed += not ok
        return ok


GIT_TIMEOUT_SECONDS = 30


class ToolError(Exception):
    """The check could not be run (a usage or environment problem, not a failed check): one printed line, exit 2."""


def _git(repo: Path, *args: str) -> tuple[int, str]:
    """``(returncode, stdout)``. git missing from PATH, a hung git (``GIT_TIMEOUT_SECONDS``) or any other OS error is a
    ``ToolError`` with a fixed text; output bytes that are not UTF-8 are replaced, never raised."""
    commit = re.search(r"[0-9a-f]{7,40}", " ".join(args))
    where = f" (commit {commit.group(0)[:12]})" if commit else ""
    try:
        proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=GIT_TIMEOUT_SECONDS)
    except FileNotFoundError:
        raise ToolError("git is not on PATH; the pinned commits cannot be checked") from None
    except subprocess.TimeoutExpired:
        raise ToolError(f"git did not answer within {GIT_TIMEOUT_SECONDS} s{where}") from None
    except OSError as exc:
        raise ToolError(f"git could not be run ({type(exc).__name__}){where}") from None
    return proc.returncode, proc.stdout


def normalise(text: str) -> str:
    """Compare qualifiers by content, not by dash or arrow typography or line wrapping."""
    text = text.replace("—", "-").replace("–", "-").replace("→", "->")
    return re.sub(r"\s+", " ", text)


def _scope_functions(body: list[ast.stmt]) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """The functions DEFINED in one scope, in source order: its own statements and those of if/try/with/for/while blocks
    (still the same scope), never the inside of a function or a class (a different scope)."""
    found: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append(node)
        elif isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While)):
            found += _scope_functions(node.body) + _scope_functions(node.orelse)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            found += _scope_functions(node.body)
        elif isinstance(node, ast.Try) or type(node).__name__ == "TryStar":
            for part in (node.body, node.orelse, node.finalbody, *[h.body for h in node.handlers]):
                found += _scope_functions(part)
    return found


def test_source(source: str, test: str) -> str | None:
    """The source text of function ``test`` the way Python resolves it: a module-level function (the LAST definition
    of the name, as the later one shadows an earlier one), else a method of a module-level class (the last definition in
    the first class that has one). A function nested inside another function is not a test."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    lines = source.splitlines()

    def text(node) -> str:
        return "\n".join(lines[node.lineno - 1: node.end_lineno])

    named = [f for f in _scope_functions(tree.body) if f.name == test]
    if named:
        return text(named[-1])
    for cls in tree.body:
        if isinstance(cls, ast.ClassDef):
            named = [f for f in _scope_functions(cls.body) if f.name == test]
            if named:
                return text(named[-1])
    return None


def check_citation(repo: Path, rep: Report, word: str, path: str, test: str, commit: str, key: str) -> None:
    label = f"{path}::{test} @ {commit}"
    code, _ = _git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
    if not rep.check(code == 0, f"commit exists: {label}"):
        return
    code, source = _git(repo, "show", f"{commit}:{path}")
    if not rep.check(code == 0, f"file exists at the commit: {label}"):
        return
    body = test_source(source, test)
    if not rep.check(body is not None, f"test function exists at the commit: {label}"):
        return
    if not rep.check(len("".join(key.split())) >= MIN_KEY_CHARS,
                     f"the key is at least {MIN_KEY_CHARS} non-space characters ({key.strip()!r}; word: {word}): {label}"):
        return                      # a letter occurs in almost any test: it cannot show the test is about the word
    rep.check(key.strip().lower() in body.lower(), f"the test mentions the key {key.strip()!r} (word: {word}): {label}")


def check_file(path: Path, repo: Path) -> int:
    rep = Report()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:       # the class only: a decode error's text names a byte and a position
        raise ToolError(f"{path} cannot be read as UTF-8 text ({type(exc).__name__})") from None
    flat = normalise(text)
    body = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    first = normalise(body[0]).lower().lstrip("*> ") if body else ""
    rep.check(first.startswith(GLOBAL_LINE.lower()), "the global estate-status line comes first")
    rows = [int(n) for n in ROW_RE.findall(text)]
    rep.check(rows == list(range(1, SYSTEMS + 1)), f"{SYSTEMS} system rows numbered 1 to {SYSTEMS} in order (found {rows})")
    rep.check("v2-one-liners-source.md" in text and "audit" in text.lower(),
              "the old-wording provenance is stated (cites v2-one-liners-source.md and the audit)")
    for qualifier in REQUIRED_QUALIFIERS:
        rep.check(normalise(qualifier) in flat, f"required qualifier present verbatim: {qualifier[:70]}")
    cites = list(CITE_RE.finditer(text))
    rep.check(len(cites) > 0, f"the file has Enforced citations ({len(cites)})")
    # every ENFORCED line must parse: a malformed one would silently escape the check
    enforced_lines = [ln for ln in text.splitlines() if re.match(r"^\s*-\s*ENFORCED:", ln)]
    rep.check(len(enforced_lines) == len(cites),
              f"every ENFORCED line parses as a citation ({len(cites)} of {len(enforced_lines)})")
    missing = sorted({m["commit"] for m in cites if _git(repo, "cat-file", "-e", f"{m['commit']}^{{commit}}")[0] != 0})
    if missing:
        print(f"error: {len(missing)} pinned commit(s) are not in this clone ({', '.join(missing)}): "
              "run `git fetch origin main` (or deepen a shallow clone) and check again")
        return 2
    for m in cites:
        check_citation(repo, rep, m["word"], m["path"], m["test"], m["commit"], m["key"])
    # keyless rows: a line that says KEYLESS must carry the exact text
    for ln in text.splitlines():
        if re.search(r"\bKEYLESS\b", ln):
            rep.check(KEYLESS_TEXT in ln, f"keyless row carries the exact text: {ln.strip()[:70]}")
    print(f"\n{rep.passed}/{rep.passed + rep.failed} checks passed")
    return 0 if rep.failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="check_one_liners", description=__doc__.split("\n\n")[0])
    ap.add_argument("--file", type=Path, default=DEFAULT_FILE)
    ap.add_argument("--repo", type=Path, default=ROOT)
    args = ap.parse_args(argv)
    if not args.file.is_file():
        print(f"error: {args.file} does not exist")
        return 2
    try:
        return check_file(args.file, args.repo)
    except ToolError as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
