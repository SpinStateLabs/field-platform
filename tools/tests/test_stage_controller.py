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

    def __init__(self, services=("registry", "ledger")):
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


def _records(tmp_path, *, alerts_proven=True, gates=()):
    r = sc.Records(tmp_path / "records.jsonl")
    if alerts_proven:
        r.append("alerts_proven", ok=True)
    for g in gates:
        r.append("gate", gate=g, ok=True)
    return r


def _env(ntfy):
    return {alerts.ENV_TOPIC: FAKE_TOPIC, alerts.ENV_BASE_URL: ntfy.base}


def _ctl(tmp_path, ntfy, driver, *, gates=("G21", "G22")):
    return sc.Controller(_records(tmp_path, gates=gates), driver, estate="gb10", env=_env(ntfy))


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
    ctl = sc.Controller(_records(tmp_path), d, estate="gb10", env={})          # no topic: every alert fails
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
    ctl = sc.Controller(_records(tmp_path), d, estate="gb10", env=_env(ntfy))
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
    assert sc.main(["record", "gate", "G22", "--records", rec]) == 0
    assert sc.Records(rec).gate_ok("G22") and not sc.Records(rec).gate_ok("G21")
    sc.main(["record", "alerts-proven", "--records", rec])
    assert sc.main(["plan", "--stage", "2", "--records", rec, "--go-sentence", GO]) == 0


def test_the_runbook_lists_every_abort_condition_and_every_stage_rollback_step():
    text = (ROOT / "docs" / "runbooks" / "v1.2-deploy-rollback.md").read_text(encoding="utf-8")
    section = text[text.index("## Stage controller (P36, G24)"):]
    for name in sc.ABORT_CONDITIONS:
        assert f"`{name}`" in section, name
