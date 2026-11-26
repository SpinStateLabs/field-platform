"""C-582 and C-623 (reviewer C-572 F-C572-1, C-596 F-C596-2): no environment value or URL secret reaches an error, a
response or a log.

* The five numeric tunables read in `create_app` are main's (S8-31, test_tuning_env_bounds.py: refused naming the
  variable, never the value); the rebuild of PR 866 drops its own copy of that part as contained (controller ruling).
* `FIELD_SENTINEL_URL` is shown as scheme://host[:port] only (`/health`, the 503 detail, logs); the call itself keeps
  the full URL.

The canaries are made up; every 4-character slice, case kept and folded, must be absent from every surface.
"""
from __future__ import annotations

import logging
import traceback

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import (SentinelClient, SentinelUnavailable, create_app, mock_upstream, sentinel_check_url,
                               public_origin)

from test_gateway_delta import FakeLedger

CANARY = "Zq7-canary-Kd93Lm-Xw41"
MSG = {"model": "m", "max_tokens": 16, "system": "s", "messages": [{"role": "user", "content": "ping"}]}
HEADERS = {"x-field-agent-id": "a-1", "x-field-token": "t-1"}


def slices(text: str, n: int = 4):
    return [text[i:i + n] for i in range(len(text) - n + 1)]


def assert_absent(canary: str, *surfaces: str) -> None:
    for surface in surfaces:
        low = surface.lower()
        for piece in slices(canary):
            assert piece not in surface and piece.lower() not in low, piece


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
    ("http://u" + ":p@sentinel:8004/x?t=1#f", "http://sentinel:8004"),   # split: no literal userinfo URL (public-safety guard)
    ("https://sentinel.example/a/b", "https://sentinel.example"),
    ("http://[::1]:9000/p", "http://[::1]:9000"),
    ("http://sentinel", "http://sentinel"),
    ("not a url", "(unparsable url)"),
    ("http://host:notaport/x", "(unparsable url)"),
    ("//nohost-scheme", "(unparsable url)"),
    ("ftp://sentinel:21/x", "(unparsable url)"),
    ("http://", "(unparsable url)"),
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
    # main's #1295: the 503 body is a fixed category; the origin is in the exception's own message only
    assert r.json()["detail"] == "sentinel check did not happen — refusing: sentinel unreachable"
    for canary in (PASSWORD, TOKEN, "svc-user"):
        assert_absent(canary, r.text, caplog.text)
    # the real call still goes to the full URL, joined the B17 way (PR 1339): /check on the path, query kept, fragment dropped
    assert stub.posted == [sentinel_check_url(URL)]
    assert stub.posted == [f"http://svc-user:{PASSWORD}@sentinel.invalid:8004/base/path/check?token={TOKEN}"]
    with pytest.raises(SentinelUnavailable) as exc:
        SentinelClient(client=DownClient(), base_url=URL, timeout=1.0).check("a-1", "t-1", "egress")
    assert "http://sentinel.invalid:8004" in str(exc.value)
    for canary in (PASSWORD, TOKEN, "svc-user", "base/path"):
        assert_absent(canary, str(exc.value))


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


@pytest.mark.parametrize("tail", [" ", ";", ",", " key=", "!", "%20"])
def test_a_junk_host_is_not_shown_c734(tail):
    """C-734 F-C734-1: text after the host (a space, `;`, `,`, `key=`) is part of urlparse's hostname; only a real host is shown."""
    url = f"http://host.example{tail}{CANARY}"
    assert public_origin(url) == "(unparsable url)"
    client, _ = gateway_with(url)
    r = client.post("/v1/messages", json=MSG, headers=HEADERS)
    assert_absent(CANARY, r.text, client.get("/health").text)


def test_the_transport_error_is_not_chained_c734():
    """C-734 F-C734-2: the httpx error text (a bad-port URL puts the port text in it) is neither cause nor context."""
    sentinel = SentinelClient(client=DownClient(), base_url=URL, timeout=1.0)
    with pytest.raises(SentinelUnavailable) as exc:
        sentinel.check("a-1", "t-1", "act")
    e = exc.value
    assert e.__cause__ is None and e.__context__ is None
    assert_absent(PASSWORD, str(e), repr(e), "".join(traceback.format_exception(e)))


@pytest.mark.parametrize("zone", [" ", ";", ",", "key=", "25", "x" * 300, "%25"])
def test_a_scope_id_in_an_ipv6_host_is_not_shown_c846(zone, caplog):
    """C-846 F-C846-1: ipaddress accepts a link-local IPv6 address followed by `%text`; the text after % must not reach /health, the 503 or the logs."""
    link_local = "fe80" + "::1"                       # built from parts: no literal private IPv6 (public-safety guard)
    url = f"http://[{link_local}%{zone}{CANARY}]:8004"
    assert public_origin(url) == "(unparsable url)"
    with caplog.at_level(logging.DEBUG):
        client, _ = gateway_with(url)
        bodies = client.get("/health").text + client.post("/v1/messages", json=MSG, headers=HEADERS).text
    assert_absent(CANARY, bodies, caplog.text)


@pytest.mark.parametrize("host", ["-host", ".host", "_host", "host-", "host.", "host_", "-", "_", "."])
def test_a_host_must_start_and_end_with_a_letter_or_digit_c846(host):
    assert public_origin(f"http://{host}:8004") == "(unparsable url)"


@pytest.mark.parametrize("host", ["sentinel_1", "sentinel-1", "a.b_c-d.example", "s1", "a"])
def test_a_hostname_with_underscore_hyphen_or_dot_is_shown_c846(host):
    assert public_origin(f"http://{host}:8004") == f"http://{host}:8004"


def test_the_log_names_the_exception_type_c846(caplog):
    """The type name (never the message) says which failure mode occurred. main's #1295 keeps it out of the 503 body
    and logs it; #1272 does not chain the transport exception, so the class rides on SentinelUnavailable.failure."""
    caplog.set_level(logging.WARNING, logger="force_gateway")
    client, _ = gateway_with(URL)
    r = client.post("/v1/messages", json=MSG, headers=HEADERS)
    assert "RuntimeError" not in r.text
    logged = " ".join(rec.getMessage() for rec in caplog.records if rec.name == "force_gateway")
    assert "RuntimeError" in logged
    assert_absent(PASSWORD, logged)


# ---- roley.reviewer C1 on #1272: the success path (a sentinel that answers) logs no userinfo, path or query ----------

def _loopback_sentinel():
    """A real HTTP sentinel on 127.0.0.1 that answers every POST with ALLOW. Returns (server, port)."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Allow(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 (http.server's name)
            self.rfile.read(int(self.headers.get("content-length") or 0))
            body = json.dumps({"decision": "ALLOW", "clause_id": None, "reason": "ok"}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # the test server itself logs nothing
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Allow)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def test_a_sentinel_allow_logs_no_userinfo_path_or_query_at_any_level(caplog):
    server, port = _loopback_sentinel()
    try:
        url = f"http://svc-user:{PASSWORD}@127.0.0.1:{port}/basepath-Qp41?token={TOKEN}#frag"
        with caplog.at_level(logging.DEBUG):
            verdict = SentinelClient(base_url=url, timeout=5.0).check("a-1", "t-1", "egress")
        assert verdict["decision"] == "ALLOW"
        lines = [r for r in caplog.records if r.name == "httpx" and r.getMessage().startswith("HTTP Request:")]
        assert lines, "httpx logged no request line: the test would prove nothing"
        assert f"http://127.0.0.1:{port}" in lines[0].getMessage()
        text = caplog.text + " ".join(repr(r.args) for r in caplog.records)
        assert_absent(PASSWORD, text)                 # the made-up canaries: no 4-character slice anywhere
        assert_absent(TOKEN, text)
        for marker in ("svc-user", "basepath-Qp41", "#frag"):   # whole markers (a slice like "base" is in BaseHTTP)
            assert marker not in text, marker
    finally:
        server.shutdown()
        server.server_close()


def test_the_filter_rewrites_only_a_sentinel_origin_and_keeps_the_record():
    import logging as _logging

    from force_gateway import api as gw

    SentinelClient(base_url=f"http://u:{PASSWORD}@sentinel.example:8004/p?token={TOKEN}", timeout=1.0, client=object())
    f = gw._SENTINEL_URL_LOG_FILTER

    def rec(url):
        return _logging.LogRecord("httpx", _logging.INFO, __file__, 1, 'HTTP Request: %s %s "%s %d %s"',
                                  ("POST", url, "HTTP/1.1", 200, "OK"), None)

    mine = rec(f"http://u:{PASSWORD}@sentinel.example:8004/p?token={TOKEN}/check")
    assert f.filter(mine) is True and mine.args[1] == "http://sentinel.example:8004"
    other = rec("https://api.example.org/v1/messages?x=1")
    assert f.filter(other) is True and other.args[1] == "https://api.example.org/v1/messages?x=1"


@pytest.mark.parametrize("msg,args", [
    ("HTTP Request: %s %s", ("POST", "{url}")),                                   # a shorter request line
    ("Request to %s failed: %s", ("{url}", "ConnectError")),                      # another format, URL first
    ("%(method)s %(url)s", {"method": "POST", "url": "{url}"}),                   # mapping args
    ("retrying %s (%d)", ("{url}", 2)),
], ids=["short", "other-format", "mapping", "with-number"])
def test_the_filter_redacts_a_sentinel_url_in_any_httpx_record_format(msg, args):
    """Independent verdict on 6ab6b25f: the filter must not fail open on a record format it does not know. Any httpx
    record argument that reads as a URL to a sentinel origin is replaced by the origin; other arguments are untouched."""
    import logging as _logging

    from force_gateway import api as gw

    base = f"http://u:{PASSWORD}@sentinel-any.example:8004/p?token={TOKEN}"
    SentinelClient(base_url=base, timeout=1.0, client=object())
    full = base + "/check"
    if isinstance(args, dict):
        args = {k: (full if v == "{url}" else v) for k, v in args.items()}
    else:
        args = tuple(full if a == "{url}" else a for a in args)
    r = _logging.LogRecord("httpx", _logging.INFO, __file__, 1, msg, None, None)
    r.args = args
    assert gw._SENTINEL_URL_LOG_FILTER.filter(r) is True
    text = r.getMessage()
    assert "http://sentinel-any.example:8004" in text
    assert_absent(PASSWORD, text)
    assert_absent(TOKEN, text)
    assert "/p" not in text.replace("http://", "")


def test_the_filter_leaves_other_origins_and_non_url_arguments_alone():
    import logging as _logging

    from force_gateway import api as gw

    SentinelClient(base_url="http://sentinel-keep.example:8004", timeout=1.0, client=object())
    r = _logging.LogRecord("httpx", _logging.INFO, __file__, 1, "%s %s %d %s",
                           ("POST", "https://api.example.org/v1/messages?x=1", 200, b"raw"), None)
    assert gw._SENTINEL_URL_LOG_FILTER.filter(r) is True
    assert r.args == ("POST", "https://api.example.org/v1/messages?x=1", 200, b"raw")


@pytest.mark.parametrize("scheme,port", [("http", 80), ("https", 443)])
def test_an_explicit_default_port_is_filtered_too_r1(caplog, scheme, port):
    """reviewer-R1 on #1272: httpx logs http://h:80/... as http://h/... (and https :443 the same way), while the
    configured base keeps the port; the filter compares both without the default port. A real httpx client on a
    MockTransport produces httpx's own request line; nothing leaves the process."""
    import httpx

    def handler(request):
        return httpx.Response(200, json={"decision": "ALLOW", "clause_id": None})

    url = f"{scheme}://svc-user:{PASSWORD}@sentinel-r1.invalid:{port}/basepath-Qp41?token={TOKEN}#frag"
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with caplog.at_level(logging.DEBUG):
            verdict = SentinelClient(client=http, base_url=url, timeout=5.0).check("a-1", "t-1", "egress")
    assert verdict["decision"] == "ALLOW"
    lines = [r.getMessage() for r in caplog.records if r.name == "httpx" and r.getMessage().startswith("HTTP Request:")]
    assert lines == [f'HTTP Request: POST {scheme}://sentinel-r1.invalid "HTTP/1.1 200 OK"']
    text = caplog.text + " ".join(repr(r.args) for r in caplog.records)
    assert_absent(PASSWORD, text)
    assert_absent(TOKEN, text)
    for marker in ("svc-user", "basepath-Qp41", "#frag"):
        assert marker not in text, marker


@pytest.mark.parametrize("authority,origin", [
    ("b\u00fccher.example:8004", "http://xn--bcher-kva.example:8004"),            # an IDN host: httpx logs punycode
    ("xn--bcher-kva.example:8004", "http://xn--bcher-kva.example:8004"),
    ("sentinel-f1.invalid:\uff18\uff10\uff10\uff14", "http://sentinel-f1.invalid:8004"),   # a non-ASCII-digit port
], ids=["idn", "punycode", "fullwidth-port"])
def test_a_host_or_port_httpx_normalises_is_filtered_too_f1(caplog, authority, origin):
    """don.reviewer N1 and teammate-don F1 on #1272: httpx logs the normalised form, so the filter must compare in it,
    or the whole URL (userinfo, path, token) is logged on every successful check. MockTransport: nothing leaves."""
    import httpx

    def handler(request):
        return httpx.Response(200, json={"decision": "ALLOW", "clause_id": None})

    url = f"http://svc-user:{PASSWORD}@{authority}/basepath-Qp41?token={TOKEN}#frag"
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with caplog.at_level(logging.DEBUG):
            verdict = SentinelClient(client=http, base_url=url, timeout=5.0).check("a-1", "t-1", "egress")
    assert verdict["decision"] == "ALLOW"
    lines = [r.getMessage() for r in caplog.records if r.name == "httpx" and r.getMessage().startswith("HTTP Request:")]
    assert lines == [f'HTTP Request: POST {origin} "HTTP/1.1 200 OK"']
    text = caplog.text + " ".join(repr(r.args) for r in caplog.records)
    assert_absent(PASSWORD, text)
    assert_absent(TOKEN, text)
    for marker in ("svc-user", "basepath-Qp41", "#frag"):
        assert marker not in text, marker


def test_the_filter_key_is_none_for_what_httpx_cannot_read():
    from force_gateway import api as gw

    for bad in ("http://[::1", "http://h:notaport", "ftp://h.example", "not a url"):
        assert gw._httpx_origin(bad) is None, bad
    assert gw._httpx_origin("http://u" + ":p@H.Example:80/x?y=1") == "http://h.example"
    assert gw._httpx_origin("https://[::1]:8443/x") == "https://[::1]:8443"
