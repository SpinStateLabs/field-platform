"""C-591 (reviewer C-539): tools/changelog_gap.py lists the commits of a branch that CHANGELOG.md does not name.

A synthetic repository (made in a temp directory, an invented identity) so the answer is known. The tool is a
report, not a gate: every outcome but a usage or read error exits 0, and the tests pin what the report says."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import changelog_gap as cg  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
           GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid")


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=ENV).stdout


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "commit.gpgsign", "false")
    shas = []
    for n in range(1, 7):
        (r / "f.txt").write_text(f"{n}\n", encoding="utf-8")
        _git(r, "add", "f.txt")
        _git(r, "commit", "-q", "-m", f"commit number {n}")
        shas.append(_git(r, "rev-parse", "HEAD").strip())
    return r, shas


def _run(repo_path, text, tmp_path, capsys):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(text, encoding="utf-8")
    code = cg.main(["--changelog", str(cl), "--ref", "main", "--repo", str(repo_path)])
    return code, capsys.readouterr().out


def test_lists_exactly_the_commits_after_the_newest_named(repo, tmp_path, capsys):
    r, s = repo
    code, out = _run(r, f"entry ({s[2][:8]}) and ({s[0][:8]})\n", tmp_path, capsys)
    lines = out.strip().splitlines()
    assert code == 0
    assert lines[0].startswith(f"compared from {s[2][:8]}") and "3 commit(s) after it, of 6" in lines[0]
    assert [ln.split(" ", 1)[0] for ln in lines[1:-1]] == [s[3][:8], s[4][:8], s[5][:8]]    # oldest first; the last line is the range line
    assert lines[1].endswith("commit number 4")


def test_the_newest_named_wins_whatever_the_order_in_the_file(repo, tmp_path, capsys):
    r, s = repo
    _, out = _run(r, f"({s[4][:7]}) then ({s[1][:7]})\n", tmp_path, capsys)
    assert out.splitlines()[0].startswith(f"compared from {s[4][:8]}") and "1 commit(s) after it" in out


def test_no_gap_when_the_tip_is_named(repo, tmp_path, capsys):
    r, s = repo
    _, out = _run(r, f"({s[5][:8]})\n", tmp_path, capsys)
    assert "0 commit(s) after it, of 6" in out and len(out.strip().splitlines()) == 2       # the comparison and the range line


def test_a_full_length_id_names_a_commit(repo, tmp_path, capsys):
    r, s = repo
    _, out = _run(r, f"{s[3]}\n", tmp_path, capsys)
    assert out.splitlines()[0].startswith(f"compared from {s[3][:8]}") and "2 commit(s)" in out


def test_an_id_shorter_than_seven_characters_names_nothing(repo, tmp_path, capsys):
    r, s = repo
    _, out = _run(r, f"({s[3][:6]}) and abcdef\n", tmp_path, capsys)
    assert out.startswith("no commit of the branch is named")


def test_a_word_that_is_not_a_commit_is_ignored_and_does_not_hide_the_real_one(repo, tmp_path, capsys):
    r, s = repo
    _, out = _run(r, f"deadbee and 0123456789abcdef and ({s[1][:8]})\n", tmp_path, capsys)
    assert out.splitlines()[0].startswith(f"compared from {s[1][:8]}") and "4 commit(s)" in out


def test_an_id_inside_a_longer_word_is_not_an_id(repo, tmp_path, capsys):
    r, s = repo
    _, out = _run(r, f"x{s[2][:8]} {s[3][:8]}y\n", tmp_path, capsys)
    assert out.startswith("no commit of the branch is named")


def test_nothing_named_says_so_and_exits_zero(repo, tmp_path, capsys):
    r, _ = repo
    code, out = _run(r, "no ids here\n", tmp_path, capsys)
    assert code == 0 and out.startswith("no commit of the branch is named")


def test_a_gap_is_reported_not_failed(repo, tmp_path, capsys):
    r, s = repo
    code, _ = _run(r, f"({s[0][:8]})\n", tmp_path, capsys)
    assert code == 0


def test_a_missing_changelog_is_a_usage_error(repo, tmp_path, capsys):
    r, _ = repo
    code = cg.main(["--changelog", str(tmp_path / "nope.md"), "--ref", "main", "--repo", str(r)])
    assert code == 2 and "could not be read" in capsys.readouterr().err


def test_a_bad_ref_is_an_error_not_an_empty_report(repo, tmp_path, capsys):
    r, s = repo
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(f"({s[0][:8]})\n", encoding="utf-8")
    code = cg.main(["--changelog", str(cl), "--ref", "no-such-ref", "--repo", str(r)])
    assert code == 2 and "git log failed" in capsys.readouterr().err


def test_unnamed_commits_inside_the_named_range_are_counted(repo, tmp_path, capsys):
    """Reviewer C-776 F-C776-1: a commit left out BETWEEN two named ones is not after the newest named, so the
    first comparison cannot see it; the second line does."""
    r, s = repo
    _, out = _run(r, f"({s[0][:8]}) ({s[2][:8]}) ({s[4][:8]})\n", tmp_path, capsys)
    lines = out.strip().splitlines()
    assert lines[0].startswith(f"compared from {s[4][:8]}") and "1 commit(s) after it" in lines[0]
    assert lines[-1] == (f"inside the named range (after {s[0][:8]}, before {s[4][:8]}): 2 unnamed commit(s)")


def test_list_earlier_prints_the_unnamed_commits_inside_the_range(repo, tmp_path, capsys):
    r, s = repo
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(f"({s[0][:8]}) ({s[4][:8]})\n", encoding="utf-8")
    code = cg.main(["--changelog", str(cl), "--ref", "main", "--repo", str(r), "--list-earlier"])
    out = capsys.readouterr().out.strip().splitlines()
    assert code == 0
    assert [ln.split(" ", 1)[0] for ln in out[-3:]] == [s[1][:8], s[2][:8], s[3][:8]]


def test_no_unnamed_commit_inside_a_fully_named_range(repo, tmp_path, capsys):
    r, s = repo
    _, out = _run(r, " ".join(f"({x[:8]})" for x in s) + "\n", tmp_path, capsys)
    assert out.strip().splitlines()[-1].endswith(": 0 unnamed commit(s)")


def test_a_single_named_commit_has_an_empty_range(repo, tmp_path, capsys):
    r, s = repo
    _, out = _run(r, f"({s[3][:8]})\n", tmp_path, capsys)
    assert out.strip().splitlines()[-1].endswith(": 0 unnamed commit(s)")


def test_the_real_changelog_is_readable_and_names_commits():
    """A smoke check on the file this tool is for: it holds ids, and the ids are well-formed words."""
    text = (TOOLS.parent / "CHANGELOG.md").read_text(encoding="utf-8")
    assert len(cg.named_ids(text)) > 50


def test_named_ids_are_lowercase_hex_words_only():
    assert cg.named_ids("ABCDEF1 abcdef1 abcdef12 ABCDEf1 0123456") == {"abcdef1", "abcdef12", "0123456"}
