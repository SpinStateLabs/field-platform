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
    """The template filled with neutral values that meet the minimum structure."""
    out = []
    for line in gg.TEMPLATE.format(sha=sha).splitlines(True):
        label = line.split(":", 1)[0]
        if label == "Step 4":
            line = f"Step 4: pushed to both remotes at {sha[:8]}\n"
        elif label.startswith("Step "):
            line = f"{label}: {label.lower()} done and noted\n"
        elif label == "CI":
            line = f"CI: green on {sha[:8]} confirmed by Dana Example\n"
        elif label.startswith("Record "):
            line = f"{label}: records/{label.split()[1].lower()}.md\n"
        else:
            line = re.sub(r"<switch>", "demo-switch", line)
            line = re.sub(r"<[^<>]*>", "recorded", line)
        out.append(line)
    return "".join(out)


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
    text = _filled().replace("Record G17: records/g17.md", f"Record G17: {value}")
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
    text = _drop(_filled(), "Record G27") + "\n## Another section\nRecord G27: records/g27.md\n"
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


# ------------------------------------------------- reviewer-8 conditions on PR 841 (C1 structure, C2 one section, Q10)
def _line(text: str, label: str, value: str) -> str:
    return re.sub(rf"^{re.escape(label)}:.*$", lambda _m: f"{label}: {value}", text, flags=re.MULTILINE)


def _all_ok() -> str:
    lines = [f"## PHASE G GATE {SHA}"]
    lines += [f"Step {n}: ok" for n in gg.STEPS] + ["CI: ok"] + [f"Record {r}: ok" for r in gg.RECORDS]
    lines += ["Armed: a | disarm: ok", "Forward-only: ok", "Not-live: ok", "Don inputs: ok"]
    return "\n".join(lines) + "\n"


def test_a_record_whose_every_line_is_ok_fails(tmp_path, capsys):
    rc, out = _run(tmp_path, _all_ok(), capsys)
    assert rc == 1
    fails = [ln for ln in out.splitlines() if ln.startswith("[FAIL]")]
    assert len(fails) == 12 + 1 + 6, out          # every step, CI and every record; the three step-11 lines are free text


@pytest.mark.parametrize("n", [n for n in gg.STEPS if n != 4])
def test_a_one_word_step_value_fails(tmp_path, capsys, n):
    rc, out = _run(tmp_path, _line(_filled(), f"Step {n}", "ok"), capsys)
    assert rc == 1 and out.count("[FAIL]") == 1 and "is one word" in out


def test_step_four_must_name_the_sha(tmp_path, capsys):
    rc, out = _run(tmp_path, _line(_filled(), "Step 4", "pushed to both remotes"), capsys)
    assert rc == 1 and out.count("[FAIL]") == 1 and f"does not name the SHA (its first 8 hex, {SHA[:8]})" in out
    rc, out = _run(tmp_path, _line(_filled(), "Step 4", f"pushed at {SHA[:8].upper()}"), capsys)
    assert rc == 0, out                                           # the 8 hex match without regard to case
    rc, out = _run(tmp_path, _line(_filled(), "Step 4", f"pushed at {OTHER[:8]}"), capsys)
    assert rc == 1 and "does not name the SHA" in out             # another SHA's 8 hex does not count


@pytest.mark.parametrize("value,msg", [
    ("green confirmed by Dana", "does not name the SHA"),
    (f"green on {SHA[:8]}", "does not say 'confirmed by <name>'"),
    (f"green on {SHA[:8]} confirmed by", "does not say 'confirmed by <name>'"),
    (f"green on {SHA[:8]} confirmed by <who>", "empty or a placeholder"),
    (f"green on {OTHER[:8]}, confirmed by Dana", "does not name the SHA"),
])
def test_the_ci_line_names_the_sha_and_who_confirmed(tmp_path, capsys, value, msg):
    rc, out = _run(tmp_path, _line(_filled(), "CI", value), capsys)
    assert rc == 1 and out.count("[FAIL]") == 1 and msg in out


@pytest.mark.parametrize("value", ["ok", "done", "see below", "in the estate", "the record exists"])
def test_a_record_line_that_does_not_say_where_the_record_is_fails(tmp_path, capsys, value):
    rc, out = _run(tmp_path, _line(_filled(), "Record G26", value), capsys)
    assert rc == 1 and out.count("[FAIL]") == 1 and "does not say where the record is" in out


@pytest.mark.parametrize("value", ["docs/records/g26.md", "STATE.md", "C:\\records\\g26.txt", "held @ 0123abc",
                                   "see STATE.md section 4", f"@{SHA[:8]}"])
def test_a_record_line_with_a_path_a_file_or_a_sha_reference_passes(tmp_path, capsys, value):
    rc, out = _run(tmp_path, _line(_filled(), "Record G26", value), capsys)
    assert rc == 0, out


def test_the_free_text_step_eleven_lines_stay_free(tmp_path, capsys):
    text = _line(_line(_line(_filled(), "Forward-only", "none"), "Not-live", "none"), "Don inputs", "none")
    rc, out = _run(tmp_path, text, capsys)
    assert rc == 0, out


def test_the_ci_line_may_carry_an_email_name_in_the_value(tmp_path, capsys):
    rc, out = _run(tmp_path, _line(_filled(), "CI", f"green on {SHA[:8]} confirmed by Dana"), capsys)
    assert rc == 0, out


# C2: exactly one section per SHA, the SHA is the whole heading argument, fenced lines are not a record
def test_two_sections_for_one_sha_fail_whichever_order(tmp_path, capsys):
    good, stale = _filled(), "## PHASE G GATE " + SHA + "\nStep 1: stale\n"
    for text in (good + "\n" + stale, stale + "\n" + good):
        rc, out = _run(tmp_path, text, capsys)
        assert rc == 1 and out.count("[FAIL]") == 1 and "2 sections headed" in out and "exactly one expected" in out


def test_a_section_for_another_sha_beside_this_one_is_fine(tmp_path, capsys):
    rc, out = _run(tmp_path, _filled(OTHER) + "\n" + _filled(), capsys)
    assert rc == 0, out


@pytest.mark.parametrize("heading", [
    f"## PHASE G GATE (superseded; the real one is for {SHA})",
    f"## PHASE G GATE {SHA} (draft)",
    f"## PHASE G GATE {SHA}-old",
    f"## PHASE G GATE for {SHA}",
])
def test_the_sha_must_be_the_whole_heading_argument(tmp_path, capsys, heading):
    text = _filled().replace(f"## PHASE G GATE {SHA}", heading)
    rc, out = _run(tmp_path, text, capsys)
    assert rc == 1 and out.count("[FAIL]") == 1 and "the SHA must be the whole heading argument" in out


def test_the_heading_may_carry_trailing_spaces_and_crlf(tmp_path, capsys):
    text = _filled().replace(f"## PHASE G GATE {SHA}", f"## PHASE G GATE {SHA}   ").replace("\n", "\r\n")
    f = tmp_path / "STATE.md"
    f.write_bytes(text.encode("utf-8"))
    assert gg.main(["--state", str(f), "--sha", SHA]) == 0


@pytest.mark.parametrize("fence", ["```", "~~~", "````", "   ```"])
def test_a_filled_example_inside_a_fenced_block_is_not_the_record(tmp_path, capsys, fence):
    quoted = f"# STATE\n\n{fence}\n{_filled()}{fence.strip()}\n"
    rc, out = _run(tmp_path, quoted, capsys)
    assert rc == 1 and out.count("[FAIL]") == 1 and "no '## PHASE G GATE" in out


def test_fenced_lines_inside_the_real_section_are_ignored(tmp_path, capsys):
    text = _drop(_filled(), "Record G16") + "```\nRecord G16: records/g16.md\n```\n"
    rc, out = _run(tmp_path, text, capsys)
    assert rc == 1 and "record G16: line 'Record G16:' is missing" in out


def test_a_fenced_heading_does_not_end_the_section_or_start_one(tmp_path, capsys):
    text = _filled() + "```\n## Not a heading\n```\n"
    assert _run(tmp_path, text, capsys)[0] == 0
    text = _drop(_filled(), "Don inputs") + "```\n## Not a heading\n```\nDon inputs: none\n"
    rc, out = _run(tmp_path, text, capsys)
    assert rc == 0, out                                            # the fenced '## ' did not close the section


def test_the_section_still_ends_at_the_next_real_heading_after_a_fence(tmp_path, capsys):
    text = _drop(_filled(), "Don inputs") + "```\nx\n```\n## Next\nDon inputs: none\n"
    rc, out = _run(tmp_path, text, capsys)
    assert rc == 1 and "Don inputs" in out


# Q10: --sha is exactly 40 hex
@pytest.mark.parametrize("sha", [SHA[:7], SHA[:8], SHA[:39], SHA + "0", SHA[:39] + "g", ""])
def test_a_sha_that_is_not_exactly_forty_hex_is_refused(tmp_path, capsys, sha):
    f = tmp_path / "STATE.md"
    f.write_text(_filled(), encoding="utf-8")
    assert gg.main(["--state", str(f), "--sha", sha]) == 2


def test_a_seven_hex_sha_does_not_match_a_heading_that_starts_with_it(tmp_path, capsys):
    f = tmp_path / "STATE.md"
    f.write_text(_filled(), encoding="utf-8")
    assert gg.main(["--state", str(f), "--sha", SHA[:7]]) == 2
    assert capsys.readouterr().out == ""


def test_the_printed_template_still_fails_and_names_the_new_minimums(capsys):
    gg.main(["--print-template", "--sha", SHA])
    out = capsys.readouterr().out
    assert "first 8 hex" in out and "confirmed by <who>" in out and "path, file name or @ sha" in out
