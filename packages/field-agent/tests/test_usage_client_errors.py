"""Scout S-2-20 (the part PR 372 does not cover): pins the UsageClient paths that had no test, on main as it is. Tests only.

Not here, because PR 372 (rebuilt as #556) changes them and ships its own tests: the wording of a non-201 message, the 404
detail, and a 201 with an unusable body. What these tests pin is stable across that change: a transport failure is a
`UsageReportError` that says the usage or spend was NOT metered, a 404 (JSON or not) is `NoSpendCapError` and a different
type from a 5xx, a 5xx is a `UsageReportError`, and the `/spend` body carries `action` only when one is given (a pre-D1
governor forbids the key)."""
from __future__ import annotations

import json

import httpx
import pytest

from field_agent.errors import NoSpendCapError, UsageReportError
from field_agent.usage import UsageClient

BASE = "http://gov.invalid"
REPORT = lambda c: c.report("a1", "claude-haiku-4-5", 10, 5)           # noqa: E731
SPEND = lambda c: c.spend("a1", cents=5)                                 # noqa: E731


def client_with(handler):
    return UsageClient(client=httpx.Client(transport=httpx.MockTransport(handler)), base_url=BASE)


def answer(status, body=None, *, raw=None):
    def handler(request):
        if raw is not None:
            return httpx.Response(status, content=raw)
        return httpx.Response(status, json=body if body is not None else {})
    return handler


class Down(httpx.BaseTransport):
    def __init__(self, exc):
        self.exc = exc

    def handle_request(self, request):
        raise self.exc


@pytest.mark.parametrize("call,what", [(REPORT, "usage"), (SPEND, "spend")])
@pytest.mark.parametrize("exc", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), RuntimeError("odd")])
def test_a_transport_failure_is_a_usage_report_error_that_says_not_metered(call, what, exc):
    c = UsageClient(client=httpx.Client(transport=Down(exc)), base_url=BASE)
    with pytest.raises(UsageReportError) as e:
        call(c)
    assert f"{what} NOT metered" in str(e.value) and not isinstance(e.value, NoSpendCapError)
    assert e.value.__cause__ is exc


@pytest.mark.parametrize("call", [REPORT, SPEND])
@pytest.mark.parametrize("handler", [
    answer(404, {"detail": "no spend cap for a1"}),       # JSON detail
    answer(404, raw=b"plain text, not json"),              # not JSON
    answer(404, raw=b""),                                  # empty
])
def test_a_404_is_no_spend_cap_whatever_its_body(call, handler):
    with pytest.raises(NoSpendCapError):
        call(client_with(handler))


@pytest.mark.parametrize("call", [REPORT, SPEND])
@pytest.mark.parametrize("status", [400, 401, 403, 409, 422, 429, 500, 502, 503])
def test_any_other_non_201_is_a_usage_report_error_never_no_spend_cap(call, status):
    with pytest.raises(UsageReportError) as e:
        call(client_with(answer(status, {"detail": "x"})))
    assert not isinstance(e.value, NoSpendCapError) and str(status) in str(e.value)


def _spend_status():
    return {"agent_id": "a1", "state": "OK", "spent_cents": 5, "limit_cents": 100}


def _capture(sent):
    def handler(request):
        sent.append((request.url.path, json.loads(request.content)))
        return httpx.Response(201, json=_spend_status())
    return handler


def test_the_spend_body_omits_action_when_it_is_none():
    sent = []
    assert client_with(_capture(sent)).spend("a1", cents=5).state == "OK"
    path, body = sent[0]
    assert path == "/spend" and "action" not in body
    assert body == {"agent_id": "a1", "cents": 5, "tokens": 0, "actions": 0, "note": None}


def test_the_spend_body_includes_action_when_it_is_set():
    sent = []
    client_with(_capture(sent)).spend("a1", cents=5, actions=2, action="send-email", note="n")
    _, body = sent[0]
    assert body["action"] == "send-email" and body["actions"] == 2 and body["note"] == "n"


def test_the_report_body_carries_every_field():
    sent = []

    def handler(request):
        sent.append((request.url.path, json.loads(request.content)))
        return httpx.Response(500, json={})

    with pytest.raises(UsageReportError):
        client_with(handler).report("a1", "m", 10, 5, cache_read_tokens=3, note="n")
    path, body = sent[0]
    assert path == "/usage"
    assert body == {"agent_id": "a1", "model": "m", "input_tokens": 10, "output_tokens": 5,
                    "cache_read_tokens": 3, "note": "n"}
