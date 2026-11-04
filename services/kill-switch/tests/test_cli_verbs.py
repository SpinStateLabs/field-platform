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
