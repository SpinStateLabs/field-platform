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


# --- C-1070 (reviewer C-1054 F-C1054-2): a stale or broken sibling is exit 3 with the right diagnosis ------------------------


def _run_with_sibling(tmp_path, sibling_text):
    shutil.copy(TOOLS / "compose_resolved_check.py", tmp_path / "compose_resolved_check.py")
    (tmp_path / "compose_bind_rules.py").write_text(sibling_text, encoding="utf-8")
    return subprocess.run([sys.executable, "-I", str(tmp_path / "compose_resolved_check.py"), "--repo-root", REPO, "-"],
                          input='{"services": {"s": {"image": "x"}}}', capture_output=True, text=True, timeout=60)


def _one_line_exit_3(r):
    out = r.stdout + r.stderr
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "Traceback" not in out and len(r.stdout.strip().splitlines()) == 1, out


@pytest.mark.parametrize("text", [
    "A_HOME = 1\n",                                   # stale: it lacks the names the check imports
    "def broken(:\n",                                 # a syntax error
    "raise RuntimeError('boom')\n",                   # raises at import
    "import no_such_module_c1070\n",                  # a missing dependency of its own
], ids=["stale", "syntax-error", "raises", "missing-dependency"])
def test_a_stale_or_broken_sibling_is_exit_3_one_line_and_says_missing_or_incompatible(tmp_path, text):
    r = _run_with_sibling(tmp_path, text)
    _one_line_exit_3(r)
    assert "missing or incompatible" in r.stdout and "compose_bind_rules" in r.stdout


def test_the_absent_sibling_message_still_says_to_copy_both_files(tmp_path):
    shutil.copy(TOOLS / "compose_resolved_check.py", tmp_path / "compose_resolved_check.py")
    r = subprocess.run([sys.executable, "-I", str(tmp_path / "compose_resolved_check.py"), "--repo-root", REPO, "-"],
                       input='{"services": {"s": {"image": "x"}}}', capture_output=True, text=True, timeout=60)
    _one_line_exit_3(r)
    assert "keep the script next to" in r.stdout and "copy both files" in r.stdout and "missing or incompatible" in r.stdout


def test_a_sibling_that_exits_on_import_does_not_leak_its_text(tmp_path):
    """The one line names the exception class only: the sibling's own text (here a marker) is never printed."""
    r = _run_with_sibling(tmp_path, "raise RuntimeError('MARK-C1070-sibling-text')\n")
    _one_line_exit_3(r)
    assert "MARK-C1070" not in r.stdout + r.stderr and "RuntimeError" in r.stdout


# --- C-1070 (reviewer C-1054 F-C1054-3): a BOM and empty text on a host without PyYAML -----------------------------------------


def test_json_with_a_leading_bom_is_read_even_without_pyyaml(monkeypatch):
    monkeypatch.setattr(crc, "yaml", None)
    assert crc.load_model("\ufeff" + '{"services": {"s": {"image": "x"}}}') == {"services": {"s": {"image": "x"}}}


@pytest.mark.parametrize("text", ["", "   ", "\n\n", "\ufeff", "\ufeff\n"])
def test_empty_text_is_said_to_be_empty_not_blamed_on_pyyaml(monkeypatch, text):
    monkeypatch.setattr(crc, "yaml", None)
    with pytest.raises(ValueError) as e:
        crc.load_model(text)
    assert "empty" in str(e.value) and "PyYAML" not in str(e.value) and not isinstance(e.value, crc.NoYamlError)


def test_the_cli_says_empty_for_empty_input(tmp_path):
    r = subprocess.run([sys.executable, "-I", str(TOOLS / "compose_resolved_check.py"), "--repo-root", REPO, "-"],
                       input="", capture_output=True, text=True, timeout=60)
    assert r.returncode == 3 and "Traceback" not in r.stderr and "empty" in r.stdout and len(r.stdout.strip().splitlines()) == 1


def test_non_json_text_without_pyyaml_still_says_pyyaml_is_missing(monkeypatch):
    monkeypatch.setattr(crc, "yaml", None)
    with pytest.raises(crc.NoYamlError):
        crc.load_model("services:\n  s:\n    image: x\n")


# --- C-1070 (reviewer C-1054 F-C1054-4, -5): the runbook sentences and the long-form volume decision ----------------------------


def _step9_paragraph():
    text = (ROOT / "docs" / "runbooks" / "v1.2-deploy-rollback.md").read_text(encoding="utf-8")
    start = text.index("Optional operator check")
    return " ".join(text[start:text.index("`docker compose $F up -d --no-build --force-recreate`.")].split())


def test_the_runbook_names_the_sibling_file_as_a_prerequisite():
    """F-C1054-4 D1: the check needs tools/compose_bind_rules.py next to it; dropping the sentence left the suite green."""
    para = _step9_paragraph()
    assert "needs `python3` and the file `tools/compose_bind_rules.py` next to it" in para


def test_the_runbook_says_what_exit_2_and_exit_3_mean():
    """F-C1054-4 D2."""
    para = _step9_paragraph()
    assert "exit 0 to go on" in para
    assert "exit 2 (a bind source is refused) or 3 (it could not check) means stop and read the lines it printed" in para


def test_the_runbook_says_the_check_was_not_run_under_docker_in_review():
    """F-C1054-4 D6: an honesty sentence; it must not be dropped quietly."""
    assert "Not run under docker in review." in _step9_paragraph()


def test_the_optional_check_paragraph_names_the_word_before():
    assert "BEFORE the `up` below" in _step9_paragraph()


# F-C1054-5 (M31): the decision is that a long-form volume with a `source` and NO `type` is judged as a bind (compose's
# default for a path-like source), so a refused source in it is refused; requiring `type: bind` would let it through.
def test_a_long_form_volume_with_a_source_and_no_type_is_judged_as_a_bind():
    doc = {"services": {"s": {"image": "x", "volumes": [{"source": "/etc", "target": "/x"}]}}}
    assert crc.check_model(doc, REPO)
    doc["services"]["s"]["volumes"] = [{"type": "bind", "source": "/etc", "target": "/x"}]
    assert crc.check_model(doc, REPO)
    doc["services"]["s"]["volumes"] = [{"type": "volume", "source": "/etc", "target": "/x"}]
    assert crc.check_model(doc, REPO) == []              # a named volume's source is not a host path
