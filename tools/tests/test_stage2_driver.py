"""B-S2-DRIVER: the Stage 2 ``Actions`` driver, proven on an in-memory estate (nothing live, no network).

``FakeEstate`` records every call. ``env={}`` means no alert topic is configured, so every controller alert fails
fast and offline. All values are made up."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sc = _load("stage_controller")
drv = _load("stage2_driver")

GO = "Don: go to stage 2"
SHA = "a1b2c3d4e5f6"
SERVICES = ("killswitch", "registry")


class FakeEstate:
    """override file + kill-switch mode in memory. ``up`` under the override makes the mode enforce; without, log-only."""

    def __init__(self, *, armed=False, bad_mode_after_up=False, healthy=True, fail_delete=False,
                 bump_counters_at=None, drop_override_at=None, unhealthy_after_delete=False, write_does_nothing=False):
        self.override = armed
        self.mode_now = "enforce" if armed else "log-only"
        self.bad_mode_after_up = bad_mode_after_up
        self._healthy = healthy
        self.fail_delete = fail_delete
        self.bump_counters_at = bump_counters_at          # the Nth counters() call and later show a dropped record
        self.drop_override_at = drop_override_at          # the Nth counters() call removes the override file
        self.unhealthy_after_delete = unhealthy_after_delete
        self.write_does_nothing = write_does_nothing
        self.counter_calls = 0
        self.calls: list[str] = []

    def override_present(self):
        return self.override

    def write_override(self):
        self.calls.append("write_override")
        if not self.write_does_nothing:
            self.override = True

    def delete_override(self):
        self.calls.append("delete_override")
        if self.fail_delete:
            raise OSError("cannot delete")
        self.override = False

    def recreate_kill_switch(self, with_override):
        self.calls.append(f"recreate:{'with' if with_override else 'without'}")
        self.mode_now = "enforce" if with_override else "log-only"
        if self.bad_mode_after_up and with_override:
            self.mode_now = "log-only"           # the runbook's silent drop of the override

    def mode(self):
        return self.mode_now

    def healthy(self):
        if self.unhealthy_after_delete and "delete_override" in self.calls:
            return False
        return self._healthy

    def counters(self):
        self.counter_calls += 1
        if self.drop_override_at is not None and self.counter_calls >= self.drop_override_at:
            self.override = False
        dropped = 1 if self.bump_counters_at is not None and self.counter_calls >= self.bump_counters_at else 0
        return {s: {"dropped_unauthenticated_records": dropped, "dropped_refused_records": 0} for s in SERVICES}


def _records(tmp_path, *, g22=True, alerts=True):
    rec = sc.Records(tmp_path / "records.jsonl")
    if alerts:
        rec.append("alerts_proven", ok=True, sha8=SHA[:8])
    if g22:
        rec.append("gate", gate="G22", ok=True, sha8=SHA[:8])
    return rec


def _run(rec, estate, **kw):
    kw.setdefault("live", True)
    return drv.run_stage2(rec, estate, go_sentence=GO, build_sha=SHA, expected_services=SERVICES, env={}, **kw)


def _kinds(rec):
    return [r["kind"] for r in rec.rows()]


# ------------------------------------------------------------------ fresh estate


def test_a_fresh_estate_arms_through_controller_run_and_records_stage_done(tmp_path):
    est, rec = FakeEstate(), _records(tmp_path)
    result = _run(rec, est)
    assert result.status == "completed" and result.steps_done == ["write_override", "recreate_killswitch"]
    assert est.calls == ["write_override", "recreate:with"] and est.mode() == "enforce"
    kinds = _kinds(rec)
    assert kinds.count("stage_start") == 1 and kinds.count("stage_done") == 1
    assert rec.stage_clean(2)


def test_a_failed_mode_check_rolls_back_to_log_only_and_leaves_no_override(tmp_path):
    est, rec = FakeEstate(bad_mode_after_up=True), _records(tmp_path)
    result = _run(rec, est)
    assert result.status == "aborted_rolled_back" and result.abort == "phase_g_check_failed"
    assert result.rolled_back == ["delete_override", "recreate_killswitch"]
    assert est.calls == ["write_override", "recreate:with", "delete_override", "recreate:without"]
    assert est.override is False and est.mode() == "log-only"
    assert "rolled_back" in _kinds(rec) and not rec.stage_clean(2)


def test_an_unhealthy_estate_aborts_and_the_failed_rollback_stops_without_retry(tmp_path):
    est, rec = FakeEstate(healthy=False, fail_delete=True), _records(tmp_path)
    result = _run(rec, est)
    assert result.status == "rollback_failed" and result.abort == "health_failure"
    assert est.calls.count("delete_override") == 1          # never retried
    assert "rollback_failed" in _kinds(rec)


# ------------------------------------------------------------------ already armed


def test_an_already_armed_estate_is_refused_before_any_action(tmp_path):
    est, rec = FakeEstate(armed=True), _records(tmp_path)
    with pytest.raises(sc.Refused) as err:
        _run(rec, est)
    assert err.value.reason == "stage2_already_armed"
    assert est.calls == [] and est.override is True and est.mode() == "enforce"
    assert "stage_start" not in _kinds(rec)
    assert [r["reason"] for r in rec.rows() if r["kind"] == "refused"] == ["stage2_already_armed"]


def test_allow_already_armed_makes_every_step_a_no_op_and_completes(tmp_path):
    est, rec = FakeEstate(armed=True), _records(tmp_path)
    result = _run(rec, est, allow_already_armed=True)
    assert result.status == "completed"
    assert est.calls == [] and est.override is True and est.mode() == "enforce"


def test_an_abort_on_a_healthy_armed_estate_rolls_back_cleanly_and_never_disarms_it(tmp_path):
    """C1(a): the abort is a dropped-record counter (no estate check fails), the estate stays armed and healthy, so the
    rollback verify expects enforce plus the override file and finds both: exactly ``aborted_rolled_back``."""
    est, rec = FakeEstate(armed=True, bump_counters_at=2), _records(tmp_path)
    result = _run(rec, est, allow_already_armed=True)
    assert result.abort == "dropped_unauth_increase"
    assert result.status == "aborted_rolled_back" and result.rolled_back == ["delete_override", "recreate_killswitch"]
    assert est.calls == [] and est.override is True and est.mode() == "enforce"
    assert "rolled_back" in _kinds(rec) and "rollback_failed" not in _kinds(rec)


def test_an_armed_estate_that_lost_enforce_fails_the_rollback_verify_on_the_mode_alone(tmp_path):
    """C1(b): healthy, override present, only the mode dropped: the verify must catch the mode."""
    est, rec = FakeEstate(armed=True), _records(tmp_path)
    est.mode_now = "log-only"
    result = _run(rec, est, allow_already_armed=True)
    assert result.abort == "phase_g_check_failed" and result.status == "rollback_failed"
    assert est._healthy is True and est.override is True and est.calls == []
    assert [r["step"] for r in rec.rows() if r["kind"] == "rollback_failed"] == ["rollback_verify"]


def test_an_armed_estate_whose_override_file_vanished_fails_the_rollback_verify_on_the_file_alone(tmp_path):
    """C1(c): healthy, mode still enforce, only the override file is gone: the verify must catch the file."""
    est, rec = FakeEstate(armed=True, drop_override_at=2), _records(tmp_path)
    result = _run(rec, est, allow_already_armed=True)
    assert result.status == "rollback_failed" and est.override is False
    assert est.mode() == "enforce" and est._healthy is True and est.calls == []
    assert [r["step"] for r in rec.rows() if r["kind"] == "rollback_failed"] == ["rollback_verify"]


def test_an_armed_estate_that_turns_unhealthy_fails_the_rollback_verify_on_health_alone(tmp_path):
    """C1(d), armed side: the abort and the verify both see an unhealthy estate that is otherwise exactly as armed."""
    est, rec = FakeEstate(armed=True, healthy=False), _records(tmp_path)
    result = _run(rec, est, allow_already_armed=True)
    assert result.abort == "health_failure" and result.status == "rollback_failed"
    assert est.override is True and est.mode() == "enforce" and est.calls == []


def test_a_fresh_run_that_is_unhealthy_only_at_the_rollback_verify_is_rollback_failed(tmp_path):
    """C1(d), fresh side: the forward checks see a healthy estate, the rollback runs fully, and only the verify's health
    check can fail."""
    est, rec = FakeEstate(bad_mode_after_up=True, unhealthy_after_delete=True), _records(tmp_path)
    result = _run(rec, est)
    assert result.abort == "phase_g_check_failed"
    assert result.rolled_back == ["delete_override", "recreate_killswitch"]
    assert est.override is False and est.mode() == "log-only"
    assert result.status == "rollback_failed"


def test_a_fresh_rollback_verify_expects_log_only_and_no_override(tmp_path):
    """The fresh side of the verify: the rollback ran but the override file is still there, so it is not clean."""
    class Sticky(FakeEstate):
        def delete_override(self):
            self.calls.append("delete_override")               # reports success, the file stays

    est, rec = Sticky(bad_mode_after_up=True), _records(tmp_path)
    assert _run(rec, est).status == "rollback_failed"


def test_a_write_override_that_leaves_no_override_is_a_checklist_abort_and_rolls_back(tmp_path):
    """C2 (m15): the forward check after write_override must notice a missing override file."""
    est, rec = FakeEstate(write_does_nothing=True), _records(tmp_path)
    result = _run(rec, est)
    assert result.abort == "checklist_item_failed" and result.status == "aborted_rolled_back"
    assert result.steps_done == [] and "recreate:with" not in est.calls


def test_a_baseline_missing_an_expected_service_is_a_health_abort_through_this_driver(tmp_path):
    """C2 (m25): ``expected_services`` reaches the controller, so a service the estate does not report aborts at once."""
    est, rec = FakeEstate(), _records(tmp_path)
    result = drv.run_stage2(rec, est, go_sentence=GO, build_sha=SHA, expected_services=SERVICES + ("absent",),
                            env={}, live=True)
    assert result.abort == "health_failure" and result.steps_done == []
    assert "write_override" not in est.calls


# ------------------------------------------------------------------ preconditions and dry run


def test_no_g22_record_refuses_and_changes_nothing(tmp_path):
    est, rec = FakeEstate(), _records(tmp_path, g22=False)
    with pytest.raises(sc.Refused) as err:
        _run(rec, est)
    assert err.value.reason == "gate_G22_not_recorded" and est.calls == []


def test_no_go_sentence_refuses(tmp_path):
    est, rec = FakeEstate(), _records(tmp_path)
    with pytest.raises(sc.Refused) as err:
        drv.run_stage2(rec, est, go_sentence=None, build_sha=SHA, expected_services=SERVICES, env={}, live=True)
    assert err.value.reason == "go_sentence_missing" and est.calls == []


def test_a_g22_record_for_another_sha_refuses(tmp_path):
    est, rec = FakeEstate(), _records(tmp_path)
    with pytest.raises(sc.Refused) as err:
        drv.run_stage2(rec, est, go_sentence=GO, build_sha="deadbeef0000", expected_services=SERVICES, env={}, live=True)
    assert err.value.reason == "alerts_not_proven" and est.calls == []


def test_the_default_is_a_dry_run_that_calls_nothing_and_writes_a_plan(tmp_path):
    est, rec = FakeEstate(armed=True), _records(tmp_path)   # armed on purpose: a dry run must not even refuse
    result = drv.run_stage2(rec, est, go_sentence=GO, build_sha=SHA, expected_services=SERVICES, env={})
    assert result.status == "dry-run" and est.calls == []
    assert _kinds(rec)[-1] == "plan"


def test_the_go_sentence_is_never_stored_only_its_length_and_prefix(tmp_path):
    est, rec = FakeEstate(), _records(tmp_path)
    _run(rec, est)
    assert GO not in (tmp_path / "records.jsonl").read_text(encoding="utf-8")
    start = next(r for r in rec.rows() if r["kind"] == "stage_start")
    assert start["go_sentence_len"] == len(GO) and len(start["go_sentence_sha8"]) == 8


def test_two_live_runs_do_not_overlap(tmp_path):
    est, rec = FakeEstate(), _records(tmp_path)
    with sc._RunLock(rec.path):
        with pytest.raises(sc.Refused) as err:
            _run(rec, est)
    assert err.value.reason == "run_in_progress" and est.calls == []


# ------------------------------------------------------------------ the driver on its own


def test_the_driver_rejects_any_other_stage_and_unknown_steps():
    d = drv.Stage2Actions(FakeEstate())
    with pytest.raises(ValueError):
        d.do(3, "write_override")
    with pytest.raises(ValueError):
        d.do(2, "set_require_flag")
    assert d.check(3, "write_override") == ["controller_error"]
    assert d.check(2, "set_require_flag") == ["controller_error"]


def test_a_check_that_raises_is_a_failed_check_not_an_exception():
    class Broken(FakeEstate):
        def override_present(self):
            raise RuntimeError("estate unreachable")

    assert drv.Stage2Actions(Broken()).check(2, "write_override") == ["controller_error"]


def test_the_module_holds_no_address_command_or_secret():
    text = (ROOT / "tools" / "stage2_driver.py").read_text(encoding="utf-8")
    for needle in ("http://", "https://", "subprocess", "os.system", "FIELD_API_KEY", "getenv", "environ"):
        assert needle not in text, needle
    json.dumps(sorted(sys.modules["stage2_driver"].__dict__.keys()), default=str)
