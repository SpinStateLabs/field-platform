"""The approval loop: one ``tick()`` against a FakeConsole and recorded FIELD services."""

from __future__ import annotations

import json

import httpx
import pytest

from approver_fakes import CONSOLE_AGENT, FIELD_AGENT, TOKEN, FakeAPIError, default_map, set_map

SID = "sesn_01"


def _pending(console, *asks, sid=SID, agent=CONSOLE_AGENT):
    """A session idle with requires_action on the given ask events."""
    console.add_session(sid, agent)
    evs = [console.ask(sid, name, **kw) for name, kw in asks]
    console.idle(sid, event_ids=[e.id for e in evs])
    return evs


# --------------------------------------------------------------- allow / deny


@pytest.mark.expects_allow
def test_allow_round_trip(console, field, make_approver, mapped):
    (ev,) = _pending(console, ("bash", {}))
    a = make_approver()
    a.tick()

    (check,) = field.checks()
    assert check["agent_id"] == FIELD_AGENT
    assert check["action"] == "run commands in sandbox"
    assert check["token_id"] == TOKEN
    assert check["irreversible"] is False
    ctx = check["context"]
    assert ctx["source"] == "claude-approver"
    assert ctx["console_session_id"] == SID
    assert ctx["console_agent_id"] == CONSOLE_AGENT
    assert ctx["tool_name"] == "bash"
    assert ctx["event_id"] == ev.id

    (conf,) = console.confirmations(SID)
    assert conf == {"type": "user.tool_confirmation", "tool_use_id": ev.id, "result": "allow"}
    assert conf["tool_use_id"].startswith("sevt_")

    (hb,) = field.heartbeats()
    assert hb.method == "POST"
    assert str(hb.url) == f"http://killswitch.test:8005/heartbeat/{FIELD_AGENT}"
    stats = a.stats()
    assert stats["allowed"] == 1 and stats["heartbeats"] == 1 and stats["denied_total"] == 0
    (rec,) = stats["decisions"]
    assert rec["decision"] == "allow" and rec["event_id"] == ev.id and rec["sent"] is True
    assert rec["ms_sentinel"] is not None and rec["ms_total"] >= rec["ms_sentinel"]


def test_deny_on_block_carries_the_clause(console, field, make_approver, mapped):
    (ev,) = _pending(console, ("bash", {}))
    field.sentinel = lambda r: field.verdict(
        "BLOCK", "D.scope", ["action 'run commands in sandbox' not in token scope", "second"])
    a = make_approver()
    a.tick()
    (conf,) = console.confirmations(SID)
    assert conf["result"] == "deny" and conf["tool_use_id"] == ev.id
    assert conf["deny_message"] == (
        "D.scope: action 'run commands in sandbox' not in token scope; second")
    assert a.stats()["denied"]["sentinel_block"] == 1
    assert a.stats()["decisions"][0]["clause_id"] == "D.scope"


def test_deny_on_escalate_says_a_human_holds_it(console, field, make_approver, mapped):
    _pending(console, ("bash", {}))
    field.sentinel = lambda r: field.verdict("ESCALATE", "E.escalation_trigger", ["trigger matched"])
    a = make_approver()
    a.tick()
    (conf,) = console.confirmations(SID)
    assert conf["result"] == "deny"
    assert conf["deny_message"] == (
        "escalated: a human holds this item; E.escalation_trigger: trigger matched")
    assert a.stats()["denied"]["sentinel_escalate"] == 1


def _raise(exc):
    def handler(request):
        raise exc
    return handler


@pytest.mark.parametrize(
    "handler, expected",
    [
        (_raise(httpx.ConnectError("refused")), "claude-approver: sentinel unreachable (ConnectError)"),
        (_raise(httpx.ReadTimeout("slow")), "claude-approver: sentinel timed out"),
        (lambda r: httpx.Response(503, json={"decision": "ALLOW"}), "claude-approver: sentinel answered HTTP 503"),
        (lambda r: httpx.Response(201, json={"decision": "ALLOW"}), "claude-approver: sentinel answered HTTP 201"),
        (lambda r: httpx.Response(200, text="ALLOW"), "claude-approver: sentinel answered non-JSON"),
        (lambda r: httpx.Response(200, json=["ALLOW"]), "claude-approver: sentinel answered a non-object"),
        (lambda r: httpx.Response(200, json={"decision": "MAYBE"}), "claude-approver: sentinel answered an unknown decision"),
        (lambda r: httpx.Response(200, json={"decision": "allow"}), "claude-approver: sentinel answered an unknown decision"),
        (lambda r: httpx.Response(200, json={"decision": " ALLOW"}), "claude-approver: sentinel answered an unknown decision"),
        (lambda r: httpx.Response(200, json={"decision": True}), "claude-approver: sentinel answered an unknown decision"),
        (lambda r: httpx.Response(200, json={}), "claude-approver: sentinel answered an unknown decision"),
    ],
    ids=["exception", "timeout", "non-200", "201", "non-json", "non-object", "unknown",
         "lowercase-allow", "padded-allow", "boolean", "no-decision"],
)
def test_every_sentinel_failure_denies(console, field, make_approver, mapped, handler, expected):
    _pending(console, ("bash", {}))
    field.sentinel = handler
    a = make_approver()
    a.tick()
    (conf,) = console.confirmations(SID)
    assert conf["result"] == "deny"
    assert conf["deny_message"] == expected
    assert a.stats()["denied"]["sentinel_error"] == 1
    assert a.stats()["allowed"] == 0


def test_unmapped_agent_denies_and_nothing_else_happens(console, field, make_approver, monkeypatch):
    # the Console agent is in the map, but with no FIELD identity
    set_map(monkeypatch, {CONSOLE_AGENT: {"token_id": TOKEN}})
    from approver_fakes import usage

    console.add_session(SID, CONSOLE_AGENT, use=usage(100, 10))
    ev = console.ask(SID, "bash")
    console.idle(SID)
    a = make_approver()
    a.tick()
    (conf,) = console.confirmations(SID)
    assert conf["result"] == "deny" and conf["tool_use_id"] == ev.id
    assert conf["deny_message"] == "claude-approver: entry has no field_agent_id"
    assert field.requests == []  # no sentinel, no heartbeat, no usage
    assert a.stats()["denied"]["unmapped"] == 1


def test_an_agent_absent_from_the_map_is_never_touched(console, field, make_approver, mapped):
    _pending(console, ("bash", {}), sid="sesn_other", agent="agent_not_in_map")
    a = make_approver()
    a.tick()
    assert console.sends() == []
    assert field.requests == []
    assert all(kw.get("agent_id") == CONSOLE_AGENT for n, kw in console.calls if n == "sessions.list")


def test_a_session_the_filter_should_not_have_returned_is_skipped(console, field, make_approver, mapped):
    _pending(console, ("bash", {}), sid="sesn_stray", agent="agent_not_in_map")
    original = console.beta.sessions.list
    console.beta.sessions.list = lambda **kw: list(console.sessions.values())  # filter ignored
    a = make_approver()
    a.tick()
    console.beta.sessions.list = original
    assert console.sends() == [] and field.requests == []


# --------------------------------------------------------------- which events


def test_allow_and_deny_events_are_never_confirmed(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    console.ask(SID, "read", permission="allow")
    console.ask(SID, "bash", permission="deny")
    console.ask(SID, "grep", permission=None)
    ask = console.ask(SID, "write")
    console.idle(SID)
    a = make_approver()
    a.tick()
    confs = console.confirmations(SID)
    assert [c["tool_use_id"] for c in confs] == [ask.id]
    assert len(field.checks()) == 1


def test_only_allow_deny_events_means_no_send_at_all(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    console.ask(SID, "read", permission="allow")
    console.ask(SID, "bash", permission="deny")
    console.idle(SID)
    make_approver().tick()
    assert console.sends() == [] and field.checks() == []


@pytest.mark.expects_allow
def test_confirmed_event_is_not_answered_twice_across_ticks(console, field, make_approver, mapped):
    (ev,) = _pending(console, ("bash", {}))
    a = make_approver()
    a.tick()
    assert len(console.confirmations(SID)) == 1
    # the session goes idle requires_action again on a NEW call; the old one is answered
    console.add_event(SID, "session.status_running")
    ev2 = console.ask(SID, "edit")
    console.idle(SID)
    a.tick()
    confs = console.confirmations(SID)
    assert [c["tool_use_id"] for c in confs] == [ev.id, ev2.id]
    assert [c["result"] for c in confs] == ["allow", "allow"]
    assert len(field.checks()) == 2
    # a third tick with nothing new answers nothing
    console.touch(SID)
    a.tick()
    assert len(console.confirmations(SID)) == 2
    assert len(field.checks()) == 2


def test_an_event_confirmed_by_someone_else_is_not_answered(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    ev = console.ask(SID, "bash")
    console.add_event(SID, "user.tool_confirmation", tool_use_id=ev.id, result="deny")
    console.idle(SID)
    make_approver().tick()
    assert console.sends() == [] and field.checks() == []


def test_second_tick_reads_only_new_events(console, field, make_approver, mapped):
    _pending(console, ("bash", {}))
    a = make_approver()
    a.tick()
    first = [kw for n, kw in console.calls if n == "events.list"]
    assert "created_at_gte" not in first[0]  # the first read takes everything
    console.add_event(SID, "session.status_running")
    console.ask(SID, "edit")
    console.idle(SID)
    a.tick()
    second = [kw for n, kw in console.calls if n == "events.list"][-1]
    assert second["created_at_gte"] is not None and second["order"] == "asc"


@pytest.mark.expects_allow
def test_all_of_one_sessions_confirmations_go_in_one_send(console, field, make_approver, mapped):
    evs = _pending(console, ("bash", {}), ("write", {}), ("edit", {}))
    field.sentinel = lambda r: (
        field.verdict("ALLOW") if json.loads(r.content)["context"]["tool_name"] != "edit"
        else field.verdict("BLOCK", "D.scope", ["no"]))
    make_approver().tick()
    (send,) = console.sends(SID)
    assert [e["tool_use_id"] for e in send["events"]] == [e.id for e in evs]
    assert [e["result"] for e in send["events"]] == ["allow", "allow", "deny"]
    assert len(field.heartbeats()) == 3


def test_not_requires_action_means_nothing_is_answered(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    console.ask(SID, "bash")
    console.idle(SID, reason="end_turn")
    make_approver().tick()
    assert console.sends() == [] and field.checks() == []


def test_running_and_terminated_sessions_are_not_read(console, field, make_approver, mapped):
    console.add_session("sesn_run", CONSOLE_AGENT, status="running")
    console.ask("sesn_run", "bash")
    console.add_session("sesn_term", CONSOLE_AGENT, status="terminated")
    console.ask("sesn_term", "bash")
    make_approver().tick()
    assert console.count("events.list") == 0 and console.sends() == []


def test_environment_filter(console, field, make_approver, mapped, monkeypatch):
    monkeypatch.setenv("CLAUDE_APPROVER_ENVIRONMENT_ID", "env_gb10")
    _pending(console, ("bash", {}))  # env_1
    make_approver().tick()
    assert console.sends() == [] and field.requests == []


def test_custom_tool_pending_leaves_the_session_untouched(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    console.ask(SID, "bash")
    console.add_event(SID, "agent.custom_tool_use", name="enter_time_in_portal", input={})
    console.idle(SID)
    a = make_approver()
    a.tick()
    a.tick()
    assert console.sends() == [] and field.checks() == []
    s = a.stats()
    assert s["custom_tool_pending"] == 1  # counted once per event, not per tick
    assert s["custom_tool_pending_now"] == 1


@pytest.mark.expects_allow
def test_answered_custom_tool_no_longer_blocks(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    custom = console.add_event(SID, "agent.custom_tool_use", name="x", input={})
    console.add_event(SID, "user.custom_tool_result", custom_tool_use_id=custom.id)
    ev = console.ask(SID, "bash")
    console.idle(SID)
    make_approver().tick()
    assert [c["tool_use_id"] for c in console.confirmations(SID)] == [ev.id]
    assert console.confirmations(SID)[0]["result"] == "allow"


# --------------------------------------------------------------- action strings


@pytest.mark.expects_allow
def test_mcp_tool_action_is_its_name(console, field, make_approver, mapped):
    (ev,) = _pending(console, ("create_issue", {"etype": "agent.mcp_tool_use"}))
    make_approver().tick()
    (check,) = field.checks()
    assert check["action"] == "create_issue"
    assert check["context"]["mcp_server_name"] == "github"
    assert check["context"]["event_type"] == "agent.mcp_tool_use"
    assert console.confirmations(SID)[0] == {
        "type": "user.tool_confirmation", "tool_use_id": ev.id, "result": "allow"}


def test_builtin_default_map(console, field, make_approver, mapped):
    _pending(console, ("bash", {}), ("write", {}), ("edit", {}), ("read", {}), ("web_fetch", {}))
    make_approver().tick()
    assert [c["action"] for c in field.checks()] == [
        "run commands in sandbox", "run commands in sandbox", "run commands in sandbox",
        "read", "web_fetch"]


def test_action_precedence_agent_then_global_then_default(console, field, make_approver, monkeypatch):
    set_map(monkeypatch, default_map(actions={"read": "draft daily timesheet"}))
    monkeypatch.setenv("CLAUDE_APPROVER_TOOL_MAP", json.dumps(
        {"read": "global read", "write": "global write", "create_issue": "file a ticket"}))
    _pending(console, ("read", {}), ("write", {}), ("bash", {}),
             ("create_issue", {"etype": "agent.mcp_tool_use"}), ("glob", {}))
    make_approver().tick()
    assert [c["action"] for c in field.checks()] == [
        "draft daily timesheet",  # per-agent beats global
        "global write",  # global beats default
        "run commands in sandbox",  # default
        "file a ticket",  # global applies to MCP tools too
        "glob",  # anything else: its own name
    ]


def test_invalid_tool_map_denies_everything(console, field, make_approver, mapped, monkeypatch):
    monkeypatch.setenv("CLAUDE_APPROVER_TOOL_MAP", "{not json")
    _pending(console, ("bash", {}))
    a = make_approver()
    a.tick()
    (conf,) = console.confirmations(SID)
    assert conf["result"] == "deny"
    assert conf["deny_message"] == "claude-approver: CLAUDE_APPROVER_TOOL_MAP is not valid JSON"
    assert field.checks() == []
    assert a.stats()["denied"]["config_error"] == 1


def test_agent_map_file_path_and_inline_both_load(console, field, make_approver, monkeypatch, tmp_path):
    path = tmp_path / "approver-map.json"
    path.write_text(json.dumps(default_map(actions={"bash": "from the file"})), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_APPROVER_AGENT_MAP", str(path))
    _pending(console, ("bash", {}))
    make_approver().tick()
    assert field.checks()[0]["action"] == "from the file"


def test_invalid_agent_map_touches_nothing(console, field, make_approver, monkeypatch):
    monkeypatch.setenv("CLAUDE_APPROVER_AGENT_MAP", "{broken")
    _pending(console, ("bash", {}))
    a = make_approver()
    a.tick()
    assert console.calls == [] and field.requests == []
    assert a.stats()["agent_map_error"] == "agent map is not valid JSON"


def test_example_map_shape_parses(monkeypatch):
    """The shape of FORCE-FIELD/tasks/claude-platform-examples/ssl-timekeeping-agent/approver-map.json."""
    from claude_approver import config

    example = {
        "_comment": "Loaded by the approver.",
        "agent_X": {
            "field_agent_id": "ssl-timekeeping-agent", "token_id": "tok",
            "actions": {"read": "draft daily timesheet", "write": "draft daily timesheet"},
            "custom_tools": {"enter_time_in_portal": "enter time in client portal"},
        },
    }
    amap = config.parse_agent_map(json.dumps(example))
    assert amap.error is None and list(amap.entries) == ["agent_X"]
    entry = amap.entries["agent_X"]
    assert entry.problem is None and entry.custom_tools["enter_time_in_portal"]
    assert amap.field_ids() == {"ssl-timekeeping-agent"}


# --------------------------------------------------------------- resilience


@pytest.mark.expects_allow
def test_heartbeat_failure_is_counted_and_changes_nothing(console, field, make_approver, mapped):
    _pending(console, ("bash", {}))
    field.heartbeat = _raise(httpx.ConnectError("down"))
    a = make_approver()
    a.tick()
    assert console.confirmations(SID)[0]["result"] == "allow"
    s = a.stats()
    assert s["heartbeat_failures"] == 1 and s["heartbeats"] == 0 and s["allowed"] == 1


@pytest.mark.expects_allow
def test_batch_failure_retries_each_confirmation_alone(console, field, make_approver, mapped):
    evs = _pending(console, ("bash", {}), ("write", {}))
    answered_elsewhere = []

    def sentinel(request):
        # while the approver is deciding, someone answers the first call in the Console
        if not answered_elsewhere:
            answered_elsewhere.append(console.add_event(
                SID, "user.tool_confirmation", tool_use_id=evs[0].id, result="deny"))
        return field.verdict("ALLOW")

    field.sentinel = sentinel
    a = make_approver()
    a.tick()
    sends = console.sends(SID)
    assert len(sends) == 3  # the batch (refused), then one per confirmation
    assert [len(s["events"]) for s in sends] == [2, 1, 1]
    s = a.stats()
    assert s["send_failures"] == 2 and s["allowed"] == 1
    ok = [r["event_id"] for r in s["decisions"] if r["sent"]]
    assert ok == [evs[1].id]


@pytest.mark.expects_allow
def test_send_failure_is_retried_next_tick(console, field, make_approver, mapped):
    _pending(console, ("bash", {}))
    console.fail["events.send"] = FakeAPIError(500)
    a = make_approver()
    a.tick()
    assert a.stats()["send_failures"] == 1 and a.stats()["allowed"] == 0
    del console.fail["events.send"]
    console.touch(SID)
    a.tick()
    assert console.confirmations(SID)[-1]["result"] == "allow"


def test_listing_failure_is_counted_and_survived(console, field, make_approver, mapped):
    console.fail["sessions.list"] = FakeAPIError(529)
    a = make_approver()
    summary = a.tick()
    assert summary["sessions"] == 0
    s = a.stats()
    assert s["list_failures"] == 1 and s["ticks"] == 1 and s["last_error"] == (
        "sessions.list failed (FakeAPIError 529)")


@pytest.mark.expects_allow
def test_log_only_shadow_allow_is_recorded_as_shadowed(console, field, make_approver, mapped):
    _pending(console, ("bash", {}))
    field.sentinel = lambda r: field.verdict(
        "ALLOW", None, ["log-only: would BLOCK on D.scope - not enforced"],
        context={"shadowed": True, "would_be": {"decision": "BLOCK", "clause_id": "D.scope"}})
    a = make_approver()
    a.tick()
    assert console.confirmations(SID)[0]["result"] == "allow"
    assert a.stats()["decisions"][0]["shadowed"] is True


def test_unchanged_idle_session_is_not_re_read_every_tick(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    console.idle(SID, reason="end_turn")
    clock = [1000.0]
    a = make_approver(clock=lambda: clock[0])
    a.tick()
    a.tick()
    assert console.count("events.list") == 1
    clock[0] += 61.0  # EVENTS_REFRESH_SECONDS
    a.tick()
    assert console.count("events.list") == 2
    console.touch(SID)
    a.tick()
    assert console.count("events.list") == 3
