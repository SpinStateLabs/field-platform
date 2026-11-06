"""G28: tools/g_gate_check.py walks the Phase G gate template (steps 1 to 12) as a checklist over one STATE.md record.

Every test builds its record in tmp_path from the tool's own --print-template text, filled with neutral dummy values.
Nothing here names an estate, a key or a host.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "g_gate_check.py"
_spec = importlib.util.spec_from_file_location("g_gate_check", TOOL)
gg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gg)

SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER = "fedcba9876543210fedcba9876543210fedcba98"


def _filled(sha: str = SHA) -> str:
    text = gg.TEMPLATE.format(sha=sha)
    text = re.sub(r"<(?:switch)>", "demo-switch", text)
    return re.sub(r"<[^<>]*>", "recorded", text)


def _run(tmp_path: Path, text: str, capsys, sha: str = SHA):
    f = tmp_path / "STATE.md"
    f.write_text(text, encoding="utf-8")
    rc = gg.main(["--state", str(f), "--sha", sha])
    return rc, capsys.readouterr().out


def _drop(text: str, label: str) -> str:
    return "".join(ln for ln in text.splitlines(True) if not ln.startswith(label + ":"))


def test_complete_record_passes(tmp_path, capsys):
    rc, out = _run(tmp_path, "# STATE\n\n" + _filled() + "\n## Next section\nStep 1: ignored\n", capsys)
    assert rc == 0, out
    assert "[FAIL]" not in out
    n = len(gg.STEPS) + len(gg.RECORDS) + 1 + 1 + 3 + 1   # steps, records, CI, armed line, 3 step-11 labels, heading
    assert out.strip().splitlines()[-1] == f"{n}/{n} checks passed"


def test_printed_template_fails_every_line(tmp_path, capsys):
    f = tmp_path / "STATE.md"
    gg.main(["--print-template", "--sha", SHA])
    f.write_text(capsys.readouterr().out, encoding="utf-8")
    rc = gg.main(["--state", str(f), "--sha", SHA])
    out = capsys.readouterr().out
    assert rc == 1
    assert out.count("[FAIL]") == 12 + 1 + 6 + 1 + 3   # steps, CI, records, armed (no switch), forward/not-live/Don
    assert "1/" in out.strip().splitlines()[-1]          # only the heading passes


@pytest.mark.parametrize("rec", gg.RECORDS)
def test_each_missing_record_fails_alone(tmp_path, capsys, rec):
    rc, out = _run(tmp_path, _drop(_filled(), f"Record {rec}"), capsys)
    assert rc == 1
    fails = [ln for ln in out.splitlines() if ln.startswith("[FAIL]")]
    assert len(fails) == 1 and f"record {rec}" in fails[0] and "missing" in fails[0]


@pytest.mark.parametrize("n", gg.STEPS)
def test_each_missing_step_fails_alone(tmp_path, capsys, n):
    rc, out = _run(tmp_path, _drop(_filled(), f"Step {n}"), capsys)
    assert rc == 1
    fails = [ln for ln in out.splitlines() if ln.startswith("[FAIL]")]
    assert len(fails) == 1 and f"step {n} (" in fails[0]


@pytest.mark.parametrize("label", ["CI", "Forward-only", "Not-live", "Don inputs", "Armed"])
def test_each_missing_summary_line_fails_alone(tmp_path, capsys, label):
    rc, out = _run(tmp_path, _drop(_filled(), label), capsys)
    assert rc == 1
    assert sum(ln.startswith("[FAIL]") for ln in out.splitlines()) == 1


@pytest.mark.parametrize("value", ["", "TBD", "todo", "<fill in>", "...", "?"])
def test_placeholder_values_fail(tmp_path, capsys, value):
    text = _filled().replace("Record G17: recorded", f"Record G17: {value}")
    rc, out = _run(tmp_path, text, capsys)
    assert rc == 1
    assert "record G17: line 'Record G17:' is empty or a placeholder" in out


def test_armed_switch_without_disarm_fails(tmp_path, capsys):
    text = _filled().replace("Armed: demo-switch | disarm: recorded", "Armed: demo-switch | disarm:")
    rc, out = _run(tmp_path, text, capsys)
    assert rc == 1
    assert "switch 'demo-switch' has no disarm line" in out
    rc, out = _run(tmp_path, _filled().replace("Armed: demo-switch | disarm: recorded", "Armed: demo-switch"), capsys)
    assert rc == 1 and "no switch name before '| disarm:'" in out


def test_each_armed_line_needs_its_own_disarm(tmp_path, capsys):
    text = _filled() + "Armed: second-switch | disarm:\n"
    rc, out = _run(tmp_path, text.replace("\n## ", "\n## "), capsys)
    assert rc == 1
    assert out.count("[FAIL]") == 1 and "'second-switch' has no disarm line" in out


def test_record_for_another_sha_does_not_count(tmp_path, capsys):
    rc, out = _run(tmp_path, _filled(OTHER), capsys)
    assert rc == 1
    assert out.count("[FAIL]") == 1 and SHA in out


def test_lines_after_the_next_heading_do_not_count(tmp_path, capsys):
    text = _drop(_filled(), "Record G27") + "\n## Another section\nRecord G27: recorded\n"
    rc, out = _run(tmp_path, text, capsys)
    assert rc == 1 and "record G27" in out


def test_duplicate_line_fails(tmp_path, capsys):
    rc, out = _run(tmp_path, _filled() + "Step 3: again\n", capsys)
    assert rc == 1 and "appears 2 times" in out


@pytest.mark.parametrize("args", [[], ["--state", "x"], ["--sha", SHA], ["--state", "x", "--sha", "abc"],
                                  ["--state", "x", "--sha", SHA.upper()[:39]]])
def test_usage_is_refused_with_2(args, capsys):
    assert gg.main(args) == 2
    assert capsys.readouterr().out == ""


def test_unreadable_file_is_refused_with_2(tmp_path, capsys):
    assert gg.main(["--state", str(tmp_path / "missing.md"), "--sha", SHA]) == 2


def test_check_reads_nothing_but_the_given_file():
    src = TOOL.read_text(encoding="utf-8")
    for banned in ("os.environ", "getenv", "socket", "urllib", "subprocess", "http"):
        assert banned not in src, banned


def test_repo_state_md_has_no_unfinished_gate_record():
    """The repository's own STATE.md must not carry a gate record that fails: either none, or a passing one."""
    state = Path(__file__).resolve().parents[2] / "STATE.md"
    text = state.read_text(encoding="utf-8")
    for m in re.finditer(r"^##\s+PHASE G GATE\s+([0-9a-f]{40})", text, re.MULTILINE):
        assert all(ok for ok, _ in gg.check(text, m.group(1))), m.group(1)
