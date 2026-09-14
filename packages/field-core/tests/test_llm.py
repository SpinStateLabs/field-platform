"""field_core.llm — base-URL precedence and platform headers (v1.2 D2e)."""

import pytest

from field_core.authn import ENV_VAR as SECRET_ENV, HEADER as AUTH_HEADER
from field_core.llm import (
    DEFAULT_ANTHROPIC_BASE_URL,
    PASSTHROUGH_HEADER,
    anthropic_base_url,
    anthropic_headers,
    via_force_gateway,
)

SYNTHETIC_KEY = "SYNTHETIC-anthropic-key-not-real"
SYNTHETIC_SECRET = "synthetic-shared-secret-for-tests"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("FORCE_GATEWAY_URL", "ANTHROPIC_BASE_URL", SECRET_ENV):
        monkeypatch.delenv(var, raising=False)


def test_default_when_nothing_is_set():
    assert anthropic_base_url() == DEFAULT_ANTHROPIC_BASE_URL == "https://api.anthropic.com"
    assert via_force_gateway() is False


def test_anthropic_base_url_used_when_gateway_unset(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.example.test:9000/")
    assert anthropic_base_url() == "http://proxy.example.test:9000"


def test_force_gateway_url_wins_over_anthropic_base_url(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.example.test:9000")
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009//")
    assert anthropic_base_url() == "http://forcegw:8009"
    assert via_force_gateway() is True


@pytest.mark.parametrize("blank", ["", "   ", "/"])
def test_blank_gateway_url_counts_as_unset(monkeypatch, blank):
    """A compose `${FORCE_GATEWAY_URL:-}` renders as an empty string: that must
    fall through, never become a relative base URL."""
    monkeypatch.setenv("FORCE_GATEWAY_URL", blank)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.example.test:9000")
    assert anthropic_base_url() == "http://proxy.example.test:9000"
    assert via_force_gateway() is False


def test_headers_to_the_default_host_carry_no_platform_headers(monkeypatch):
    monkeypatch.setenv(SECRET_ENV, SYNTHETIC_SECRET)
    assert anthropic_headers(SYNTHETIC_KEY) == {
        "x-api-key": SYNTHETIC_KEY, "anthropic-version": "2023-06-01"}


def test_secret_never_rides_to_anthropic_base_url(monkeypatch):
    """ANTHROPIC_BASE_URL may be any third-party proxy: no shared secret."""
    monkeypatch.setenv(SECRET_ENV, SYNTHETIC_SECRET)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.example.test:9000")
    headers = anthropic_headers(SYNTHETIC_KEY)
    assert AUTH_HEADER not in headers
    assert PASSTHROUGH_HEADER not in headers


def test_gateway_target_gets_passthrough_and_auth(monkeypatch):
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    monkeypatch.setenv(SECRET_ENV, SYNTHETIC_SECRET)
    assert anthropic_headers(SYNTHETIC_KEY) == {
        "x-api-key": SYNTHETIC_KEY, "anthropic-version": "2023-06-01",
        "x-force-passthrough": "judge", "x-field-auth": SYNTHETIC_SECRET}


def test_gateway_target_on_a_secretless_estate_has_no_auth_header(monkeypatch):
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    headers = anthropic_headers(SYNTHETIC_KEY)
    assert headers[PASSTHROUGH_HEADER] == "judge"
    assert AUTH_HEADER not in headers


def test_read_per_call_not_at_import(monkeypatch):
    assert anthropic_base_url() == DEFAULT_ANTHROPIC_BASE_URL
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://127.0.0.1:8009")
    assert anthropic_base_url() == "http://127.0.0.1:8009"
