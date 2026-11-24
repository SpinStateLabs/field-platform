"""S11-18: the "custom tool already counted" marker dies with its session.

`Approver.custom_seen` was a process-wide set that every `agent.custom_tool_use` event id was added to and nothing
removed, so a daemon poller leaked one string per custom tool use for its whole life, while `self.sessions` entries
(and their `seen`/`answered`/`stale`) were already forgotten when a session left the listing. The marker now lives on
`SessionState`: `custom_tool_pending` still counts each custom id exactly once while the session is listed.
"""
from __future__ import annotations

from approver_fakes import CONSOLE_AGENT

SID = "sesn_custom"
N = 25


def _held(approver) -> int:
    """Every custom-tool marker the approver holds anywhere: per session, plus the old process-wide set if it exists."""
    per_session = sum(len(getattr(st, "customs_counted", ())) for st in approver.sessions.values())
    return per_session + len(getattr(approver, "custom_seen", ()))


def _session_with_customs(console, n=N, sid=SID):
    console.add_session(sid, CONSOLE_AGENT)
    for i in range(n):
        console.add_event(sid, "agent.custom_tool_use", name=f"t{i}", input={})
    console.idle(sid)


def test_each_custom_id_is_counted_exactly_once_while_the_session_is_listed(console, field, make_approver, mapped):
    _session_with_customs(console)
    a = make_approver()
    a.tick()
    a.tick()
    a.tick()
    s = a.stats()
    assert s["custom_tool_pending"] == N
    assert s["custom_tool_pending_now"] == N
    assert _held(a) == N


def test_a_new_custom_event_on_a_later_tick_is_counted_once_more(console, field, make_approver, mapped):
    _session_with_customs(console, n=2)
    a = make_approver()
    a.tick()
    console.add_event(SID, "agent.custom_tool_use", name="later", input={})
    console.idle(SID)
    a.tick()
    a.tick()
    assert a.stats()["custom_tool_pending"] == 3


def test_dropping_the_session_from_the_listing_frees_every_marker(console, field, make_approver, mapped):
    _session_with_customs(console)
    a = make_approver()
    a.tick()
    assert _held(a) == N
    del console.sessions[SID]            # archived, deleted or unmapped: it leaves the listing
    a.tick()
    assert SID not in a.sessions
    assert _held(a) == 0


def test_the_structure_stays_bounded_over_many_short_lived_sessions(console, field, make_approver, mapped):
    a = make_approver()
    for k in range(20):
        sid = f"sesn_{k}"
        _session_with_customs(console, n=5, sid=sid)
        a.tick()
        del console.sessions[sid]
        a.tick()
    assert _held(a) == 0
    assert a.stats()["custom_tool_pending"] == 100          # every id was counted once, none leaked


def test_a_session_that_stays_listed_keeps_its_markers_so_it_is_not_recounted(console, field, make_approver, mapped):
    _session_with_customs(console, n=3)
    other = "sesn_other"
    console.add_session(other, CONSOLE_AGENT)
    console.idle(other)
    a = make_approver()
    a.tick()
    del console.sessions[other]
    a.tick()
    a.tick()
    assert a.stats()["custom_tool_pending"] == 3 and _held(a) == 3


def test_a_session_that_returns_after_leaving_is_counted_afresh(console, field, make_approver, mapped):
    """The consequence of a per-session marker: the gauge `custom_tool_pending` is a counter of what each listed
    session showed, so a session that left and came back is read, and counted, again."""
    _session_with_customs(console, n=2)
    a = make_approver()
    a.tick()
    kept = console.sessions.pop(SID)
    a.tick()
    console.sessions[SID] = kept
    a.tick()
    assert a.stats()["custom_tool_pending"] == 4
