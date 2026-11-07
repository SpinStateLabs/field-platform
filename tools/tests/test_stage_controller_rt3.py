"""RT-HARD-3 F-H3-1 and F-H3-2 (reviewer-8, MEDIUM) on tools/stage_controller.py.

F-H3-1: after "ROLLBACK FAILED ... act by hand" (or a stage that never reached a terminal row) a new run must be
refused until somebody records `ack-rollback` for that stage.
F-H3-2: two live runs on one records file must not both execute: an exclusive lock for the live run.

A fake driver and a temporary records file only. No estate, no alert is sent (env is empty), every value is made up."""
from __future__ import annotations

import importlib.util
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("stage_controller_rt3", ROOT / "tools" / "stage_controller.py")
sc = importlib.util.module_from_spec(_spec)
sys.modules["stage_controller_rt3"] = sc
_spec.loader.exec_module(sc)

GO = "Don: go to stage"
SHA = "a" * 40


class Driver:
    """Records its calls. ``fail_do[step]`` makes that step raise that many times; ``fail_check[step]`` returns aborts;
    ``gate`` (a threading.Event) makes the first arming ``do`` wait, so a second run can be attempted meanwhile."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.fail_do: dict[str, int] = {}
        self.fail_check: dict[str, list[str]] = {}
        self.entered = threading.Event()
        self.gate: threading.Event | None = None
        self.delay = 0.0
        self._now = {s: {k: 0 for k in sc.COUNTER_KEYS} for s in sc.EIGHT_SERVICES} if hasattr(sc, "EIGHT_SERVICES") else {}

    def counters(self):
        return {s: dict(c) for s, c in self._now.items()} or {"killswitch": {k: 0 for k in sc.COUNTER_KEYS}}

    def do(self, stage, step):
        self.calls.append(("do", stage, step))
        self.entered.set()
        if self.gate is not None:
            assert self.gate.wait(10)
        if self.delay:
            time.sleep(self.delay)
        if self.fail_do.get(step, 0) > 0:
            self.fail_do[step] -= 1
            raise RuntimeError("driver failure")

    def check(self, stage, step):
        self.calls.append(("check", stage, step))
        return self.fail_check.get(step, [])

    def dos(self):
        return [c[2] for c in self.calls if c[0] == "do"]


def _records(tmp_path):
    r = sc.Records(tmp_path / "records.jsonl")
    r.append("alerts_proven", ok=True)
    r.append("gate", gate="G22", ok=True)
    r.append("gate", gate="G18", ok=True)
    r.append("gate", gate="G21", ok=True)
    r.append("stage_done", stage=2)
    return r


def _ctl(records, driver):
    return sc.Controller(records, driver, estate="gb10", env={})


def _fail_stage2(records):
    """A Stage 2 run whose check fails and whose first rollback step raises: ends in ``rollback_failed``."""
    d = Driver()
    d.fail_check["write_override"] = ["canary_c0_failed"]
    d.fail_do["delete_override"] = 1
    result = _ctl(records, d).run(2, go_sentence=GO, live=True)
    assert result.status == "rollback_failed", result
    return d


def _kinds(records):
    return [r["kind"] for r in records.rows()]


# ---------------------------------------------------------------- F-H3-1: a failed rollback needs an ack

def test_a_stage_whose_rollback_failed_is_refused_until_the_hand_work_is_acknowledged(tmp_path):
    records = _records(tmp_path)
    _fail_stage2(records)
    d2 = Driver()
    with pytest.raises(sc.Refused) as ei:
        _ctl(records, d2).run(2, go_sentence=GO, live=True)
    assert ei.value.reason == "rollback_failed_unresolved"
    assert d2.calls == []                                           # nothing ran on the half-rolled-back estate
    assert _kinds(records)[-1] == "refused" and records.rows()[-1]["reason"] == "rollback_failed_unresolved"


def test_a_dry_run_plan_is_refused_too(tmp_path):
    records = _records(tmp_path)
    _fail_stage2(records)
    with pytest.raises(sc.Refused) as ei:
        _ctl(records, None).run(2, go_sentence=GO)
    assert ei.value.reason == "rollback_failed_unresolved"


def test_an_ack_for_that_stage_lets_the_stage_start_again(tmp_path):
    records = _records(tmp_path)
    _fail_stage2(records)
    assert sc.main(["record", "ack-rollback", "--stage", "2", "--records", str(records.path)]) == 0
    assert _kinds(records)[-1] == "rollback_ack" and records.rows()[-1]["stage"] == 2
    d2 = Driver()
    assert _ctl(records, d2).run(2, go_sentence=GO, live=True).status == "completed"


def test_an_ack_of_another_stage_does_not_clear_it(tmp_path):
    records = _records(tmp_path)
    _fail_stage2(records)
    records.append("rollback_ack", stage=1)
    records.append("rollback_ack", stage=3)
    with pytest.raises(sc.Refused) as ei:
        _ctl(records, Driver()).run(2, go_sentence=GO, live=True)
    assert ei.value.reason == "rollback_failed_unresolved"


def test_an_ack_written_before_the_failure_does_not_count(tmp_path):
    records = _records(tmp_path)
    records.append("rollback_ack", stage=2)
    _fail_stage2(records)
    with pytest.raises(sc.Refused) as ei:
        _ctl(records, Driver()).run(2, go_sentence=GO, live=True)
    assert ei.value.reason == "rollback_failed_unresolved"


def test_a_second_failure_after_an_ack_needs_a_new_ack(tmp_path):
    records = _records(tmp_path)
    _fail_stage2(records)
    records.append("rollback_ack", stage=2)
    _fail_stage2(records)
    with pytest.raises(sc.Refused):
        _ctl(records, Driver()).run(2, go_sentence=GO, live=True)
    records.append("rollback_ack", stage=2)
    assert _ctl(records, Driver()).run(2, go_sentence=GO, live=True).status == "completed"


@pytest.mark.parametrize("rows", [
    [("stage_start", {})],
    [("stage_start", {}), ("step_done", {"step": "write_override"})],
    [("stage_start", {}), ("abort", {"condition": "canary_c0_failed"})],
    [("stage_start", {}), ("abort", {"condition": "canary_c0_failed"}), ("rollback_step", {"step": "delete_override"})],
], ids=["start-only", "after-a-step", "abort-without-rollback", "rollback-interrupted"])
def test_a_stage_that_never_reached_a_terminal_row_is_in_progress(tmp_path, rows):
    records = _records(tmp_path)
    for kind, extra in rows:
        records.append(kind, stage=2, **extra)
    d = Driver()
    with pytest.raises(sc.Refused) as ei:
        _ctl(records, d).run(2, go_sentence=GO, live=True)
    assert ei.value.reason == "stage_in_progress" and d.calls == []
    records.append("rollback_ack", stage=2)                        # the operator says it was dealt with by hand
    assert _ctl(records, Driver()).run(2, go_sentence=GO, live=True).status == "completed"


def test_an_in_progress_row_of_another_stage_does_not_block_this_one(tmp_path):
    records = _records(tmp_path)
    records.append("stage_start", stage=1)
    assert _ctl(records, Driver()).run(2, go_sentence=GO, live=True).status == "completed"


def test_a_clean_rollback_or_a_finished_stage_may_run_again(tmp_path):
    records = _records(tmp_path)
    d = Driver()
    d.fail_check["write_override"] = ["canary_c0_failed"]
    assert _ctl(records, d).run(2, go_sentence=GO, live=True).status == "aborted_rolled_back"
    assert _ctl(records, Driver()).run(2, go_sentence=GO, live=True).status == "completed"
    assert _ctl(records, Driver()).run(2, go_sentence=GO, live=True).status == "completed"   # stage_done: a re-run is allowed


def test_the_unresolved_reason_is_checked_after_the_ordinary_preconditions(tmp_path):
    records = sc.Records(tmp_path / "records.jsonl")               # no alerts_proven at all
    records.append("rollback_failed", stage=2, condition="canary_c0_failed", step="delete_override")
    with pytest.raises(sc.Refused) as ei:
        _ctl(records, Driver()).run(2, go_sentence=GO, live=True)
    assert ei.value.reason == "alerts_not_proven"


# ---------------------------------------------------------------- the ack-rollback command

def test_ack_rollback_needs_a_known_stage(tmp_path, capsys):
    path = str(tmp_path / "r.jsonl")
    assert sc.main(["record", "ack-rollback", "--records", path]) == 2
    assert sc.main(["record", "ack-rollback", "--stage", "9", "--records", path]) == 2
    assert sc.main(["record", "ack-rollback", "--stage", "0", "--records", path]) == 2
    assert not Path(path).exists()                                 # nothing was written by a refused ack
    out = capsys.readouterr().out
    assert out.count("refused:") == 3


def test_ack_rollback_writes_only_its_stage_and_no_free_text(tmp_path, capsys):
    path = tmp_path / "r.jsonl"
    assert sc.main(["record", "ack-rollback", "--stage", "3", "--records", str(path)]) == 0
    row = sc.Records(path).rows()[-1]
    assert set(row) == {"ts", "kind", "stage"} and row["kind"] == "rollback_ack" and row["stage"] == 3
    assert "recorded ack-rollback" in capsys.readouterr().out


def test_the_other_record_verbs_are_unchanged(tmp_path):
    path = str(tmp_path / "r.jsonl")
    assert sc.main(["record", "alerts-proven", "--records", path]) == 0
    assert sc.main(["record", "gate", "G22", "--records", path]) == 0
    assert sc.main(["record", "gate", "--records", path]) == 2


# ---------------------------------------------------------------- F-H3-2: one live run at a time

def test_a_second_live_run_while_the_first_is_inside_a_step_is_refused(tmp_path):
    records = _records(tmp_path)
    a, b = Driver(), Driver()
    a.gate = threading.Event()
    box = {}
    t = threading.Thread(target=lambda: box.update(r=_ctl(records, a).run(2, go_sentence=GO, live=True)))
    t.start()
    try:
        assert a.entered.wait(10)
        with pytest.raises(sc.Refused) as ei:
            _ctl(sc.Records(records.path), b).run(2, go_sentence=GO, live=True)
        assert ei.value.reason == "run_in_progress" and b.calls == []
        assert records.rows()[-1]["kind"] == "refused" and records.rows()[-1]["reason"] == "run_in_progress"
    finally:
        a.gate.set()
        t.join(10)
    assert box["r"].status == "completed" and a.dos() == ["write_override", "recreate_killswitch"]
    assert [r["kind"] for r in records.rows()].count("stage_start") == 1       # only the first run started the stage


def test_two_overlapping_runs_execute_each_step_once(tmp_path):
    records = _records(tmp_path)
    drivers = [Driver(), Driver()]
    for d in drivers:
        d.delay = 0.15
    outcome: list[str] = []

    def go(d, wait):
        time.sleep(wait)
        try:
            outcome.append(_ctl(sc.Records(records.path), d).run(2, go_sentence=GO, live=True).status)
        except sc.Refused as exc:
            outcome.append(exc.reason)

    threads = [threading.Thread(target=go, args=(drivers[0], 0)), threading.Thread(target=go, args=(drivers[1], 0.05))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    assert sorted(outcome) == ["completed", "run_in_progress"], outcome
    assert sorted(len(d.dos()) for d in drivers) == [0, 2]            # one run did both steps, the other did none


def test_the_lock_is_released_after_a_run_and_after_a_refusal(tmp_path):
    records = _records(tmp_path)
    assert _ctl(records, Driver()).run(2, go_sentence=GO, live=True).status == "completed"
    with pytest.raises(sc.Refused):
        _ctl(records, Driver()).run(2, live=True)                    # go_sentence_missing: refused after taking the lock
    assert _ctl(records, Driver()).run(2, go_sentence=GO, live=True).status == "completed"


def test_the_lock_is_released_when_a_run_is_interrupted(tmp_path):
    records = _records(tmp_path)

    class Boom(Driver):
        def do(self, stage, step):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _ctl(records, Boom()).run(2, go_sentence=GO, live=True)
    records.append("rollback_ack", stage=2)                           # (the interrupted stage needs the ack, not the lock)
    assert _ctl(records, Driver()).run(2, go_sentence=GO, live=True).status == "completed"


def test_a_dry_run_takes_no_lock_and_is_not_blocked_by_a_live_run(tmp_path):
    records = _records(tmp_path)
    a = Driver()
    a.gate = threading.Event()
    t = threading.Thread(target=lambda: _ctl(records, a).run(2, go_sentence=GO, live=True))
    t.start()
    try:
        assert a.entered.wait(10)
        # The plan reads the same rows: the stage is in progress, so it is refused for THAT reason, not for the lock.
        with pytest.raises(sc.Refused) as ei:
            _ctl(sc.Records(records.path), None).run(2, go_sentence=GO)
        assert ei.value.reason == "stage_in_progress"
    finally:
        a.gate.set()
        t.join(10)


def test_the_lock_file_sits_beside_the_records_and_holds_nothing(tmp_path):
    records = _records(tmp_path)
    _ctl(records, Driver()).run(2, go_sentence=GO, live=True)
    lock = Path(str(records.path) + ".lock")
    assert lock.exists() and lock.read_bytes() == b""
