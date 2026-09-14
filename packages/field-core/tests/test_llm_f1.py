"""field_core.llm — F1 self-agent identity at the egress.

An enforcing force-gateway requires `x-field-agent-id` + `x-field-token` on
every /v1/messages, the platform's own judge calls included. The headers are
added ONLY toward FORCE_GATEWAY_URL and ONLY when BOTH FIELD_SELF_AGENT_ID and
FIELD_SELF_TOKEN_ID are set; otherwise the headers are exactly D2e's."""

import pytest

from field_core.authn import ENV_VAR as SECRET_ENV
from field_core.llm import (
    AGENT_ID_HEADER,
    EGRESS_ACTION,
    SELF_AGENT_ID_ENV,
    SELF_TOKEN_ID_ENV,
    TOKEN_HEADER,
    anthropic_headers,
    self_identity_headers,
)

SYNTHETIC_KEY = "SYNTHETIC-anthropic-key-not-real"
D2E_GATEWAY_HEADERS = {"x-api-key": SYNTHETIC_KEY, "anthropic-version": "2023-06-01",
                       "x-force-passthrough": "judge"}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("FORCE_GATEWAY_URL", "ANTHROPIC_BASE_URL", SECRET_ENV,
                SELF_AGENT_ID_ENV, SELF_TOKEN_ID_ENV):
        monkeypatch.delenv(var, raising=False)


def test_wire_names_are_the_gateways():
    assert AGENT_ID_HEADER == "x-field-agent-id"
    assert TOKEN_HEADER == "x-field-token"
    assert EGRESS_ACTION == "llm.messages"
    assert (SELF_AGENT_ID_ENV, SELF_TOKEN_ID_ENV) == ("FIELD_SELF_AGENT_ID", "FIELD_SELF_TOKEN_ID")


def test_both_unset_is_exactly_d2e(monkeypatch):
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    assert self_identity_headers() == {}
    assert anthropic_headers(SYNTHETIC_KEY) == D2E_GATEWAY_HEADERS


def test_both_set_adds_the_pair_toward_the_gateway(monkeypatch):
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    monkeypatch.setenv(SELF_AGENT_ID_ENV, "conformance-sentinel")
    monkeypatch.setenv(SELF_TOKEN_ID_ENV, "tok-self-1")
    assert anthropic_headers(SYNTHETIC_KEY) == {
        **D2E_GATEWAY_HEADERS, "x-field-agent-id": "conformance-sentinel",
        "x-field-token": "tok-self-1"}


def test_the_pair_never_rides_to_a_third_party(monkeypatch):
    """A token id is a bearer at the egress: ANTHROPIC_BASE_URL may be any
    proxy, the default host is Anthropic — neither gets it."""
    monkeypatch.setenv(SELF_AGENT_ID_ENV, "conformance-sentinel")
    monkeypatch.setenv(SELF_TOKEN_ID_ENV, "tok-self-1")
    assert anthropic_headers(SYNTHETIC_KEY) == {
        "x-api-key": SYNTHETIC_KEY, "anthropic-version": "2023-06-01"}
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.example.test:9000")
    headers = anthropic_headers(SYNTHETIC_KEY)
    assert AGENT_ID_HEADER not in headers and TOKEN_HEADER not in headers


@pytest.mark.parametrize("agent,token", [
    ("conformance-sentinel", None), (None, "tok-self-1"),
    ("conformance-sentinel", ""), ("  ", "tok-self-1"),
])
def test_a_half_configured_pair_sends_neither(monkeypatch, agent, token):
    """Both or neither: a half-configured self-agent gets the gateway's 401
    (visible), never a guessed identity."""
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    if agent is not None:
        monkeypatch.setenv(SELF_AGENT_ID_ENV, agent)
    if token is not None:
        monkeypatch.setenv(SELF_TOKEN_ID_ENV, token)
    assert self_identity_headers() == {}
    assert anthropic_headers(SYNTHETIC_KEY) == D2E_GATEWAY_HEADERS


def test_values_are_stripped_but_not_url_normalised(monkeypatch):
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    monkeypatch.setenv(SELF_AGENT_ID_ENV, " force-gateway ")
    monkeypatch.setenv(SELF_TOKEN_ID_ENV, "tok/with/slash/")
    assert self_identity_headers() == {"x-field-agent-id": "force-gateway",
                                       "x-field-token": "tok/with/slash/"}


def test_read_per_call_not_at_import(monkeypatch):
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    assert AGENT_ID_HEADER not in anthropic_headers(SYNTHETIC_KEY)
    monkeypatch.setenv(SELF_AGENT_ID_ENV, "compliance-crosswalk")
    monkeypatch.setenv(SELF_TOKEN_ID_ENV, "tok-self-2")
    assert anthropic_headers(SYNTHETIC_KEY)[AGENT_ID_HEADER] == "compliance-crosswalk"
    monkeypatch.delenv(SELF_TOKEN_ID_ENV)
    assert AGENT_ID_HEADER not in anthropic_headers(SYNTHETIC_KEY)


def test_secret_and_pair_ride_together_to_the_gateway(monkeypatch):
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    monkeypatch.setenv(SECRET_ENV, "synthetic-shared-secret-for-tests")
    monkeypatch.setenv(SELF_AGENT_ID_ENV, "force-gateway")
    monkeypatch.setenv(SELF_TOKEN_ID_ENV, "tok-self-3")
    headers = anthropic_headers(SYNTHETIC_KEY)
    assert headers["x-field-auth"] == "synthetic-shared-secret-for-tests"
    assert headers[AGENT_ID_HEADER] == "force-gateway" and headers[TOKEN_HEADER] == "tok-self-3"
