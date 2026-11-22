"""B-S11-31: POST /api/check bounds agent_id, action and token_id before anything is forwarded to the sentinel."""

import httpx
import pytest
from fastapi.testclient import TestClient

from ops_console.api import create_app


@pytest.fixture()
def wire(monkeypatch):
    seen: list[httpx.Request] = []
    real = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    return seen


def _post(body):
    return TestClient(create_app()).post("/api/check", json=body)


@pytest.mark.parametrize("body", [
    {"agent_id": "a" * 129, "action": "x"},                 # oversized id
    {"agent_id": "Not Registry", "action": "x"},            # not the registry grammar
    {"agent_id": "domain/x", "action": "x"},
    {"agent_id": "a1", "action": "x" * 501},                # oversized action
    {"agent_id": "a1", "action": "line1\nline2"},           # multi-line
    {"agent_id": "a1", "action": "bell\x07"},               # control character
    {"agent_id": "a1", "action": "   "},                    # blank after strip
    {"agent_id": "a1", "action": "x", "token_id": "t" * 300},
    {"agent_id": "a1", "action": "x", "token_id": "t\r\nu"},
])
def test_a_bad_check_body_is_a_422_and_nothing_reaches_the_sentinel(wire, body):
    r = _post(body)
    assert r.status_code == 422, r.text
    assert wire == []


# reviewer C1 on #1246: every character class that starts a new line in a viewer or terminal, inside the text (a trailing one
# would be removed by the strip of `action`, which is fine)
@pytest.mark.parametrize("ch", ["", " ", " ", "", "", "", "", ""],
                         ids=["NEL", "LINE-SEPARATOR", "PARAGRAPH-SEPARATOR", "C1-first", "C1-CSI", "C1-last", "ESC", "DEL"])
@pytest.mark.parametrize("field", ["action", "token_id"])
def test_a_line_breaking_or_control_character_is_a_422(wire, ch, field):
    body = {"agent_id": "a1", "action": "pay", "token_id": "tok_1"}
    body[field] = "a" + ch + "b"
    r = _post(body)
    assert r.status_code == 422, (field, repr(ch), r.text)
    assert wire == []


def test_printable_non_ascii_still_passes(wire):
    assert _post({"agent_id": "a1", "action": "payer la facture n° 42 — été"}).status_code == 200


def test_a_normal_body_is_forwarded_unchanged_and_action_is_stripped(wire):
    r = _post({"agent_id": "invoicing-agent", "action": "  pay invoice 42  ", "token_id": "tok_1",
               "irreversible": True})
    assert r.status_code == 200, r.text
    (req,) = wire
    import json
    assert json.loads(req.content) == {"agent_id": "invoicing-agent", "action": "pay invoice 42",
                                        "token_id": "tok_1", "irreversible": True}
