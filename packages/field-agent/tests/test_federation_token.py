"""The SDK sends the agent's own token with a crossing request, as ``x-field-token``."""

from __future__ import annotations

import pytest

from field_agent.agent import FieldAgent
from field_agent.federation import FederationClient

MANIFEST = {"agent": "example"}


class Reply:
    status_code = 200

    def json(self):
        return {"decision": "ALLOW"}


class Broker:
    def __init__(self):
        self.headers = []

    def post(self, url, json=None, headers=None):
        self.headers.append({k.lower(): v for k, v in (headers or {}).items()})
        return Reply()


def test_the_client_sends_the_token_it_is_given():
    broker = Broker()
    FederationClient(client=broker, base_url="http://b").cross("a1", "Borealis Example", "read", "public", MANIFEST,
                                                               token_id="token-value")
    assert broker.headers[0]["x-field-token"] == "token-value"


@pytest.mark.parametrize("value", [None, "", "two\nlines", "caf\u00e9"])
def test_a_value_that_cannot_travel_is_left_out(value):
    broker = Broker()
    FederationClient(client=broker, base_url="http://b").cross("a1", "Borealis Example", "read", "public", MANIFEST,
                                                               token_id=value)
    assert "x-field-token" not in broker.headers[0]


@pytest.mark.parametrize("token,sent", [("token-value", "token-value"), (lambda: "rotated-value", "rotated-value"),
                                        (None, None)])
def test_the_agent_sends_its_current_token(token, sent):
    broker = Broker()
    FieldAgent("a1", token, federation_client=broker, federation_url="http://b").cross(
        "Borealis Example", "read", "public", MANIFEST)
    assert broker.headers[0].get("x-field-token") == sent
