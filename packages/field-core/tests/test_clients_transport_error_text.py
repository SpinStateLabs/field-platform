"""S7-5: a ledger or registry client that cannot reach its service says WHICH KIND of failure (the exception type), never the
exception's own text. ``str(exc)`` is whatever the HTTP stack wrote: a bad header value quotes the value (a
``FIELD_SHARED_SECRET`` with a trailing newline), a URL error quotes the URL. Services copy the text into 502 details and logs.
The original exception stays as ``__cause__``; ``status_code`` on a non-200 is unchanged."""

from __future__ import annotations

import socket
import threading

import httpx
import pytest

from field_core.clients import (
    LedgerClient, LedgerUnreachableError, RegistryClient, RegistryUnreachableError, _transport_text,
)

SECRET = "secret-value-0123456789"


class Boom:
    """an http object whose every call raises Exception(SECRET)"""

    def __init__(self, exc=None):
        self.exc = exc if exc is not None else Exception(SECRET)

    def get(self, *a, **k):
        raise self.exc

    post = patch = put = request = get


def calls():
    led = LedgerClient(client=Boom(), base_url="http://t")
    reg = RegistryClient(client=Boom(), base_url="http://t")
    return [
        ("ledger.append", LedgerUnreachableError, lambda: led.append("e.t", {})),
        ("ledger.retention_check", LedgerUnreachableError, led.retention_check),
        ("ledger.events", LedgerUnreachableError, led.events),
        ("registry.get_agent", RegistryUnreachableError, lambda: reg.get_agent("a1")),
        ("registry.set_status", RegistryUnreachableError, lambda: reg.set_status("a1", "killed")),
        ("registry.list_agents", RegistryUnreachableError, reg.list_agents),
    ]


@pytest.mark.parametrize("name,err,call", calls(), ids=[c[0] for c in calls()])
def test_no_site_copies_the_exception_text(name, err, call):
    with pytest.raises(err) as e:
        call()
    assert SECRET not in str(e.value) and str(e.value) == "Exception"
    assert isinstance(e.value.__cause__, Exception) and SECRET in str(e.value.__cause__)   # the cause is kept


def test_the_helper_is_the_type_name_only():
    assert _transport_text(ValueError(SECRET)) == "ValueError"
    assert _transport_text(httpx.ConnectError(SECRET)) == "ConnectError"
    assert _transport_text(KeyboardInterrupt()) == "KeyboardInterrupt"


def test_a_non_200_still_reports_its_status():
    class R:
        status_code = 503
        text = "x"

        def json(self):
            return {}

    class H:
        def post(self, *a, **k):
            return R()
        get = post
    with pytest.raises(LedgerUnreachableError) as e:
        LedgerClient(client=H(), base_url="http://t").append("e.t", {})
    assert e.value.status_code == 503 and "503" in str(e.value)


def test_a_real_illegal_header_value_no_longer_leaks_the_secret():
    """the verified leak: h11 raises ``Illegal header value b'<value>'`` for a secret with a trailing newline."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    port = srv.getsockname()[1]

    def serve():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            c.recv(65536)
            c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}")
            c.close()
    threading.Thread(target=serve, daemon=True).start()
    try:
        client = httpx.Client(headers={"x-field-auth": SECRET + "\n"}, timeout=2)
        with pytest.raises(httpx.LocalProtocolError) as raw:
            client.get(f"http://127.0.0.1:{port}/x")
        assert SECRET in str(raw.value)                                   # the unwrapped error DOES quote it
        with pytest.raises(LedgerUnreachableError) as e:
            LedgerClient(client=client, base_url=f"http://127.0.0.1:{port}").events()
        assert SECRET not in str(e.value) and str(e.value) == "LocalProtocolError"
    finally:
        srv.close()
