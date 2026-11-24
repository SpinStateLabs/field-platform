"""S6-24: ``deployment_agent run --journal-dir`` that is not usable is ONE ``refused:`` line and exit 2 (it was a
FileExistsError / NotADirectoryError / PermissionError traceback), and a repeated ``--target`` is one target in ``plan`` and
``run`` (it was seeded and rotated twice)."""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from deployment_agent import cli  # noqa: E402


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


# ---- --journal-dir --------------------------------------------------------------------------------------------------------

def test_a_regular_file_as_the_journal_dir_is_refused(tmp_path):
    f = tmp_path / "afile"
    f.write_text("x")
    code, out, err = run("run", "--target", "fly-app-a", "--journal-dir", str(f))
    assert code == 2 and err.count("\n") == 1 and err.startswith("refused: --journal-dir is not usable")
    assert "Traceback" not in err and f.read_text() == "x"
    assert "target fly-app-a" not in out                      # nothing was simulated


def test_a_path_under_a_regular_file_is_refused(tmp_path):
    f = tmp_path / "afile"
    f.write_text("x")
    code, _, err = run("run", "--target", "fly-app-a", "--journal-dir", str(f / "sub" / "j"))
    assert code == 2 and err.startswith("refused: --journal-dir is not usable") and err.count("\n") == 1


def test_a_nul_byte_path_is_refused(tmp_path):
    code, _, err = run("run", "--target", "fly-app-a", "--journal-dir", str(tmp_path) + "/a\x00b")
    assert code == 2 and err.startswith("refused: --journal-dir is not usable")


def test_an_unwritable_directory_is_refused(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        if os.access(ro, os.W_OK):
            pytest.skip("running as a user that ignores permissions")
        code, _, err = run("run", "--target", "fly-app-a", "--journal-dir", str(ro))
        assert code == 2 and err.startswith("refused: --journal-dir is not usable")
        code, _, err = run("run", "--target", "fly-app-a", "--journal-dir", str(ro / "new"))
        assert code == 2 and err.startswith("refused: --journal-dir is not usable")
    finally:
        ro.chmod(0o700)


def test_a_good_or_creatable_journal_dir_still_works(tmp_path):
    code, out, err = run("run", "--target", "fly-app-a", "--journal-dir", str(tmp_path / "a" / "b"))
    assert code == 0 and err == "" and "target fly-app-a:" in out
    assert (tmp_path / "a" / "b" / "journal" / "rotation-fly-app-a.jsonl").is_file()
    code, _, _ = run("run", "--target", "fly-app-a", "--journal-dir", str(tmp_path / "a" / "b"))
    assert code == 0                                                     # an existing directory is fine


def test_no_journal_dir_uses_a_temp_dir(capsys):
    code, out, err = run("run", "--target", "fly-app-a")
    assert code == 0 and "journal:" in out


def test_nothing_is_checked_when_there_is_no_target(tmp_path):
    f = tmp_path / "afile"
    f.write_text("x")
    code, out, err = run("run", "--journal-dir", str(f))
    assert code == 0 and "nothing to simulate" in out        # unchanged: the dir is only needed when something runs


# ---- repeated --target ---------------------------------------------------------------------------------------------------

def test_plan_prints_one_block_per_distinct_target():
    code, out, _ = run("plan", "--target", "fly-app-a", "--target", "fly-app-a")
    assert code == 0 and out.count("target fly-app-a:") == 1


def test_run_simulates_a_repeated_target_once(tmp_path):
    code, out, _ = run("run", "--target", "fly-app-a", "--target", "fly-app-a", "--target", "fly-app-a",
                       "--journal-dir", str(tmp_path))
    assert code == 0 and out.count("target fly-app-a:") == 1
    lines = (tmp_path / "journal" / "rotation-fly-app-a.jsonl").read_text(encoding="utf-8").splitlines()
    assert sum('"state":"planned"' in ln for ln in lines) == 1            # one run, not three


def test_distinct_targets_keep_their_first_occurrence_order(tmp_path):
    code, out, _ = run("run", "--target", "fly-app-b", "--target", "fly-app-a", "--target", "fly-app-b",
                       "--journal-dir", str(tmp_path))
    assert code == 0
    assert [ln.split(":")[0] for ln in out.splitlines() if ln.startswith("target ")] == ["target fly-app-b", "target fly-app-a"]
    code, out, _ = run("plan", "--target", "fly-app-b", "--target", "fly-app-a", "--target", "fly-app-b")
    assert [ln for ln in out.splitlines() if ln.startswith("target ")] == ["target fly-app-b:", "target fly-app-a:"]
