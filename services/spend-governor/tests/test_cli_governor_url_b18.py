"""Backlog B18: a FIELD_GOVERNOR_URL that httpx cannot build a URL from (httpx.InvalidURL or ValueError) escaped the
governor CLI as a traceback, and some shapes echoed the value. ``_base()`` now refuses such a value, and one that is
not http(s) or has no host, before any request: one fixed line on stderr, exit 2, never the value. Blank is unset.
httpx.Client.request is faked; nothing leaves the process. Values are made up."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
import typer
from typer.testing import CliRunner

from spend_governor import cli

runner = CliRunner()
MARK = "Qz7mark"


@pytest.fixture()
def calls(monkeypatch):
    seen: list[str] = []

    def fake(self, method, url, **kw):
        seen.append(url)
        return SimpleNamespace(status_code=200, text="{}", json=lambda: {})

    # the CLI sends through one httpx.Client (S10-12, #1263), so the recorder sits on Client.request
    monkeypatch.setattr(cli.httpx.Client, "request", fake)
    return seen


BAD = [
    f"http://{MARK}.invalid:99999",            # port out of range (httpx.InvalidURL)
    f"http://{MARK}.invalid:port",              # port not a number
    f"http://[::1{MARK}",                       # unclosed IPv6 bracket
    f"http://{MARK} host.invalid",              # a space in the host
    f"http://{MARK}\x01.invalid",              # a control character (os.environ refuses NUL itself)
    f"http://{MARK}\x7f.invalid",              # DEL
    f"http://user:{MARK}@gov.invalid",           # userinfo: a password in the URL
    f"http://{MARK}@gov.invalid",                # userinfo: a user name alone
    f"ftp://{MARK}.invalid",                     # not http(s)
    f"{MARK}.invalid:8006",                     # no scheme
    "http://",                                   # no host
    f"//{MARK}.invalid",                         # no scheme
    f"http://{MARK}.invalid..:8006",             # two trailing dots
    "http://.:8006",                             # only a dot
    f"http://user:{MARK}@xn--bcher-kva.example",  # userinfo on a punycode host
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
    ("http://xn--bcher-kva.example:8006", "http://xn--bcher-kva.example:8006"),   # an IDN host in punycode
    ("http://b\u00fccher.example:8006", "http://b\u00fccher.example:8006"),       # the same host, decoded
    ("http://gov.invalid.:8006", "http://gov.invalid.:8006"),                     # a fully qualified name
    ("http://xn--bcher-kva.example.:8006", "http://xn--bcher-kva.example.:8006"),
    ("  http://gov.invalid  ", "http://gov.invalid"),
    ("", cli.DEFAULT_GOVERNOR_URL),
    ("   ", cli.DEFAULT_GOVERNOR_URL),
])
def test_a_usable_or_blank_value_is_used(monkeypatch, calls, value, base):
    monkeypatch.setenv("FIELD_GOVERNOR_URL", value)
    r = runner.invoke(cli.app, ["rate-limits", "agent-1"])
    assert r.exit_code == 0, r.output
    assert calls == [f"{base}/rate-limits/agent-1"]


def test_a_nul_in_the_value_is_refused(monkeypatch, capsys):
    """os.environ cannot hold a NUL, so the environment is replaced for this one call."""
    monkeypatch.setattr(cli, "os", SimpleNamespace(environ={"FIELD_GOVERNOR_URL": f"http://{MARK}\x00.invalid"}))
    with pytest.raises(typer.Exit) as exc:
        cli._base()
    assert exc.value.exit_code == 2
    err = capsys.readouterr().err
    assert cli.BAD_GOVERNOR_URL in err and MARK not in err


def test_unset_is_the_default(monkeypatch, calls):
    monkeypatch.delenv("FIELD_GOVERNOR_URL", raising=False)
    assert runner.invoke(cli.app, ["rate-limits", "agent-1"]).exit_code == 0
    assert calls == [f"{cli.DEFAULT_GOVERNOR_URL}/rate-limits/agent-1"]


class _BareHttpx:
    """A stand-in for ``cli.httpx`` with only ``Client`` and ``HTTPError``, the shape the existing CLI tests install
    (test_cli_set_cap_manifest_inputs, test_throttle): it has no ``URL`` and no ``InvalidURL``."""

    def __init__(self, seen):
        self.seen = seen
        self.HTTPError = httpx.HTTPError

    def Client(self, **kw):  # noqa: N802 (httpx's name)
        seen = self.seen

        class _C:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def request(self, method, url, **rkw):
                seen.append(url)
                return SimpleNamespace(status_code=200, text="{}", json=lambda: {})

        return _C()


def test_the_check_survives_a_fake_httpx_without_url_or_invalidurl(monkeypatch):
    """rb61: the check named httpx.URL and httpx.InvalidURL at call time, so a test fake of cli.httpx made every CLI
    call fail. Both are bound at import now."""
    seen: list[str] = []
    monkeypatch.setattr(cli, "httpx", _BareHttpx(seen))
    monkeypatch.setenv("FIELD_GOVERNOR_URL", "http://gov.invalid")
    r = runner.invoke(cli.app, ["rate-limits", "agent-1"])
    assert r.exit_code == 0, r.output
    assert seen == ["http://gov.invalid/rate-limits/agent-1"]
    monkeypatch.setenv("FIELD_GOVERNOR_URL", f"http://{MARK}.invalid:port")
    r = runner.invoke(cli.app, ["rate-limits", "agent-1"])
    assert r.exit_code == 2 and cli.BAD_GOVERNOR_URL in r.output and MARK not in r.output
    assert seen == ["http://gov.invalid/rate-limits/agent-1"]
