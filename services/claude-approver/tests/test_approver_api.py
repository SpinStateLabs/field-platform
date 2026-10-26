"""HTTP surface: /health, /stats, /halt, the perimeter, and the key never leaving."""

from __future__ import annotations

import logging
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from approver_fakes import CONSOLE_AGENT, FIELD_AGENT, FakeConsole, FieldServices, usage

from claude_approver import __version__
from claude_approver.api import create_app
from claude_approver.core import Approver, percentile

KEY_SENTINEL = "test-api-key-KEYSENTINEL-do-not-leak-9f8e7d"  # never a real key
ORIGIN = {"x-field-kill-origin": "kill-switch"}


def _key_file(tmp_path, monkeypatch, content=f"\n  {KEY_SENTINEL}  \n"):
    path = tmp_path / "api-key"
    path.write_text(content, encoding="utf-8")
    monkeypatch.setenv("CLAUDE_APPROVER_API_KEY_FILE", str(path))
    return path


# --------------------------------------------------------------------- health


def test_health_without_a_key_file(make_approver, monkeypatch):
    monkeypatch.setenv("FIELD_BUILD_SHA", "abc123")
    body = TestClient(create_app(make_approver(client=None, client_factory=lambda k: None))).get(
        "/health").json()
    assert body == {"ok": True, "service": "claude-approver", "version": __version__,
                    "build_sha": "abc123", "key_file_present": False, "polling": False}


def test_key_never_leaves_the_process(tmp_path, monkeypatch, caplog, field, mapped):
    _key_file(tmp_path, monkeypatch)
    seen_keys = []
    console = FakeConsole()

    def factory(key):
        seen_keys.append(key)
        return console

    console.add_session("sesn_k", CONSOLE_AGENT, use=usage(5, 1))
    console.ask("sesn_k", "bash")
    console.idle("sesn_k")
    a = Approver(client_factory=factory, http=field.client(),
                 cursor_path=tmp_path / "cursor.json", sleep=lambda s: None)
    caplog.set_level(logging.DEBUG)
    a.tick()
    assert seen_keys == [KEY_SENTINEL]  # trimmed, and actually used
    client = TestClient(create_app(a))
    health = client.get("/health")
    assert health.json()["key_file_present"] is True
    bodies = [
        health.text,
        client.get("/stats").text,
        client.post(f"/halt/{FIELD_AGENT}").text,
        client.post(f"/halt/{FIELD_AGENT}", headers=ORIGIN).text,
        client.post("/halt/unmapped", headers=ORIGIN).text,
    ]
    # an SDK error whose message carries the key must not surface either
    def leaky(key):
        raise RuntimeError(f"bad key {key}")

    b = Approver(client_factory=leaky, http=field.client(), cursor_path=tmp_path / "c2.json")
    b.tick()
    bodies += [TestClient(create_app(b)).get("/stats").text,
               TestClient(create_app(b)).post(f"/halt/{FIELD_AGENT}", headers=ORIGIN).text]
    for body in bodies:
        assert KEY_SENTINEL not in body
        assert KEY_SENTINEL[:12] not in body  # not even a prefix
    assert KEY_SENTINEL not in caplog.text
    assert KEY_SENTINEL not in str(console.calls)
    assert b.stats()["last_error"] == "client construction failed (RuntimeError)"


def test_key_file_present_false_for_a_blank_file(tmp_path, monkeypatch, make_approver):
    _key_file(tmp_path, monkeypatch, content="  \n")
    body = TestClient(create_app(make_approver())).get("/health").json()
    assert body["key_file_present"] is False


def test_rotated_key_rebuilds_the_client(tmp_path, monkeypatch, field, mapped):
    path = _key_file(tmp_path, monkeypatch, content="key-one")
    built = []
    a = Approver(client_factory=lambda k: built.append(k) or FakeConsole(), http=field.client(),
                 cursor_path=tmp_path / "c.json")
    a.tick()
    a.tick()
    path.write_text("key-two", encoding="utf-8")
    a.tick()
    assert built == ["key-one", "key-two"]


def test_no_key_means_no_polling(tmp_path, monkeypatch, field, mapped):
    built = []
    a = Approver(client_factory=lambda k: built.append(k), http=field.client(),
                 cursor_path=tmp_path / "c.json")
    a.tick()
    assert built == [] and a.last_tick_had_client is False
    assert field.requests == []


# ---------------------------------------------------------------------- halt


def test_halt_needs_the_origin_header(console, make_approver, mapped):
    console.add_session("sesn_h", CONSOLE_AGENT, status="running")
    client = TestClient(create_app(make_approver()))
    for headers in ({}, {"x-field-kill-origin": "someone-else"}, {"x-field-kill-origin": "Kill-Switch"}):
        resp = client.post(f"/halt/{FIELD_AGENT}", headers=headers)
        assert resp.status_code == 403
    assert console.calls == []  # nothing changed, nothing was even listed


def test_halt_unmapped_agent_is_404(console, make_approver, mapped):
    resp = TestClient(create_app(make_approver())).post("/halt/someone-else", headers=ORIGIN)
    assert resp.status_code == 404
    assert console.calls == []


def test_halt_without_a_key_is_503(make_approver, mapped):
    a = make_approver(client=None, client_factory=lambda k: pytest.fail("no key, no client"))
    resp = TestClient(create_app(a)).post(f"/halt/{FIELD_AGENT}", headers=ORIGIN)
    assert resp.status_code == 503


def test_halt_interrupts_waits_for_idle_then_archives(console, make_approver, mapped):
    console.add_session("sesn_run", CONSOLE_AGENT, status="running")
    console.retrieve_script["sesn_run"] = ["running", "running", "idle"]
    console.add_session("sesn_idle", CONSOLE_AGENT, status="idle")
    console.add_session("sesn_done", CONSOLE_AGENT, status="terminated")
    console.add_session("sesn_other", "agent_unrelated", status="running")
    reason = "x3-abc123 operator said stop\r\nInjected: header " + "z" * 600
    resp = TestClient(create_app(make_approver())).post(
        f"/halt/{FIELD_AGENT}", headers={**ORIGIN, "x-field-kill-reason": quote(reason, safe="")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_id"] == FIELD_AGENT
    assert body["reason"] == reason[:512]
    assert body["sessions"] == [
        {"id": "sesn_run", "interrupted": True, "archived": True, "final_status": "idle"},
        {"id": "sesn_idle", "interrupted": True, "archived": True, "final_status": "idle"},
    ]
    names = [n for n, _ in console.calls]
    # every interrupt goes out before the first wait
    assert names.index("sessions.retrieve") > max(
        i for i, n in enumerate(names) if n == "events.send")
    interrupts = [kw for n, kw in console.calls if n == "events.send"]
    assert all(kw["events"] == [{"type": "user.interrupt"}] for kw in interrupts)
    assert {kw["session_id"] for kw in interrupts} == {"sesn_run", "sesn_idle"}
    assert console.sessions["sesn_other"].archived_at is None
    assert console.sessions["sesn_done"].archived_at is None


def test_halt_never_archives_a_session_still_running(console, make_approver, mapped, monkeypatch):
    monkeypatch.setenv("CLAUDE_APPROVER_HALT_WAIT_SECONDS", "1")
    console.add_session("sesn_stuck", CONSOLE_AGENT, status="running")
    console.retrieve_script["sesn_stuck"] = ["running"]
    clock = [0.0]

    def sleep(s):
        clock[0] += s

    a = make_approver(sleep=sleep, clock=lambda: clock[0])
    resp = TestClient(create_app(a)).post(f"/halt/{FIELD_AGENT}", headers=ORIGIN)
    assert resp.json()["sessions"] == [
        {"id": "sesn_stuck", "interrupted": True, "archived": False, "final_status": "running"}]
    assert console.count("sessions.archive") == 0
    assert console.count("sessions.retrieve") >= 5  # it really waited (0.2 s polls over 1 s)


def test_halt_reports_errors_per_session(console, make_approver, mapped):
    from approver_fakes import FakeAPIError

    console.add_session("sesn_x", CONSOLE_AGENT, status="idle")
    console.fail["sessions.archive"] = FakeAPIError(409)
    body = TestClient(create_app(make_approver())).post(
        f"/halt/{FIELD_AGENT}", headers=ORIGIN).json()
    assert body["sessions"] == [{"id": "sesn_x", "interrupted": True, "archived": False,
                                 "final_status": "idle", "error": "archive failed (FakeAPIError 409)"}]


# ------------------------------------------------------------------ perimeter


def test_perimeter_exempts_only_mapped_halt_paths(console, make_approver, mapped, monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", "perimeter-SENTINEL")
    console.add_session("sesn_p", CONSOLE_AGENT, status="idle")
    client = TestClient(create_app(make_approver()))
    # the kill-switch's signal carries no x-field-auth: handled anyway
    resp = client.post(f"/halt/{FIELD_AGENT}", headers=ORIGIN)
    assert resp.status_code == 200 and resp.json()["sessions"][0]["archived"] is True
    # ... but still needs the origin marker
    assert client.post(f"/halt/{FIELD_AGENT}").status_code == 403
    assert client.get("/stats").status_code == 401
    assert client.get("/stats", headers={"x-field-auth": "perimeter-SENTINEL"}).status_code == 200
    assert client.post("/halt/unmapped", headers=ORIGIN).status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/nope").status_code == 401


# ---------------------------------------------------------------------- stats


def test_stats_percentiles():
    assert percentile([], 50) is None
    assert percentile([5.0], 95) == 5.0
    vals = [float(v) for v in range(1, 101)]
    assert percentile(vals, 50) == 50.0
    assert percentile(vals, 95) == 95.0
    assert percentile([3.0, 1.0, 2.0, 4.0], 50) == 2.0


def test_stats_exposes_counters_decisions_and_latency(console, field, make_approver, mapped):
    a = make_approver()
    for i in range(1, 21):
        a.decisions.append({"ms_sentinel": float(i), "ms_total": float(i * 2)})
    a.decisions.append({"ms_sentinel": None, "ms_total": 1.0})  # an unmapped deny: no sentinel call
    body = TestClient(create_app(a)).get("/stats").json()
    lat = body["latency"]
    assert lat["n"] == 21
    assert lat["ms_sentinel_p50"] == 10.0 and lat["ms_sentinel_p95"] == 19.0
    assert lat["ms_total_p50"] == 20.0 and lat["ms_total_p95"] == 38.0
    for key in ("allowed", "denied", "heartbeats", "usage_posts", "usage_failures", "ticks",
                "last_tick_at", "custom_tool_pending", "decisions"):
        assert key in body
    assert set(body["denied"]) == {"sentinel_block", "sentinel_escalate", "sentinel_error",
                                   "unmapped", "config_error"}


def test_decisions_keep_the_last_500(console, field, make_approver, mapped):
    a = make_approver()
    for i in range(600):
        a.decisions.append({"i": i, "ms_sentinel": 1.0, "ms_total": 1.0})
    d = a.stats()["decisions"]
    assert len(d) == 500 and d[0]["i"] == 100


# ------------------------------------------------------------------------ cli


def test_cli_version():
    from typer.testing import CliRunner

    from claude_approver.cli import app

    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0 and result.output.strip() == f"claude-approver {__version__}"


def test_poller_thread_ticks(console, field, make_approver, mapped, monkeypatch):
    import time

    monkeypatch.setenv("CLAUDE_APPROVER_POLL_SECONDS", "0")  # floored at 0.5 s
    a = make_approver()
    a.start()
    t0 = time.monotonic()
    deadline = t0 + 5
    while a.stats()["ticks"] < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    elapsed = time.monotonic() - t0
    assert a.polling() is True
    a.stop()
    assert a.stats()["ticks"] >= 2
    assert elapsed >= 0.45  # the second tick waited for the floor, not 0 s
