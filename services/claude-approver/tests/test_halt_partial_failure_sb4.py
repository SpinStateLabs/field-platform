"""POST /halt/{agent}: the partial-failure paths are pinned as they behave TODAY
(scout S-B4). Only the archive failure was tested. These tests do NOT say 200 is right:
when nothing was interrupted the route still answers 200 with the errors in the body, and
whether that should be a 502 or a flag is an open question for Don. If it changes, these
tests change with it, on purpose."""
from __future__ import annotations

from approver_fakes import CONSOLE_AGENT, FIELD_AGENT, FakeAPIError
from fastapi.testclient import TestClient

from claude_approver.api import create_app

ORIGIN = {"x-field-kill-origin": "kill-switch"}


def _halt(make_approver):
    return TestClient(create_app(make_approver())).post(f"/halt/{FIELD_AGENT}", headers=ORIGIN)


def test_a_sessions_list_failure_is_a_top_level_error_and_the_status_is_200(console, make_approver, mapped):
    console.add_session("sesn_a", CONSOLE_AGENT, status="idle")
    console.fail["sessions.list"] = FakeAPIError(503)
    resp = _halt(make_approver)
    assert resp.status_code == 200
    body = resp.json()
    assert body["sessions"] == []
    assert body["errors"] == [{"console_agent_id": CONSOLE_AGENT,
                               "error": "sessions.list failed (FakeAPIError 503)"}]
    assert console.count("events.send") == 0 and console.count("sessions.archive") == 0
    assert console.sessions["sesn_a"].archived_at is None          # nothing was touched


def test_an_interrupt_failure_is_reported_per_session(
        console, make_approver, mapped):
    console.add_session("sesn_a", CONSOLE_AGENT, status="idle")
    console.fail["events.send"] = FakeAPIError(500)
    resp = _halt(make_approver)
    assert resp.status_code == 200
    (row,) = resp.json()["sessions"]
    assert row["id"] == "sesn_a" and row["interrupted"] is False
    assert row["error"] == "interrupt failed (FakeAPIError 500)"
    assert "errors" not in resp.json()


def test_a_retrieve_failure_is_reported_per_session_and_it_is_not_archived(console, make_approver, mapped):
    console.add_session("sesn_a", CONSOLE_AGENT, status="running")
    console.fail["sessions.retrieve"] = FakeAPIError(502)
    resp = _halt(make_approver)
    assert resp.status_code == 200
    (row,) = resp.json()["sessions"]
    assert row["interrupted"] is True and row["archived"] is False
    assert row["error"] == "retrieve failed (FakeAPIError 502)"
    assert console.count("sessions.archive") == 0


def test_one_failing_session_does_not_stop_the_others(console, make_approver, mapped):
    console.add_session("sesn_a", CONSOLE_AGENT, status="idle")
    console.add_session("sesn_b", CONSOLE_AGENT, status="idle")
    real = console.fail

    class _FailFirstSend(dict):
        def get(self, key, default=None):
            if key == "events.send" and console.count("events.send") == 1:  # the call is recorded first
                return FakeAPIError(500)
            return real.get(key, default)

    console.fail = _FailFirstSend()
    rows = _halt(make_approver).json()["sessions"]
    by = {r["id"]: r for r in rows}
    assert len(by) == 2
    assert sorted(r["interrupted"] for r in rows) == [False, True]
    # TODAY a session whose interrupt failed is still polled and, being idle, archived:
    # a failed interrupt does not skip the wait. Pinned, not endorsed.
    assert all(r["archived"] for r in rows)


def test_the_error_text_never_carries_the_exception_message(console, make_approver, mapped):
    secret = "zz-marker-do-not-echo"
    console.add_session("sesn_a", CONSOLE_AGENT, status="idle")
    console.fail["sessions.list"] = RuntimeError(secret)
    console.fail["events.send"] = RuntimeError(secret)
    assert secret not in _halt(make_approver).text


def test_a_clean_halt_has_no_errors_key(console, make_approver, mapped):
    console.add_session("sesn_a", CONSOLE_AGENT, status="idle")
    body = _halt(make_approver).json()
    assert "errors" not in body and body["sessions"][0]["archived"] is True
