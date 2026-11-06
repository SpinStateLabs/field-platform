"""C-1191: CI runs `python tools/environment_anchors.py --check`, so a stale `First read` anchor in docs/ENVIRONMENT.md
cannot merge unseen.

The tool landed with C-1116 and its own-doc test, but only the tools suite ran it; a step of its own makes a wrong
anchor a named red step. This file pins that the `tests` job has that step, that it cannot be softened
(`continue-on-error`, `if:`), and that the command exits 1 on a stale anchor and 0 on a good one. The workflow is read
with the strict duplicate-key loader of test_yaml_duplicate_keys.py (B-21), so a repeated key in the file is refused
instead of silently resolved.

Stated limit: this reads the workflow text and runs the command; it does not run GitHub Actions."""
from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
TOOL = ROOT / "tools" / "environment_anchors.py"
COMMAND = "python tools/environment_anchors.py --check"

_spec = importlib.util.spec_from_file_location("yaml_dup_keys", Path(__file__).with_name("test_yaml_duplicate_keys.py"))
_dup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dup)


def anchor_steps(doc: dict) -> list[dict]:
    """Every step of the `tests` job whose run text names the anchor check."""
    steps = doc["jobs"]["tests"]["steps"]
    return [s for s in steps if "environment_anchors.py" in str(s.get("run", ""))]


def problems(doc: dict) -> list[str]:
    """What is wrong with the step, as short messages; an empty list means the step is present and hard."""
    found = anchor_steps(doc)
    if len(found) != 1:
        return [f"expected exactly one anchor step in the tests job, found {len(found)}"]
    step, out = found[0], []
    if str(step["run"]).strip() != COMMAND:
        out.append(f"the step must run exactly `{COMMAND}`")
    for soft in ("continue-on-error", "if"):
        if soft in step:
            out.append(f"the step must not carry `{soft}`")
    return out


def _ci() -> dict:
    return _dup.load_strict(CI.read_text(encoding="utf-8"))


def test_the_tests_job_runs_the_anchor_check_and_nothing_softens_it():
    assert problems(_ci()) == []


def test_a_missing_step_a_changed_command_and_a_softened_step_are_each_caught():
    doc = _ci()
    gone = copy.deepcopy(doc)
    gone["jobs"]["tests"]["steps"] = [s for s in gone["jobs"]["tests"]["steps"] if s not in anchor_steps(doc)]
    assert problems(gone) == ["expected exactly one anchor step in the tests job, found 0"]
    changed = copy.deepcopy(doc)
    anchor_steps(changed)[0]["run"] = "python tools/environment_anchors.py --fix"
    assert problems(changed) == [f"the step must run exactly `{COMMAND}`"]
    for soft, value in (("continue-on-error", True), ("if", "always()")):
        softened = copy.deepcopy(doc)
        anchor_steps(softened)[0][soft] = value
        assert problems(softened) == [f"the step must not carry `{soft}`"]


def test_a_second_step_is_caught_too():
    doc = _ci()
    twice = copy.deepcopy(doc)
    twice["jobs"]["tests"]["steps"].append(copy.deepcopy(anchor_steps(doc)[0]))
    assert problems(twice) == ["expected exactly one anchor step in the tests job, found 2"]


def test_a_repeated_key_in_the_workflow_is_refused_not_resolved():
    with pytest.raises(_dup.DuplicateKey):
        _dup.load_strict(CI.read_text(encoding="utf-8") + "\nname: again\n")


# --- the command itself: exit 1 on a stale anchor, 0 on a good one ------------------------------------------------------
def _repo(tmp_path: Path, anchor: int) -> Path:
    src = tmp_path / "packages" / "demo" / "src" / "demo"
    src.mkdir(parents=True)
    (src / "mod.py").write_text('import os\n\nALPHA = os.environ.get("FIELD_ALPHA")\n', encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ENVIRONMENT.md").write_text(
        "# Environment variables\n\n"
        "| Variable | Component | Default | Accepted values | Security impact | First read |\n"
        "|---|---|---|---|---|---|\n"
        f"| `FIELD_ALPHA` | demo | none | any string | none | demo/mod.py:{anchor} |\n", encoding="utf-8")
    return tmp_path


def _run(root: Path | None) -> subprocess.CompletedProcess:
    args = [sys.executable, "-I", str(TOOL), "--check"] + (["--root", str(root)] if root else [])
    return subprocess.run(args, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)


def test_the_command_is_red_on_a_stale_anchor_and_green_on_a_good_one(tmp_path):
    assert _run(_repo(tmp_path / "good", 3)).returncode == 0
    stale = _run(_repo(tmp_path / "stale", 1))
    assert stale.returncode == 1, stale.stdout + stale.stderr


def test_the_command_is_green_on_this_repository():
    done = _run(None)
    assert done.returncode == 0, done.stdout + done.stderr
