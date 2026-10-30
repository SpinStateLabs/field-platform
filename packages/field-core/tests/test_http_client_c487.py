"""C-487 slice 1 (Lane 10 note 20261101-0300-design-env-proxy-class.md section 4): the ONE constructor for a
platform HTTP client, ``field_core.http.client`` and ``async_client``.

What is pinned, each by a mutant:

* ``trust_env=False``: an environment proxy (HTTP_PROXY, HTTPS_PROXY, ALL_PROXY) is never used. A control
  with a stock ``httpx.Client`` proves the listener WOULD have been hit, so a zero is not a vacuous zero.
* redirects are not followed (a 3xx carries the perimeter header nowhere);
* the timeout is required, and ``None`` (no timeout) or a non-positive number is refused;
* a caller cannot override ``trust_env``, ``follow_redirects``, ``proxy``, ``proxies`` or ``mounts``;
* the only proxy is the explicit ``FIELD_EGRESS_PROXY``, an http(s) URL with a host; a bad value is refused
  WITHOUT echoing it (it may carry credentials).

Local listeners only; nothing leaves the machine."""

from __future__ import annotations

import asyncio
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from field_core import http as fhttp

SECRET_VALUE = "ftp://user:hunter2-not-a-real-secret@proxy.invalid:21"


class _Listener:
    """A local HTTP server that counts requests and answers every one with `status` (+ Location)."""

    def __init__(self, status=200, location=None):
        self.hits: list[str] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _answer(self):
                outer.hits.append(self.path)
                self.send_response(status)
                if location:
                    self.send_header("Location", location)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            do_GET = do_POST = do_CONNECT = _answer

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.t.join(timeout=5)


@pytest.fixture()
def target():
    s = _Listener()
    yield s
    s.close()


@pytest.fixture()
def proxy():
    s = _Listener()
    yield s
    s.close()


@pytest.fixture()
def proxy_env(monkeypatch, proxy):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, proxy.url)
    for name in ("NO_PROXY", "no_proxy", fhttp.ENV_EGRESS_PROXY):
        monkeypatch.delenv(name, raising=False)
    return proxy


# ---- the control and the point ----------------------------------------------------------


def test_control_a_stock_client_does_use_the_environment_proxy(proxy_env, target):
    """Without this the zero below would prove nothing."""
    with httpx.Client(timeout=5) as c:
        c.get(target.url + "/x")
    assert proxy_env.hits and not target.hits


def test_client_never_uses_the_environment_proxy(proxy_env, target):
    with fhttp.client(timeout=5) as c:
        assert c.get(target.url + "/x").status_code == 200
    assert proxy_env.hits == [] and target.hits == ["/x"]


def test_async_client_never_uses_the_environment_proxy(proxy_env, target):
    async def go():
        async with fhttp.async_client(timeout=5) as c:
            return (await c.get(target.url + "/x")).status_code

    assert asyncio.run(go()) == 200
    assert proxy_env.hits == [] and target.hits == ["/x"]


@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
def test_flags_and_types(make):
    c = make(timeout=7)
    assert c.trust_env is False and c.follow_redirects is False
    assert isinstance(c, httpx.AsyncClient if make is fhttp.async_client else httpx.Client)
    assert c.timeout == httpx.Timeout(7)


def test_a_redirect_is_returned_not_followed(proxy_env):
    final = _Listener()
    first = _Listener(status=302, location=final.url + "/landed")
    try:
        with fhttp.client(timeout=5) as c:
            r = c.get(first.url + "/start")
        assert r.status_code == 302 and final.hits == [] and first.hits == ["/start"]
    finally:
        first.close()
        final.close()


# ---- timeout ------------------------------------------------------------------------------


def test_the_timeout_is_required():
    with pytest.raises(TypeError):
        fhttp.client()
    with pytest.raises(TypeError):
        fhttp.async_client()


@pytest.mark.parametrize("bad", [None, 0, -1, 0.0, True, "5"])
@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
def test_a_missing_or_unusable_timeout_is_refused(make, bad):
    with pytest.raises(ValueError):
        make(timeout=bad)


def test_an_httpx_timeout_object_is_accepted():
    t = httpx.Timeout(3.0, connect=1.0)
    assert fhttp.client(timeout=t).timeout == t


# ---- callers cannot weaken it ---------------------------------------------------------------


@pytest.mark.parametrize("key", ["trust_env", "follow_redirects", "proxy", "proxies", "mounts"])
@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
def test_a_caller_cannot_override_the_pinned_arguments(make, key):
    with pytest.raises(ValueError) as e:
        make(timeout=5, **{key: True})
    assert key in str(e.value)


@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
def test_other_arguments_pass_through(make):
    c = make(timeout=5, base_url="http://svc.internal:8000", headers={"x-test": "1"})
    assert str(c.base_url).startswith("http://svc.internal:8000") and c.headers["x-test"] == "1"


# ---- the one explicit proxy ----------------------------------------------------------------


def test_the_explicit_egress_proxy_is_used_when_set(monkeypatch, proxy):
    monkeypatch.setenv(fhttp.ENV_EGRESS_PROXY, proxy.url)
    with fhttp.client(timeout=5) as c:
        c.get("http://example.invalid/via-proxy")
    assert proxy.hits and "example.invalid" in proxy.hits[0]


def test_no_egress_proxy_means_a_direct_client(monkeypatch, target):
    monkeypatch.delenv(fhttp.ENV_EGRESS_PROXY, raising=False)
    with fhttp.client(timeout=5) as c:
        c.get(target.url + "/direct")
    assert target.hits == ["/direct"]


@pytest.mark.parametrize("value", [SECRET_VALUE, "not a url", "http://", "socks5://127.0.0.1:1080", "//host:3128"])
@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
def test_a_bad_egress_proxy_is_refused_and_never_echoed(monkeypatch, make, value):
    monkeypatch.setenv(fhttp.ENV_EGRESS_PROXY, value)
    with pytest.raises(ValueError) as e:
        make(timeout=5)
    msg = str(e.value)
    assert fhttp.ENV_EGRESS_PROXY in msg
    assert "hunter2" not in msg and "proxy.invalid" not in msg and value not in msg


def test_a_blank_egress_proxy_means_none(monkeypatch, target):
    monkeypatch.setenv(fhttp.ENV_EGRESS_PROXY, "   ")
    with fhttp.client(timeout=5) as c:
        c.get(target.url + "/blank")
    assert target.hits == ["/blank"]


# ---- reviewer C-746: the contract is the pinned list, and it is enforced ----------------------


@pytest.mark.parametrize("bad", [
    httpx.Timeout(None),
    httpx.Timeout(None, connect=5),
    httpx.Timeout(5, read=None),
    httpx.Timeout(5, write=None),
    httpx.Timeout(5, pool=None),
    httpx.Timeout(0),
    httpx.Timeout(5, connect=0),
])
@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
def test_a_timeout_object_with_a_missing_or_zero_part_is_refused(make, bad):
    with pytest.raises(ValueError):
        make(timeout=bad)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
def test_a_non_finite_timeout_is_refused(make, bad):
    with pytest.raises(ValueError):
        make(timeout=bad)


@pytest.mark.parametrize("ok", [httpx.Timeout(5), httpx.Timeout(5, connect=1, read=2, write=3, pool=4)])
def test_a_fully_positive_timeout_object_is_accepted_as_given(ok):
    assert fhttp.client(timeout=ok).timeout == ok


@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
@pytest.mark.parametrize("bad", [False, "/etc/ssl/cert.pem", 0, None])
def test_verify_other_than_true_or_a_context_is_refused(make, bad):
    with pytest.raises(ValueError) as e:
        make(timeout=5, verify=bad)
    assert "verify" in str(e.value)


@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
def test_verify_true_and_a_caller_built_context_are_accepted(make):
    assert make(timeout=5, verify=True) is not None
    assert make(timeout=5, verify=ssl.create_default_context()) is not None


@pytest.mark.parametrize("key", ["transport", "event_hooks", "cert"])
@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
def test_transport_hooks_and_cert_cannot_be_passed(make, key):
    with pytest.raises(ValueError) as e:
        make(timeout=5, **{key: object()})
    assert key in str(e.value)


# ---- reviewer C-778: the upper bound, a context that does not verify, base_url ------------------------------


@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
def test_the_timeout_at_the_cap_is_accepted_and_one_second_over_is_refused(make):
    assert make(timeout=fhttp.MAX_TIMEOUT_S) is not None
    for bad in (fhttp.MAX_TIMEOUT_S + 1, 10**9, httpx.Timeout(5, read=fhttp.MAX_TIMEOUT_S + 1),
                httpx.Timeout(fhttp.MAX_TIMEOUT_S + 1)):
        with pytest.raises(ValueError):
            make(timeout=bad)


def _ctx(*, verify_mode, check_hostname):
    c = ssl.create_default_context()
    c.check_hostname = check_hostname
    c.verify_mode = verify_mode
    return c


@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
@pytest.mark.parametrize("bad", [
    _ctx(verify_mode=ssl.CERT_NONE, check_hostname=False),
    _ctx(verify_mode=ssl.CERT_OPTIONAL, check_hostname=False),
    _ctx(verify_mode=ssl.CERT_REQUIRED, check_hostname=False),
])
def test_a_context_that_does_not_require_and_check_the_certificate_is_refused(make, bad):
    with pytest.raises(ValueError) as e:
        make(timeout=5, verify=bad)
    assert "verify" in str(e.value)


@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
def test_a_strict_context_is_accepted(make):
    assert make(timeout=5, verify=_ctx(verify_mode=ssl.CERT_REQUIRED, check_hostname=True)) is not None


@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
@pytest.mark.parametrize("bad", [
    "http://user:pw-not-real@svc.internal:8000", "http://:pw-not-real@svc.internal", "ftp://svc.internal/",
    "file:///etc/passwd", "//svc.internal", "http://", "http://169.254.169.254/latest", "http://[fe80::1]/",
    "http://[fe80::1%25eth0]/",
])
def test_a_base_url_with_userinfo_a_bad_scheme_no_host_or_a_link_local_address_is_refused(make, bad):
    with pytest.raises(ValueError) as e:
        make(timeout=5, base_url=bad)
    assert "pw-not-real" not in str(e.value) and "169.254" not in str(e.value)


@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
@pytest.mark.parametrize("ok", ["http://svc.internal:8000", "https://example.com/api", "http://127.0.0.1:9", "http://[::1]:9/"])
def test_an_ordinary_base_url_is_accepted(make, ok):
    assert make(timeout=5, base_url=ok) is not None


@pytest.mark.parametrize("make", [fhttp.client, fhttp.async_client])
def test_no_base_url_is_fine(make):
    assert make(timeout=5, base_url="") is not None
