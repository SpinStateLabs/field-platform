"""Usage bridge: cumulative ``session.usage`` -> positive deltas on the governor,
with a restart-safe cursor that moves only on a 201."""

from __future__ import annotations

import json

import httpx

from approver_fakes import CONSOLE_AGENT, FIELD_AGENT, ns, usage

SID = "sesn_u1"


def test_two_snapshots_post_two_deltas(console, field, make_approver, mapped):
    s = console.add_session(SID, CONSOLE_AGENT, status="running", use=usage(1000, 100, 50))
    a = make_approver()
    a.tick()
    s.usage = usage(1600, 180, 50)
    a.tick()
    posts = field.usage_posts()
    assert posts == [
        {"agent_id": FIELD_AGENT, "model": "claude-opus-5-5", "input_tokens": 1000,
         "output_tokens": 100, "cache_read_tokens": 50, "note": f"console session {SID}"},
        {"agent_id": FIELD_AGENT, "model": "claude-opus-5-5", "input_tokens": 600,
         "output_tokens": 80, "cache_read_tokens": 0, "note": f"console session {SID}"},
    ]
    assert a.stats()["usage_posts"] == 2
    a.tick()  # unchanged usage: nothing posted
    assert len(field.usage_posts()) == 2


def test_restart_with_the_cursor_file_does_not_re_post(console, field, make_approver, mapped, tmp_path):
    console.add_session(SID, CONSOLE_AGENT, status="terminated", use=usage(700, 70))
    make_approver().tick()
    cursor = tmp_path / "data" / "claude-approver" / "usage-cursor.json"
    assert json.loads(cursor.read_text())[SID] == {
        "input_tokens": 700, "output_tokens": 70, "cache_read_tokens": 0}
    restarted = make_approver()  # a new process: same cursor path, empty memory
    restarted.tick()
    assert len(field.usage_posts()) == 1


def test_default_cursor_path_is_under_field_data_dir(console, field, mapped, tmp_path):
    from claude_approver.core import Approver

    console.add_session(SID, CONSOLE_AGENT, use=usage(5, 1))
    Approver(client=console, http=field.client()).tick()
    assert (tmp_path / "data" / "claude-approver" / "usage-cursor.json").is_file()


def test_governor_404_leaves_the_cursor_unchanged(console, field, make_approver, mapped, tmp_path):
    console.add_session(SID, CONSOLE_AGENT, use=usage(300, 30))
    field.usage = lambda r: httpx.Response(404, json={"detail": "no spend cap configured"})
    a = make_approver()
    a.tick()
    cursor = tmp_path / "data" / "claude-approver" / "usage-cursor.json"
    assert not cursor.exists()
    assert a.stats()["usage_failures"] == 1 and a.stats()["usage_posts"] == 0
    field.usage = lambda r: httpx.Response(201, json={})
    a.tick()  # the same delta is retried
    assert [p["input_tokens"] for p in field.usage_posts()] == [300, 300]
    assert json.loads(cursor.read_text())[SID]["input_tokens"] == 300


def test_governor_unreachable_is_counted_never_raised(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT, use=usage(1, 1))

    def boom(request):
        raise httpx.ConnectError("down")

    field.usage = boom
    a = make_approver()
    a.tick()
    assert a.stats()["usage_failures"] == 1 and a.stats()["tick_errors"] == 0


def test_model_falls_back_to_agents_retrieve_cached_per_tick(console, field, make_approver, mapped):
    console.add_agent(CONSOLE_AGENT, model="claude-sonnet-5-5")
    console.add_session("sesn_a", CONSOLE_AGENT, model=None, use=usage(10, 1))
    console.add_session("sesn_b", CONSOLE_AGENT, model=None, use=usage(20, 2))
    make_approver().tick()
    assert [p["model"] for p in field.usage_posts()] == ["claude-sonnet-5-5"] * 2
    assert console.count("agents.retrieve") == 1


def test_model_unknown_when_nothing_names_it(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT, model=None, use=usage(10, 1))  # no agent registered
    make_approver().tick()
    assert field.usage_posts()[0]["model"] == "unknown"


def test_usage_from_the_latest_usage_event_when_the_session_has_none(console, field, make_approver, mapped):
    s = console.add_session(SID, CONSOLE_AGENT)
    s.usage = None
    console.add_event(SID, "session.usage", usage=usage(40, 4))
    console.add_event(SID, "session.usage", usage=usage(90, 9))
    make_approver().tick()
    assert [(p["input_tokens"], p["output_tokens"]) for p in field.usage_posts()] == [(90, 9)]
    (call,) = [kw for n, kw in console.calls if n == "events.list" and kw.get("types")]
    assert call["types"] == ["session.usage"] and call["order"] == "desc" and call["limit"] == 1


def test_corrupt_cursor_disables_posting_instead_of_double_posting(
        console, field, make_approver, mapped, tmp_path):
    cursor = tmp_path / "data" / "claude-approver" / "usage-cursor.json"
    cursor.parent.mkdir(parents=True)
    cursor.write_text("{not json", encoding="utf-8")
    console.add_session(SID, CONSOLE_AGENT, use=usage(10, 1))
    a = make_approver()
    a.tick()
    assert field.usage_posts() == []
    assert a.stats()["usage_cursor_error"] == "usage cursor is corrupt"


def test_counters_going_backwards_post_nothing_and_never_negative(console, field, make_approver, mapped):
    s = console.add_session(SID, CONSOLE_AGENT, use=usage(100, 10, 10))
    a = make_approver()
    a.tick()
    s.usage = usage(90, 20, 10)  # input went down (should not happen); output went up
    a.tick()
    posts = field.usage_posts()
    assert posts[1]["input_tokens"] == 0 and posts[1]["output_tokens"] == 10
    s.usage = usage(110, 20, 10)  # input counted from the high-water mark, not the dip
    a.tick()
    assert field.usage_posts()[2]["input_tokens"] == 10


def test_unusable_entry_posts_no_usage(console, field, make_approver, monkeypatch):
    from approver_fakes import set_map

    set_map(monkeypatch, {CONSOLE_AGENT: {"field_agent_id": ""}})
    console.add_session(SID, CONSOLE_AGENT, use=usage(10, 1))
    make_approver().tick()
    assert field.requests == []


def test_cache_creation_tokens_are_not_sent(console, field, make_approver, mapped):
    """The governor's UsageRequest is extra=forbid with no cache-creation field."""
    u = usage(10, 1, 2)
    u.cache_creation = ns(ephemeral_5m_input_tokens=500, ephemeral_1h_input_tokens=0)
    console.add_session(SID, CONSOLE_AGENT, use=u)
    make_approver().tick()
    (post,) = field.usage_posts()
    assert set(post) == {"agent_id", "model", "input_tokens", "output_tokens",
                         "cache_read_tokens", "note"}
