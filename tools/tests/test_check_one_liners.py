"""E1: tools/check_one_liners.py, the E-gate input for v2-one-liners.md. It must go red on exactly the breakage it
exists to catch (a cited test that is gone, a key the test does not mention, a missing qualifier or global line), and
green on a file that is right. Each test builds a throwaway git repository."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_one_liners", ROOT / "tools" / "check_one_liners.py")
cl = importlib.util.module_from_spec(_spec)
sys.modules["check_one_liners"] = cl
_spec.loader.exec_module(cl)

TEST_SRC = '''
def test_token_expires():
    """An expired token is refused."""
    assert refuse("expired")


class TestRevoke:
    def test_revoked_token_is_refused(self):
        assert refuse("revoked")
'''


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(TEST_SRC, encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "tests")
    return tmp_path


def document(commit, *, global_line=True, qualifiers=cl.REQUIRED_QUALIFIERS, cites=None, rows=range(1, 13),
             extra=""):
    out = []
    if global_line:
        out.append(cl.GLOBAL_LINE.capitalize() + ".")
    out.append("Old wording: see v2-one-liners-source.md and the audit.")
    for n in rows:
        out.append(f"## {n} — System {n}")
    out += [f"qualifier: {q}" for q in qualifiers]
    out += cites if cites is not None else [
        f"- ENFORCED: expiring | CITE: tests/test_a.py::test_token_expires @ {commit} | KEY: expired"]
    out.append(extra)
    return "\n".join(out) + "\n"


def run(tmp_path, repo, text, capsys):
    f = tmp_path / "doc.md" if tmp_path != repo else repo / "doc.md"
    f.write_text(text, encoding="utf-8")
    code = cl.main(["--file", str(f), "--repo", str(repo)])
    return code, capsys.readouterr().out


def test_a_right_file_passes(repo, capsys):
    commit = git(repo, "rev-parse", "HEAD")
    code, out = run(repo, repo, document(commit), capsys)
    assert code == 0, out
    assert "[FAIL]" not in out


def test_a_method_inside_a_class_is_found(repo, capsys):
    commit = git(repo, "rev-parse", "--short=8", "HEAD")
    cite = [f"- ENFORCED: revoking | CITE: tests/test_a.py::test_revoked_token_is_refused @ {commit} | KEY: revoked"]
    assert run(repo, repo, document(commit, cites=cite), capsys)[0] == 0


@pytest.mark.parametrize("cite_fmt,failing", [
    ("- ENFORCED: w | CITE: tests/test_a.py::test_gone @ {c} | KEY: expired", "test function exists"),
    ("- ENFORCED: w | CITE: tests/test_missing.py::test_token_expires @ {c} | KEY: expired", "file exists"),
    ("- ENFORCED: w | CITE: tests/test_a.py::test_token_expires @ {bad} | KEY: expired", "commit exists"),
    ("- ENFORCED: w | CITE: tests/test_a.py::test_token_expires @ {c} | KEY: unrelated-word", "mentions the key"),
])
def test_a_bad_citation_fails(cite_fmt, failing, repo, capsys):
    commit = git(repo, "rev-parse", "HEAD")
    cite = [cite_fmt.format(c=commit, bad="0" * 40)]
    code, out = run(repo, repo, document(commit, cites=cite), capsys)
    assert code == 1 and f"[FAIL]" in out and failing in out.split("[FAIL]")[1]


def test_a_test_that_exists_only_after_the_pinned_commit_fails(repo, capsys):
    old = git(repo, "rev-parse", "HEAD")
    (repo / "tests" / "test_a.py").write_text(TEST_SRC + "\ndef test_later():\n    assert 'later'\n", encoding="utf-8")
    git(repo, "commit", "-aq", "-m", "later")
    cite = [f"- ENFORCED: w | CITE: tests/test_a.py::test_later @ {old} | KEY: later"]
    assert run(repo, repo, document(old, cites=cite), capsys)[0] == 1


def test_the_key_is_checked_in_the_named_test_only(repo, capsys):
    """'revoked' occurs in the file, but not in test_token_expires."""
    commit = git(repo, "rev-parse", "HEAD")
    cite = [f"- ENFORCED: w | CITE: tests/test_a.py::test_token_expires @ {commit} | KEY: revoked"]
    assert run(repo, repo, document(commit, cites=cite), capsys)[0] == 1


def test_a_malformed_enforced_line_is_a_failure_not_a_skip(repo, capsys):
    commit = git(repo, "rev-parse", "HEAD")
    bad = ["- ENFORCED: w | CITE: tests/test_a.py::test_token_expires | KEY: expired",      # no commit
           f"- ENFORCED: expiring | CITE: tests/test_a.py::test_token_expires @ {commit} | KEY: expired"]
    code, out = run(repo, repo, document(commit, cites=bad), capsys)
    assert code == 1 and "every ENFORCED line parses" in out.split("[FAIL]")[1]


def test_a_file_with_no_citation_fails(repo, capsys):
    commit = git(repo, "rev-parse", "HEAD")
    assert run(repo, repo, document(commit, cites=[]), capsys)[0] == 1


def test_a_missing_global_line_fails(repo, capsys):
    commit = git(repo, "rev-parse", "HEAD")
    code, out = run(repo, repo, document(commit, global_line=False), capsys)
    assert code == 1 and "global estate-status line" in out.split("[FAIL]")[1]


def test_the_global_line_must_come_first(repo, capsys):
    commit = git(repo, "rev-parse", "HEAD")
    text = "Some other opening line.\n" + document(commit)
    assert run(repo, repo, text, capsys)[0] == 1


@pytest.mark.parametrize("rows", [range(1, 12), range(1, 14), [1, 2, 3, 5, 4, 6, 7, 8, 9, 10, 11, 12]])
def test_the_rows_must_be_twelve_in_the_audit_numbering(rows, repo, capsys):
    commit = git(repo, "rev-parse", "HEAD")
    assert run(repo, repo, document(commit, rows=rows), capsys)[0] == 1


@pytest.mark.parametrize("dropped", list(range(len(cl.REQUIRED_QUALIFIERS))))
def test_every_required_qualifier_is_needed(dropped, repo, capsys):
    commit = git(repo, "rev-parse", "HEAD")
    quals = [q for i, q in enumerate(cl.REQUIRED_QUALIFIERS) if i != dropped]
    code, out = run(repo, repo, document(commit, qualifiers=quals), capsys)
    assert code == 1 and cl.REQUIRED_QUALIFIERS[dropped][:70] in out


def test_qualifiers_compare_by_content_not_by_dash_or_wrapping(repo, capsys):
    commit = git(repo, "rev-parse", "HEAD")
    quals = [q.replace(" - ", " — ").replace("->", "→") for q in cl.REQUIRED_QUALIFIERS]
    quals = [q.replace(" ", "\n", 3) if i % 2 else q for i, q in enumerate(quals)]
    assert run(repo, repo, document(commit, qualifiers=quals), capsys)[0] == 0


def test_a_keyless_row_must_carry_the_exact_text(repo, capsys):
    commit = git(repo, "rev-parse", "HEAD")
    assert run(repo, repo, document(commit, extra=f"KEYLESS: {cl.KEYLESS_TEXT}"), capsys)[0] == 0
    assert run(repo, repo, document(commit, extra="KEYLESS: not verified live"), capsys)[0] == 1


def test_the_provenance_line_is_required(repo, capsys):
    commit = git(repo, "rev-parse", "HEAD")
    text = document(commit).replace("Old wording: see v2-one-liners-source.md and the audit.", "")
    assert run(repo, repo, text, capsys)[0] == 1


def test_a_missing_file_is_a_usage_error(tmp_path, capsys):
    assert cl.main(["--file", str(tmp_path / "nope.md")]) == 2
