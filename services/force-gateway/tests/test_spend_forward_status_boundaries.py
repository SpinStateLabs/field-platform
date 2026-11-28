"""The edges of the metering gap count: which governor answers are counted, on the first route and on the fallback."""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import create_app, mock_upstream

AGENT = {"x-field-agent-id": "invoicing-agent"}
BODY = {"model": "m", "messages": []}


class Governor:
    """Answers each route with a status, raises it when it is an exception, or answers with no status at all (None)."""

    def __init__(self, usage, spend=201):
        self.answers, self.calls = {"/usage": usage, "/spend": spend}, []

    def post(self, url, json=None, **kw):
        self.calls.append(url)
        answer = self.answers[url]
        if isinstance(answer, Exception):
            raise answer

        class R:
            pass

        if answer is not None:
            R.status_code = answer
        return R()


def run(governor):
    client = TestClient(create_app(upstream=mock_upstream, governor_client=governor))
    r = client.post("/v1/messages", json=BODY, headers=AGENT)
    assert r.status_code == 200, r.text
    return client.get("/health").json()["spend_forwards_dropped"]


@pytest.mark.parametrize("status,counted", [(199, 1), (200, 0), (204, 0), (299, 0), (300, 1)])
def test_only_a_2xx_answer_is_accepted(status, counted):
    governor = Governor(status)
    assert run(governor) == counted
    assert governor.calls == ["/usage"]


@pytest.mark.parametrize("spend,counted", [(204, 0), (299, 0), (300, 1)])
def test_the_fallback_answer_is_judged_by_the_same_edges(spend, counted):
    governor = Governor(404, spend=spend)
    assert run(governor) == counted
    assert governor.calls == ["/usage", "/spend"]


def test_a_refused_fallback_is_logged_by_status_and_never_names_the_agent(caplog):
    with caplog.at_level(logging.WARNING, logger="force_gateway"):
        assert run(Governor(404, spend=422)) == 1
    assert "HTTP 422" in caplog.text and "invoicing-agent" not in caplog.text


def test_a_fallback_that_raises_is_counted_once_and_logged_by_type_only(caplog):
    governor = Governor(404, spend=RuntimeError("MADE-UP-MARKER invoicing-agent"))
    with caplog.at_level(logging.WARNING, logger="force_gateway"):
        assert run(governor) == 1
    assert governor.calls == ["/usage", "/spend"]
    assert "RuntimeError" in caplog.text
    assert "MADE-UP-MARKER" not in caplog.text and "invoicing-agent" not in caplog.text


def test_an_answer_without_a_status_is_taken_as_accepted():
    assert run(Governor(None)) == 0
