"""S9-32: tools/check_one_liners.py keeps its exit contract when the world is broken. A one-liners file that is not UTF-8
or cannot be read, git missing from PATH, a git that hangs, or a git error is ONE printed ``error:`` line and exit 2
(nothing was checked), never a traceback. A pinned file that is not UTF-8 at its commit is read with replacement
characters and is a normal pass or FAIL, not a crash. Throwaway git repositories; every value is made up."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_one_liners_faults", ROOT / "tools" / "check_one_liners.py")
cl = importlib.util.module_from_spec(_spec)
sys.modules["check_one_liners_faults"] = cl
_spec.loader.exec_module(cl)

MARK = "MARKER-6b20"
COMMIT = "a" * 40
TEST_SRC = 'def test_token_expires():\n    """An expired token is refused."""\n    assert refuse("expired")\n'


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


def doc(tmp_path, commit):
    p = tmp_path / "doc.md"
    p.write_text(cl.GLOBAL_LINE.capitalize() + ".\n"
                 f"- ENFORCED: expiring | CITE: tests/test_a.py::test_token_expires @ {commit} | KEY: expired\n",
                 encoding="utf-8")
    return p


def run(capsys, *argv):
    rc = cl.main(list(argv))
    out = capsys.readouterr().out
    assert "Traceback" not in out
    return rc, out


# -- the one-liners file -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("content", [b"\xff\xfe\x00bad", b"# ok\n\xc3\x28\n", MARK.encode() + b"\xff"],
                         ids=["bytes", "truncated-utf8", "marker-then-bad-byte"])
def test_a_non_utf8_file_is_one_error_line_and_exit_2(tmp_path, capsys, content):
    f = tmp_path / "doc.md"
    f.write_bytes(content)
    rc, out = run(capsys, "--file", str(f), "--repo", str(tmp_path))
    assert rc == 2 and out.strip().splitlines() == [f"error: {f} cannot be read as UTF-8 text (UnicodeDecodeError)"]
    assert MARK not in out


def test_an_unreadable_file_is_one_error_line_and_exit_2(tmp_path, capsys, monkeypatch):
    f = tmp_path / "doc.md"
    f.write_text("x", encoding="utf-8")
    real = Path.read_text

    def read_text(self, *a, **k):
        if self == f:
            raise PermissionError(MARK)
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", read_text)
    rc, out = run(capsys, "--file", str(f), "--repo", str(tmp_path))
    assert rc == 2 and "(PermissionError)" in out and MARK not in out


def test_a_missing_file_is_still_exit_2(tmp_path, capsys):
    rc, out = run(capsys, "--file", str(tmp_path / "absent.md"), "--repo", str(tmp_path))
    assert rc == 2 and "does not exist" in out


# -- git ---------------------------------------------------------------------------------------------------------------
def stub_run(monkeypatch, exc):
    def run_(*a, **k):
        raise exc

    monkeypatch.setattr(cl.subprocess, "run", run_)


def test_git_missing_from_path_is_one_error_line_and_exit_2(tmp_path, capsys, monkeypatch):
    stub_run(monkeypatch, FileNotFoundError(MARK))
    rc, out = run(capsys, "--file", str(doc(tmp_path, COMMIT)), "--repo", str(tmp_path))
    assert rc == 2 and out.strip().splitlines()[-1] == "error: git is not on PATH; the pinned commits cannot be checked"
    assert MARK not in out


def test_a_hung_git_is_exit_2_naming_the_commit_and_the_limit(tmp_path, capsys, monkeypatch):
    stub_run(monkeypatch, subprocess.TimeoutExpired(cmd=["git", MARK], timeout=30))
    rc, out = run(capsys, "--file", str(doc(tmp_path, COMMIT)), "--repo", str(tmp_path))
    assert rc == 2
    assert out.strip().splitlines()[-1] == f"error: git did not answer within 30 s (commit {COMMIT[:12]})"
    assert MARK not in out


def test_any_other_os_error_from_git_is_exit_2_with_the_class_only(tmp_path, capsys, monkeypatch):
    stub_run(monkeypatch, PermissionError(MARK))
    rc, out = run(capsys, "--file", str(doc(tmp_path, COMMIT)), "--repo", str(tmp_path))
    assert rc == 2 and "git could not be run (PermissionError)" in out and MARK not in out


def test_every_git_call_has_the_30_second_timeout(repo, tmp_path, capsys, monkeypatch):
    commit = git(repo, "rev-parse", "HEAD")    # before the patch: this helper also uses subprocess.run
    seen = []
    real = subprocess.run

    def run_(*a, **k):
        seen.append(k.get("timeout"))
        return real(*a, **k)

    monkeypatch.setattr(cl.subprocess, "run", run_)
    rc, out = run(capsys, "--file", str(doc(tmp_path, commit)), "--repo", str(repo))
    assert seen and set(seen) == {30} and cl.GIT_TIMEOUT_SECONDS == 30
    assert rc in (0, 1)   # the throwaway document does not carry every required qualifier: only the calls matter


def test_a_pinned_file_that_is_not_utf8_is_read_with_replacement_not_a_crash(repo, tmp_path, capsys):
    (repo / "tests" / "test_a.py").write_bytes(b"# caf\xe9\n" + TEST_SRC.encode())
    git(repo, "commit", "-aq", "-m", "latin-1 comment")
    commit = git(repo, "rev-parse", "HEAD")
    rc, out = run(capsys, "--file", str(doc(tmp_path, commit)), "--repo", str(repo))
    assert "[PASS] test function exists at the commit" in out and "[PASS] the test mentions the key" in out


def test_a_pinned_commit_missing_from_the_clone_is_still_exit_2(repo, tmp_path, capsys):
    rc, out = run(capsys, "--file", str(doc(tmp_path, "b" * 40)), "--repo", str(repo))
    assert rc == 2 and "are not in this clone" in out
