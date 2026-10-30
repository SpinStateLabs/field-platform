"""C-582 and C-623 (reviewer C-572 F-C572-1, C-596 F-C596-2): no environment value or URL secret reaches an error, a
response or a log.

* Five numeric tunables read in `create_app` (`FORCE_HYGIENE_WINDOW`, `FORCE_HYGIENE_BAND`,
  `FORCE_HYGIENE_BASELINE_WINDOWS`, `FORCE_GATEWAY_LATENCY_BUDGET_MS`, `FORCE_GATEWAY_BYPASS_COOLDOWN`): a value that
  is not a number refuses with the variable name only, never the value.
* `FIELD_SENTINEL_URL` is shown as scheme://host[:port] only (`/health`, the 503 detail, logs); the call itself keeps
  the full URL.

The canaries are made up; every 4-character slice, case kept and folded, must be absent from every surface.
"""
from __future__ import annotations

import logging
import traceback

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import (InvalidNumericSetting, SentinelClient, create_app, mock_upstream, public_origin)

from test_gateway_delta import FakeLedger

CANARY = "Zq7-canary-Kd93Lm-Xw41"
NUMERIC = [("FORCE_HYGIENE_WINDOW", int), ("FORCE_HYGIENE_BAND", float), ("FORCE_HYGIENE_BASELINE_WINDOWS", int),
           ("FORCE_GATEWAY_LATENCY_BUDGET_MS", float), ("FORCE_GATEWAY_BYPASS_COOLDOWN", int)]
MSG = {"model": "m", "max_tokens": 16, "system": "s", "messages": [{"role": "user", "content": "ping"}]}
HEADERS = {"x-field-agent-id": "a-1", "x-field-token": "t-1"}


def slices(text: str, n: int = 4):
    return [text[i:i + n] for i in range(len(text) - n + 1)]


def assert_absent(canary: str, *surfaces: str) -> None:
    for surface in surfaces:
        low = surface.lower()
        for piece in slices(canary):
            assert piece not in surface and piece.lower() not in low, piece


@pytest.mark.parametrize("var,cast", NUMERIC)
def test_a_non_numeric_value_never_reaches_the_exception_or_a_log(monkeypatch, caplog, var, cast):
    monkeypatch.setenv(var, CANARY)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(InvalidNumericSetting) as exc:
            create_app(upstream=mock_upstream)
    e = exc.value
    assert isinstance(e, ValueError) and var in str(e)
    assert e.__cause__ is None and e.__context__ is None          # the original text is not chained either
    assert_absent(CANARY, str(e), repr(e), repr(e.args), "".join(traceback.format_exception(e)), caplog.text)
    assert ("integer" if cast is int else "number") in str(e)    # the expected form is named


@pytest.mark.parametrize("var,cast", NUMERIC)
@pytest.mark.parametrize("raw", ["", " ", "1,5", "ten", "0x10", "1e", "--1"])
def test_every_other_junk_value_is_refused_the_same_way(monkeypatch, var, cast, raw):
    monkeypatch.setenv(var, raw)
    with pytest.raises(InvalidNumericSetting) as exc:
        create_app(upstream=mock_upstream)
    assert var in str(exc.value)


def test_valid_values_and_the_defaults_are_unchanged(monkeypatch):
    app = create_app(upstream=mock_upstream)
    assert (app.state.bypass_cooldown, app.state.latency_budget_ms) == (10, 250.0)
    d = app.state.drift
    assert (d.window_size, d.band, d.baseline_windows) == (5, 0.15, 2)
    monkeypatch.setenv("FORCE_HYGIENE_WINDOW", "7")
    monkeypatch.setenv("FORCE_HYGIENE_BAND", "0.25")
    monkeypatch.setenv("FORCE_HYGIENE_BASELINE_WINDOWS", "3")
    monkeypatch.setenv("FORCE_GATEWAY_LATENCY_BUDGET_MS", "12.5")
    monkeypatch.setenv("FORCE_GATEWAY_BYPASS_COOLDOWN", " 4 ")
    app = create_app(upstream=mock_upstream)
    d = app.state.drift
    assert (d.window_size, d.band, d.baseline_windows) == (7, 0.25, 3)
    assert (app.state.bypass_cooldown, app.state.latency_budget_ms) == (4, 12.5)


# ---- C-623: the sentinel URL ----------------------------------------------------------------------------------------

PASSWORD = "Pw9-canary-Rt58Vb"
TOKEN = "Tk3-canary-Hy72Nc"
URL = f"http://svc-user:{PASSWORD}@sentinel.invalid:8004/base/path?token={TOKEN}#frag"


class DownClient:
    """An injected transport whose error text carries the full URL, as a real transport error may."""

    def __init__(self):
        self.posted: list[str] = []

    def post(self, url, json=None):
        self.posted.append(url)
        raise RuntimeError(f"could not reach {url}")


def gateway_with(url: str, client=None):
    client = client or DownClient()
    sentinel = SentinelClient(client=client, base_url=url, timeout=1.0)
    app = create_app(upstream=mock_upstream, ledger_client=FakeLedger(), sentinel_client=sentinel, enforce=True,
                     sample_every=0, latency_budget_ms=10_000.0)
    return TestClient(app), client


@pytest.mark.parametrize("url,shown", [
    ("http://u:p@sentinel:8004/x?t=1#f", "http://sentinel:8004"),
    ("https://sentinel.example/a/b", "https://sentinel.example"),
    ("http://[::1]:9000/p", "http://[::1]:9000"),
    ("http://sentinel", "http://sentinel"),
    ("not a url", "(unparsable url)"),
    ("http://host:notaport/x", "(unparsable url)"),
    ("//nohost-scheme", "(unparsable url)"),
])
def test_public_origin_keeps_scheme_host_and_port_only(url, shown):
    assert public_origin(url) == shown
    assert public_origin(None) is None and public_origin("") is None


def test_health_shows_the_origin_only(caplog):
    with caplog.at_level(logging.DEBUG):
        client, _ = gateway_with(URL)
        body = client.get("/health").text
    assert "http://sentinel.invalid:8004" in body
    for canary in (PASSWORD, TOKEN, "svc-user", "base/path", "frag"):
        assert_absent(canary, body, caplog.text)


def test_the_503_detail_and_the_logs_show_the_origin_only_and_the_call_keeps_the_full_url(caplog):
    with caplog.at_level(logging.DEBUG):
        client, stub = gateway_with(URL)
        r = client.post("/v1/messages", json=MSG, headers=HEADERS)
    assert r.status_code == 503
    assert "sentinel.invalid:8004" in r.text
    for canary in (PASSWORD, TOKEN, "svc-user"):
        assert_absent(canary, r.text, caplog.text)
    assert stub.posted == [URL.rstrip("/") + "/check"]               # the real call still goes to the full URL


def test_the_health_sentinel_url_of_a_plain_origin_is_unchanged():
    client, _ = gateway_with("http://sentinel:8004")
    assert client.get("/health").json()["sentinel_url"] == "http://sentinel:8004"


def test_the_503_body_carries_no_credentialed_url_c686():
    """C-686 F-C686-3: the unreachable-sentinel 503 under a credentialed URL; no userinfo, path, query or fragment in the body."""
    client, _ = gateway_with(URL)
    r = client.post("/v1/messages", json=MSG, headers=HEADERS)
    assert r.status_code == 503
    for canary in (PASSWORD, TOKEN, "svc-user", "base/path", "frag"):
        assert_absent(canary, r.text)
    for marker in ("@", "?", "#", "/base", "token="):
        assert marker not in r.text, marker
