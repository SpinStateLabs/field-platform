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


# ---- a non-ASCII x-field-auth value is a 401, never a 500 (hmac.compare_digest refuses
# a str with a non-ASCII character; the middleware must compare bytes) ---------------

@pytest.mark.parametrize("raw", [b"\xe9", b"s3cret-demo-only\xe9", "é".encode("utf-8"), b"\xff\xfe"])
def test_a_non_ascii_header_value_is_401_not_a_crash(monkeypatch, raw):
    monkeypatch.setenv(ENV_VAR, "s3cret-demo-only")
    client = make_app()
    r = client.get("/data", headers=[(HEADER.encode(), raw)])
    assert r.status_code == 401
    assert "x-field-auth" in r.json()["detail"]


def test_a_non_ascii_configured_secret_still_authenticates(monkeypatch):
    secret = "sécret-demo-only"
    monkeypatch.setenv(ENV_VAR, secret)
    client = make_app()
    wire = secret.encode("utf-8")           # what a client puts on the wire
    assert client.get("/data", headers=[(HEADER.encode(), wire)]).status_code == 200
    assert client.get("/data", headers=[(HEADER.encode(), "s\u00e9cret-other".encode("utf-8"))]).status_code == 401
    assert client.get("/data", headers=[(HEADER.encode(), b"wrong")]).status_code == 401
