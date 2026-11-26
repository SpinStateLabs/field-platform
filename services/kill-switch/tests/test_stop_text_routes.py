"""A refused reason or operator is a 422 on kill, domain kill, revive and drill, with nothing read, written or sent;
an ordinary reason still halts."""

from __future__ import annotations

import json
from urllib.parse import unquote

import pytest

from kill_switch.api import REASON_HEADER, REASON_HEADER_MAX, _reason_header

from test_endpoint_and_liveness import Stack

HOST = "halt.allowed.host"
ROUTES = ["/kill/agent-1", "/kill/domain/finance", "/revive/agent-1", "/drill/agent-1"]
REFUSED = {"line-feed": "two" + chr(10) + "lines", "tab": "a" + chr(9) + "tab",
           "zero-width-joiner": "zero" + chr(0x200D) + "width", "line-separator": "a" + chr(0x2028) + "b",
           "lone-surrogate": "lone" + chr(0xD800), "blank": "   "}


@pytest.fixture()
def halted(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", HOST)
    stack = Stack(tmp_path)
    stack.with_endpoint("agent-1", f"http://{HOST}/halt")
    return stack


def send(stack, path, body):
    # raw JSON: a lone surrogate travels as the \uXXXX escape the server's parser accepts
    return stack.kill.post(path, content=json.dumps(body, ensure_ascii=True),
                           headers={"content-type": "application/json"})


def status_of(stack):
    return stack.registry.get("/agents/agent-1").json()["status"]


@pytest.mark.parametrize("path", ROUTES)
@pytest.mark.parametrize("name", REFUSED)
def test_a_refused_reason_changes_writes_and_sends_nothing(halted, path, name):
    before = halted.events()
    r = send(halted, path, {"operator": "CISO", "reason": REFUSED[name]})
    assert r.status_code == 422, r.text
    assert any(e["loc"] == ["body", "reason"] for e in r.json()["detail"]), r.text
    assert status_of(halted) == "active" and halted.events() == before and halted.endpoint.calls == []


@pytest.mark.parametrize("path", ROUTES)
def test_operator_text_with_an_unpaired_surrogate_changes_writes_and_sends_nothing(halted, path):
    before = halted.events()
    r = send(halted, path, {"operator": "CISO" + chr(0xD800), "reason": "incident"})
    assert r.status_code == 422, r.text
    assert any(e["loc"] == ["body", "operator"] for e in r.json()["detail"]), r.text
    assert status_of(halted) == "active" and halted.events() == before and halted.endpoint.calls == []


@pytest.mark.parametrize("path", ["/kill/agent-1", "/kill/domain/finance"])
def test_an_ordinary_reason_still_halts(halted, path):
    r = send(halted, path, {"operator": "CISO", "reason": "incident 42"})
    assert r.status_code == 200, r.text
    assert status_of(halted) == "killed" and len(halted.endpoint.calls) == 1
    assert unquote(halted.endpoint.calls[0]["headers"][REASON_HEADER]) == "incident 42"


def test_an_ordinary_reason_still_drills_and_revives(halted):
    body = {"operator": "CISO", "reason": "incident 42"}
    assert send(halted, "/drill/agent-1", body).status_code == 200
    assert send(halted, "/kill/agent-1", body).status_code == 200
    assert send(halted, "/revive/agent-1", body).status_code == 200
    assert status_of(halted) == "active"


def test_the_header_encoder_removes_line_breaks_on_its_own():
    """The request model refuses them first; the encoder does not depend on that."""
    evil = "a" + chr(13) + chr(10) + "x-injected: 1 " + "z" * 600
    encoded = _reason_header(evil)
    assert chr(13) not in encoded and chr(10) not in encoded and " " not in encoded and encoded.isascii()
    assert unquote(encoded) == evil[:REASON_HEADER_MAX]
