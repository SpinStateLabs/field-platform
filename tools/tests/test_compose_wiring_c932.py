"""C-932 (reviewer C-43 on PR 387, F-C387-1..3): the script copied alone is exit 3 with a message, `network_mode: bridge` is
refused on purpose with an honest message in both layers, and the runbook says the resolved check is an optional operator
step that nothing runs."""
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

import compose_bind_rules as rules  # noqa: E402
import compose_resolved_check as crc  # noqa: E402
import test_compose_static_pins as pins  # noqa: E402

REPO = "/srv-fixture/checkout"
BRIDGE = "network_mode: bridge is refused: only absent or `none` is allowed (bridge is the default, leave the key out)"


# --- F-C387-1: the script copied alone ------------------------------------------------------------------------------------


def test_the_script_copied_alone_is_exit_3_with_a_message_not_a_traceback(tmp_path):
    shutil.copy(TOOLS / "compose_resolved_check.py", tmp_path / "compose_resolved_check.py")
    r = subprocess.run([sys.executable, "-I", str(tmp_path / "compose_resolved_check.py"), "--repo-root", REPO, "-"],
                       input='{"services": {"s": {"image": "x"}}}', capture_output=True, text=True, timeout=60)
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "Traceback" not in r.stderr and "compose_bind_rules" in r.stdout and "copy both files" in r.stdout
    assert "keep the script next to" in r.stdout


def test_the_script_copied_with_its_sibling_works(tmp_path):
    for name in ("compose_resolved_check.py", "compose_bind_rules.py"):
        shutil.copy(TOOLS / name, tmp_path / name)
    r = subprocess.run([sys.executable, "-I", str(tmp_path / "compose_resolved_check.py"), "--repo-root", REPO, "-"],
                       input='{"services": {"s": {"image": "x"}}}', capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout, r.stderr)


# --- F-C387-2: network_mode bridge ----------------------------------------------------------------------------------------


def test_the_shared_message_says_bridge_is_refused_on_purpose():
    assert rules.namespace_problem("network_mode", "bridge") == BRIDGE
    assert rules.namespace_problem("network_mode", None) is None
    assert rules.namespace_problem("network_mode", "none") is None
    assert rules.namespace_problem("network_mode", "host") == "network_mode: host joins another namespace"
    assert rules.namespace_problem("network_mode", "service:x") == "network_mode: service:x joins another namespace"
    assert rules.namespace_problem("pid", "host") == "pid: host joins another namespace"
    assert rules.namespace_problem("pid", None) is None
    assert rules.namespace_problem("ipc", "container:x") == "ipc: container:x joins another namespace"


def test_bridge_is_not_reported_for_another_option():
    assert rules.namespace_problem("pid", "bridge") == "pid: bridge joins another namespace"


def test_the_resolved_layer_refuses_bridge_with_the_honest_message():
    out = crc.check_model({"services": {"s": {"network_mode": "bridge"}}}, REPO)
    assert out == [f"service s: {BRIDGE}"]
    assert crc.check_model({"services": {"s": {"network_mode": "none"}}}, REPO) == []
    assert crc.check_model({"services": {"s": {"image": "x"}}}, REPO) == []
    assert crc.check_model({"services": {"s": {"network_mode": "host"}}}, REPO) == ["service s: network_mode: host joins another namespace"]


def test_the_static_layer_refuses_bridge_with_the_same_message():
    out = pins.key_violations("services:\n  s:\n    image: x\n    network_mode: bridge\n", "services: {}\n")
    assert out == [f"s: {BRIDGE}"]
    assert pins.key_violations("services:\n  s:\n    image: x\n    network_mode: none\n", "services: {}\n") == []
    host = pins.key_violations("services:\n  s:\n    image: x\n    network_mode: host\n", "services: {}\n")
    assert host == ["s: network_mode: host joins another namespace"]


def test_a_non_string_network_mode_is_still_not_a_string():
    assert any("not a string" in line for line in crc.check_model({"services": {"s": {"network_mode": 5}}}, REPO))


# --- F-C387-3: what the runbook says about the check ------------------------------------------------------------------------


def test_the_runbook_names_the_check_as_optional_and_says_nothing_runs_it():
    text = (ROOT / "docs" / "runbooks" / "v1.2-deploy-rollback.md").read_text(encoding="utf-8")
    assert "tools/compose_resolved_check.py --repo-root" in text
    assert "nothing in this repository or in CI runs it" in text and "Optional operator check" in text
    assert text.index("Optional operator check") < text.index("`--force-recreate` is required:")
    # C-1015 (reviewer C-939 F-C939-2): the paragraph comes BEFORE the command it is meant to precede, in step 9
    up = "`docker compose $F up -d --no-build --force-recreate`."
    assert text.count(up) == 1 and text.index("Optional operator check") < text.index(up)
    assert "PyYAML is needed only for a model that is not JSON" in text


def test_the_tool_header_points_at_the_runbook_and_stays_honest():
    assert "NOT WIRED" in crc.__doc__ and "OPTIONAL operator check" in crc.__doc__
    assert "nothing runs it" in crc.__doc__
