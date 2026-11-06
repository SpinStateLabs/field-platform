"""C-1192: the `--shard I/N` split of the tools tests is a partition, is deterministic, is balanced, and its hook works.

The unit tests read this directory's real file list. The hook tests start a real pytest in a throw-away project that
holds a copy of conftest.py and _sharding.py and three tiny test files, and read which tests each shard collects."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import _sharding as sh

HERE = Path(__file__).resolve().parent
FILES = sorted(p.name for p in HERE.glob("test_*.py"))


@pytest.mark.parametrize("total", [1, 2, 3, 4, 6])
def test_every_test_file_is_in_exactly_one_shard(total):
    owner = sh.assign(FILES, total)
    assert sorted(owner) == FILES, "every file gets an owner"
    assert set(owner.values()) <= set(range(1, total + 1))
    if total <= len(FILES):
        assert set(owner.values()) == set(range(1, total + 1)), "no shard is left empty"


def test_the_split_does_not_depend_on_the_order_the_files_arrive_in():
    assert sh.assign(FILES, 3) == sh.assign(list(reversed(FILES)), 3) == sh.assign(FILES + FILES, 3)


@pytest.mark.parametrize("total", [2, 3, 4])
def test_the_heaviest_shard_is_close_to_an_even_share(total):
    owner = sh.assign(FILES, total)
    load = [0.0] * total
    for name, shard in owner.items():
        load[shard - 1] += sh.WEIGHTS.get(name, sh.DEFAULT_WEIGHT)
    ideal = sum(load) / total
    assert max(load) <= ideal * 1.25, (load, ideal)


def test_the_three_heaviest_files_never_share_a_shard_with_three_shards():
    heavy = ["test_topology_lint.py", "test_phase_g_check.py", "test_renew_token.py"]
    owner = sh.assign(FILES, 3)
    assert len({owner[h] for h in heavy}) == 3, "the three heaviest files go to three different shards"


@pytest.mark.parametrize("spec, expect", [("1/3", (1, 3)), ("3/3", (3, 3)), ("1/1", (1, 1)), ("12/20", (12, 20))])
def test_a_good_spec_parses(spec, expect):
    assert sh.parse_spec(spec) == expect


@pytest.mark.parametrize("spec", ["", "3", "0/3", "4/3", "1/0", "a/b", "1/", "/3", "-1/3", "1/3/5", "1.5/3"])
def test_a_bad_spec_is_refused(spec):
    with pytest.raises(ValueError):
        sh.parse_spec(spec)


# --- the pytest hook, in a throw-away project -------------------------------------------------------------------------
def _project(tmp_path: Path) -> Path:
    for name in ("conftest.py", "_sharding.py"):
        shutil.copy(HERE / name, tmp_path / name)
    (tmp_path / "test_a.py").write_text("def test_a1():\n    pass\n\n\ndef test_a2():\n    pass\n", encoding="utf-8")
    (tmp_path / "test_b.py").write_text("def test_b1():\n    pass\n", encoding="utf-8")
    (tmp_path / "test_c.py").write_text("def test_c1():\n    pass\n\n\ndef test_c2():\n    pass\n", encoding="utf-8")
    return tmp_path


def _collect(project: Path, *args: str) -> tuple[int, list[str], str]:
    r = subprocess.run([sys.executable, "-I", "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *args],
                       cwd=project, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
    ids = re.findall(r"^(test_\w+\.py::test_\w+)$", r.stdout, flags=re.M)
    return r.returncode, ids, r.stdout + r.stderr


def test_without_the_option_every_test_is_collected(tmp_path):
    rc, ids, _ = _collect(_project(tmp_path))
    assert rc == 0 and len(ids) == 5


def test_the_shards_together_run_every_test_exactly_once(tmp_path):
    project = _project(tmp_path)
    seen: list[str] = []
    for i in (1, 2, 3):
        rc, ids, out = _collect(project, "--shard", f"{i}/3")
        assert rc == 0, out
        seen += ids
    assert sorted(seen) == ["test_a.py::test_a1", "test_a.py::test_a2", "test_b.py::test_b1",
                            "test_c.py::test_c1", "test_c.py::test_c2"]


def test_a_shard_keeps_whole_files_together(tmp_path):
    project = _project(tmp_path)
    for i in (1, 2):
        _, ids, _ = _collect(project, "--shard", f"{i}/2")
        by_file: dict[str, int] = {}
        for t in ids:
            by_file[t.split("::")[0]] = by_file.get(t.split("::")[0], 0) + 1
        expect = {"test_a.py": 2, "test_b.py": 1, "test_c.py": 2}
        assert all(by_file[f] == expect[f] for f in by_file), by_file


def test_a_bad_spec_is_a_usage_error_not_a_silent_full_run(tmp_path):
    rc, ids, out = _collect(_project(tmp_path), "--shard", "4/3")
    assert rc == 4 and ids == [] and "--shard I/N needs 1 <= I <= N" in out
