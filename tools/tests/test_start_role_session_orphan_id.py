"""S8-32 (the part PR 595 leaves): a failed kickoff must not lose the id of a session that already exists.

`start_role_session.py` creates a billable session and only then posts the kickoff message; `print(sid)` ran after both calls, so
a failure of the second (HTTP error, refused connection, bad reply) left a live session nobody could find. Now the id is
printed to stderr as soon as the session exists, and a failed kickoff exits with one line saying so by id. The session name
is 1..64 characters of [A-Za-z0-9_-] (the help says "no personal name"; no attempt is made to detect names). Stacked on #595
(and #546); local servers only, nothing leaves the machine."""
from __future__ import annotations

import json
import sys

import pytest
from test_start_role_session import Server, _load, servers  # noqa: F401
from test_start_role_session_hardening import mod, run  # noqa: F401

BODY_MARKER = "UPSTREAM-BODY-MARKER-9921"


def two_step(second):
    state = {"n": 0}

    def reply(h):
        state["n"] += 1
        return (200, {}, b'{"id": "sess_77"}') if state["n"] == 1 else second

    return reply


@pytest.mark.parametrize("second", [
    (500, {}, BODY_MARKER.encode()),
    (401, {}, b'{"error": "x"}'),
    (200, {}, b"not json"),
], ids=["http-500", "http-401", "non-json-200"])
def test_a_failed_kickoff_still_reports_the_session_id_on_stderr_and_in_the_exit_line(mod, servers, monkeypatch, capsys, second):  # noqa: F811
    srv = servers(two_step(second))
    monkeypatch.setattr(mod, "API_BASE", srv.url)
    with pytest.raises(SystemExit) as e:
        run(mod, monkeypatch, "architect", "name-1", "A")
    msg = str(e.value)
    assert "sess_77" in msg and "was created but not started" in msg
    assert BODY_MARKER not in msg
    err = capsys.readouterr().err
    assert "sess_77" in err                                         # printed before the kickoff was attempted
    assert [r["path"] for r in srv.requests] == ["/v1/sessions", "/v1/sessions/sess_77/events"]


def test_the_id_is_printed_before_the_kickoff_is_posted(mod, servers, monkeypatch, capsys):  # noqa: F811
    seen = {}

    def reply(h):
        seen["stderr_at_kickoff"] = capsys.readouterr().err if len(srv.requests) == 2 else None
        return (200, {}, b'{"id": "sess_5"}')

    srv = servers(reply)
    monkeypatch.setattr(mod, "API_BASE", srv.url)
    run(mod, monkeypatch, "architect", "name-1", "A")
    assert seen["stderr_at_kickoff"] and "sess_5" in seen["stderr_at_kickoff"]


def test_a_good_run_still_prints_only_the_id_on_stdout(mod, servers, monkeypatch, capsys):  # noqa: F811
    srv = servers(lambda h: (200, {}, b'{"id": "sess_9"}'))
    monkeypatch.setattr(mod, "API_BASE", srv.url)
    run(mod, monkeypatch, "architect", "name-1", "A")
    out = capsys.readouterr()
    assert out.out.strip() == "sess_9"


def test_a_refused_connection_on_the_kickoff_names_the_session(mod, monkeypatch, servers, capsys):  # noqa: F811
    import urllib.error

    class Opener:
        n = 0

        def open(self, req, timeout=None):
            Opener.n += 1
            if Opener.n == 1:
                import io

                class R(io.BytesIO):
                    status = 200

                    def __enter__(self):
                        return self

                    def __exit__(self, *a):
                        return False
                return R(b'{"id": "sess_3"}')
            raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(mod, "_OPENER", Opener())
    with pytest.raises(SystemExit) as e:
        run(mod, monkeypatch, "architect", "name-1", "A")
    assert "sess_3" in str(e.value) and "was created but not started" in str(e.value) and "URLError" in str(e.value)


@pytest.mark.parametrize("bad", ["", "a b", "a/b", "name;x", "é", "x" * 65, "a\nb", "a.b", "Jane Doe"])
def test_a_bad_session_name_exits_2_before_any_request(mod, servers, monkeypatch, capsys, bad):  # noqa: F811
    srv = servers(lambda h: (200, {}, b'{"id": "s"}'))
    monkeypatch.setattr(mod, "API_BASE", srv.url)
    with pytest.raises(SystemExit) as e:
        run(mod, monkeypatch, "architect", bad, "A")
    assert e.value.code == 2 and srv.requests == []
    assert "session_name" in capsys.readouterr().err


@pytest.mark.parametrize("good", ["a", "name-1", "Lane_B-2", "x" * 64, "0123"])
def test_a_good_session_name_is_accepted(mod, servers, monkeypatch, good):  # noqa: F811
    srv = servers(lambda h: (200, {}, b'{"id": "s"}'))
    monkeypatch.setattr(mod, "API_BASE", srv.url)
    run(mod, monkeypatch, "architect", good, "A")
    assert json.loads(srv.requests[1]["body"])["events"][0]["content"][0]["text"].startswith(f"Session name: {good}\n")
