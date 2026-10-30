"""C-258 (reviewer C-233 P2): a send that raised AFTER the API applied it.

`_send` reads a 5xx, a transport error, 408 or 429 as "retry next tick", but the confirmation may already have been
applied. The next tick asks the sentinel again (a kill or a revoked token since must win) and sends again; the API
then refuses the duplicate with a 4xx, which used to be read as a terminal rejection (`confirm_rejected`, the ask
marked stale and stranded). The event is now remembered as possibly sent (bounded, per session), and a 4xx for such
an event is "already applied": `confirm_duplicate`, the ask is answered, never stale."""

from __future__ import annotations

import pytest

from approver_fakes import CONSOLE_AGENT, FakeAPIError
from claude_approver.core import POSSIBLY_SENT_MAX

SID = "sesn_retry"


def pending(console, n=1):
    console.add_session(SID, CONSOLE_AGENT)
    asks = [console.ask(SID, "bash") for _ in range(n)]
    console.idle(SID, event_ids=[e.id for e in asks])
    return asks


def lossy_api(console, *, apply_on_failure=True, echo=False, failures=1, status=502):
    """The API applies the confirmation (or not) and the reply is lost, `failures` times; afterwards it refuses a
    confirmation it has already applied, like the real API (400 "already confirmed"). `echo=False`: the applied
    confirmation is not visible in the event list a read returns."""
    real = console._events_send
    applied: list[str] = []
    n = {"calls": 0}

    def send(session_id, events, **kw):
        n["calls"] += 1
        if n["calls"] <= failures:
            console.calls.append(("events.send", {"session_id": session_id, "events": events, **kw}))
            if apply_on_failure:
                for e in events:
                    applied.append(e["tool_use_id"])
                    if echo:
                        console.add_event(session_id, e["type"], **{k: v for k, v in e.items() if k != "type"})
            raise FakeAPIError(status, "reply lost")
        if any(e["tool_use_id"] in applied for e in events):
            console.calls.append(("events.send", {"session_id": session_id, "events": events, **kw}))
            raise FakeAPIError(400, "already confirmed")
        for e in events:
            applied.append(e["tool_use_id"])
        return real(session_id, events, **kw)

    console.beta.sessions.events.send = send
    return applied


@pytest.mark.parametrize("status", [500, 502, 503, 408, 429])
@pytest.mark.expects_allow
def test_a_send_that_failed_after_applying_is_one_effective_approval_and_one_counted_duplicate(
        console, field, make_approver, mapped, status):
    (ev,) = pending(console)
    applied = lossy_api(console, status=status)
    a = make_approver()
    a.tick()
    assert a.sessions[SID].possibly_sent == {ev.id: "allow"}
    console.touch(SID)
    a.tick()
    st = a.stats()
    assert applied == [ev.id]                                          # one effective approval
    assert st["confirm_duplicate"] == 1 and st["confirm_rejected"] == 0
    assert st["send_failures"] == 2 and console.count("events.send") == 2
    state = a.sessions[SID]
    assert ev.id in state.answered and ev.id not in state.stale and ev.id not in state.asks
    assert state.possibly_sent == {}
    assert len(field.checks()) == 2                                    # the retry takes a fresh verdict


def test_once_answered_as_a_duplicate_no_further_send_is_made(console, field, make_approver, mapped):
    (ev,) = pending(console)
    lossy_api(console)
    a = make_approver()
    a.tick()
    console.touch(SID)
    a.tick()
    for _ in range(3):
        console.touch(SID)
        a.tick()
    assert console.count("events.send") == 2 and len(field.checks()) == 2


@pytest.mark.expects_allow
def test_a_failure_that_did_not_apply_is_retried_to_one_approval_with_no_duplicate(console, field, make_approver, mapped):
    (ev,) = pending(console)
    lossy_api(console, apply_on_failure=False)
    a = make_approver()
    a.tick()
    console.touch(SID)
    a.tick()
    accepted = [e for e in console.events[SID] if e.type == "user.tool_confirmation"]
    assert [(e.tool_use_id, e.result) for e in accepted] == [(ev.id, "allow")]
    st = a.stats()
    assert st["confirm_duplicate"] == 0 and st["confirm_rejected"] == 0 and st["allowed"] == 1
    assert a.sessions[SID].possibly_sent == {}


@pytest.mark.expects_allow
def test_when_the_applied_confirmation_is_visible_on_the_next_read_nothing_is_sent_again(console, field, make_approver, mapped):
    (ev,) = pending(console)
    lossy_api(console, echo=True)
    a = make_approver()
    a.tick()
    assert a.sessions[SID].possibly_sent == {ev.id: "allow"}
    console.touch(SID)
    a.tick()
    assert console.count("events.send") == 1 and len(field.checks()) == 1
    assert a.sessions[SID].possibly_sent == {} and ev.id in a.sessions[SID].answered
    assert a.stats()["confirm_duplicate"] == 0


def test_a_4xx_with_no_earlier_failed_send_is_still_a_terminal_rejection(console, field, make_approver, mapped):
    (ev,) = pending(console)
    console.fail["events.send"] = FakeAPIError(400, "no")
    a = make_approver()
    a.tick()
    st = a.stats()
    assert st["confirm_rejected"] == 1 and st["confirm_duplicate"] == 0
    assert ev.id in a.sessions[SID].stale and a.sessions[SID].possibly_sent == {}


@pytest.mark.expects_allow
def test_in_a_batch_only_the_event_whose_earlier_send_failed_is_read_as_a_duplicate(console, field, make_approver, mapped):
    one, two = pending(console, 2)
    real = console._events_send
    applied: list[str] = []
    calls = {"n": 0}

    def send(session_id, events, **kw):
        calls["n"] += 1
        console.calls.append(("events.send", {"session_id": session_id, "events": events, **kw}))
        if calls["n"] == 1:                               # the batch: the API applied ONLY the first, the reply is lost
            applied.append(events[0]["tool_use_id"])
            raise FakeAPIError(503, "lost")
        if any(e["tool_use_id"] in applied for e in events):   # a batch holding an applied one is refused whole
            raise FakeAPIError(400, "already confirmed")
        for e in events:
            applied.append(e["tool_use_id"])
        real(session_id, events, **kw)
        return None

    console.beta.sessions.events.send = send
    a = make_approver()
    a.tick()
    assert a.sessions[SID].possibly_sent == {one.id: "allow", two.id: "allow"}
    console.touch(SID)
    a.tick()                                               # batch refused 4xx -> split: `one` duplicate, `two` sent
    st = a.stats()
    assert sorted(applied) == sorted([one.id, two.id])
    assert st["confirm_duplicate"] == 1 and st["confirm_rejected"] == 0 and st["allowed"] == 1
    state = a.sessions[SID]
    assert {one.id, two.id} <= state.answered and not state.stale and state.possibly_sent == {}


def test_the_possibly_sent_memory_is_bounded_and_forgets_the_oldest(console, field, make_approver, mapped):
    asks = pending(console, POSSIBLY_SENT_MAX + 6)
    console.fail["events.send"] = FakeAPIError(503)
    a = make_approver()
    a.tick()
    marked = list(a.sessions[SID].possibly_sent)
    assert len(marked) == POSSIBLY_SENT_MAX
    assert marked == [e.id for e in asks][-POSSIBLY_SENT_MAX:]


def test_the_bound_is_sixty_four():
    assert POSSIBLY_SENT_MAX == 64


def test_a_superseded_ask_loses_its_possibly_sent_marker(console, field, make_approver, mapped):
    (ev,) = pending(console)
    console.fail["events.send"] = FakeAPIError(503)
    a = make_approver()
    a.tick()
    assert ev.id in a.sessions[SID].possibly_sent
    del console.fail["events.send"]
    console.idle(SID, event_ids=[])                        # a later idle that names nothing: the turn is over
    a.tick()
    state = a.sessions[SID]
    assert state.possibly_sent == {} and ev.id in state.stale
    assert console.count("events.send") == 1


def test_a_deny_verdict_is_remembered_as_deny(console, field, make_approver, mapped):
    (ev,) = pending(console)
    field.sentinel = lambda r: field.verdict("BLOCK", "D.scope", ["no"])
    console.fail["events.send"] = FakeAPIError(500)
    a = make_approver()
    a.tick()
    assert a.sessions[SID].possibly_sent == {ev.id: "deny"}


# --- C-409 (reviewer C-404 F-C404-1/-2/-3; coordinator ruling): only a duplicate-shaped refusal reads as applied -------

from claude_approver.core import DUPLICATE_STATUSES


def sends_503_then(console, status, *, first_session=None):
    """The first send of the run is lost with a 503 (it may have been applied); every later send is refused `status`."""
    n = {"calls": 0}

    def send(session_id, events, **kw):
        n["calls"] += 1
        console.calls.append(("events.send", {"session_id": session_id, "events": events, **kw}))
        raise FakeAPIError(503 if n["calls"] == 1 else status, "scripted")

    console.beta.sessions.events.send = send


def test_the_duplicate_statuses_are_400_and_409():
    assert DUPLICATE_STATUSES == (400, 409)


@pytest.mark.parametrize("status", [400, 409])
@pytest.mark.expects_allow
def test_a_duplicate_shaped_refusal_after_an_unknown_outcome_is_a_duplicate(console, field, make_approver, mapped, status):
    (ev,) = pending(console)
    sends_503_then(console, status)
    a = make_approver()
    a.tick()
    console.touch(SID)
    a.tick()
    st = a.stats()
    assert st["confirm_duplicate"] == 1 and st["confirm_rejected"] == 0
    assert ev.id in a.sessions[SID].answered and ev.id not in a.sessions[SID].stale


@pytest.mark.parametrize("status", [401, 403, 404, 405, 410, 413, 422, 451])
@pytest.mark.expects_allow
def test_any_other_4xx_after_an_unknown_outcome_is_a_permanent_rejection(console, field, make_approver, mapped, status):
    """The probe of F-C404-1: 503 then 403 (a revoked Console key) must not read as success-like."""
    (ev,) = pending(console)
    sends_503_then(console, status)
    a = make_approver()
    a.tick()
    assert a.sessions[SID].possibly_sent == {ev.id: "allow"}
    console.touch(SID)
    a.tick()
    st = a.stats()
    assert st["confirm_rejected"] == 1 and st["confirm_duplicate"] == 0 and st["confirm_duplicate_conflict"] == 0
    state = a.sessions[SID]
    assert ev.id in state.stale and ev.id not in state.answered and state.possibly_sent == {}
    assert state.asks == {}


def test_a_408_or_429_is_still_a_retry_not_a_rejection_of_either_kind(console, field, make_approver, mapped):
    (ev,) = pending(console)
    sends_503_then(console, 429)
    a = make_approver()
    a.tick()
    console.touch(SID)
    a.tick()
    st = a.stats()
    assert st["confirm_rejected"] == 0 and st["confirm_duplicate"] == 0
    assert a.sessions[SID].possibly_sent == {ev.id: "allow"}


@pytest.mark.expects_allow
def test_the_duplicate_record_carries_what_the_earlier_send_said_and_a_conflict_is_counted(console, field, make_approver, mapped):
    """F-C404-2: the allow was lost (503) and may have been applied; the sentinel then says BLOCK and the deny is
    refused as a duplicate: the effective answer may be the earlier allow, and the record and a counter say so."""
    (ev,) = pending(console)
    sends_503_then(console, 400)
    a = make_approver()
    a.tick()
    field.sentinel = lambda r: field.verdict("BLOCK", "D.scope", ["a kill since"])
    console.touch(SID)
    a.tick()
    st = a.stats()
    assert st["confirm_duplicate"] == 1 and st["confirm_duplicate_conflict"] == 1
    last = st["decisions"][-1]
    assert last["decision"] == "deny" and last["possibly_applied"] == "allow" and last["rejected"] is True


@pytest.mark.expects_allow
def test_a_duplicate_with_the_same_result_is_not_a_conflict(console, field, make_approver, mapped):
    (ev,) = pending(console)
    sends_503_then(console, 409)
    a = make_approver()
    a.tick()
    console.touch(SID)
    a.tick()
    st = a.stats()
    assert st["confirm_duplicate"] == 1 and st["confirm_duplicate_conflict"] == 0
    assert st["decisions"][-1]["possibly_applied"] == "allow"


@pytest.mark.expects_allow
def test_the_marker_of_one_session_does_not_leak_into_another_with_the_same_event_id(console, field, make_approver, mapped):
    """F-C404-3: two sessions whose ask events share an id. Session A's send is lost (marker); session B's send is
    refused 400 with no earlier send: B is a rejection, A's retry the duplicate."""
    for sid in ("sesn_a", "sesn_b"):
        console.add_session(sid, CONSOLE_AGENT)
        ev = console.ask(sid, "bash", id="shared-event-id")
        console.idle(sid, event_ids=[ev.id])
    seen = {"sesn_a": 0, "sesn_b": 0}

    def send(session_id, events, **kw):
        seen[session_id] += 1
        console.calls.append(("events.send", {"session_id": session_id, "events": events, **kw}))
        if session_id == "sesn_a" and seen["sesn_a"] == 1:
            raise FakeAPIError(503, "lost")
        raise FakeAPIError(400, "already confirmed")

    console.beta.sessions.events.send = send
    a = make_approver()
    a.tick()
    assert a.sessions["sesn_a"].possibly_sent == {"shared-event-id": "allow"}
    assert a.sessions["sesn_b"].possibly_sent == {}                      # B's was a plain 400: terminal
    assert a.stats()["confirm_rejected"] == 1
    for sid in ("sesn_a", "sesn_b"):
        console.touch(sid)
    a.tick()
    st = a.stats()
    assert st["confirm_duplicate"] == 1 and st["confirm_rejected"] == 1
    assert "shared-event-id" in a.sessions["sesn_a"].answered
    assert "shared-event-id" in a.sessions["sesn_b"].stale


def test_a_batch_whose_event_is_refused_403_is_rejected_not_a_duplicate(console, field, make_approver, mapped):
    one, two = pending(console, 2)
    n = {"calls": 0}

    def send(session_id, events, **kw):
        n["calls"] += 1
        console.calls.append(("events.send", {"session_id": session_id, "events": events, **kw}))
        if n["calls"] == 1:
            raise FakeAPIError(503, "lost")
        if len(events) > 1:
            raise FakeAPIError(400, "batch refused")
        raise FakeAPIError(403 if events[0]["tool_use_id"] == one.id else 409, "split")

    console.beta.sessions.events.send = send
    a = make_approver()
    a.tick()
    console.touch(SID)
    a.tick()
    st = a.stats()
    assert st["confirm_rejected"] == 1 and st["confirm_duplicate"] == 1
    state = a.sessions[SID]
    assert one.id in state.stale and two.id in state.answered
