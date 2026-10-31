"""C-932 (reviewer C-43 on PR 387, F-C387-1 and F-C387-2; F-C387-3 is a runbook line, pinned in test_deploy_docs style below).

* A script copied to another directory without its sibling `compose_bind_rules.py` is exit 3 with one line, never a
  `ModuleNotFoundError` traceback and exit 1 (the header promises "no traceback, never 1").
* `network_mode: bridge` (the default mode, spelled out) is refused on purpose ("only absent or none") and says so: the
  message names the rule, not "joins another namespace".
* The deploy runbook's pre-`up` step names the tool, so it is a habit with a place to live.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import compose_resolved_check as crc  # noqa: E402
import test_compose_resolved_bind_c512 as c512  # noqa: E402

REPO = c512.REPO


def test_the_script_copied_alone_is_exit_3_with_one_line_not_a_traceback(tmp_path):
    lone = tmp_path / "compose_resolved_check.py"
    shutil.copy(TOOLS / "compose_resolved_check.py", lone)
    r = subprocess.run([sys.executable, "-I", str(lone), "--repo-root", REPO, "-"], input='{"services": {"s": {}}}',
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "Traceback" not in r.stdout + r.stderr and "ModuleNotFoundError" not in r.stdout + r.stderr
    assert "compose_bind_rules.py" in r.stdout and "next to" in r.stdout and "not checked" in r.stdout
    assert len(r.stdout.strip().splitlines()) == 1


def test_the_script_with_its_sibling_still_works_in_place():
    r = subprocess.run([sys.executable, "-I", str(TOOLS / "compose_resolved_check.py"), "--repo-root", REPO, "-"],
                       input='{"services": {"s": {}}}', capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout, r.stderr)


@pytest.mark.parametrize("mode", ["bridge", "host", "service:x", "container:x", "slirp4netns"])
def test_every_network_mode_but_none_is_refused_and_the_message_names_the_rule(mode):
    problems = crc.check_model({"services": {"s": {"network_mode": mode}}}, REPO)
    assert problems and any("network_mode" in p and "only absent or none" in p for p in problems), problems


@pytest.mark.parametrize("mode", [None, "none"])
def test_an_absent_network_mode_and_none_are_allowed(mode):
    svc = {} if mode is None else {"network_mode": mode}
    assert crc.check_model({"services": {"s": svc}}, REPO) == []


def test_the_other_namespace_options_keep_their_wording():
    problems = crc.check_model({"services": {"s": {"pid": "host"}}}, REPO)
    assert any("pid" in p and "joins another namespace" in p for p in problems), problems


def test_the_deploy_runbook_pre_up_step_names_the_tool():
    text = (ROOT / "docs" / "runbooks" / "v1.2-deploy-rollback.md").read_text(encoding="utf-8")
    assert "compose_resolved_check.py" in text
    line = next(ln for ln in text.splitlines() if "compose_resolved_check.py" in ln)
    assert "--run-compose" in line or "--repo-root" in line
    assert "before" in line.lower() and "up" in line.lower()
