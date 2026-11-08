"""B-S11-19: /halt shares ONE archive-wait deadline across all sessions."""

from __future__ import annotations

from fastapi.testclient import TestClient

from approver_fakes import CONSOLE_AGENT, FIELD_AGENT

from claude_approver.api import create_app
from claude_approver.core import HALT_POLL_INTERVAL_S

ORIGIN = {"x-field-kill-origin": "kill-switch"}


def test_halt_total_wait_is_one_deadline_not_per_session(console, make_approver, mapped, monkeypatch):
    monkeypatch.setenv("CLAUDE_APPROVER_HALT_WAIT_SECONDS", "20")
    ids = [f"sesn_stuck{i}" for i in range(5)]
    for sid in ids:
        console.add_session(sid, CONSOLE_AGENT, status="running")
        console.retrieve_script[sid] = ["running"]
    clock = [0.0]

    def sleep(s):
        clock[0] += s

    a = make_approver(sleep=sleep, clock=lambda: clock[0])
    resp = TestClient(create_app(a)).post(f"/halt/{FIELD_AGENT}", headers=ORIGIN)
    sessions = resp.json()["sessions"]
    assert sorted(s["id"] for s in sessions) == sorted(ids)
    assert all(s["archived"] is False and s["final_status"] == "running" and s["interrupted"]
               for s in sessions)
    assert console.count("sessions.archive") == 0
    assert clock[0] <= 20 + HALT_POLL_INTERVAL_S, clock[0]
