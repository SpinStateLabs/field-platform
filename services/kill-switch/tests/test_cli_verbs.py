"""S3-4: kill-switch CLI verb behaviour over httpx.MockTransport: exit codes,
an unreachable service is one line (no traceback, no URL), ids are one encoded
path segment, a 200 with a non-object body is a named exit 1."""

from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from kill_switch import cli

runner = CliRunner()


@pytest.fixture()
def seen(monkeypatch):
    """Install a transport; returns (requests, set_handler)."""
    requests: list[httpx.Request] = []
    box = {"h": lambda r: httpx.Response(200, json={"killed": False})}

    def handler(request):
        requests.append(request)
        return box["h"](request)

    monkeypatch.setattr(
        cli, "_client",
        lambda pair=None, timeout=10.0: httpx.Client(transport=httpx.MockTransport(handler), timeout=timeout),
    )
    return requests, lambda f: box.__setitem__("h", f)


@pytest.mark.parametrize("verb", ["heartbeat", "checkin"])
@pytest.mark.parametrize("killed,code", [(True, 1), (False, 0)])
def test_heartbeat_and_checkin_exit_codes(seen, verb, killed, code):
    _, set_h = seen
    set_h(lambda r: httpx.Response(200, json={"killed": killed}))
    assert runner.invoke(cli.app, [verb, "a1"]).exit_code == code


@pytest.mark.parametrize("verb", ["heartbeat", "checkin"])
def test_a_non_200_is_exit_1_with_status_and_detail(seen, verb):
    _, set_h = seen
    set_h(lambda r: httpx.Response(404, json={"detail": "unknown agent"}))
    res = runner.invoke(cli.app, [verb, "a1"])
    assert res.exit_code == 1
    assert "error 404: unknown agent" in res.output


@pytest.mark.parametrize("body", [b"not json", b"[1,2]", b'"x"'])
def test_a_200_with_a_non_object_body_is_a_named_exit_1(seen, body):
    _, set_h = seen
    set_h(lambda r: httpx.Response(200, content=body))
    res = runner.invoke(cli.app, ["heartbeat", "a1"])
    assert res.exit_code == 1
    assert "not a JSON object" in res.output
    assert res.exception is None or isinstance(res.exception, SystemExit)


VERBS = [
    ["agent", "a1", "--operator", "o", "--reason", "r"],
    ["domain", "d1", "--operator", "o", "--reason", "r"],
    ["drill", "a1", "--operator", "o"],
    ["revive", "a1", "--operator", "o"],
    ["heartbeat", "a1"],
    ["checkin", "a1"],
    ["liveness"],
]


@pytest.mark.parametrize("argv", VERBS)
def test_an_unreachable_service_is_one_line_never_a_traceback(seen, argv):
    _, set_h = seen

    def boom(request):
        raise httpx.ConnectError("secret-host-detail refused", request=request)

    set_h(boom)
    res = runner.invoke(cli.app, argv)
    assert res.exit_code == 1
    assert "kill-switch unreachable (ConnectError)" in res.output
    assert "secret-host-detail" not in res.output and "http" not in res.output
    assert "Traceback" not in res.output
    assert isinstance(res.exception, SystemExit)
    if argv[0] not in ("heartbeat", "liveness"):
        assert "nothing was changed" in res.output


def test_an_id_with_url_metacharacters_is_one_encoded_path_segment(seen):
    reqs, _ = seen
    runner.invoke(cli.app, ["heartbeat", "a?x=1/../b#f"])
    runner.invoke(cli.app, ["agent", "a?x=1", "--operator", "o", "--reason", "r"])
    runner.invoke(cli.app, ["domain", "d/../x", "--operator", "o", "--reason", "r"])
    paths = [r.url.raw_path.decode() for r in reqs]
    assert paths[0] == "/heartbeat/a%3Fx%3D1%2F..%2Fb%23f"
    assert paths[1] == "/kill/a%3Fx%3D1"
    assert paths[2] == "/kill/domain/d%2F..%2Fx"
    assert all("?" not in p for p in paths)


def test_liveness_passes_stale_after_as_a_param(seen):
    reqs, set_h = seen
    set_h(lambda r: httpx.Response(200, json=[]))
    res = runner.invoke(cli.app, ["liveness", "--stale-after", "42"])
    assert res.exit_code == 0
    assert reqs[0].url.params["stale_after"] == "42.0"


# ---- reviewer-2 BLOCK on 3514b5f (B1, B2) and the survivors Q5, Q6, Q8, U4, U5, T1, T2 -----------------------------

WRITES = [VERBS[0], VERBS[1], VERBS[2], VERBS[3], VERBS[5]]
READS = [VERBS[4], VERBS[6]]


@pytest.mark.parametrize("exc_name", ["ReadTimeout", "RemoteProtocolError", "ReadError", "WriteTimeout"])
@pytest.mark.parametrize("argv", WRITES)
def test_a_write_whose_reply_is_lost_does_not_claim_nothing_was_changed(seen, argv, exc_name):
    _, set_h = seen

    def lost(request):
        raise getattr(httpx, exc_name)("secret-host-detail", request=request)

    set_h(lost)
    res = runner.invoke(cli.app, argv)
    assert res.exit_code == 1
    assert f"kill-switch unreachable ({exc_name})" in res.output
    assert "nothing was changed" not in res.output
    assert "outcome is unknown" in res.output and "heartbeat" in res.output
    assert "secret-host-detail" not in res.output and "Traceback" not in res.output
    assert isinstance(res.exception, SystemExit)


@pytest.mark.parametrize("exc_name", ["ConnectError", "ConnectTimeout"])
@pytest.mark.parametrize("argv", WRITES)
def test_a_write_that_was_never_sent_says_nothing_was_changed(seen, argv, exc_name):
    _, set_h = seen

    def never_sent(request):
        raise getattr(httpx, exc_name)("secret-host-detail", request=request)

    set_h(never_sent)
    res = runner.invoke(cli.app, argv)
    assert res.exit_code == 1 and "nothing was changed" in res.output and "outcome is unknown" not in res.output


@pytest.mark.parametrize("exc_name", ["ReadTimeout", "ConnectError"])
@pytest.mark.parametrize("argv", READS)
def test_a_read_carries_no_note_either_way(seen, argv, exc_name):
    _, set_h = seen

    def fail(request):
        raise getattr(httpx, exc_name)("x", request=request)

    set_h(fail)
    res = runner.invoke(cli.app, argv)
    assert res.exit_code == 1 and f"kill-switch unreachable ({exc_name})" in res.output
    assert "nothing was changed" not in res.output and "outcome is unknown" not in res.output


@pytest.mark.parametrize("bad", [".", ".."])
@pytest.mark.parametrize("argv", [
    ["agent", "{}", "--operator", "o", "--reason", "r"],
    ["domain", "{}", "--operator", "o", "--reason", "r"],
    ["drill", "{}", "--operator", "o"],
    ["revive", "{}", "--operator", "o"],
    ["heartbeat", "{}"],
    ["checkin", "{}"],
])
def test_dot_ids_are_refused_before_any_request(seen, argv, bad):
    reqs, _ = seen
    res = runner.invoke(cli.app, [a.replace("{}", bad) for a in argv])
    assert res.exit_code == 2, res.output
    assert "may not be" in res.output and "nothing was sent" in res.output
    assert reqs == []


@pytest.mark.parametrize("argv,prefix", [
    (["drill", "a?x=1/b", "--operator", "o"], "/drill/"),
    (["revive", "a?x=1/b", "--operator", "o"], "/revive/"),
    (["checkin", "a?x=1/b"], "/heartbeat/"),
])
def test_every_id_site_encodes_the_id(seen, argv, prefix):
    reqs, _ = seen
    runner.invoke(cli.app, argv)
    assert reqs[0].url.raw_path.decode() == prefix + "a%3Fx%3D1%2Fb"


@pytest.mark.parametrize("argv,seconds", [
    (["domain", "d1", "--operator", "o", "--reason", "r"], 30.0),
    (["drill", "a1", "--operator", "o"], 30.0),
    (["agent", "a1", "--operator", "o", "--reason", "r"], 10.0),
    (["revive", "a1", "--operator", "o"], 10.0),
    (["heartbeat", "a1"], 10.0),
])
def test_the_per_verb_timeouts(seen, argv, seconds):
    reqs, _ = seen
    runner.invoke(cli.app, argv)
    assert reqs[0].extensions["timeout"]["read"] == seconds
