"""Backlog B18: a FIELD_GOVERNOR_URL that httpx cannot build a URL from (httpx.InvalidURL or ValueError) escaped the
governor CLI as a traceback, and some shapes echoed the value. ``_base()`` now refuses such a value, and one that is
not http(s) or has no host, before any request: one fixed line on stderr, exit 2, never the value. Blank is unset.
httpx's request functions are faked; nothing leaves the process. Values are made up."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from spend_governor import cli

runner = CliRunner()
MARK = "Qz7mark"


@pytest.fixture()
def calls(monkeypatch):
    seen: list[str] = []

    def fake(url, **kw):
        seen.append(url)
        return SimpleNamespace(status_code=200, text="{}", json=lambda: {})

    for name in ("get", "put", "post"):
        monkeypatch.setattr(cli.httpx, name, fake)
    return seen


BAD = [
    f"http://{MARK}.invalid:99999",            # port out of range (httpx.InvalidURL)
    f"http://{MARK}.invalid:port",              # port not a number
    f"http://[::1{MARK}",                       # unclosed IPv6 bracket
    f"http://{MARK} host.invalid",              # a space in the host
    f"http://{MARK}\x00.invalid",              # a control character
    f"ftp://{MARK}.invalid",                     # not http(s)
    f"{MARK}.invalid:8006",                     # no scheme
    "http://",                                   # no host
    f"//{MARK}.invalid",                         # no scheme
]


@pytest.mark.parametrize("value", BAD)
def test_a_bad_governor_url_is_refused_with_fixed_text_exit_2_and_no_request(monkeypatch, calls, value):
    monkeypatch.setenv("FIELD_GOVERNOR_URL", value)
    r = runner.invoke(cli.app, ["rate-limits", "agent-1"])
    assert r.exit_code == 2, r.output
    assert isinstance(r.exception, SystemExit), repr(r.exception)
    assert cli.BAD_GOVERNOR_URL in r.output and "Traceback" not in r.output
    assert MARK not in r.output and value not in r.output
    assert calls == []


@pytest.mark.parametrize("args", [["status", "agent-1"], ["escalations"], ["rate-limits", "agent-1"]])
def test_every_command_path_goes_through_the_same_check(monkeypatch, calls, args):
    monkeypatch.setenv("FIELD_GOVERNOR_URL", f"http://{MARK}.invalid:99999")
    r = runner.invoke(cli.app, args)
    assert r.exit_code == 2 and cli.BAD_GOVERNOR_URL in r.output and MARK not in r.output and calls == []


@pytest.mark.parametrize("value,base", [
    ("http://gov.invalid", "http://gov.invalid"),
    ("http://gov.invalid/", "http://gov.invalid"),
    ("https://gov.invalid:8443/prefix", "https://gov.invalid:8443/prefix"),
    ("http://[::1]:8006", "http://[::1]:8006"),
    ("  http://gov.invalid  ", "http://gov.invalid"),
    ("", cli.DEFAULT_GOVERNOR_URL),
    ("   ", cli.DEFAULT_GOVERNOR_URL),
])
def test_a_usable_or_blank_value_is_used(monkeypatch, calls, value, base):
    monkeypatch.setenv("FIELD_GOVERNOR_URL", value)
    r = runner.invoke(cli.app, ["rate-limits", "agent-1"])
    assert r.exit_code == 0, r.output
    assert calls == [f"{base}/rate-limits/agent-1"]


def test_unset_is_the_default(monkeypatch, calls):
    monkeypatch.delenv("FIELD_GOVERNOR_URL", raising=False)
    assert runner.invoke(cli.app, ["rate-limits", "agent-1"]).exit_code == 0
    assert calls == [f"{cli.DEFAULT_GOVERNOR_URL}/rate-limits/agent-1"]
