"""G24: the Phase G stage controller. A fake driver stands in for the estate (the controller ships no action of its
own); a local HTTP server stands in for ntfy, so the alerts that go out are counted for real. Topics are FAKE."""

from __future__ import annotations

import ast
import http.server
import importlib.util
import json
import sys
import threading
from pathlib import Path

import pytest

from field_core import alerts

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("stage_controller", ROOT / "tools" / "stage_controller.py")
sc = importlib.util.module_from_spec(_spec)
sys.modules["stage_controller"] = sc
_spec.loader.exec_module(sc)

FAKE_TOPIC = "faketopic_unit_test_only_xyz"
FAKE_KEY = "fok_" + "A" * 43
GO = "Don: go to stage"


class _Ntfy:
    def __init__(self):
        self.requests: list[dict] = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length") or 0)
                outer.requests.append({"title": self.headers.get("Title"), "priority": self.headers.get("Priority"),
                                       "body": self.rfile.read(n).decode("utf-8")})
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def titles(self):
        return [r["title"] for r in self.requests]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def ntfy():
    s = _Ntfy()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _clean():
    alerts._reset_stats()
    yield
    alerts._reset_stats()


class Driver:
    """Records every call. ``fail_do`` / ``fail_check`` / ``counters_at`` inject a fault at a (stage, step)."""

    def __init__(self, services=sc.EIGHT_SERVICES):
        self.calls: list[tuple] = []
        self.services = services
        self.fail_do: dict[str, int] = {}        # step -> times it raises, then it works
        self.fail_on_call: set[tuple[str, int]] = set()   # (step, n): the n-th call of that step raises
        self.fail_check: dict[str, list[str]] = {}
        self.counters_after: dict[str, dict] = {}  # step -> {service: {key: value}} (a delta over zero)
        self.counters_raise = False
        self._now = {s: {k: 0 for k in sc.COUNTER_KEYS} for s in services}
        self.broken_counters = None

    def counters(self):
        self.calls.append(("counters",))
        if self.counters_raise:
            raise RuntimeError("health unreachable")
        if self.broken_counters is not None:
            return self.broken_counters
        return {s: dict(c) for s, c in self._now.items()}

    def do(self, stage, step):
        self.calls.append(("do", stage, step))
        if (step, self.dos().count(step)) in self.fail_on_call:
            raise RuntimeError("driver failure")
        if self.fail_do.get(step, 0) > 0:
            self.fail_do[step] -= 1                  # raises the number of times asked, then works
            raise RuntimeError("driver failure")
        for s, delta in self.counters_after.get(step, {}).items():
            self._now[s].update(delta)

    def check(self, stage, step):
        self.calls.append(("check", stage, step))
        return self.fail_check.get(step, [])

    def dos(self):
        return [c[2] for c in self.calls if c[0] == "do"]


def _records(tmp_path, *, alerts_proven=True, gates=(), clean_stage2=True, sha="a" * 40):
    r = sc.Records(tmp_path / "records.jsonl")
    extra = {"sha8": sha[:8]} if sha else {}
    if alerts_proven:
        r.append("alerts_proven", ok=True, **extra)
    for g in gates:
        r.append("gate", gate=g, ok=True, **extra)
    if clean_stage2 and gates:                   # the ready estate Stage 3 needs: Stage 2 armed, held and recorded done
        r.append("stage_done", stage=2)
    return r


def _env(ntfy):
    return {alerts.ENV_TOPIC: FAKE_TOPIC, alerts.ENV_BASE_URL: ntfy.base}


def _ctl(tmp_path, ntfy, driver, *, gates=("G21", "G22")):
    return sc.Controller(_records(tmp_path, gates=gates), driver, estate="gb10", env=_env(ntfy), build_sha="a" * 40)


def _kinds(ctl):
    return [r["kind"] for r in ctl.records.rows()]


# ----------------------------------------------------------------- defaults

def test_a_run_is_a_dry_run_by_default_and_touches_nothing(tmp_path, ntfy):
    d = Driver()
    ctl = _ctl(tmp_path, ntfy, d)
    result = ctl.run(1)
    assert result.status == "dry-run" and d.calls == [] and ntfy.requests == []
    assert _kinds(ctl)[-1] == "plan" and ctl.records.rows()[-1]["dry_run"] is True


def test_live_without_a_driver_is_still_a_dry_run(tmp_path, ntfy):
    ctl = sc.Controller(_records(tmp_path), None, estate="gb10", env=_env(ntfy))
    assert ctl.run(1, live=True).status == "dry-run" and ntfy.requests == []


def test_the_module_ships_no_estate_action():
    tree = ast.parse((ROOT / "tools" / "stage_controller.py").read_text(encoding="utf-8"))
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not imported & {"subprocess", "socket", "urllib", "http", "requests", "httpx", "shutil"}
    called = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not called & {"system", "popen", "Popen", "check_call", "check_output", "execv", "spawn"}


# ------------------------------------------------------------- a clean stage

@pytest.mark.parametrize("stage", [1, 2, 3])
def test_a_clean_stage_runs_every_step_in_order_with_one_transition_alert_per_step(stage, tmp_path, ntfy):
    d = Driver()
    ctl = _ctl(tmp_path, ntfy, d)
    result = ctl.run(stage, go_sentence=GO, live=True)
    spec = sc.STAGES[stage]
    assert result.status == "completed" and result.steps_done == list(spec.steps)
    assert d.dos() == list(spec.steps)
    assert ntfy.titles() == [alerts.CLASSES["stage_transition"].title] * len(spec.steps)
    assert _kinds(ctl)[-1] == "stage_done"


# ------------------------------------------------------------- abort conditions

def _inject(d, cond, step):
    if cond == sc.Abort.DROPPED_UNAUTHENTICATED:
        d.counters_after[step] = {"ledger": {"dropped_unauthenticated_records": 1}}
    elif cond == sc.Abort.DROPPED_REFUSED:
        d.counters_after[step] = {"registry": {"dropped_refused_records": 3}}
    elif cond == sc.Abort.CONTROLLER_ERROR:
        d.fail_do[step] = 1
    else:
        d.fail_check[step] = [cond.value]


@pytest.mark.parametrize("cond", list(sc.Abort), ids=[a.value for a in sc.Abort])
@pytest.mark.parametrize("stage", [1, 2, 3])
def test_every_abort_condition_rolls_back_in_order_and_sends_exactly_one_aborted_alert(cond, stage, tmp_path, ntfy):
    spec = sc.STAGES[stage]
    d = Driver()
    ctl = _ctl(tmp_path, ntfy, d)
    broken = spec.steps[-1]
    _inject(d, cond, broken)
    result = ctl.run(stage, go_sentence=GO, live=True)
    assert result.status == "aborted_rolled_back" and result.abort == cond.value
    assert result.steps_done == list(spec.steps[:-1])
    # the failing step ran, nothing after it did, then the rollback ran in the runbook's order
    assert d.dos() == list(spec.steps) + list(spec.rollback)
    assert result.rolled_back == list(spec.rollback)
    assert ("check", stage, "rollback_verify") in d.calls
    titles = ntfy.titles()
    assert titles.count(alerts.CLASSES["stage_aborted"].title) == 1
    assert titles.count(alerts.CLASSES["stage_transition"].title) == len(spec.steps) - 1
    kinds = _kinds(ctl)
    assert "abort" in kinds and kinds[-1] == "rolled_back"
    abort_row = next(r for r in ctl.records.rows() if r["kind"] == "abort")
    assert abort_row["condition"] == cond.value                      # not withheld by the record content check
    aborted = next(r for r in ntfy.requests if r["title"] == alerts.CLASSES["stage_aborted"].title)
    assert cond.value in aborted["body"] and alerts.WITHHELD not in aborted["body"]   # nor by the alert's


def test_no_abort_condition_name_trips_the_content_check():
    for name in sc.ABORT_CONDITIONS:
        assert alerts.content_problem(f"{name}, rolled back") is None, name


def test_the_abort_conditions_are_the_eight_of_the_p36_review():
    assert set(sc.ABORT_CONDITIONS) == {
        "dropped_unauth_increase", "dropped_refused_increase", "checklist_item_failed",
        "phase_g_check_failed", "canary_c0_failed", "health_failure", "restart_failure", "controller_error"}


def test_an_abort_on_the_first_step_rolls_back_with_no_transition_alert(tmp_path, ntfy):
    d = Driver()
    d.fail_check["install_operators_file"] = ["canary_c0_failed"]
    ctl = _ctl(tmp_path, ntfy, d)
    result = ctl.run(1, live=True)
    assert result.steps_done == [] and ntfy.titles() == [alerts.CLASSES["stage_aborted"].title]


def test_an_unchanged_counter_is_not_an_abort_and_an_increase_in_a_service_not_named_by_the_step_is(tmp_path, ntfy):
    d = Driver()
    d.counters_after["set_env_paths"] = {"registry": {"dropped_refused_records": 0}}   # unchanged
    assert _ctl(tmp_path, ntfy, d).run(1, live=True).status == "completed"
    d2 = Driver()
    d2.counters_after["install_operators_file"] = {"registry": {"dropped_unauthenticated_records": 2}}
    assert _ctl(tmp_path / "b", ntfy, d2).run(1, live=True).abort == "dropped_unauth_increase"


@pytest.mark.parametrize("broken", [None, "text", {"registry": None}, {"registry": {"dropped_refused_records": "7",
                                    "dropped_unauthenticated_records": 0}}, {}])
def test_a_counter_that_cannot_be_judged_fails_closed_as_a_health_failure(broken, tmp_path, ntfy):
    d = Driver()
    ctl = _ctl(tmp_path, ntfy, d)
    good = d.counters
    calls = {"n": 0}

    def counters():
        calls["n"] += 1
        return good() if calls["n"] == 1 else broken     # the baseline is good, every later sample is not
    d.counters = counters
    assert ctl.run(1, live=True).abort == "health_failure"


def test_a_baseline_that_cannot_be_read_aborts_before_any_step_and_still_rolls_back(tmp_path, ntfy):
    d = Driver()
    d.counters_raise = True
    ctl = _ctl(tmp_path, ntfy, d)
    result = ctl.run(1, live=True)
    assert result.abort == "health_failure" and result.steps_done == []
    assert d.dos() == list(sc.STAGES[1].rollback)
    assert ntfy.titles() == [alerts.CLASSES["stage_aborted"].title]


def test_an_unknown_condition_name_from_the_driver_fails_closed(tmp_path, ntfy):
    d = Driver()
    d.fail_check["recreate_eight"] = ["not-a-condition"]
    assert _ctl(tmp_path, ntfy, d).run(1, live=True).abort == "controller_error"


# --------------------------------------------------------------------- rollback

def test_the_rollback_order_is_the_reverse_dependency_order_of_the_runbook():
    assert sc.STAGES[1].rollback == ("delete_flag_lines", "recreate_eight")
    assert sc.STAGES[2].rollback == ("delete_override", "recreate_killswitch")
    # Stage 3: remove REQUIRE first, the seven, the kill-switch LAST (runbook step 8 and Stage 3 rollback)
    assert sc.STAGES[3].rollback == ("remove_require_flag", "recreate_seven", "recreate_killswitch")


@pytest.mark.parametrize("stage", [1, 2, 3])
def test_a_rollback_step_that_fails_stops_the_rollback_once_with_one_alert_and_never_loops(stage, tmp_path, ntfy):
    spec = sc.STAGES[stage]
    for i, bad in enumerate(spec.rollback):
        d = Driver()
        d.fail_check[spec.steps[-1]] = ["phase_g_check_failed"]
        d.fail_on_call.add((bad, 2 if bad in spec.steps else 1))     # its ROLLBACK call, not its arming call
        ctl = _ctl(tmp_path / f"s{stage}-{i}", ntfy, d)
        before = len(ntfy.requests)
        result = ctl.run(stage, go_sentence=GO, live=True)
        assert result.status == "rollback_failed"
        assert result.rolled_back == list(spec.rollback[:i])
        assert d.dos()[len(spec.steps):] == list(spec.rollback[:i + 1])     # the failing step once, nothing after it
        sent = ntfy.requests[before:]
        aborted = [r for r in sent if r["title"] == alerts.CLASSES["stage_aborted"].title]
        assert len(aborted) == 1 and "ROLLBACK FAILED" in aborted[0]["body"] and bad in aborted[0]["body"]
        assert _kinds(ctl)[-1] == "rollback_failed"
        assert ("check", stage, "rollback_verify") not in d.calls


def test_a_rollback_whose_verification_fails_is_a_rollback_failure(tmp_path, ntfy):
    d = Driver()
    d.fail_check["recreate_eight"] = ["health_failure"]
    d.fail_check["rollback_verify"] = ["phase_g_check_failed"]
    result = _ctl(tmp_path, ntfy, d).run(1, live=True)
    assert result.status == "rollback_failed"
    assert ntfy.titles().count(alerts.CLASSES["stage_aborted"].title) == 1
    assert d.dos() == list(sc.STAGES[1].steps) + list(sc.STAGES[1].rollback)      # not retried


def test_a_rollback_verification_that_raises_is_a_rollback_failure(tmp_path, ntfy):
    d = Driver()
    d.fail_check["recreate_eight"] = ["health_failure"]
    orig = d.check

    def check(stage, step):
        if step == "rollback_verify":
            raise RuntimeError("probe down")
        return orig(stage, step)
    d.check = check
    assert _ctl(tmp_path, ntfy, d).run(1, live=True).status == "rollback_failed"


def test_an_alert_that_cannot_be_sent_never_stops_the_stage_or_its_rollback(tmp_path):
    d = Driver()
    d.fail_check["recreate_eight"] = ["canary_c0_failed"]
    ctl = sc.Controller(_records(tmp_path), d, estate="gb10", env={}, build_sha="a" * 40)   # no topic: every alert fails
    result = ctl.run(1, live=True)
    assert result.status == "aborted_rolled_back" and d.dos() == list(sc.STAGES[1].steps) + list(sc.STAGES[1].rollback)
    assert alerts.health_fields({})["alerts_failed"] >= 1


# ----------------------------------------------------------------- preconditions

@pytest.mark.parametrize("stage", [0, 4, -1, True, "1", None, 1.0])
def test_an_unknown_stage_is_refused(stage, tmp_path):
    d = Driver()
    ctl = sc.Controller(_records(tmp_path, gates=("G21", "G22")), d)
    with pytest.raises(sc.Refused) as e:
        ctl.run(stage, go_sentence=GO, live=True)
    assert e.value.reason == "unknown_stage" and d.calls == []


@pytest.mark.parametrize("stage", [1, 2, 3])
def test_no_stage_arms_without_an_alerts_proven_record(stage, tmp_path):
    d = Driver()
    ctl = sc.Controller(sc.Records(tmp_path / "r.jsonl"), d)
    ctl.records.append("gate", gate="G21", ok=True)
    ctl.records.append("gate", gate="G22", ok=True)
    with pytest.raises(sc.Refused) as e:
        ctl.run(stage, go_sentence=GO, live=True)
    assert e.value.reason == "alerts_not_proven" and d.calls == []
    assert _kinds(ctl)[-1] == "refused"


def test_an_alerts_proven_record_that_is_not_ok_does_not_count(tmp_path):
    r = sc.Records(tmp_path / "r.jsonl")
    r.append("alerts_proven", ok=False)
    r.append("alerts_proven", ok="yes")
    assert not r.alerts_proven()


def test_stage_two_needs_the_g22_gate_and_stage_three_needs_g21(tmp_path):
    for stage, missing, have in ((2, "G22", ("G21",)), (3, "G21", ("G22",))):
        d = Driver()
        ctl = sc.Controller(_records(tmp_path / f"s{stage}", gates=have), d)
        with pytest.raises(sc.Refused) as e:
            ctl.run(stage, go_sentence=GO, live=True)
        assert e.value.reason == f"gate_{missing}_not_recorded" and d.calls == []


@pytest.mark.parametrize("stage", [2, 3])
@pytest.mark.parametrize("sentence", [None, "", "   ", "x" * 501, 7, FAKE_KEY, "ab" * 20])
def test_stage_two_and_three_never_run_without_dons_go_sentence(stage, sentence, tmp_path):
    d = Driver()
    ctl = sc.Controller(_records(tmp_path, gates=("G21", "G22")), d)
    with pytest.raises(sc.Refused) as e:
        ctl.run(stage, go_sentence=sentence, live=True)
    assert e.value.reason == "go_sentence_missing" and d.calls == []


def test_stage_one_runs_on_the_alerts_record_alone(tmp_path, ntfy):
    d = Driver()
    ctl = sc.Controller(_records(tmp_path), d, estate="gb10", env=_env(ntfy), build_sha="a" * 40)
    assert ctl.run(1, live=True).status == "completed"


def test_the_go_sentence_is_never_recorded_only_its_length_and_a_hash_prefix(tmp_path, ntfy):
    d = Driver()
    ctl = _ctl(tmp_path, ntfy, d)
    ctl.run(2, go_sentence=GO, live=True)
    text = ctl.records.path.read_text(encoding="utf-8")
    assert GO not in text
    start = next(r for r in ctl.records.rows() if r["kind"] == "stage_start")
    assert start["go_sentence_len"] == len(GO) and len(start["go_sentence_sha8"]) == 8


def test_the_go_sentence_is_not_taken_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_GO_SENTENCE", GO)
    ctl = sc.Controller(_records(tmp_path, gates=("G22",)), Driver())
    with pytest.raises(sc.Refused):
        ctl.run(2, live=True)


# ------------------------------------------------------------------------ records

def test_a_record_never_holds_a_key_a_pem_header_or_a_hex_run(tmp_path):
    r = sc.Records(tmp_path / "r.jsonl")
    r.append("note", a=FAKE_KEY, b="-----BEGIN PRIVATE KEY-----", c="ab" * 20, d="fine", e=["x", FAKE_KEY])
    text = (tmp_path / "r.jsonl").read_text(encoding="utf-8")
    assert FAKE_KEY not in text and "BEGIN" not in text and "ab" * 20 not in text
    row = json.loads(text)
    assert row["a"] == row["b"] == row["c"] == sc.WITHHELD and row["d"] == "fine" and row["e"] == ["x", sc.WITHHELD]


def test_a_damaged_line_in_the_records_file_proves_nothing(tmp_path):
    p = tmp_path / "r.jsonl"
    p.write_text('{"kind": "alerts_proven", "ok": tr\n{"kind": "gate", "gate": "G22", "ok": true}\n[1]\n',
                 encoding="utf-8")
    r = sc.Records(p)
    assert not r.alerts_proven() and r.gate_ok("G22")


def test_the_records_file_is_owner_only(tmp_path):
    r = sc.Records(tmp_path / "sub" / "r.jsonl")
    r.append("note", a=1)
    assert oct(r.path.stat().st_mode & 0o777) == "0o600" or sys.platform == "win32"


# --------------------------------------------------------------------- command line

def test_the_command_line_has_no_run_and_plans_without_touching_anything(tmp_path, capsys):
    rec = str(tmp_path / "r.jsonl")
    assert sc.main(["plan", "--stage", "1", "--records", rec]) == 2
    assert "refused: alerts_not_proven" in capsys.readouterr().out
    assert sc.main(["record", "alerts-proven", "--records", rec]) == 0
    assert sc.main(["plan", "--stage", "1", "--records", rec]) == 0
    out = capsys.readouterr().out
    assert "dry run, nothing was changed" in out and "rollback, in order: delete_flag_lines, recreate_eight" in out
    assert sc.main(["plan", "--stage", "2", "--records", rec]) == 2          # no G22, no go sentence
    with pytest.raises(SystemExit) as e:
        sc.main(["run", "--stage", "1"])
    assert e.value.code == 2


def test_the_command_line_records_a_gate_and_refuses_a_gate_record_without_a_name(tmp_path, capsys):
    rec = str(tmp_path / "r.jsonl")
    assert sc.main(["record", "gate", "--records", rec]) == 2
    assert sc.main(["record", "gate", "G22", "--records", rec, "--build-sha", SHA_A]) == 0
    assert sc.Records(rec).gate_ok("G22") and not sc.Records(rec).gate_ok("G21")
    sc.main(["record", "alerts-proven", "--records", rec, "--build-sha", SHA_A])
    assert sc.main(["plan", "--stage", "2", "--records", rec, "--go-sentence", GO, "--build-sha", SHA_A]) == 0


def test_the_runbook_lists_every_abort_condition_and_every_stage_rollback_step():
    text = (ROOT / "docs" / "runbooks" / "v1.2-deploy-rollback.md").read_text(encoding="utf-8")
    section = text[text.index("## Stage controller (P36, G24)"):]
    for name in sc.ABORT_CONDITIONS:
        assert f"`{name}`" in section, name


# ------------------------------------------------- fail closed (red team F-816-1, F-816-2, F-816-3)
def _fail_records(ctl, *kinds):
    """Make ``ctl.records.append`` raise OSError for these kinds, as a full disk or a locked file would."""
    real = ctl.records.append

    def append(kind, **fields):
        if kind in kinds:
            raise OSError("records write failed")
        return real(kind, **fields)
    ctl.records.append = append


@pytest.mark.parametrize("kind", ["step_done", "stage_done"])
@pytest.mark.parametrize("stage", [1, 2, 3])
def test_a_records_write_that_fails_rolls_the_stage_back_as_a_controller_error(kind, stage, tmp_path, ntfy):
    spec = sc.STAGES[stage]
    d = Driver()
    ctl = _ctl(tmp_path, ntfy, d)
    _fail_records(ctl, kind)
    result = ctl.run(stage, go_sentence=GO, live=True)               # nothing propagates to the caller
    assert result.status == "aborted_rolled_back" and result.abort == "controller_error"
    ran = list(spec.steps[:1] if kind == "step_done" else spec.steps)
    assert d.dos() == ran + list(spec.rollback) and result.rolled_back == list(spec.rollback)
    assert ntfy.titles().count(alerts.CLASSES["stage_aborted"].title) == 1


def test_a_records_file_that_fails_for_every_write_still_rolls_back_and_alerts(tmp_path, ntfy):
    d = Driver()
    ctl = _ctl(tmp_path, ntfy, d)
    _fail_records(ctl, "step_done", "abort", "rollback_step", "rolled_back", "rollback_failed")
    result = ctl.run(2, go_sentence=GO, live=True)
    assert result.status == "aborted_rolled_back" and result.rolled_back == list(sc.STAGES[2].rollback)
    assert d.dos() == list(sc.STAGES[2].steps[:1]) + list(sc.STAGES[2].rollback)
    assert ntfy.titles().count(alerts.CLASSES["stage_aborted"].title) == 1


@pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("stage", [1, 2, 3])
def test_an_interrupt_mid_stage_rolls_back_and_is_raised_again(exc, stage, tmp_path, ntfy):
    spec = sc.STAGES[stage]
    d = Driver()
    real = d.do

    def do(st, step):
        if step == spec.steps[-1] and step not in d.dos():
            d.calls.append(("do", st, step))
            raise exc()
        return real(st, step)
    d.do = do
    ctl = _ctl(tmp_path, ntfy, d)
    with pytest.raises(exc):
        ctl.run(stage, go_sentence=GO, live=True)
    assert d.dos() == list(spec.steps) + list(spec.rollback)         # the rollback ran before the interrupt left
    kinds = _kinds(ctl)
    assert "abort" in kinds and kinds[-1] == "rolled_back"
    assert ntfy.titles().count(alerts.CLASSES["stage_aborted"].title) == 1


def test_an_empty_counters_baseline_is_a_health_failure_not_a_free_pass(tmp_path, ntfy):
    d = Driver(services=())
    d.counters_after["install_operators_file"] = {}
    ctl = _ctl(tmp_path, ntfy, d)
    result = ctl.run(1, live=True)
    assert result.abort == "health_failure" and result.steps_done == []
    assert d.dos() == list(sc.STAGES[1].rollback)


def test_a_baseline_that_misses_an_expected_service_is_a_health_failure(tmp_path, ntfy):
    d = Driver(services=("registry",))
    ctl = sc.Controller(_records(tmp_path), d, estate="gb10", env=_env(ntfy), expected_services=("registry", "ledger"),
                        build_sha=SHA_A)
    result = ctl.run(1, live=True)
    assert result.abort == "health_failure" and result.steps_done == []
    d2 = Driver(services=("registry", "ledger"))
    ok = sc.Controller(_records(tmp_path / "ok"), d2, estate="gb10", env=_env(ntfy), expected_services=("registry", "ledger"),
                       build_sha=SHA_A)
    assert ok.run(1, live=True).status == "completed"


# ------------------------------------------------- stage order and gate binding (red team F-816-4, F-816-5)
def test_stage_three_needs_a_recorded_clean_stage_two(tmp_path, ntfy):
    ctl = sc.Controller(_records(tmp_path, gates=("G21", "G22"), clean_stage2=False), Driver(), estate="gb10", env=_env(ntfy))
    with pytest.raises(sc.Refused) as ei:
        ctl.run(3, go_sentence=GO)
    assert ei.value.reason == "stage_2_not_clean"
    ok = sc.Controller(_records(tmp_path / "ok", gates=("G21", "G22")), Driver(), estate="gb10", env=_env(ntfy))
    assert ok.run(3, go_sentence=GO).status == "dry-run"


@pytest.mark.parametrize("later", ["stage_start", "abort", "rolled_back", "rollback_failed"])
def test_a_stage_two_that_was_started_again_aborted_or_rolled_back_is_not_clean(later, tmp_path, ntfy):
    records = _records(tmp_path, gates=("G21", "G22"))
    records.append(later, stage=2)
    with pytest.raises(sc.Refused) as ei:
        sc.Controller(records, Driver(), estate="gb10", env=_env(ntfy)).run(3, go_sentence=GO)
    assert ei.value.reason == "stage_2_not_clean"
    records.append("stage_done", stage=2)                            # done again after it: clean again
    assert sc.Controller(records, Driver(), estate="gb10", env=_env(ntfy)).run(3, go_sentence=GO).status == "dry-run"


def test_a_stage_done_for_another_stage_does_not_make_stage_two_clean(tmp_path, ntfy):
    records = _records(tmp_path, gates=("G21", "G22"), clean_stage2=False)
    records.append("stage_done", stage=1)
    records.append("stage_done", stage=3)
    with pytest.raises(sc.Refused) as ei:
        sc.Controller(records, Driver(), estate="gb10", env=_env(ntfy)).run(3, go_sentence=GO)
    assert ei.value.reason == "stage_2_not_clean"


SHA_A, SHA_B = "a" * 40, "b" * 40


def test_with_a_build_sha_the_records_must_carry_that_sha(tmp_path, ntfy):
    records = _records(tmp_path, gates=("G22",), sha=SHA_A)
    ok = sc.Controller(records, Driver(), estate="gb10", env=_env(ntfy), build_sha=SHA_A)
    assert ok.run(2, go_sentence=GO).status == "dry-run"
    with pytest.raises(sc.Refused) as ei:                            # a record from an old head stays valid without this
        sc.Controller(records, Driver(), estate="gb10", env=_env(ntfy), build_sha=SHA_B).run(2, go_sentence=GO)
    assert ei.value.reason == "alerts_not_proven"


def test_a_gate_recorded_for_another_sha_is_not_recorded(tmp_path, ntfy):
    records = _records(tmp_path, gates=(), sha=SHA_A)
    records.append("gate", gate="G22", ok=True, sha8=SHA_B[:8])
    with pytest.raises(sc.Refused) as ei:
        sc.Controller(records, Driver(), estate="gb10", env=_env(ntfy), build_sha=SHA_A).run(2, go_sentence=GO)
    assert ei.value.reason == "gate_G22_not_recorded"


def test_records_without_a_sha_do_not_satisfy_a_run_that_names_a_build_sha(tmp_path, ntfy):
    records = _records(tmp_path, gates=("G22",), sha=None)
    with pytest.raises(sc.Refused) as ei:
        sc.Controller(records, Driver(), estate="gb10", env=_env(ntfy), build_sha=SHA_A).run(2, go_sentence=GO)
    assert ei.value.reason == "alerts_not_proven"


@pytest.mark.parametrize("bad", ["", "xyz", "A" * 40, "a" * 6, "a" * 41, 5])
def test_a_build_sha_that_is_not_lowercase_hex_is_refused(bad, tmp_path, ntfy):
    with pytest.raises(sc.Refused) as ei:
        sc.Controller(_records(tmp_path, gates=("G22",)), Driver(), estate="gb10", env=_env(ntfy),
                      build_sha=bad).run(2, go_sentence=GO)
    assert ei.value.reason == "build_sha_invalid"


def test_the_command_line_binds_a_record_to_a_sha_and_a_plan_checks_it(tmp_path, capsys):
    path = str(tmp_path / "r.jsonl")
    assert sc.main(["record", "alerts-proven", "--records", path, "--build-sha", SHA_A]) == 0
    assert sc.main(["record", "gate", "G22", "--records", path, "--build-sha", SHA_A]) == 0
    row = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines()][-1]
    assert row["sha8"] == SHA_A[:8] and SHA_A not in json.dumps(row)         # 8 characters only, never the full sha
    capsys.readouterr()
    assert sc.main(["plan", "--stage", "2", "--records", path, "--go-sentence", GO, "--build-sha", SHA_A]) == 0
    assert sc.main(["plan", "--stage", "2", "--records", path, "--go-sentence", GO, "--build-sha", SHA_B]) == 2
    assert "alerts_not_proven" in capsys.readouterr().out
    assert sc.main(["record", "gate", "G22", "--records", path, "--build-sha", "not-a-sha"]) == 2


# ------------------------------------------------- red team re-review of 832 (RT-832-R1 to R4)
def test_a_live_run_without_a_build_sha_is_refused_before_anything_runs(tmp_path, ntfy):
    d = Driver()
    ctl = sc.Controller(_records(tmp_path), d, estate="gb10", env=_env(ntfy))           # no build_sha
    with pytest.raises(sc.Refused) as ei:
        ctl.run(1, live=True)
    assert ei.value.reason == "build_sha_required" and d.calls == []
    assert [r["reason"] for r in ctl.records.rows() if r["kind"] == "refused"] == ["build_sha_required"]
    assert ctl.run(1).status == "dry-run"                                              # a plan stays possible without one


@pytest.mark.parametrize("stage,named", [(1, ("registry",)), (2, ("registry",)), (2, ("killswitch",)), (3, ("killswitch", "registry"))])
def test_a_baseline_that_names_too_few_services_for_the_stage_is_a_health_failure(stage, named, tmp_path, ntfy):
    d = Driver(services=named)
    result = _ctl(tmp_path, ntfy, d).run(stage, go_sentence=GO, live=True)
    assert result.abort == "health_failure" and result.steps_done == []


def test_stage_two_needs_only_the_killswitch_and_the_registry_in_the_baseline(tmp_path, ntfy):
    d = Driver(services=("killswitch", "registry"))
    assert _ctl(tmp_path, ntfy, d).run(2, go_sentence=GO, live=True).status == "completed"


def test_the_explicit_expected_services_override_the_stage_default(tmp_path, ntfy):
    d = Driver(services=("registry",))
    ctl = sc.Controller(_records(tmp_path), d, estate="gb10", env=_env(ntfy), build_sha=SHA_A, expected_services=("registry",))
    assert ctl.run(1, live=True).status == "completed"


@pytest.mark.parametrize("later", ["abort", "rolled_back", "rollback_failed"])
def test_a_stage_three_abort_or_rollback_makes_stage_two_not_clean(later, tmp_path, ntfy):
    records = _records(tmp_path, gates=("G21", "G22"))
    records.append(later, stage=3)
    with pytest.raises(sc.Refused) as ei:
        sc.Controller(records, Driver(), estate="gb10", env=_env(ntfy)).run(3, go_sentence=GO)
    assert ei.value.reason == "stage_2_not_clean"
    records.append("stage_done", stage=2)                       # Stage 2 re-armed and recorded: clean again
    assert sc.Controller(records, Driver(), estate="gb10", env=_env(ntfy)).run(3, go_sentence=GO).status == "dry-run"


def test_an_abort_of_an_earlier_stage_does_not_unclean_a_later_one(tmp_path):
    records = _records(tmp_path, gates=("G21", "G22"))
    records.append("abort", stage=1)
    assert records.stage_clean(2) is True


def test_a_failed_stage_start_record_arms_nothing_and_rolls_nothing_back(tmp_path, ntfy):
    d = Driver()
    ctl = _ctl(tmp_path, ntfy, d)
    _fail_records(ctl, "stage_start")
    result = ctl.run(2, go_sentence=GO, live=True)
    assert result.status == "aborted_nothing_armed" and result.abort == "controller_error"
    assert d.dos() == [] and result.rolled_back == []                 # an untouched estate is not restarted
    assert [r["stage"] for r in ctl.records.rows() if r["kind"] == "abort"] == [2]      # the abort is still recorded
    assert ntfy.titles().count(alerts.CLASSES["stage_aborted"].title) == 1


# ------------------------------------------------- reviewer-7 conditions on PR 840 (literal lists, empty override)
def test_the_service_lists_are_pinned_literally():
    compose = ("registry", "ledger", "delegation", "killswitch", "governor", "fedbroker", "console", "lifecycle")
    assert sc.EIGHT_SERVICES == compose and len(set(compose)) == 8
    assert sc.STAGES[1].services == compose and sc.STAGES[3].services == compose
    assert sc.STAGES[2].services == ("killswitch", "registry")


@pytest.mark.parametrize("stage,names", [(1, sc.EIGHT_SERVICES), (3, sc.EIGHT_SERVICES), (2, ("killswitch", "registry"))])
def test_a_driver_naming_exactly_the_literal_list_completes_the_stage(stage, names, tmp_path, ntfy):
    assert _ctl(tmp_path, ntfy, Driver(services=names)).run(stage, go_sentence=GO, live=True).status == "completed"


@pytest.mark.parametrize("missing", ["registry", "ledger", "delegation", "killswitch", "governor", "fedbroker", "console", "lifecycle"])
def test_each_of_the_eight_names_is_required_in_stage_one(missing, tmp_path, ntfy):
    named = tuple(s for s in sc.EIGHT_SERVICES if s != missing)
    result = _ctl(tmp_path, ntfy, Driver(services=named)).run(1, go_sentence=GO, live=True)
    assert result.abort == "health_failure" and result.steps_done == []


def test_the_stage_zero_label_federation_does_not_satisfy_the_baseline(tmp_path, ntfy):
    named = tuple("federation" if s == "fedbroker" else s for s in sc.EIGHT_SERVICES)
    result = _ctl(tmp_path, ntfy, Driver(services=named)).run(1, go_sentence=GO, live=True)
    assert result.abort == "health_failure" and result.steps_done == []


@pytest.mark.parametrize("override", [(), [], ""])
def test_an_empty_expected_services_override_is_the_stage_list_not_no_check(override, tmp_path, ntfy):
    ctl = sc.Controller(_records(tmp_path), Driver(services=("registry",)), estate="gb10", env=_env(ntfy),
                        build_sha=SHA_A, expected_services=override)
    assert ctl.expected_services is None
    result = ctl.run(1, live=True)
    assert result.abort == "health_failure" and result.steps_done == []        # one name is not the eight


@pytest.mark.parametrize("bad", [("federation",), ("registry", "federation"), ("fed",), "registry", ("Registry",)])
def test_an_override_with_a_name_that_is_not_a_compose_name_is_refused_loudly(bad, tmp_path, ntfy):
    with pytest.raises(ValueError, match="compose names"):
        sc.Controller(_records(tmp_path), Driver(), estate="gb10", env=_env(ntfy), build_sha=SHA_A, expected_services=bad)


def test_every_compose_name_is_accepted_as_an_override(tmp_path, ntfy):
    for name in sc.EIGHT_SERVICES:
        ctl = sc.Controller(_records(tmp_path), Driver(), estate="gb10", env=_env(ntfy), expected_services=(name,))
        assert ctl.expected_services == (name,)


# ------------------------------------------------- G26: Stage 3 readiness (rehearsal over a fake estate, plan notice)
EIGHT = ("registry", "ledger", "delegation", "killswitch", "governor", "fedbroker", "console", "lifecycle")


class FakeEstate(Driver):
    """A stateful stand-in for the eight services: each has a mode that it takes from the ``.env`` flag only when it is
    recreated, as compose does. The rehearsal asserts where the estate ends up, not only which steps ran."""

    def __init__(self):
        super().__init__(services=EIGHT)
        self.require = False
        self.override = True                              # the Stage 2 kill-switch override is in place
        self.mode = {s: "log-only" for s in EIGHT}
        self.recreated: list[str] = []

    def _adopt(self, names):
        for n in names:
            self.mode[n] = "require" if self.require else "log-only"
            self.recreated.append(n)

    def do(self, stage, step):
        super().do(stage, step)
        if step == "set_require_flag":
            self.require = True
        elif step == "remove_require_flag":
            self.require = False
        elif step == "delete_override":
            self.override = False
        elif step == "recreate_eight":
            self._adopt(EIGHT)
        elif step == "recreate_seven":
            self._adopt([n for n in EIGHT if n != "killswitch"])
        elif step == "recreate_killswitch":
            self._adopt(["killswitch"])


@pytest.mark.parametrize("broken", ["recreate_eight"])
def test_a_stage_three_abort_rehearsal_ends_log_only_with_the_killswitch_recreated_last(broken, tmp_path, ntfy):
    estate = FakeEstate()
    estate.fail_check[broken] = ["canary_c0_failed"]
    ctl = _ctl(tmp_path, ntfy, estate)
    result = ctl.run(3, go_sentence=GO, live=True)
    assert result.status == "aborted_rolled_back"
    # the flag is gone before any service is recreated, so every service comes back LOG-ONLY
    assert estate.require is False and set(estate.mode.values()) == {"log-only"}
    rollback = [c[2] for c in estate.calls if c[0] == "do"][len(sc.STAGES[3].steps):]
    assert rollback == ["remove_require_flag", "recreate_seven", "recreate_killswitch"]
    assert estate.recreated[-1] == "killswitch" and "killswitch" not in estate.recreated[len(EIGHT):-1]


def test_the_rehearsal_would_leave_services_in_require_if_the_flag_were_removed_last():
    """The fake estate is sensitive to the order: recreating before removing the flag leaves the estate in REQUIRE."""
    estate = FakeEstate()
    for step in ("set_require_flag", "recreate_eight", "recreate_seven", "recreate_killswitch", "remove_require_flag"):
        estate.do(3, step)
    assert set(estate.mode.values()) == {"require"}


def test_a_stage_three_plan_prints_the_irreversibility_notice_and_the_other_stages_do_not(tmp_path, capsys):
    path = str(tmp_path / "r.jsonl")
    r = sc.Records(path)
    sha = {"sha8": sc.sha8_of(SHA_A)}
    r.append("alerts_proven", ok=True, **sha)
    r.append("gate", gate="G21", ok=True, **sha)
    r.append("gate", gate="G22", ok=True, **sha)
    r.append("stage_done", stage=2)
    assert sc.main(["plan", "--stage", "3", "--records", path, "--go-sentence", GO, "--build-sha", SHA_A]) == 0
    out = capsys.readouterr().out
    assert "irreversibility: an image rollback is unavailable once REQUIRE is on all eight" in out
    assert "FIELD_OPERATOR_REQUIRE first, never by image alone" in out
    for stage in (1, 2):
        assert sc.main(["plan", "--stage", str(stage), "--records", path, "--go-sentence", GO, "--build-sha", SHA_A]) == 0
        assert "irreversibility" not in capsys.readouterr().out


@pytest.mark.parametrize("sentence", [None, "", "   "])
def test_a_stage_three_plan_without_a_go_sentence_refuses(sentence, tmp_path, capsys):
    path = str(tmp_path / "r.jsonl")
    r = sc.Records(path)
    sha = {"sha8": sc.sha8_of(SHA_A)}
    r.append("alerts_proven", ok=True, **sha)
    r.append("gate", gate="G21", ok=True, **sha)
    r.append("stage_done", stage=2)
    argv = ["plan", "--stage", "3", "--records", path, "--build-sha", SHA_A] + (
        [] if sentence is None else ["--go-sentence", sentence])
    assert sc.main(argv) == 2
    assert "refused: go_sentence_missing" in capsys.readouterr().out


# --- S2-2: the driver's two arguments ------------------------------------------------------------------------------

def _clean_records(tmp_path, stage=2):
    path = str(tmp_path / "r.jsonl")
    r = sc.Records(path)
    sha = {"sha8": sc.sha8_of(SHA_A)}
    r.append("alerts_proven", ok=True, **sha)
    r.append("gate", gate="G22", ok=True, **sha)
    return path


@pytest.mark.parametrize("stage, expect", [(1, sc.EIGHT_SERVICES), (2, ("killswitch", "registry")), (3, sc.EIGHT_SERVICES)])
def test_plan_without_services_prints_the_stages_own_list(stage, expect, tmp_path, capsys):
    path = str(tmp_path / "r.jsonl")
    r = sc.Records(path)
    sha = {"sha8": sc.sha8_of(SHA_A)}
    r.append("alerts_proven", ok=True, **sha)
    r.append("gate", gate="G21", ok=True, **sha)
    r.append("gate", gate="G22", ok=True, **sha)
    r.append("stage_done", stage=2)
    argv = ["plan", "--stage", str(stage), "--records", path]
    if stage > 1:
        argv += ["--go-sentence", GO, "--build-sha", SHA_A]
    assert sc.main(argv) == 0
    assert ("services: " + ", ".join(expect)) in capsys.readouterr().out


def test_plan_with_services_shows_exactly_that_list_in_that_order(tmp_path, capsys):
    path = _clean_records(tmp_path)
    assert sc.main(["plan", "--stage", "2", "--records", path, "--go-sentence", GO, "--build-sha", SHA_A,
                    "--services", "registry, killswitch ,governor"]) == 0
    assert "services: registry, killswitch, governor" in capsys.readouterr().out.splitlines()


@pytest.mark.parametrize("value", ["", "  ", ",", "registry,,killswitch", "registry,"])
def test_an_empty_services_list_or_an_empty_name_is_refused(value, tmp_path, capsys):
    path = _clean_records(tmp_path)
    assert sc.main(["plan", "--stage", "2", "--records", path, "--go-sentence", GO, "--build-sha", SHA_A,
                    "--services", value]) == 2
    out = capsys.readouterr().out
    assert "refused: services_empty" in out and "services:" not in out.replace("refused: services_empty", "")


@pytest.mark.parametrize("value", ["federation", "registry,nope", "REGISTRY", "kill-switch"])
def test_an_unknown_service_name_is_refused_with_the_compose_names(value, tmp_path, capsys):
    path = _clean_records(tmp_path)
    assert sc.main(["plan", "--stage", "2", "--records", path, "--go-sentence", GO, "--build-sha", SHA_A,
                    "--services", value]) == 2
    out = capsys.readouterr().out
    assert "refused: services_unknown" in out and "fedbroker" in out


def test_a_go_sentence_without_a_build_sha_is_refused_and_a_plan_without_one_is_not(tmp_path, capsys):
    path = _clean_records(tmp_path)
    assert sc.main(["plan", "--stage", "2", "--records", path, "--go-sentence", GO]) == 2
    assert "refused: build_sha_required" in capsys.readouterr().out
    assert sc.main(["plan", "--stage", "1", "--records", str(tmp_path / "x.jsonl")]) == 2    # no alerts proof: other refusal
    r = sc.Records(str(tmp_path / "y.jsonl"))
    r.append("alerts_proven", ok=True)
    assert sc.main(["plan", "--stage", "1", "--records", str(tmp_path / "y.jsonl")]) == 0     # no go sentence, no sha needed


def test_the_services_flag_reaches_the_controller_as_expected_services(tmp_path, monkeypatch):
    seen = {}
    real = sc.Controller

    class Spy(real):
        def __init__(self, *a, **k):
            seen.update(k)
            super().__init__(*a, **k)

    monkeypatch.setattr(sc, "Controller", Spy)
    path = _clean_records(tmp_path)
    assert sc.main(["plan", "--stage", "2", "--records", path, "--go-sentence", GO, "--build-sha", SHA_A,
                    "--services", "registry,killswitch"]) == 0
    assert tuple(seen["expected_services"]) == ("registry", "killswitch") and seen["build_sha"] == SHA_A
    seen.clear()
    assert sc.main(["plan", "--stage", "2", "--records", path, "--go-sentence", GO, "--build-sha", SHA_A]) == 0
    assert seen["expected_services"] is None


def test_the_runbook_shows_the_two_flags_and_the_matching_expected_services():
    text = (ROOT / "docs" / "runbooks" / "v1.2-deploy-rollback.md").read_text(encoding="utf-8")
    section = text[text.index("## Stage controller (P36, G24)"):]
    for needle in ("--services", "--build-sha", "build_sha_required", "expected_services", "services_unknown"):
        assert needle in section, needle


@pytest.mark.parametrize("sentence", ["", "   ", GO])
def test_any_go_sentence_argument_even_an_empty_one_needs_a_build_sha(sentence, tmp_path, capsys):
    path = _clean_records(tmp_path)
    assert sc.main(["plan", "--stage", "2", "--records", path, "--go-sentence", sentence]) == 2
    assert "refused: build_sha_required" in capsys.readouterr().out

