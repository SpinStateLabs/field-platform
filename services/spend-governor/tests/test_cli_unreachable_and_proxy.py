"""S10-12: every governor CLI verb goes through one client that ignores the proxy environment, and an unreachable governor is one line.

Before: each verb called ``httpx.get/put/post`` directly. Those read ``HTTP(S)_PROXY`` / ``ALL_PROXY`` (httpx ``trust_env=True``),
so an ambient proxy received the ``x-field-auth`` perimeter secret and, on a guarded write, the operator pair; and a
refused connection was a Python traceback. The kill-switch and lifecycle CLIs already use one ``trust_env=False`` client
(C-575, C-1171). Every value here is made up; no request leaves the process (a dead local proxy address is only a name
that must never be dialled)."""
from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from field_core import authn
from spend_governor import cli

RUNNER = CliRunner()
DEAD_PROXY = "http://127.0.0.1:9"      # nothing listens on the discard port; a request to it would be a ConnectError
SECRET = "made-up-perimeter-secret"

VERBS = [
    ["set-cap", "agent-a", "--limit-cents", "100"],
    ["spend", "agent-a", "--cents", "5"],
    ["rate-limits", "agent-a"],
    ["status", "agent-a"],
    ["usage", "agent-a"],
    ["usage", "agent-a", "--model", "m", "--in", "1", "--out", "1"],
    ["set-policy", "agent-a", "--allowed-model", "m"],
    ["escalations"],
    ["resolve", "esc-1", "--by", "someone"],
]
IDS = [" ".join(v[:2]) + (" --model" if "--model" in v else "") for v in VERBS]


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    monkeypatch.setenv("FIELD_GOVERNOR_URL", "http://governor.invalid")
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(k, raising=False)


def _transport(monkeypatch, handler):
    """Make every httpx.Client the CLI builds use this handler, and record the Client kwargs it was built with."""
    built = []
    real = httpx.Client.__init__

    def init(self, *a, **kw):
        built.append(dict(kw))
        kw["transport"] = httpx.MockTransport(handler)
        real(self, *a, **kw)

    monkeypatch.setattr(httpx.Client, "__init__", init)
    return built


@pytest.mark.parametrize("argv", VERBS, ids=IDS)
def test_no_verb_dials_the_proxy_named_in_the_environment(monkeypatch, argv):
    monkeypatch.setenv("HTTPS_PROXY", DEAD_PROXY)
    monkeypatch.setenv("HTTP_PROXY", DEAD_PROXY)
    monkeypatch.setenv("ALL_PROXY", DEAD_PROXY)
    built = _transport(monkeypatch, lambda req: httpx.Response(
        201 if req.method == "POST" and req.url.path in ("/spend", "/usage") else 200, json={"state": "OK", "rogue": False, "rate_limits": []}))
    res = RUNNER.invoke(cli.app, argv)
    assert res.exit_code in (0, 1, 3), res.output
    assert built, "the verb sent nothing through a client"
    for kw in built:
        assert kw.get("trust_env") is False, kw
        assert kw.get("follow_redirects") is False, kw


@pytest.mark.parametrize("argv", VERBS, ids=IDS)
def test_a_proxy_in_the_environment_is_never_used_even_without_the_mock(monkeypatch, argv):
    """No mock transport: the proxy is dead and the governor host does not resolve. If the proxy were read, the error is the
    proxy's; either way the CLI must exit 1 with one line and no traceback, and the line must not name the proxy."""
    monkeypatch.setenv("HTTPS_PROXY", DEAD_PROXY)
    monkeypatch.setenv("HTTP_PROXY", DEAD_PROXY)
    res = RUNNER.invoke(cli.app, argv)
    assert res.exit_code == 1, res.output
    assert res.exception is None or isinstance(res.exception, SystemExit)
    assert "Traceback" not in res.output
    assert "127.0.0.1:9" not in res.output and "governor.invalid" not in res.output and SECRET not in res.output


@pytest.mark.parametrize("argv", VERBS, ids=IDS)
def test_a_refused_connection_is_one_line_and_exit_1_no_traceback(monkeypatch, argv):
    def refuse(req):
        raise httpx.ConnectError("boom http://governor.invalid " + SECRET)
    _transport(monkeypatch, refuse)
    res = RUNNER.invoke(cli.app, argv)
    assert res.exit_code == 1
    assert isinstance(res.exception, SystemExit) or res.exception is None
    lines = [l for l in res.output.splitlines() if l.strip()]
    assert lines and lines[-1].startswith("error: governor unreachable (ConnectError)"), res.output
    assert "Traceback" not in res.output
    assert SECRET not in res.output and "governor.invalid" not in res.output and "boom" not in res.output
    reads = argv[0] in ("rate-limits", "status", "escalations") or (argv[0] == "usage" and "--model" not in argv)
    assert ("nothing was changed" in lines[-1]) is (not reads)


def test_a_read_timeout_on_a_write_does_not_claim_nothing_was_changed(monkeypatch):
    def slow(req):
        raise httpx.ReadTimeout("late")
    _transport(monkeypatch, slow)
    res = RUNNER.invoke(cli.app, ["spend", "agent-a", "--cents", "5"])
    assert res.exit_code == 1
    last = res.output.strip().splitlines()[-1]
    assert last.startswith("error: governor unreachable (ReadTimeout)")
    assert "nothing was changed" not in last and "outcome is unknown" in last


def test_exit_codes_pinned_by_s9_13_are_unchanged(monkeypatch):
    _transport(monkeypatch, lambda req: httpx.Response(
        201, json={"state": "BLOCK", "rogue": True}))
    assert RUNNER.invoke(cli.app, ["spend", "agent-a", "--cents", "5"]).exit_code == 1
    assert RUNNER.invoke(cli.app, ["usage", "agent-a", "--model", "m"]).exit_code == 3


def test_a_redirect_is_not_followed_and_does_not_carry_the_secret(monkeypatch):
    seen = []

    def handler(req):
        seen.append(req.url.host)
        if req.url.host == "governor.invalid":
            return httpx.Response(307, headers={"location": "http://elsewhere.invalid/status/agent-a"})
        return httpx.Response(200, json={})
    _transport(monkeypatch, handler)
    res = RUNNER.invoke(cli.app, ["status", "agent-a"])
    assert seen == ["governor.invalid"], seen
    assert res.exit_code == 1
