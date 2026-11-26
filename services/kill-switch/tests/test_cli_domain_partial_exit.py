"""S11-11: `killswitch domain` is not a success while named agents are still active.

POST /kill/domain answers 200 with per-agent outcomes (including `error`) unless EVERY attempt errored (then 502). The
CLI treated any 200 as success, so the break-glass command exited 0 with agents still active. Now: the report is printed
on stdout as before; when any result's outcome is `error` the CLI prints `N agent(s) NOT halted: ids` on stderr and
exits 1. A 200 body that is not a JSON object is a named exit 1 (as `_killed` does for heartbeat).
"""
from __future__ import annotations

import json

import httpx
import pytest
from typer.testing import CliRunner

from kill_switch import cli

runner = CliRunner()
ARGV = ["domain", "finance", "--operator", "o", "--reason", "r"]


@pytest.fixture()
def reply(monkeypatch):
    box = {"resp": httpx.Response(200, json={})}
    monkeypatch.setattr(
        cli, "_client",
        lambda pair=None, timeout=10.0: httpx.Client(transport=httpx.MockTransport(lambda r: box["resp"]), timeout=timeout),
    )
    return lambda **kw: box.__setitem__("resp", httpx.Response(200, **kw))


def report(*outcomes: tuple[str, str]) -> dict:
    return {"domain": "finance", "killed": [a for a, o in outcomes if o == "killed"],
            "results": [{"agent_id": a, "outcome": o, **({"error": "500: boom"} if o == "error" else {})}
                        for a, o in outcomes]}


def test_one_of_two_agents_erroring_is_exit_1_with_the_ids_on_stderr_and_the_report_on_stdout(reply):
    body = report(("a1", "killed"), ("a2", "error"))
    reply(json=body)
    res = runner.invoke(cli.app, ARGV)
    assert res.exit_code == 1, res.output
    assert json.loads(res.stdout) == body                              # the report is printed as today
    assert "1 agent(s) NOT halted: a2" in res.stderr
    assert "a1" not in res.stderr


def test_every_erroring_agent_is_named_and_counted(reply):
    reply(json=report(("a1", "error"), ("a2", "killed"), ("a3", "error")))
    res = runner.invoke(cli.app, ARGV)
    assert res.exit_code == 1 and "2 agent(s) NOT halted: a1, a3" in res.stderr


@pytest.mark.parametrize("outcomes", [
    [("a1", "killed"), ("a2", "killed")],
    [("a1", "already_killed"), ("a2", "killed")],
    [("a1", "already_killed"), ("a2", "already_killed")],
    [("a1", "killed"), ("a2", "skipped_retired")],
    [],
])
def test_all_killed_already_killed_and_retired_stay_exit_0(reply, outcomes):
    reply(json=report(*outcomes))
    res = runner.invoke(cli.app, ARGV)
    assert res.exit_code == 0, res.output
    assert "NOT halted" not in res.output


def test_an_id_with_control_characters_cannot_write_to_the_terminal(reply):
    reply(json=report(("a1\x1b[31m", "error")))
    res = runner.invoke(cli.app, ARGV)
    assert res.exit_code == 1
    assert "\x1b" not in res.stderr and "a1\\x1b[31m" in res.stderr


@pytest.mark.parametrize("content", [b"not json", b"[1,2]", b'"x"', b"null"])
def test_a_200_that_is_not_a_json_object_is_a_named_exit_1(reply, content):
    reply(content=content)
    res = runner.invoke(cli.app, ARGV)
    assert res.exit_code == 1
    assert "not a JSON object" in res.output
    assert res.exception is None or isinstance(res.exception, SystemExit)


@pytest.mark.parametrize("body", [{}, {"killed": ["a1"]}, {"results": "x"}, {"results": None}])
def test_a_200_object_without_a_results_list_names_no_failed_agent_and_is_exit_0(reply, body):
    """No list, no outcome to read: nothing is reported failed (the real route always carries `results`)."""
    reply(json=body)
    res = runner.invoke(cli.app, ARGV)
    assert res.exit_code == 0 and "NOT halted" not in res.output


def test_a_result_row_that_is_not_an_object_is_ignored_not_a_crash(reply):
    reply(json={"results": ["x", 3, None, {"agent_id": "a1", "outcome": "killed"}]})
    res = runner.invoke(cli.app, ARGV)
    assert res.exit_code == 0


def test_a_502_all_errored_report_is_still_the_existing_failure(reply, monkeypatch):
    monkeypatch.setattr(
        cli, "_client",
        lambda pair=None, timeout=10.0: httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(502, json={"detail": report(("a1", "error"))})),
            timeout=timeout),
    )
    res = runner.invoke(cli.app, ARGV)
    assert res.exit_code == 1 and "error 502" in res.stderr
