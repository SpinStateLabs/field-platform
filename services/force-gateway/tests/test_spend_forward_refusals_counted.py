"""A usage report the governor answers with a non-2xx status is counted and logged (the status only); 404 (no such
route, or no cap for the agent) is not. Traffic is unchanged either way."""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import create_app, mock_upstream

AGENT = {"x-field-agent-id": "invoicing-agent"}
BODY = {"model": "m", "messages": []}


class Governor:
    def __init__(self, usage, spend=201):
        self.status, self.calls = {"/usage": usage, "/spend": spend}, []

    def post(self, url, json=None, **kw):
        self.calls.append(url)

        class R:
            status_code = self.status[url]

        return R()


def run(governor):
    client = TestClient(create_app(upstream=mock_upstream, governor_client=governor))
    r = client.post("/v1/messages", json=BODY, headers=AGENT)
    assert r.status_code == 200, r.text
    return client.get("/health").json()["spend_forwards_dropped"]


@pytest.mark.parametrize("status", [301, 400, 401, 403, 422, 429, 500, 503])
def test_a_refused_usage_report_is_counted_once_and_logged_by_status(caplog, status):
    governor = Governor(status)
    with caplog.at_level(logging.WARNING, logger="force_gateway"):
        assert run(governor) == 1
    assert governor.calls == ["/usage"]
    assert f"HTTP {status}" in caplog.text and "invoicing-agent" not in caplog.text


@pytest.mark.parametrize("status", [422, 500])
def test_a_refused_fallback_report_is_counted_once(status):
    governor = Governor(404, spend=status)
    assert run(governor) == 1
    assert governor.calls == ["/usage", "/spend"]


@pytest.mark.parametrize("usage,spend,calls", [(200, 201, ["/usage"]), (201, 201, ["/usage"]),
                                               (404, 201, ["/usage", "/spend"]), (404, 404, ["/usage", "/spend"])])
def test_an_accepted_report_and_a_404_are_not_counted(usage, spend, calls):
    governor = Governor(usage, spend)
    assert run(governor) == 0
    assert governor.calls == calls
