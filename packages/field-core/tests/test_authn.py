"""Shared-secret authn tests (STATE.md OQ-1)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from field_core.authn import ENV_VAR, HEADER, auth_headers, install


def make_app() -> TestClient:
    app = FastAPI()
    install(app)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/data")
    def data():
        return {"value": 42}

    return TestClient(app)


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    client = make_app()
    assert client.get("/data").status_code == 200
    assert auth_headers() == {}


def test_secret_required_when_set(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "s3cret-demo-only")
    client = make_app()

    r = client.get("/data")
    assert r.status_code == 401
    assert "x-field-auth" in r.json()["detail"]

    assert client.get("/data", headers={HEADER: "wrong"}).status_code == 401
    assert client.get("/data", headers={HEADER: "s3cret-demo-only"}).status_code == 200
    assert auth_headers() == {HEADER: "s3cret-demo-only"}


def test_health_stays_open(monkeypatch):
    """Liveness probes must work without the secret."""
    monkeypatch.setenv(ENV_VAR, "s3cret-demo-only")
    client = make_app()
    assert client.get("/health").status_code == 200


def test_adversarial_empty_header_rejected(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "s3cret-demo-only")
    client = make_app()
    assert client.get("/data", headers={HEADER: ""}).status_code == 401


# ---- red team F-H1-1, F-H1-2: a non-ASCII header or secret is a 401 or a match, never a 500 ----------------------------

class _Status:
    def __init__(self, status_code):
        self.status_code = status_code


def _asgi(app, path, headers):
    """Drive the ASGI app directly: the test client re-encodes header bytes, so only a raw scope reaches the middleware
    with exactly these bytes (the server decodes them as latin-1)."""
    import asyncio

    seen = []

    async def go():
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "path": path,
                 "raw_path": path.encode(), "query_string": b"", "root_path": "", "scheme": "http",
                 "headers": headers, "client": ("127.0.0.1", 1), "server": ("testserver", 80)}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                seen.append(message["status"])
        await app(scope, receive, send)
    asyncio.run(go())
    return _Status(seen[0])


class _RawClient:
    """The same make_app(), reached through raw ASGI for the x-field-auth bytes and through TestClient otherwise."""
    def __init__(self):
        self.client = make_app()

    def get(self, path, headers=None):
        if headers:
            return _asgi(self.client.app, path, [(k, v) for k, v in headers])
        return self.client.get(path)


def _raw(client, path, raw_value):
    return client.get(path, headers=[(b"x-field-auth", raw_value)])


@pytest.mark.parametrize("raw", [b"\xe9", b"s3cret-demo-only\xe9", b"\xff\xfe", "é".encode("utf-8"), b"\x80" * 40])
def test_a_non_ascii_header_is_401_not_500_and_health_stays_open(monkeypatch, raw):
    monkeypatch.setenv(ENV_VAR, "s3cret-demo-only")
    client = _RawClient()
    assert _raw(client, "/data", raw).status_code == 401
    assert client.get("/health").status_code == 200


def test_the_right_secret_still_passes_after_the_change(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "s3cret-demo-only")
    assert _raw(_RawClient(), "/data", b"s3cret-demo-only").status_code == 200


def test_a_non_ascii_secret_matches_its_utf8_bytes_and_refuses_anything_else(monkeypatch, caplog):
    secret = "sécret-demo-only-é"
    monkeypatch.setenv(ENV_VAR, secret)
    with caplog.at_level("WARNING", logger="field_core.authn"):
        client = _RawClient()
    assert _raw(client, "/data", secret.encode("utf-8")).status_code == 200
    assert _raw(client, "/data", secret.encode("latin-1")).status_code == 401
    assert _raw(client, "/data", b"wrong").status_code == 401
    assert client.get("/data").status_code == 401
    assert client.get("/health").status_code == 200
    assert [r.getMessage() for r in caplog.records].count(
        f"{ENV_VAR} holds a non-ASCII character; callers must send its UTF-8 bytes in {HEADER}") == 1
    assert secret not in caplog.text and "cret-demo" not in caplog.text


def test_an_ascii_secret_logs_nothing_at_install(monkeypatch, caplog):
    monkeypatch.setenv(ENV_VAR, "s3cret-demo-only")
    with caplog.at_level("DEBUG", logger="field_core.authn"):
        make_app()
    assert caplog.text == ""


def test_secret_matches_never_raises_and_compares_bytes():
    from field_core.authn import secret_matches
    assert secret_matches("abc", "abc") and not secret_matches("abd", "abc")
    assert not secret_matches("é", "abc") and not secret_matches("aĀ", "abc")     # beyond latin-1: no match, no raise
    assert secret_matches("\xc3\xa9", "é")                                              # the raw UTF-8 bytes of the secret
    assert not secret_matches("abc", "")
