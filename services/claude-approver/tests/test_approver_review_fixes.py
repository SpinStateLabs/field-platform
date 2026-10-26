"""Fixes from the independent review of PR #35 head 83ef8f09
(FORCE-FIELD/tasks/progress/pilot-s2-review-pr35-83ef8f0.md, findings 2-6)."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from approver_fakes import CONSOLE_AGENT, FIELD_AGENT, TOKEN, FakeAPIError, set_map, usage

from claude_approver.api import create_app

SID = "sesn_r1"
ORIGIN = {"x-field-kill-origin": "kill-switch"}


def _pending(console, *names, sid=SID):
    console.add_session(sid, CONSOLE_AGENT)
    evs = [console.ask(sid, n) for n in names]
    console.idle(sid)
    return evs


# ------------------------------------------- finding 2b: a 4xx rejection is terminal


def test_a_rejected_confirmation_is_never_rechecked_or_resent(console, field, make_approver, mapped):
    """Reviewer repro: one ask, events.send always 400, 6 ticks -> ONE sentinel check."""
    _pending(console, "bash")
    console.fail["events.send"] = FakeAPIError(400, "not ask")
    a = make_approver()
    for _ in range(6):
        console.touch(SID)
        a.tick()
    assert len(field.checks()) == 1
    s = a.stats()
    assert s["confirm_rejected"] == 1 and s["send_failures"] == 1
    assert s["allowed"] == 0 and s["denied_total"] == 0
    (rec,) = s["decisions"]
    assert rec["sent"] is False and rec["rejected"] is True
    assert field.heartbeats() == []


@pytest.mark.parametrize("exc", [
    FakeAPIError(500), FakeAPIError(503), FakeAPIError(529), FakeAPIError(429), FakeAPIError(408),
    ConnectionError("reset"),
], ids=["500", "503", "529", "429", "408", "transport"])
@pytest.mark.expects_allow
def test_5xx_transport_408_429_are_retried_next_tick(console, field, make_approver, mapped, exc):
    (ev,) = _pending(console, "bash")
    console.fail["events.send"] = exc
    a = make_approver()
    a.tick()
    assert a.stats()["confirm_rejected"] == 0
    del console.fail["events.send"]
    console.touch(SID)
    a.tick()
    # what the API accepted (the echoed events), not every attempt
    accepted = [e for e in console.events[SID] if e.type == "user.tool_confirmation"]
    assert [(e.tool_use_id, e.result) for e in accepted] == [(ev.id, "allow")]
    assert console.count("events.send") == 2
    assert len(field.checks()) == 2  # re-checked: the retry is a fresh verdict


def test_a_failing_batch_that_is_not_a_rejection_is_not_split(console, field, make_approver, mapped):
    _pending(console, "bash", "write", "edit")
    console.fail["events.send"] = FakeAPIError(503)
    a = make_approver()
    a.tick()
    assert console.count("events.send") == 1  # no burst of single sends
    assert a.stats()["send_failures"] == 1 and a.stats()["confirm_rejected"] == 0


# ------------------------------- finding 2a: only the asks the latest idle names


def test_a_stale_ask_from_an_interrupted_turn_is_never_confirmed(console, field, make_approver, mapped):
    """Reviewer repro: stale ask + end_turn + running + fresh ask +
    status_idle(requires_action, event_ids=[fresh]) -> only the fresh one."""
    console.add_session(SID, CONSOLE_AGENT)
    stale = console.ask(SID, "bash")
    console.add_event(SID, "user.interrupt")
    console.idle(SID, reason="end_turn")
    console.add_event(SID, "session.status_running")
    fresh = console.ask(SID, "write")
    console.idle(SID, event_ids=[fresh.id])
    a = make_approver()
    a.tick()
    assert [c["tool_use_id"] for c in console.confirmations(SID)] == [fresh.id]
    assert [c["context"]["event_id"] for c in field.checks()] == [fresh.id]
    assert a.stats()["asks_superseded"] == 1
    # later pauses never revive it
    console.add_event(SID, "session.status_running")
    console.idle(SID, event_ids=[stale.id, "sevt_other"])
    console.touch(SID)
    a.tick()
    assert [c["tool_use_id"] for c in console.confirmations(SID)] == [fresh.id]


def test_a_stale_ask_seen_on_an_earlier_tick_is_dropped_at_the_next_pause(
        console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    stale = console.ask(SID, "bash")
    console.idle(SID, reason="end_turn")  # not requires_action: nothing answered
    a = make_approver()
    a.tick()
    assert console.sends() == []
    console.add_event(SID, "session.status_running")
    fresh = console.ask(SID, "edit")
    console.idle(SID, event_ids=[fresh.id])
    a.tick()
    assert [c["tool_use_id"] for c in console.confirmations(SID)] == [fresh.id]
    assert stale.id in a.sessions[SID].stale


def test_without_event_ids_every_open_ask_is_answered(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    one, two = console.ask(SID, "bash"), console.ask(SID, "write")
    console.idle(SID, omit_ids=True)
    make_approver().tick()
    assert [c["tool_use_id"] for c in console.confirmations(SID)] == [one.id, two.id]


def test_a_superseded_custom_tool_use_no_longer_blocks(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    console.add_event(SID, "agent.custom_tool_use", name="enter_time_in_portal", input={})
    console.add_event(SID, "user.interrupt")
    console.idle(SID, reason="end_turn")
    console.add_event(SID, "session.status_running")
    fresh = console.ask(SID, "bash")
    console.idle(SID, event_ids=[fresh.id])
    make_approver().tick()
    assert [c["tool_use_id"] for c in console.confirmations(SID)] == [fresh.id]


def test_a_restart_does_not_answer_an_event_twice(console, field, make_approver, mapped):
    """Review INFO item: tick, a NEW Approver (empty memory), tick -> one confirmation."""
    _pending(console, "bash")
    make_approver().tick()
    console.touch(SID)
    make_approver().tick()
    assert len(console.confirmations(SID)) == 1
    assert len(field.checks()) == 1


# ------------------------------------------------ finding 3: rescheduling is live


def test_halt_never_archives_a_rescheduling_session(console, make_approver, mapped, monkeypatch):
    monkeypatch.setenv("CLAUDE_APPROVER_HALT_WAIT_SECONDS", "1")
    console.add_session("sesn_resch", CONSOLE_AGENT, status="rescheduling")
    console.retrieve_script["sesn_resch"] = ["rescheduling"]
    clock = [0.0]

    def sleep(s):
        clock[0] += s

    a = make_approver(sleep=sleep, clock=lambda: clock[0])
    body = TestClient(create_app(a)).post(f"/halt/{FIELD_AGENT}", headers=ORIGIN).json()
    assert body["sessions"] == [{"id": "sesn_resch", "interrupted": True, "archived": False,
                                 "final_status": "rescheduling"}]
    assert console.count("sessions.archive") == 0
    assert console.count("sessions.retrieve") >= 5  # it waited for the deadline


def test_halt_archives_once_rescheduling_settles_to_idle(console, make_approver, mapped):
    console.add_session("sesn_resch", CONSOLE_AGENT, status="rescheduling")
    console.retrieve_script["sesn_resch"] = ["rescheduling", "running", "idle"]
    body = TestClient(create_app(make_approver())).post(
        f"/halt/{FIELD_AGENT}", headers=ORIGIN).json()
    assert body["sessions"][0]["archived"] is True
    assert body["sessions"][0]["final_status"] == "idle"


# --------------------------------- finding 4: the estate secret is read per request

FLY_AGENT = "agent_fly"


@pytest.mark.expects_allow
def test_estate_secret_rotation_mid_batch_is_honoured(console, field, make_approver, monkeypatch, tmp_path):
    secret = tmp_path / "fly-secret"
    secret.write_text("first-SENTINEL", encoding="utf-8")
    set_map(monkeypatch, {FLY_AGENT: {"field_agent_id": "git-post-agent", "token_id": TOKEN,
                                      "estate_base_url": "https://fly.test",
                                      "secret_file": str(secret)}})
    console.add_session(SID, FLY_AGENT, use=usage(10, 1))
    console.ask(SID, "bash")
    console.ask(SID, "write")
    console.idle(SID)

    def sentinel(request):
        secret.write_text("second-SENTINEL", encoding="utf-8")  # rotated after the first check
        return field.verdict("ALLOW")

    field.sentinel = sentinel
    make_approver().tick()
    assert [c["result"] for c in console.confirmations(SID)] == ["allow", "allow"]
    by_path = [(r.url.path, r.headers.get("x-field-auth")) for r in field.requests]
    assert by_path[0] == ("/sentinel/check", "first-SENTINEL")
    assert by_path[1] == ("/sentinel/check", "second-SENTINEL")
    assert all(h == "second-SENTINEL" for p, h in by_path[2:])  # heartbeats and the usage post
    assert {p for p, _ in by_path[2:]} == {"/killswitch/heartbeat/git-post-agent", "/governor/usage"}


# ------------------------------------- finding 5: no credentials in estate_base_url


@pytest.mark.parametrize("url", ["https://user:pass@fly.test", "https://user@fly.test",
                                 "http://:pw@fly.test:8080"])
def test_estate_base_url_with_credentials_is_unusable(console, field, make_approver, monkeypatch, url):
    set_map(monkeypatch, {FLY_AGENT: {"field_agent_id": "git-post-agent", "estate_base_url": url}})
    console.add_session(SID, FLY_AGENT, use=usage(10, 1))
    ev = console.ask(SID, "bash")
    console.idle(SID)
    a = make_approver()
    a.tick()
    (conf,) = console.confirmations(SID)
    assert conf == {"type": "user.tool_confirmation", "tool_use_id": ev.id, "result": "deny",
                    "deny_message": "claude-approver: estate_base_url must not carry credentials"}
    assert field.requests == []
    assert "pass" not in json.dumps(a.stats())


# ----------------------------- finding 6: the cursor file is written before memory


def test_a_failed_cursor_write_leaves_memory_unchanged_and_the_delta_is_reposted(
        console, field, make_approver, mapped, monkeypatch, tmp_path):
    import claude_approver.core as core

    console.add_session(SID, CONSOLE_AGENT, use=usage(100, 10))
    real_replace = core.os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(core.os, "replace", flaky_replace)
    a = make_approver()
    a.tick()
    assert a.cursor.get(SID) == {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0}
    assert a.stats()["last_error"] == "usage cursor write failed (OSError)"
    a.tick()  # memory was not advanced: the same delta is posted again, then recorded
    assert [p["input_tokens"] for p in field.usage_posts()] == [100, 100]
    cursor = tmp_path / "data" / "claude-approver" / "usage-cursor.json"
    assert json.loads(cursor.read_text())[SID]["input_tokens"] == 100
    a.tick()
    assert len(field.usage_posts()) == 2
