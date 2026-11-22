"""P308 (carried from e_gate in the superseded PR 308): tools/check_one_liners.py cross-checks a service README row's
status against the status E1 gives it. A mismatch in EITHER direction fails, as do a missing, ambiguous or malformed
row reference; the real E1 file references an Enforced and a Declared row for every one of the twelve systems."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_one_liners_p308", ROOT / "tools" / "check_one_liners.py")
cl = importlib.util.module_from_spec(_spec)
sys.modules["check_one_liners_p308"] = cl
_spec.loader.exec_module(cl)

TEST_SRC = '''
def test_token_expires():
    """An expired token is refused."""
    assert refuse("expired")
'''

README = """# demo-service

| Guarantee | Status | How |
|---|---|---|
| Tokens bind to a scope | **Enforced in code** | model validator |
| Tokens bind to a scope when armed | **Enforced in code when an operator mode is armed** | guard |
| The caller is the grantor | **Declared only** | a recorded string |
| A cell with a \\| pipe in it | **Declared only** (mechanism only) | text |
"""
README_PATH = "services/demo-service/README.md"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(TEST_SRC, encoding="utf-8")
    readme = tmp_path / README_PATH
    readme.parent.mkdir(parents=True)
    readme.write_text(README, encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "tests")
    return tmp_path


def document(commit, readme_lines):
    out = [cl.GLOBAL_LINE.capitalize() + ".", "Old wording: see v2-one-liners-source.md and the audit."]
    out += [f"## {n} — System {n}" for n in range(1, 13)]
    out += [f"qualifier: {q}" for q in cl.REQUIRED_QUALIFIERS]
    out.append(f"- ENFORCED: expiring | CITE: tests/test_a.py::test_token_expires @ {commit} | KEY: expired")
    out += readme_lines
    return "\n".join(out) + "\n"


def run(repo, readme_lines, capsys):
    commit = git(repo, "rev-parse", "HEAD")
    f = repo / "doc.md"
    f.write_text(document(commit, readme_lines), encoding="utf-8")
    code = cl.main(["--file", str(f), "--repo", str(repo)])
    return code, capsys.readouterr().out


def row(prefix, status, path=README_PATH):
    return f"- README-ROW: {path} | ROW: {prefix} | STATUS: {status}"


def test_matching_rows_pass(repo, capsys):
    code, out = run(repo, [row("Tokens bind to a scope when armed", "Enforced"),
                           row("The caller is", "Declared")], capsys)
    assert code == 0, out
    assert "[FAIL]" not in out
    assert "every README-ROW line parses (2 of 2)" in out


def test_e1_enforced_but_readme_declared_fails(repo, capsys):
    code, out = run(repo, [row("The caller is", "Enforced")], capsys)
    assert code == 1
    assert "[FAIL] the README row says Declared, E1 says Enforced" in out


def test_e1_declared_but_readme_enforced_fails(repo, capsys):
    code, out = run(repo, [row("Tokens bind to a scope when armed", "Declared")], capsys)
    assert code == 1
    assert "[FAIL] the README row says Enforced, E1 says Declared" in out


def test_a_missing_row_fails(repo, capsys):
    code, out = run(repo, [row("No such guarantee", "Enforced")], capsys)
    assert code == 1
    assert "[FAIL] the README row is found exactly once (0 found)" in out


def test_an_ambiguous_row_fails(repo, capsys):
    # "Tokens bind to a scope" starts two rows: the reference must pick exactly one
    code, out = run(repo, [row("Tokens bind to a scope", "Enforced")], capsys)
    assert code == 1
    assert "[FAIL] the README row is found exactly once (2 found)" in out


def test_a_missing_readme_fails(repo, capsys):
    code, out = run(repo, [row("Tokens bind", "Enforced", path="services/no-such-service/README.md")], capsys)
    assert code == 1
    assert "[FAIL] README exists and reads as UTF-8" in out


@pytest.mark.parametrize("line", [
    f"- README-ROW: {README_PATH} | ROW: The caller is | STATUS: Maybe",
    f"- README-ROW: {README_PATH} | ROW: The caller is",
    "- README-ROW: README.md | ROW: The caller is | STATUS: Declared",
    f"- README-ROW: {README_PATH} | ROW:  | STATUS: Declared",
], ids=["unknown status", "no status", "not a service README", "empty row"])
def test_a_malformed_readme_row_line_is_a_failure_not_a_skip(line, repo, capsys):
    code, out = run(repo, [line], capsys)
    assert code == 1
    assert "[FAIL] every README-ROW line parses (0 of 1)" in out


def test_an_escaped_pipe_stays_inside_its_cell(repo, capsys):
    # split on the escaped pipe, the row's second cell would be "pipe in it" (no status) and the row would not be found
    code, out = run(repo, [row("A cell with a", "Declared")], capsys)
    assert code == 0, out
    assert cl.readme_table_rows(README)[-1] == ("A cell with a \\| pipe in it", "**Declared only** (mechanism only)")


def test_rows_are_matched_by_content_not_case_or_spacing(repo, capsys):
    code, out = run(repo, [row("the   CALLER is", "Declared")], capsys)
    assert code == 0, out


def test_the_real_file_references_an_enforced_and_a_declared_row_for_every_system():
    text = cl.DEFAULT_FILE.read_text(encoding="utf-8")
    sections = re.split(r"^## (\d+) [-—] ", text, flags=re.M)
    found = {int(sections[i]): sections[i + 1] for i in range(1, len(sections) - 1, 2) if sections[i].isdigit()}
    assert sorted(found) == list(range(1, 13))
    for n, body in found.items():
        statuses = {m["status"] for m in cl.README_ROW_RE.finditer(body)}
        assert statuses == {"Enforced", "Declared"}, (n, statuses)


def test_the_real_file_readme_rows_match_the_readmes(capsys):
    """Every README-ROW in the real E1 file holds against this checkout (no git history needed)."""
    rep = cl.Report()
    for m in cl.README_ROW_RE.finditer(cl.DEFAULT_FILE.read_text(encoding="utf-8")):
        cl.check_readme_row(cl.ROOT, rep, m["path"], m["row"], m["status"])
    out = capsys.readouterr().out
    assert rep.failed == 0 and rep.passed >= 48, out
