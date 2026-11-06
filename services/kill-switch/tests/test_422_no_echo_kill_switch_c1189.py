"""kill-switch's 422s never repeat the caller's text and keep the offending field name (C-1189; Lane 17 C-1185).

Four routes take a ``KillRequest`` body (/kill/{agent_id}, /kill/domain/{domain}, /revive/{agent_id}, /drill/{agent_id}).
FastAPI's default 422 puts the rejected input back in an ``input`` field and, for an unexpected field, the caller's own
key name in ``loc``; the field-core handler that stops that (C-1018) was not installed here, and the guard's "not yet"
reason named the one route (/heartbeat) that has no body. Every value here is a made-up marker."""

import pytest
from fastapi.testclient import TestClient

from kill_switch.api import create_app

MARK = "MADE-UP-MARKER-0123456789"
ROUTES = ["/kill/agent-1", "/kill/domain/dom-1", "/revive/agent-1", "/drill/agent-1"]


@pytest.fixture()
def client():
    return TestClient(create_app())


def _errors(r):
    detail = r.json()["detail"]
    assert isinstance(detail, list), r.text
    return detail


@pytest.mark.parametrize("path", ROUTES)
@pytest.mark.parametrize("body", [
    MARK,                                              # a JSON string where an object belongs
    {"operator": "o", "reason": "r", MARK: "x"},       # an unexpected field: the caller's key name
    {"operator": [MARK], "reason": "r"},               # a wrong-typed declared field
    {"operator": "o", "reason": {MARK: 1}},            # a dict key inside a value
    {},                                                # missing fields: the whole body would be echoed
], ids=["string-body", "extra-key", "wrong-type", "dict-key", "empty"])
def test_a_422_does_not_repeat_what_was_sent(client, path, body):
    r = client.post(path, json=body)
    assert r.status_code == 422
    assert MARK not in r.text, r.text
    assert all("input" not in e for e in _errors(r)), r.text


@pytest.mark.parametrize("path", ROUTES)
def test_the_offending_declared_field_is_still_named_with_a_fixed_reason(client, path):
    r = client.post(path, json={"operator": [MARK], "reason": "r"})
    assert r.status_code == 422
    errs = _errors(r)
    assert any(e["loc"] == ["body", "operator"] and e["type"] == "string_type" for e in errs), r.text
    assert all(isinstance(e["msg"], str) and MARK not in e["msg"] for e in errs)


@pytest.mark.parametrize("path", ROUTES)
def test_an_unexpected_key_is_redacted_not_named(client, path):
    r = client.post(path, json={"operator": "o", "reason": "r", MARK: "x"})
    assert r.status_code == 422
    assert any(e["type"] == "extra_forbidden" and e["loc"][-1] == "(field)" for e in _errors(r)), r.text
