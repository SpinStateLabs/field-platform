"""FP-5: the served app installs the field_core authn middleware.

Black-box, no upstream services: a stub engine returns a minimal pack. The
secret is random per run (never a literal). /health stays open; every other
route is refused without the x-field-auth header and served with it.
"""

import secrets

import pytest
from fastapi.testclient import TestClient

from attestation_reporter.api import create_app
from attestation_reporter.engine import BoardPack, Window
from field_core.authn import ENV_VAR, HEADER


class _StubEngine:
    org = "Test Org"

    def build(self, period=None, since=None, until=None):
        return BoardPack(org=self.org, period="all-time", window=Window(kind="all-time", note="stub"), generated_at="2026-01-01T00:00:00+00:00", sections=[])


@pytest.fixture()
def secret(monkeypatch):
    value = secrets.token_hex(16)
    monkeypatch.setenv(ENV_VAR, value)
    return value


@pytest.fixture()
def client(secret):
    return TestClient(create_app(engine=_StubEngine()))


@pytest.mark.parametrize("path", ["/pack", "/pack.html", "/openapi.json", "/docs"])
def test_non_health_routes_refused_without_header(client, path):
    assert client.get(path).status_code == 401


def test_wrong_secret_refused(client):
    assert client.get("/pack", headers={HEADER: secrets.token_hex(16)}).status_code == 401


def test_health_stays_open(client):
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("path", ["/pack", "/pack.html"])
def test_correct_secret_accepted(client, secret, path):
    assert client.get(path, headers={HEADER: secret}).status_code == 200


# Review M13 (LOW): the cases above import HEADER, so a renamed constant would follow the test. External callers
# send the literal wire name; pin it here without the constant.
@pytest.mark.parametrize("path", ["/pack", "/pack.html"])
def test_literal_wire_header_name_is_accepted(client, secret, path):
    assert client.get(path, headers={"x-field-auth": secret}).status_code == 200


def test_header_constant_is_the_literal_wire_name():
    assert HEADER == "x-field-auth"
