"""S3-16: an events URL is never printed with its userinfo or query. fetch_events used to raise
WitnessError(f"{url} answered {status}") and verify-witness printed that text, so https://user:pass@host/x?token=...
reached stderr and any CI log. A --events-url that carries userinfo at all is refused (exit 2, fixed text): the
secret belongs in --secret-file."""

from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from sealed_ledger import witness as w
from sealed_ledger.cli import app as cli_app

runner = CliRunner()
REAL_CLIENT = httpx.Client


@pytest.fixture()
def answer(monkeypatch):
    """Route fetch_events' httpx.Client through a MockTransport; returns a setter for the reply."""
    box = {"r": lambda req: httpx.Response(503)}

    def factory(**kw):
        kw.pop("transport", None)
        return REAL_CLIENT(transport=httpx.MockTransport(lambda req: box["r"](req)), **kw)

    monkeypatch.setattr(w.httpx, "Client", factory)
    return lambda f: box.__setitem__("r", f)


def verify(url, tmp_path, *extra):
    return runner.invoke(cli_app, ["verify-witness", "--estate", "fly", "--events-url", url,
                                   "--path", str(tmp_path / "events.jsonl"), *extra])


@pytest.mark.parametrize("url,shown", [
    ("https://fly.test/x?token=abc", "https://fly.test/x"),
    ("https://fly.test:8443/ledger/events?token=abc&k=v", "https://fly.test:8443/ledger/events"),
])
def test_a_503_names_the_url_without_its_query(url, shown, tmp_path, answer):
    answer(lambda r: httpx.Response(503))
    res = verify(url, tmp_path)
    assert res.exit_code == 2
    assert "token=abc" not in res.output and "abc" not in res.output
    assert shown in res.output and "503" in res.output


def test_a_301_is_refused_and_prints_no_credential(tmp_path, answer):
    answer(lambda r: httpx.Response(301, headers={"location": "https://other.test/?token=zzz"}))
    res = verify("https://fly.test/x?token=abc", tmp_path)
    assert res.exit_code == 2
    assert "token=abc" not in res.output and "zzz" not in res.output and "301" in res.output


def test_the_exception_text_from_fetch_events_never_carries_userinfo_or_query():
    t = httpx.MockTransport(lambda r: httpx.Response(503))
    with pytest.raises(w.WitnessError) as e:
        w.fetch_events("https://u:p@fly.test/x?token=abc", None, transport=t)
    msg = str(e.value)
    assert "u:p" not in msg and "token=abc" not in msg and "@" not in msg
    assert msg == "https://fly.test/x answered 503"


@pytest.mark.parametrize("url", ["https://u:p@fly.test/x", "https://user@fly.test/x", "http://a:b@fly.test/x?token=abc"])
def test_a_url_with_userinfo_is_refused_before_any_request(url, tmp_path, answer):
    calls = []
    answer(lambda r: calls.append(r) or httpx.Response(200, json=[]))
    res = verify(url, tmp_path)
    assert res.exit_code == 2
    assert "must not carry credentials" in res.output and "--secret-file" in res.output
    for secret_part in ("u:p", "user@", "a:b", "token=abc"):
        assert secret_part not in res.output
    assert calls == []


def test_the_non_https_secret_refusal_is_unchanged(tmp_path):
    f = tmp_path / "s"
    f.write_text("x", encoding="utf-8")
    res = verify("http://fly.test/events", tmp_path, "--secret-file", str(f))
    assert res.exit_code == 2 and "refusing to send a secret to a non-https --events-url" in res.output


def test_a_clean_url_is_shown_as_it_is(tmp_path, answer):
    answer(lambda r: httpx.Response(500))
    res = verify("https://fly.test/ledger/events", tmp_path)
    assert "https://fly.test/ledger/events answered 500" in res.output


@pytest.mark.parametrize("url,expected", [
    ("https://u:p@Fly.test:8443/a/b?token=1#frag", "https://fly.test:8443/a/b"),
    ("https://[::1]:9/x?q=1", "https://[::1]:9/x"),
    ("https://fly.test", "https://fly.test"),
])
def test_the_helper_renders_scheme_host_port_path_only(url, expected):
    assert w.redact_url(url) == expected


def test_the_helper_never_raises_on_garbage():
    assert "secret" not in w.redact_url("https://u:secret@host:notaport/x")
    assert isinstance(w.redact_url("::::"), str)
