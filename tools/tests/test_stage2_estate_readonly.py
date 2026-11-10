"""The read-only ``Stage2Estate`` and its command line, proven on a stub transport (nothing live, no network).

``Host`` stands in for the estate: it answers each probe script with one ``S2PROBE`` line. Every socket is refused for
the whole module, and ``env={}`` means no alert topic is configured, so every controller alert fails fast and offline.
All values are made up."""

from __future__ import annotations

import importlib.util
import io
import json
import socket
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace

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
ro = _load("stage2_estate_readonly")

GO = "Don says: record stage two, change nothing, zebra-quartz"
SHA = "a1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0"
EIGHT = tuple(ro.HEALTH_PATHS)
NATIVE = ["stage_start", "step_done", "step_done", "stage_done"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **kw):
        raise AssertionError("a test opened a socket")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


class Host:
    """The estate as the probe sees it. Each call is one probe; the script it was sent is kept."""

    def __init__(self, *, armed=True, mode="enforce", build=SHA, down=(), bump_at=None, bump_key=None, raw=None):
        self.armed, self.mode, self.build, self.down = armed, mode, build, set(down)
        self.bump_at = bump_at                      # the Nth probe and later show a dropped record
        self.bump_key = bump_key or sc.COUNTER_KEYS[0]
        self.raw = raw                              # answer with this text instead of a snapshot
        self.scripts: list[str] = []

    def snapshot(self):
        services = {}
        for name in EIGHT:
            if name in self.down:
                services[name] = {"status": None, "error": "URLError"}
                continue
            row = {"status": 200, "build_sha": self.build, "operator_mode": "log-only",
                   "dropped_unauthenticated_records": 0, "dropped_refused_records": 0}
            if name == ro.KILL_SWITCH:
                row["operator_mode"] = self.mode
            if self.bump_at is not None and len(self.scripts) >= self.bump_at:
                row[self.bump_key] = 1
            services[name] = row
        return {"v": 1, "override_present": self.armed, "services": services}

    def __call__(self, script):
        self.scripts.append(script)
        if self.raw is not None:
            return self.raw
        return "run-on-gb10: LIVE\n" + ro.MARKER + json.dumps(self.snapshot()) + "\nRC: 0\n"


def _records(tmp_path, name="records.jsonl"):
    rec = sc.Records(tmp_path / name)
    rec.append("alerts_proven", ok=True, sha8=SHA[:8])
    rec.append("gate", gate="G22", ok=True, sha8=SHA[:8])
    return rec


def _kinds(rec):
    return [r["kind"] for r in rec.rows()][2:]       # after the two precondition rows


def _drive(rec, host, **kw):
    estate = ro.ReadOnlyStage2Estate(host, expected_build_sha=SHA)
    result = drv.run_stage2(rec, estate, go_sentence=GO, build_sha=SHA, expected_services=EIGHT, live=True,
                            allow_already_armed=True, env={}, **kw)
    return estate, result


def _go_file(tmp_path, text=GO):
    path = tmp_path / "go.txt"
    path.write_text(text + "\n", encoding="utf-8")
    return str(path)


def _cli(tmp_path, rec, host, *extra, go=True, flag=True, stdin=None):
    argv = ["--records", str(rec.path), "--build-sha", SHA, *extra]
    if flag:
        argv.append("--allow-already-armed")
    if go:
        argv += ["--go-sentence-file", _go_file(tmp_path)]
    return ro.main(argv, transport=host, stdin=stdin, env={})


# ------------------------------------------------------------------ the happy path


def test_an_armed_estate_is_recorded_natively_and_nothing_is_written(tmp_path):
    rec, host = _records(tmp_path), Host()
    estate, result = _drive(rec, host)
    assert result.status == "completed" and result.steps_done == ["write_override", "recreate_killswitch"]
    assert _kinds(rec) == NATIVE and rec.stage_clean(2)
    assert [r["step"] for r in rec.rows() if r["kind"] == "step_done"] == ["write_override", "recreate_killswitch"]
    # one probe per read, none cached: armed? / baseline / check 1 / counters / check 2 (three reads) / counters
    assert estate.probes == len(host.scripts) == 8
    assert set(host.scripts) == {estate.script}      # only ever the read-only probe


def test_the_command_line_live_run_writes_the_native_rows(tmp_path, capsys):
    rec, host = _records(tmp_path), Host()
    assert _cli(tmp_path, rec, host, "--live") == 0
    assert _kinds(rec) == NATIVE and rec.stage_clean(2)
    assert len(host.scripts) == 9                    # the pre-flight probe, then the driver's eight
    assert "stage 2 recorded" in capsys.readouterr().out


def test_the_default_is_a_plan_row_and_no_probe(tmp_path, capsys):
    rec, host = _records(tmp_path), Host()
    assert _cli(tmp_path, rec, host) == 0
    assert _kinds(rec) == ["plan"] and host.scripts == [] and not rec.stage_clean(2)
    assert "dry run" in capsys.readouterr().out


# ------------------------------------------------------------------ the command line refuses


def test_without_allow_already_armed_the_command_line_refuses_and_reads_nothing(tmp_path, capsys):
    rec, host = _records(tmp_path), Host()
    for extra in ((), ("--live",)):
        assert _cli(tmp_path, rec, host, *extra, flag=False) == 2
    assert _kinds(rec) == [] and host.scripts == []
    assert "refused: allow_already_armed_required" in capsys.readouterr().out


def test_an_estate_that_is_not_armed_is_refused_before_stage_start(tmp_path, capsys):
    rec, host = _records(tmp_path), Host(armed=False, mode="log-only")
    assert _cli(tmp_path, rec, host, "--live") == 2
    assert _kinds(rec) == ["refused"] and rec.rows()[-1]["reason"] == "stage2_not_armed"
    assert len(host.scripts) == 1 and "refused: stage2_not_armed" in capsys.readouterr().out


def test_a_half_armed_estate_is_refused_by_the_command_line_before_stage_start(tmp_path):
    rec, host = _records(tmp_path), Host(armed=True, mode="log-only")
    assert _cli(tmp_path, rec, host, "--live") == 2
    assert _kinds(rec) == ["refused"] and rec.rows()[-1]["reason"] == "stage2_not_enforce"
    assert not rec.stage_clean(2)


def test_another_build_on_the_estate_is_refused(tmp_path):
    rec, host = _records(tmp_path), Host(build="f" * 40)
    assert _cli(tmp_path, rec, host, "--live") == 2
    assert rec.rows()[-1]["reason"] == "build_sha_mismatch" and "stage_start" not in _kinds(rec)


def test_a_probe_that_cannot_answer_is_refused_before_stage_start(tmp_path):
    rec, host = _records(tmp_path), Host(raw="ssh: connection refused\n")
    assert _cli(tmp_path, rec, host, "--live") == 2
    assert _kinds(rec) == ["refused"] and rec.rows()[-1]["reason"] == "probe_answer_count"


def test_live_needs_a_transport_and_a_stub_needs_stub_records(tmp_path, capsys):
    rec = _records(tmp_path)
    base = ["--records", str(rec.path), "--build-sha", SHA, "--allow-already-armed", "--go-sentence-file",
            _go_file(tmp_path), "--live"]
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps(Host().snapshot()), encoding="utf-8")
    assert ro.main(base, env={}) == 2
    assert ro.main(base + ["--stub-snapshot", str(snap)], env={}) == 2
    assert ro.main(base + ["--stub-snapshot", str(snap), "--pg-run", "x.py"], env={}) == 2
    assert ro.main(base + ["--pg-run", str(tmp_path / "absent.py")], env={}) == 2
    out = capsys.readouterr().out
    for reason in ("transport_required", "stub_needs_stub_records", "one_transport_only", "pg_run_not_found"):
        assert f"refused: {reason}" in out
    assert _kinds(rec) == []


def test_a_stub_snapshot_run_records_into_a_stub_records_file(tmp_path):
    rec = _records(tmp_path, "records.stub.jsonl")
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps(Host().snapshot()), encoding="utf-8")
    argv = ["--records", str(rec.path), "--build-sha", SHA, "--allow-already-armed", "--go-sentence-file",
            _go_file(tmp_path), "--live", "--stub-snapshot", str(snap)]
    assert ro.main(argv) == 0                        # no env given: a stub run always gets an empty alert environment
    assert _kinds(rec) == NATIVE


# ------------------------------------------------------------------ fail closed


def test_a_half_armed_estate_fails_closed_through_the_driver(tmp_path):
    """Override present, kill-switch still log-only: the mode check fails, the no-op rollback cannot verify enforce."""
    rec, host = _records(tmp_path), Host(armed=True, mode="log-only")
    estate, result = _drive(rec, host)
    assert result.status == "rollback_failed" and result.abort == "phase_g_check_failed"
    kinds = _kinds(rec)
    assert "stage_done" not in kinds and kinds[-1] == "rollback_failed" and not rec.stage_clean(2)
    assert rec.unresolved(2) == "rollback_failed_unresolved"
    assert set(host.scripts) == {estate.script}


@pytest.mark.parametrize("call", [lambda e: e.write_override(), lambda e: e.delete_override(),
                                  lambda e: e.recreate_kill_switch(True), lambda e: e.recreate_kill_switch(False),
                                  lambda e: e.recreate_kill_switch(with_override=True)])
def test_every_write_method_raises_and_runs_no_probe(call):
    host = Host()
    estate = ro.ReadOnlyStage2Estate(host)
    with pytest.raises(ro.ReadOnlyViolation):
        call(estate)
    assert host.scripts == [] and estate.probes == 0


def test_a_write_reached_through_the_driver_raises_and_the_run_fails_closed(tmp_path):
    """The estate is NOT armed, so the driver does call write_override: it raises, the rollback raises, nothing is
    written to the estate and the stage is never recorded done."""
    rec, host = _records(tmp_path), Host(armed=False, mode="log-only")
    estate, result = _drive(rec, host)
    assert result.status == "rollback_failed" and result.abort == "controller_error" and result.steps_done == []
    assert "stage_done" not in _kinds(rec) and not rec.stage_clean(2)
    assert set(host.scripts) == {estate.script}
    with pytest.raises(ro.ReadOnlyViolation):
        drv.Stage2Actions(estate).do(2, "write_override")
    with pytest.raises(ro.ReadOnlyViolation):
        drv.Stage2Actions(estate).do(2, "delete_override")


@pytest.mark.parametrize("key,abort", [("dropped_unauthenticated_records", "dropped_unauth_increase"),
                                       ("dropped_refused_records", "dropped_refused_increase")])
def test_a_counter_that_rises_aborts_the_run(tmp_path, key, abort):
    rec, host = _records(tmp_path), Host(bump_at=4, bump_key=key)      # probe 4 is the counters read after step 1
    estate, result = _drive(rec, host)
    assert result.abort == abort and result.status == "aborted_rolled_back" and result.rolled_back != []
    kinds = _kinds(rec)
    assert "stage_done" not in kinds and "abort" in kinds and not rec.stage_clean(2)
    assert set(host.scripts) == {estate.script}      # the "rollback" of an armed estate is a no-op: probes only


def test_a_counter_rise_is_exit_3_on_the_command_line(tmp_path, capsys):
    rec, host = _records(tmp_path), Host(bump_at=5)  # one later: the pre-flight probe comes first
    assert _cli(tmp_path, rec, host, "--live") == 3
    assert "dropped_unauth_increase" in capsys.readouterr().out and "stage_done" not in _kinds(rec)


def test_a_service_that_does_not_answer_is_a_health_failure(tmp_path):
    rec, host = _records(tmp_path), Host(down={"ledger"})
    estate = ro.ReadOnlyStage2Estate(host, expected_build_sha=SHA)
    assert estate.healthy() is False and "ledger" not in estate.counters()
    assert ro.ReadOnlyStage2Estate(host).healthy() is False              # with no build to compare, still not healthy
    assert ro.ReadOnlyStage2Estate(Host()).healthy() is True
    _, result = _drive(rec, host)
    assert result.abort == "health_failure" and "stage_done" not in _kinds(rec)


def test_a_counter_that_is_not_an_integer_is_left_out():
    host = Host()
    snap = host.snapshot()
    snap["services"]["registry"]["dropped_refused_records"] = "0"
    snap["services"]["ledger"]["dropped_unauthenticated_records"] = True
    estate = ro.ReadOnlyStage2Estate(Host(raw=ro.MARKER + json.dumps(snap)))
    counters = estate.counters()
    assert counters["registry"] == {"dropped_unauthenticated_records": 0}
    assert counters["ledger"] == {"dropped_refused_records": 0}
    assert sc._increases(counters, counters) == {sc.Abort.HEALTH}


def test_healthy_needs_the_expected_build_on_every_service():
    assert ro.ReadOnlyStage2Estate(Host(), expected_build_sha=SHA).healthy() is True
    assert ro.ReadOnlyStage2Estate(Host(), expected_build_sha=SHA[:8]).healthy() is True
    assert ro.ReadOnlyStage2Estate(Host(build="f" * 40), expected_build_sha=SHA).healthy() is False
    assert ro.ReadOnlyStage2Estate(Host(build="a"), expected_build_sha=SHA).healthy() is False
    assert ro.ReadOnlyStage2Estate(Host(build=None), expected_build_sha=SHA).healthy() is False


@pytest.mark.parametrize("raw,token", [
    ("", "probe_answer_count"),
    ("nothing useful\nRC: 0\n", "probe_answer_count"),
    (ro.MARKER + "{}\n" + ro.MARKER + "{}\n", "probe_answer_count"),
    (ro.MARKER + "not json", "probe_answer_not_json"),
    (ro.MARKER + "[]", "probe_answer_shape"),
    (ro.MARKER + json.dumps({"v": 2, "override_present": True, "services": {}}), "probe_answer_shape"),
    (ro.MARKER + json.dumps({"v": 1, "override_present": "yes", "services": {}}), "probe_answer_shape"),
    (ro.MARKER + json.dumps({"v": 1, "override_present": True, "services": {"killswitch": {}}}), "probe_answer_shape"),
    (None, "probe_answer_not_text"),
])
def test_an_answer_that_cannot_be_trusted_is_a_probe_error_on_every_read(raw, token):
    estate = ro.ReadOnlyStage2Estate(lambda script: raw)
    for read in (estate.override_present, estate.mode, estate.healthy, estate.counters, estate.preflight):
        with pytest.raises(ro.ProbeError, match=token):
            read()


def test_a_transport_that_raises_is_a_probe_error_and_a_failed_check():
    def broken(script):
        raise OSError("zebra-quartz in a transport message")
    estate = ro.ReadOnlyStage2Estate(broken)
    with pytest.raises(ro.ProbeError, match="probe_transport_failed") as caught:
        estate.override_present()
    assert "zebra" not in str(caught.value)
    assert drv.Stage2Actions(estate, armed_before=True).check(2, "recreate_killswitch") == ["controller_error"]


def test_an_unreadable_kill_switch_mode_is_an_error_not_a_guess():
    for mode in (None, "ENFORCE", "armed", 1):
        with pytest.raises(ro.ProbeError, match="kill_switch_mode_unreadable"):
            ro.ReadOnlyStage2Estate(Host(mode=mode)).mode()
    with pytest.raises(ro.ProbeError):
        ro.ReadOnlyStage2Estate(Host(down={"killswitch"})).mode()
    assert ro.ReadOnlyStage2Estate(Host()).mode() == "enforce"


# ------------------------------------------------------------------ the go sentence


def _all_text(tmp_path, capsys):
    captured = capsys.readouterr()
    files = "".join(p.read_text(encoding="utf-8", errors="replace") for p in tmp_path.iterdir()
                    if p.is_file() and p.name != "go.txt")
    return captured.out + captured.err + files


def test_the_go_sentence_never_reaches_the_output_or_the_records(tmp_path, capsys):
    for host, extra in ((Host(), ()), (Host(), ("--live",)), (Host(bump_at=5), ("--live",)),
                        (Host(mode="log-only"), ("--live",))):
        rec = _records(tmp_path)
        _cli(tmp_path, rec, host, *extra)
        assert all(GO not in script for script in host.scripts)
    text = _all_text(tmp_path, capsys)
    assert "zebra" not in text and GO not in text
    rows = [r for r in sc.Records(tmp_path / "records.jsonl").rows() if r["kind"] == "stage_start"]
    assert rows and all(r["go_sentence_len"] == len(GO) and len(r["go_sentence_sha8"]) == 8 for r in rows)


def test_the_go_sentence_is_read_from_stdin_with_a_byte_order_mark(tmp_path, capsys):
    rec, host = _records(tmp_path), Host()
    stdin = SimpleNamespace(buffer=io.BytesIO((chr(0xFEFF) + GO + "\r\n").encode("utf-8")))
    argv = ["--records", str(rec.path), "--build-sha", SHA, "--allow-already-armed", "--go-sentence-file", "-", "--live"]
    assert ro.main(argv, transport=host, stdin=stdin, env={}) == 0
    start = [r for r in rec.rows() if r["kind"] == "stage_start"][0]
    assert start["go_sentence_len"] == len(GO) and "zebra" not in _all_text(tmp_path, capsys)


@pytest.mark.parametrize("argv", [["--go-sentence", GO], ["--go-sentence=" + GO], [GO], ["--go", GO]])
def test_a_go_sentence_on_the_argument_list_is_a_usage_error_that_echoes_nothing(tmp_path, capsys, argv):
    rec, host = _records(tmp_path), Host()
    for go in (True, False):                         # with the file given too, the parser reaches the stray argument
        assert _cli(tmp_path, rec, host, "--live", *argv, go=go) == 2
    text = _all_text(tmp_path, capsys)
    assert "usage error" in text and "zebra" not in text and host.scripts == [] and _kinds(rec) == []


def test_a_missing_or_unreadable_go_sentence_is_refused(tmp_path, capsys):
    rec, host = _records(tmp_path), Host()
    argv = ["--records", str(rec.path), "--build-sha", SHA, "--allow-already-armed", "--live", "--go-sentence-file"]
    assert ro.main(argv + [str(tmp_path / "absent.txt")], transport=host, env={}) == 2
    bad = tmp_path / "bad.txt"
    bad.write_bytes(bytes([0xFF, 0xFE, 0x00]))
    assert ro.main(argv + [str(bad)], transport=host, env={}) == 2
    empty = tmp_path / "empty.txt"
    empty.write_text("  \n", encoding="utf-8")
    assert ro.main(argv + [str(empty)], transport=host, env={}) == 2
    out = capsys.readouterr().out
    assert out.count("refused: go_sentence_unreadable") == 2 and "refused: go_sentence_missing" in out
    assert "stage_start" not in _kinds(rec)


def test_the_go_sentence_is_not_read_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("GO_SENTENCE", GO)
    monkeypatch.setenv("FIELD_GO_SENTENCE", GO)
    rec, host = _records(tmp_path), Host()
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    argv = ["--records", str(rec.path), "--build-sha", SHA, "--allow-already-armed", "--go-sentence-file", str(empty)]
    assert ro.main(argv, transport=host, env={}) == 2 and _kinds(rec) == ["refused"]


def test_an_unexpected_error_prints_its_type_only(tmp_path, capsys, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("zebra-quartz")
    monkeypatch.setattr(ro.drv, "run_stage2", boom)
    rec, host = _records(tmp_path), Host()
    assert _cli(tmp_path, rec, host) == 1
    assert capsys.readouterr().out.strip() == "error: RuntimeError"


# ------------------------------------------------------------------ the probe script


def test_the_probe_script_is_ascii_lf_and_holds_only_checked_values():
    script = ro.probe_script()
    assert script.encode("ascii") and chr(13) not in script and script.startswith("#!/usr/bin/env bash\n")
    assert script.count("S2PROBE_PY") == 2 and script.endswith("S2PROBE_PY\n")
    for bad in ({"health_base": "http://10.0.0.62:18080"}, {"health_base": "http://127.0.0.1:18080/x"},
                {"health_base": "http://127.0.0.1:18080'; rm -rf x"}, {"override_path": "../x.yml"},
                {"override_path": "/etc/passwd"}, {"override_path": "a b.yml"}, {"override_path": "x.yml\nS2PROBE_PY"},
                {"paths": {"killswitch": "/health?x=$(id)"}}, {"paths": {"kill switch": "/health"}}, {"paths": {}}):
        with pytest.raises(ValueError):
            ro.probe_script(**bad)


def test_the_estate_refuses_a_service_without_a_path_or_without_the_kill_switch():
    for services in (("registry",), ("killswitch", "nonesuch"), ()):
        with pytest.raises(ValueError):
            ro.ReadOnlyStage2Estate(Host(), services=services)


def test_the_probe_reads_the_override_file_and_each_health_with_a_get_and_nothing_else(tmp_path, monkeypatch, capsys):
    """Run the probe's own Python against a fake opener (no socket): the answer is what the estate then reads."""
    script = ro.probe_script()
    source = script.split("<<'S2PROBE_PY'\n", 1)[1].rsplit("S2PROBE_PY\n", 1)[0]
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    override = tmp_path / ro.DEFAULT_OVERRIDE_PATH
    override.parent.mkdir(parents=True)
    override.write_text("services: {}\n", encoding="utf-8")
    before = sorted(p.as_posix() for p in tmp_path.rglob("*"))
    opened: list[tuple] = []

    class Answer:
        def __init__(self, url):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def getcode(self):
            return 200

        def read(self, n):
            mode = "enforce" if self.url.endswith("/killswitch/health") else "log-only"
            return json.dumps({"operator_mode": mode, "build_sha": SHA, "dropped_unauthenticated_records": 0,
                               "dropped_refused_records": 2, "refused_count": 7, "secretish": "x"}).encode()

    class Opener:
        def open(self, url, data=None, timeout=None):
            if url.endswith("/ledger/health"):
                raise OSError("down")
            opened.append((url, data))
            return Answer(url)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: Opener())
    exec(compile(source, "probe", "exec"), {"__name__": "probe"})
    printed = capsys.readouterr().out
    assert sorted(u for u, _ in opened) == sorted(ro.DEFAULT_HEALTH_BASE + p for n, p in ro.HEALTH_PATHS.items()
                                                  if n != "ledger")
    assert all(data is None for _, data in opened)                       # GET only
    assert sorted(p.as_posix() for p in tmp_path.rglob("*")) == before   # nothing written
    assert "secretish" not in printed and "refused_count" not in printed
    estate = ro.ReadOnlyStage2Estate(lambda s: printed, expected_build_sha=SHA)
    assert estate.override_present() is True and estate.mode() == "enforce" and estate.healthy() is False
    counters = estate.counters()
    assert "ledger" not in counters and counters["registry"] == {"dropped_unauthenticated_records": 0,
                                                                 "dropped_refused_records": 2}
    override.unlink()
    exec(compile(source, "probe", "exec"), {"__name__": "probe"})
    assert ro.ReadOnlyStage2Estate(lambda s: capsys.readouterr().out).override_present() is False


# ------------------------------------------------------------------ the pg-run transport


def test_the_pg_run_transport_runs_one_fixed_command_and_removes_its_file(tmp_path):
    seen = {}

    def runner(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        seen["script"] = Path(cmd[2]).read_bytes()
        return SimpleNamespace(returncode=0, stdout="S2PROBE {}\nRC: 0\n")

    transport = ro.PgRunTransport("pg-run.py", SHA, allow_not_tip=True, timeout=90, runner=runner, python="py",
                                  tmpdir=tmp_path)
    script = ro.probe_script()
    assert transport(script) == "S2PROBE {}\nRC: 0\n"
    cmd = seen["cmd"]
    assert cmd[:2] == ["py", "pg-run.py"] and cmd[2].endswith(".sh")
    assert cmd[3:] == ["--live", "--sha", SHA, "--timeout", "90", "--allow-not-tip"]
    assert seen["script"] == script.encode("ascii") and not Path(cmd[2]).exists() and list(tmp_path.iterdir()) == []
    assert seen["kw"]["stdin"] is ro.subprocess.DEVNULL and seen["kw"]["capture_output"] is True
    plain = ro.PgRunTransport("pg-run.py", SHA, runner=runner, python="py", tmpdir=tmp_path)
    assert plain.command("p.sh") == ["py", "pg-run.py", "p.sh", "--live", "--sha", SHA, "--timeout", "120"]


def test_the_pg_run_transport_fails_closed(tmp_path):
    def failing(cmd, **kw):
        return SimpleNamespace(returncode=4, stdout=ro.MARKER + json.dumps(Host().snapshot()))

    def raising(cmd, **kw):
        raise ro.subprocess.TimeoutExpired(cmd, 1)

    with pytest.raises(ro.ProbeError, match="probe_transport_failed"):
        ro.PgRunTransport("pg-run.py", SHA, runner=failing, tmpdir=tmp_path)("x")
    estate = ro.ReadOnlyStage2Estate(ro.PgRunTransport("pg-run.py", SHA, runner=raising, tmpdir=tmp_path))
    with pytest.raises(ro.ProbeError, match="probe_transport_failed"):
        estate.override_present()
    assert list(tmp_path.iterdir()) == []            # the probe file is removed on every path
    for sha, timeout in ((SHA[:8], 120), ("G" * 40, 120), (SHA, 5), (SHA, 5000), (SHA, True)):
        with pytest.raises(ValueError):
            ro.PgRunTransport("pg-run.py", sha, timeout=timeout)


def test_the_module_imports_nothing_that_reaches_an_estate_by_itself():
    """Standard library plus the driver and the controller: no ssh client, no HTTP client, no socket of its own."""
    import ast
    tree = ast.parse((ROOT / "tools" / "stage2_estate_readonly.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported == {"__future__", "argparse", "json", "os", "re", "subprocess", "sys", "tempfile", "pathlib",
                        "typing", "stage2_driver", "stage_controller"}
