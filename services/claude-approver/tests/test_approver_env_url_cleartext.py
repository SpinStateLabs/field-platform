"""The env (default) route sends FIELD_SHARED_SECRET on every sentinel, heartbeat and usage call. Over plain http
it may go only to a loopback address, localhost, a .test / .localhost name or a single-label host name (an in-network
compose service name). Anything else is not called, with fixed text that does not echo the URL."""
from __future__ import annotations

from pathlib import Path

import pytest

from claude_approver import config
from claude_approver.core import ENV_URL_REFUSED, Estate, estate_for

from approver_fakes import CONSOLE_AGENT, FIELD_AGENT

ALLOWED = [
    "http://sentinel:8004", "http://killswitch:8005", "http://governor:8006",
    "HTTP://SENTINEL:8004", "Http://Sentinel.", "http://field_sentinel", "http://my-sentinel/x",
    "http://127.0.0.1:8004", "http://127.255.255.254", "http://[::1]:8004", "http://localhost:8004",
    "http://sentinel.test:8004", "http://a.b.localhost", "http://LOCALHOST.",
    "https://sentinel.example.org", "HTTPS://203.0.113.5:8443", "https://sentinel",
]

REFUSED = [
    "http://sentinel.example.org", "HTTP://sentinel.example.org", "Http://203.0.113.5",
    "http://evil.example.", "http://sentinel..", "http://localhost..", "http://sentinel.internal",
    "http://host.docker.internal:8004", "http://sentinel.test.example.org",
    "http://192.0.2.5", "http://198.51.100.7:8004", "http://0.0.0.0", "http://128.0.0.1",
    "http://127.1", "http://2130706433", "http://017700000001", "http://0x7f000001", "http://0X7F000001",
    "http://0177.0.0.1", "http://[2001:db8::1]:8004", "http://[2001:db8::2]",
    "http://sentinel%2eexample%2eorg", "http://sentinel\u3002example\u3002org",
    "sentinel:8004", "ftp://sentinel", "ws://sentinel", "http://", "",
]


@pytest.mark.parametrize("url", ALLOWED, ids=repr)
def test_an_acceptable_env_url_may_carry_the_secret(url):
    assert config.env_url_secret_ok(url) is True


@pytest.mark.parametrize("url", REFUSED, ids=repr)
def test_any_other_env_url_may_not(url):
    assert config.env_url_secret_ok(url) is False


def test_the_refusal_is_fixed_text_for_the_env_route_only_and_only_when_a_secret_is_sent():
    env = Estate("http://s.example.org", "http://k.example.org", "http://g.example.org", False)
    routed = Estate("http://s.example.org", "http://k.example.org", "http://g.example.org", True)
    secret = {"x-field-auth": "made-up"}
    assert env.refusal("http://s.example.org/check", secret) == ENV_URL_REFUSED
    assert "example.org" not in ENV_URL_REFUSED
    assert env.refusal("http://s.example.org/check", {}) is None
    assert env.refusal("http://sentinel:8004/check", secret) is None
    assert routed.refusal("http://s.example.org/check", secret) is None


def remote_env(monkeypatch):
    for name, host in (("FIELD_SENTINEL_URL", "s"), ("FIELD_KILLSWITCH_URL", "k"), ("FIELD_GOVERNOR_URL", "g")):
        monkeypatch.setenv(name, f"HTTP://{host}.example.org")
    monkeypatch.setenv("FIELD_SHARED_SECRET", "made-up-perimeter-value")


def test_a_refused_env_url_is_not_called_and_the_tool_call_is_denied(monkeypatch, make_approver, field, mapped):
    remote_env(monkeypatch)
    approver = make_approver()
    entry = config.load_agent_map().entries[CONSOLE_AGENT]
    assert entry.field_agent_id == FIELD_AGENT and entry.estate_base_url is None
    estate = estate_for(entry)
    sent = []
    monkeypatch.setattr(approver.http, "post", lambda *a, **k: sent.append(a))
    verdict = approver._check(entry, estate, "run commands in sandbox", {})
    assert (verdict.result, verdict.reason_class) == ("deny", "config_error")
    assert verdict.deny_message == f"claude-approver: {ENV_URL_REFUSED}"
    approver._heartbeat(entry, estate)
    assert sent == []
    assert approver.counters["heartbeat_failures"] == 1


def test_without_a_secret_a_remote_http_env_url_is_called_as_before(monkeypatch, make_approver, mapped):
    remote_env(monkeypatch)
    monkeypatch.delenv("FIELD_SHARED_SECRET")
    approver = make_approver()
    entry = config.load_agent_map().entries[CONSOLE_AGENT]
    sent = []

    def post(url, **kw):
        sent.append((url, kw["headers"]))
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(approver.http, "post", post)
    approver._check(entry, estate_for(entry), "run commands in sandbox", {})
    assert sent == [("HTTP://s.example.org/check", {})]


def test_the_readme_states_the_rule_and_what_stays_open():
    text = " ".join((Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8").split())
    assert "or a single-label host name (no dot, such as a compose service name)" in text
    assert "resolved through the container's DNS search path, which the estate's operator controls" in text
