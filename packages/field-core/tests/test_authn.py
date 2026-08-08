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
