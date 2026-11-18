"""C-1187 (reviewer Q-107 F8): pin the key phrases of the Stage 1 to 3 pre-flight checklists in the deploy runbook.

`docs/runbooks/v1.2-deploy-rollback.md` carries "Stage pre-flight checklists" (C-1163), a reading aid over the numbered
steps: who runs what, which steps are the coordinator's at a go-point, which are Don's own, and what a lane never
does. Q-107 mutated that text twelve ways and none turned a test red, because no test read it. This file reads the
section and pins what a careless edit would silently change. Every pin below was run against its own hand mutant of
the runbook text and went red (the list is in the PR text). It pins WORDS in a document that no code reads: a
rewording that keeps the meaning must change the pin in the same commit, which is the point.

It does not pin that the procedure is right, that any stage is safe to arm, or any soak floor: this repository records
none, and the section says so (`test_the_soak_floors_are_not_invented`)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs" / "runbooks" / "v1.2-deploy-rollback.md"
START = "**Stage pre-flight checklists (C-1163"
END = "**Header files (`op.hdr`)"
STAGES = {
    "1": ("*Stage 1, LOG-ONLY", "*Stage 2, kill-switch only"),
    "2": ("*Stage 2, kill-switch only", "*Stage 3, REQUIRE on all eight"),
    "3": ("*Stage 3, REQUIRE on all eight", None),
}


def _text() -> str:
    return RUNBOOK.read_text(encoding="utf-8").replace("\r\n", "\n")


def _section() -> str:
    text = _text()
    assert text.count(START) == 1 and text.count(END) == 1, "the checklist section markers moved or were duplicated"
    return text[text.index(START):text.index(END)]


def _stage(n: str) -> str:
    sec = _section()
    begin, end = STAGES[n]
    assert sec.count(begin) == 1, begin
    return sec[sec.index(begin):(sec.index(end) if end else len(sec))]


def _flat(s: str) -> str:
    """The text with every run of whitespace, line wraps included, as one space."""
    return " ".join(s.split())


def _steps(block: str) -> list[str]:
    """The numbered items of a stage block, each joined onto one line."""
    items: list[list[str]] = []
    for line in block.splitlines():
        if re.match(r"^\d+\. ", line):
            items.append([line])
        elif items and line.startswith("   "):
            items[-1].append(line.strip())
    return [" ".join(i) for i in items]


# ---- who runs what ------------------------------------------------------------------------------------------------


def test_the_section_says_the_coordinator_runs_stages_one_to_four_at_a_go_point():
    flat = _flat(_section())
    assert "the COORDINATOR runs Stages 1 to 4, each arming or deploy step only at a go-point with its entry checks green" in flat
    assert "and Don's per-go-point confirmation in chat" in flat


def test_a_lane_is_told_to_never_arm_deploy_touch_an_estate_or_read_a_secret():
    flat = _flat(_section())
    assert "A lane never arms, never deploys, never touches an estate, and never reads or prints a secret." in flat


def test_exactly_four_steps_carry_the_coordinator_go_point_mark():
    """Stage 1 step 6, Stage 2 steps 4 and 5, Stage 3 step 4; the fifth occurrence is the sentence that defines the mark."""
    sec = _section()
    assert sec.count("COORDINATOR AT GO-POINT") == 5
    marked = {n: [s for s in _steps(_stage(n)) if "COORDINATOR AT GO-POINT" in s] for n in STAGES}
    assert {n: len(v) for n, v in marked.items()} == {"1": 1, "2": 2, "3": 1}
    assert marked["1"][0].startswith("6. Install the operators file")
    assert [s[:2] for s in marked["2"]] == ["4.", "5."] and marked["3"][0].startswith("4. `FIELD_OPERATOR_REQUIRE=1`")


def test_only_the_key_copy_step_is_dons_own_and_no_step_says_don_only():
    sec = _section()
    own = [s for n in STAGES for s in _steps(_stage(n)) if "DON'S OWN" in s]
    assert len(own) == 1 and own[0].startswith("3. Entry: the four daemon key files")
    assert "DON ONLY" not in sec                      # an arming step is the coordinator's, never labelled Don's


# ---- the arming and rollback steps ---------------------------------------------------------------------------------


def test_stage_three_arms_by_adding_require_deleting_the_override_and_recreating_after_the_gate_prints_eight():
    step4 = _steps(_stage("3"))[3]
    flat = _flat(step4)
    assert "`FIELD_OPERATOR_REQUIRE=1` into `.env`, delete the override, recreate the eight" in flat
    assert "(the gate must print `8` first)" in flat


def test_stage_three_rollback_removes_require_first_then_recreates_in_reverse_order_and_checks_log_only():
    rollback = _flat(_steps(_stage("3"))[5])
    assert rollback.startswith("6. Rollback: remove `FIELD_OPERATOR_REQUIRE` from `.env` first, then recreate")
    assert "the seven first, the kill-switch last" in rollback
    assert rollback.endswith("`$PGC --expect-mode log-only`.")


def test_stage_two_rollback_deletes_the_override_recreates_the_kill_switch_and_checks_log_only():
    rollback = _flat(_steps(_stage("2"))[7])
    assert rollback.startswith("8. Rollback: delete the override")
    assert "`$C up -d --no-build --no-deps killswitch`" in rollback and "`$PGC --expect-mode log-only`" in rollback


def test_stage_one_rollback_is_ready_before_the_arm_and_removes_both_flag_lines():
    step8 = _flat(_steps(_stage("1"))[7])
    assert step8.startswith("8. Rollback ready before the arm") and "delete both flag lines" in step8


def test_every_arming_stage_recreates_the_services_it_changes():
    assert "recreate the eight" in _flat(_steps(_stage("1"))[5])
    assert "recreate the eight" in _flat(_steps(_stage("3"))[3])
    assert "recreate" in _flat(_steps(_stage("3"))[5])


# ---- scoping: the canary, never a domain kill -------------------------------------------------------------------------


def test_stage_three_kill_revive_and_drill_are_run_on_the_canary_only():
    step5 = _flat(_steps(_stage("3"))[4])
    assert "a kill and a revive of the canary answer 200" in step5
    assert "a drill of the canary answers 200" in step5


def test_a_domain_kill_is_never_run_on_an_estate_to_look_for_the_symptom():
    assert "never run a domain kill on an estate to look for it" in _flat(_stage("3"))


# ---- entry checks that carry a decision --------------------------------------------------------------------------------


def test_stage_three_entry_points_at_the_open_item_and_the_open_item_exists_below():
    step2 = _flat(_steps(_stage("3"))[1])
    assert "OPEN ITEM below (rows C1 and T6) resolved or ruled" in step2
    text = _text()
    heading = re.search(r"^\*\*OPEN ITEM \(rows C1 and T6", text, re.M)
    assert heading and heading.start() > text.index(START), "the OPEN ITEM must come AFTER the checklist it is 'below' of"


def test_stage_one_entry_checks_the_key_files_by_size_and_mode_and_never_prints_them():
    step3 = _flat(_steps(_stage("1"))[2])
    assert "(`test -s`, never `cat`; modes by `stat -c '%a %n'` on each directory and file: 700 and 600)" in step3


def test_the_verifier_runs_as_the_machine_identity_never_with_dons_key():
    assert "`svc-verifier-<estate>`, never with Don's key" in _flat(_steps(_stage("1"))[6])


# ---- no soak number is invented ----------------------------------------------------------------------------------------


def test_the_soak_floors_are_not_invented():
    """The section says the repo records no floor for Stages 1 to 3 and quotes only the two it does hold. A duration
    that appears anywhere else in the section (other than the 6 s the exit evidence measures) is a new claim."""
    sec = _section()
    flat = _flat(sec)
    assert "this repo records no soak floor for Stages 1, 2 or 3" in flat
    assert "do not take a number from this list" in flat
    durations = re.findall(r"(?:≥|>=|at least)?\s*\d+(?:\.\d+)?\s*(?:h|hours?|min|minutes?|s|seconds?|days?)\b", sec)
    assert {d.strip().lstrip("≥").strip() for d in durations} <= {"6 s", "5 min", "25 h"}, durations
    assert not re.search(r"(?:≥|>=|at least)\s*\d+", "".join(_stage(n) for n in STAGES))   # no floor inside a stage block
