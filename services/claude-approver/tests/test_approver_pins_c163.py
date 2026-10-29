"""C-163 (reviewer C-156 F-C156-3/-4/-5): survivors pinned.

* `shadowed` is True only for a sentinel ALLOW whose context says ``shadowed: true`` (core.py `_check`);
* a terminal rejection inside a split batch is labelled ``rejected`` and never re-sent (`_send`);
* `halt` skips a session of another agent and a session without an id, and stops waiting exactly at
  the deadline;
* config shape checks: every malformed agent-map or tool-map entry becomes an ``AgentEntry.problem``
  (the approver denies ``unmapped``), never a usable entry.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from approver_fakes import (CONSOLE_AGENT, FIELD_AGENT, FakeAPIError, FieldServices, default_map,
                            ns, set_map)
from claude_approver import config
from claude_approver.api import create_app
from claude_approver.core import HALT_POLL_INTERVAL_S

ORIGIN = {"x-field-kill-origin": "kill-switch"}


# --- F-C156-3: shadowed ---------------------------------------------------------------------


@pytest.mark.parametrize("context", [
    {}, {"source": "sentinel"}, {"shadowed": False}, {"shadowed": "true"}, {"shadowed": 1},
    {"would_be": {"decision": "BLOCK"}}], ids=repr)
def test_a_non_shadow_allow_is_not_recorded_as_shadowed(console, field, make_approver, mapped, context):
    console.add_session("sesn_a", CONSOLE_AGENT)
    console.ask("sesn_a")
    console.idle("sesn_a")
    field.sentinel = lambda r: FieldServices.verdict("ALLOW", context=context)
    a = make_approver()
    a.tick()
    [rec] = a.stats()["decisions"]
    assert rec["decision"] == "allow" and rec["shadowed"] is False


@pytest.mark.parametrize("body_context", [None, "shadowed", ["shadowed"], 5], ids=repr)
def test_a_non_dict_context_is_not_shadowed(console, field, make_approver, mapped, body_context):
    import httpx

    console.add_session("sesn_a", CONSOLE_AGENT)
    console.ask("sesn_a")
    console.idle("sesn_a")
    field.sentinel = lambda r: httpx.Response(200, json={
        "decision": "ALLOW", "clause_id": None, "reasons": [], "context": body_context})
    a = make_approver()
    a.tick()
    [rec] = a.stats()["decisions"]
    assert rec["decision"] == "allow" and rec["shadowed"] is False


# --- F-C156-3: a terminal rejection in a split batch ----------------------------------------


def test_a_rejected_confirmation_in_a_split_batch_is_labelled_and_never_resent(
        console, field, make_approver, mapped):
    console.add_session("sesn_s", CONSOLE_AGENT)
    e1 = console.ask("sesn_s", id="sevt_one")
    e2 = console.ask("sesn_s", id="sevt_two")
    console.idle("sesn_s")
    real_send = console.beta.sessions.events.send
    sent = []

    def send(session_id, events, **kw):
        sent.append([e["tool_use_id"] for e in events if e["type"] == "user.tool_confirmation"])
        if len(events) > 1:
            raise FakeAPIError(400, "batch refused")            # the whole batch is rejected ...
        if events[0]["tool_use_id"] == e1.id:
            raise FakeAPIError(400, "someone answered it")     # ... and one is stale for good
        return real_send(session_id=session_id, events=events, **kw)

    console.beta.sessions.events.send = send
    a = make_approver()
    a.tick()
    by_event = {r["event_id"]: r for r in a.stats()["decisions"]}
    assert by_event[e1.id]["sent"] is False and by_event[e1.id]["rejected"] is True
    assert by_event[e2.id]["sent"] is True and "rejected" not in by_event[e2.id]
    assert a.stats()["confirm_rejected"] == 1
    assert sent == [[e1.id, e2.id], [e1.id], [e2.id]]
    a.tick()                                                    # neither is sent again
    assert len(sent) == 3


def test_a_transient_failure_in_a_split_batch_is_retried_not_rejected(
        console, field, make_approver, mapped):
    console.add_session("sesn_t", CONSOLE_AGENT)
    e1 = console.ask("sesn_t", id="sevt_one")
    e2 = console.ask("sesn_t", id="sevt_two")
    console.idle("sesn_t")
    real_send = console.beta.sessions.events.send
    state = {"n": 0}

    def send(session_id, events, **kw):
        state["n"] += 1
        if len(events) > 1:
            raise FakeAPIError(400, "batch refused")
        if events[0]["tool_use_id"] == e1.id and state["n"] < 4:
            raise FakeAPIError(503, "try again")               # transient: retry next tick
        return real_send(session_id=session_id, events=events, **kw)

    console.beta.sessions.events.send = send
    a = make_approver()
    a.tick()
    recs = {r["event_id"]: r for r in a.stats()["decisions"]}
    assert recs[e1.id]["sent"] is False and "rejected" not in recs[e1.id]
    assert recs[e2.id]["sent"] is True
    assert a.stats()["confirm_rejected"] == 0


# --- F-C156-4: halt -------------------------------------------------------------------------


def _list_everything(console):
    console.beta.sessions.list = lambda **kw: list(console.sessions.values())


def test_halt_skips_a_session_the_list_returned_for_another_agent(console, make_approver, mapped):
    console.add_session("sesn_mine", CONSOLE_AGENT, status="idle")
    console.add_session("sesn_other", "agent_unrelated", status="idle")
    _list_everything(console)                                   # the API's agent filter failed open
    body = TestClient(create_app(make_approver())).post(f"/halt/{FIELD_AGENT}", headers=ORIGIN).json()
    assert [s["id"] for s in body["sessions"]] == ["sesn_mine"]
    assert {kw["session_id"] for kw in console.sends()} == {"sesn_mine"}
    assert console.sessions["sesn_other"].archived_at is None


def test_halt_skips_a_session_without_an_id(console, make_approver, mapped):
    console.add_session("sesn_mine", CONSOLE_AGENT, status="idle")
    console.sessions["blank"] = ns(id="", agent=ns(id=CONSOLE_AGENT), status="idle", archived_at=None)
    _list_everything(console)
    body = TestClient(create_app(make_approver())).post(f"/halt/{FIELD_AGENT}", headers=ORIGIN).json()
    assert [s["id"] for s in body["sessions"]] == ["sesn_mine"]
    assert all(kw["session_id"] for kw in console.sends())


def test_halt_stops_waiting_exactly_at_the_deadline(console, make_approver, mapped, monkeypatch):
    """Clock 0, wait 2, one second per sleep: the poll at t=2 is the last (>= deadline)."""
    monkeypatch.setenv("CLAUDE_APPROVER_HALT_WAIT_SECONDS", "2")
    console.add_session("sesn_stuck", CONSOLE_AGENT, status="running")
    console.retrieve_script["sesn_stuck"] = ["running"]
    clock = [0.0]

    def sleep(seconds):
        assert seconds == HALT_POLL_INTERVAL_S
        clock[0] += 1.0

    a = make_approver(sleep=sleep, clock=lambda: clock[0])
    body = TestClient(create_app(a)).post(f"/halt/{FIELD_AGENT}", headers=ORIGIN).json()
    assert body["sessions"][0]["archived"] is False
    assert console.count("sessions.retrieve") == 3             # t=0, t=1, t=2 (deadline: stop)
    assert console.count("sessions.archive") == 0


# --- F-C156-5: config shape checks ----------------------------------------------------------


def entry(**over):
    base = {"field_agent_id": FIELD_AGENT}
    base.update(over)
    return base


def parse(raw):
    m = config.parse_agent_map(json.dumps({CONSOLE_AGENT: raw}))
    assert m.error is None
    return m.entries[CONSOLE_AGENT]


@pytest.mark.parametrize(("raw", "problem"), [
    ("x", "entry is not a JSON object"),
    ([], "entry is not a JSON object"),
    (None, "entry is not a JSON object"),
    ({}, "entry has no field_agent_id"),
    (entry(field_agent_id=""), "entry has no field_agent_id"),
    (entry(field_agent_id="   "), "entry has no field_agent_id"),
    (entry(field_agent_id=5), "entry has no field_agent_id"),
    (entry(token_id=5), "token_id is not a string"),
    (entry(actions=[]), "actions is not an object of non-empty strings"),
    (entry(actions={"bash": ""}), "actions is not an object of non-empty strings"),
    (entry(actions={"bash": "  "}), "actions is not an object of non-empty strings"),
    (entry(actions={"bash": 5}), "actions is not an object of non-empty strings"),
    (entry(custom_tools=[]), "custom_tools is not an object of non-empty strings"),
    (entry(custom_tools={"t": ""}), "custom_tools is not an object of non-empty strings"),
    (entry(custom_tools={"t": 5}), "custom_tools is not an object of non-empty strings"),
    (entry(estate_base_url=5), "estate_base_url is not a string"),
    (entry(estate_base_url="ftp://estate.test"), "estate_base_url is not an http(s) URL"),
    (entry(estate_base_url="http://"), "estate_base_url is not an http(s) URL"),
    (entry(estate_base_url="estate.test:8000"), "estate_base_url is not an http(s) URL"),
    (entry(estate_base_url="http://user:pw@estate.test"), "estate_base_url must not carry credentials"),
    (entry(estate_base_url="http://user@estate.test"), "estate_base_url must not carry credentials"),
    (entry(secret_file=5), "secret_file is not a string"),
], ids=repr)
def test_a_malformed_agent_map_entry_becomes_a_problem(raw, problem):
    e = parse(raw)
    assert e.problem == problem and e.field_agent_id is None
    m = config.parse_agent_map(json.dumps({CONSOLE_AGENT: raw}))
    assert m.consoles_for(FIELD_AGENT) == [] and m.field_ids() == set()


def test_a_well_formed_entry_has_no_problem_and_is_normalised():
    e = parse(entry(token_id="tok_1", actions={"bash": "run it"}, custom_tools={"t": "x"},
                    estate_base_url=" http://estate.test:8000/ ", secret_file=" /run/s "))
    assert e.problem is None and e.field_agent_id == FIELD_AGENT and e.token_id == "tok_1"
    assert e.actions == {"bash": "run it"} and e.custom_tools == {"t": "x"}
    assert e.estate_base_url == "http://estate.test:8000" and e.secret_file == "/run/s"
    bare = parse(entry(actions=None, custom_tools=None, estate_base_url="", secret_file="  ",
                       token_id=None))
    assert bare.problem is None and bare.actions == {} and bare.custom_tools == {}
    assert bare.estate_base_url is None and bare.secret_file is None and bare.token_id is None


def test_a_malformed_entry_is_denied_unmapped_and_never_reaches_the_sentinel(
        console, field, make_approver, monkeypatch):
    set_map(monkeypatch, {CONSOLE_AGENT: entry(actions={"bash": ""})})
    console.add_session("sesn_b", CONSOLE_AGENT)
    console.ask("sesn_b")
    console.idle("sesn_b")
    a = make_approver()
    a.tick()
    [rec] = a.stats()["decisions"]
    assert rec["decision"] == "deny" and rec["reason_class"] == "unmapped"
    assert field.checks() == []


@pytest.mark.parametrize("text", ["", "not json", "[]", '"s"', "5", "null"])
def test_structural_garbage_empties_the_whole_map(text):
    m = config.parse_agent_map(text)
    assert m.entries == {} and m.error in ("agent map is not valid JSON", "agent map is not a JSON object")


def test_a_blank_console_agent_id_empties_the_whole_map():
    m = config.parse_agent_map(json.dumps({CONSOLE_AGENT: entry(), "  ": entry()}))
    assert m.entries == {} and m.error == "agent map has a blank console agent id"


def test_underscore_keys_are_ignored_and_the_rest_kept():
    m = config.parse_agent_map(json.dumps({"_comment": "x", CONSOLE_AGENT: entry()}))
    assert list(m.entries) == [CONSOLE_AGENT] and m.error is None


def test_empty_agent_map_env_is_an_empty_map_without_an_error(monkeypatch):
    for value in ("", "   "):
        monkeypatch.setenv(config.ENV_AGENT_MAP, value)
        m = config.load_agent_map()
        assert m.entries == {} and m.error is None


@pytest.mark.parametrize("text", ["{\"bash\": \"\"}", "{\"bash\": 5}", "[]", "\"s\"", "5"])
def test_a_malformed_tool_map_is_an_error_not_a_partial_map(monkeypatch, text):
    monkeypatch.setenv(config.ENV_TOOL_MAP, text)
    m = config.load_tool_map()
    assert m.entries == {} and m.error == (
        "CLAUDE_APPROVER_TOOL_MAP is not an object of non-empty strings")


def test_tool_map_env_cases(monkeypatch):
    monkeypatch.setenv(config.ENV_TOOL_MAP, "not json")
    assert config.load_tool_map().error == "CLAUDE_APPROVER_TOOL_MAP is not valid JSON"
    for empty in ("", "   "):
        monkeypatch.setenv(config.ENV_TOOL_MAP, empty)
        m = config.load_tool_map()
        assert m.entries == {} and m.error is None
    monkeypatch.setenv(config.ENV_TOOL_MAP, '{"bash": "run it", "mcp": "other"}')
    assert config.load_tool_map().entries == {"bash": "run it", "mcp": "other"}


@pytest.mark.parametrize(("raw", "want"), [
    ("", 7.0), ("   ", 7.0), ("abc", 7.0), ("-1", 7.0), ("-0.5", 7.0), ("0", 0.0), ("2.5", 2.5)])
def test_float_env_falls_back_to_the_default(monkeypatch, raw, want):
    monkeypatch.setenv(config.ENV_HALT_WAIT, raw)
    assert config._float_env(config.ENV_HALT_WAIT, 7.0) == want
    monkeypatch.delenv(config.ENV_HALT_WAIT)
    assert config._float_env(config.ENV_HALT_WAIT, 7.0) == 7.0
