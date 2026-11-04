"""Scout S-2-17: `/api/events` and `/api/events/export` trusted a 200 ledger answer to be a list of event dicts. A dict body
(iterating its keys), a list holding a non-dict, or an event whose `payload` was a string, list or number raised
AttributeError, so the console answered 500 with the framework's body. Now: a 200 answer that is not a list of dicts is a
502 with a fixed text (no upstream body); an event with a non-dict payload still exports (empty clause_id, the payload as
JSON). The ledger really returns a list of dict events; this is the guard against a misbehaving or substituted upstream."""
from __future__ import annotations

import csv
import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from ops_console.api import create_app

MARK = "MARK-S217-body-FIELD_SHARED_SECRET=zz"
GOOD = {"ts": "2026-01-01T00:00:00Z", "event_id": "e1", "event_type": "conformance.block", "agent_id": "a1",
        "hash": "h1", "prev_hash": "h0", "payload": {"clause_id": "D.scope", "action": "x"}}


@pytest.fixture()
def wire(monkeypatch):
    class Wire:
        answer = staticmethod(lambda request: httpx.Response(200, json=[]))

    w = Wire()
    real = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(lambda request: w.answer(request))
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    return w


def ledger_says(wire, body):
    # content=, not json=: json=None would send an empty body, and JSON `null` is one of the shapes under test
    wire.answer = lambda request: httpx.Response(200, content=json.dumps(body).encode(),
                                                 headers={"content-type": "application/json"})
    return TestClient(create_app())


def rows_of(r):
    return list(csv.reader(io.StringIO(r.text)))


WRONG_SHAPES = [
    {"detail": MARK, "events": [GOOD]},        # a dict (iterating it yields its keys)
    {MARK: 1},
    [1, "x"],
    ["only-a-string-" + MARK],
    [GOOD, 5],                                  # one good row does not excuse a bad one
    [GOOD, None],
    [[GOOD]],
    "just a string " + MARK,
    5,
    None,
    True,
]
IDS = ["dict-with-events", "dict-key", "ints-and-strings", "string-row", "good-then-int", "good-then-null", "nested-list",
       "string", "number", "null", "bool"]


@pytest.mark.parametrize("path", ["/api/events", "/api/events/export", "/api/events/export?format=json"])
@pytest.mark.parametrize("body", WRONG_SHAPES, ids=IDS)
def test_a_200_ledger_answer_of_the_wrong_shape_is_a_502_with_a_fixed_text(wire, path, body):
    r = ledger_says(wire, body).get(path)
    assert r.status_code == 502, (r.status_code, r.text)
    assert MARK not in r.text and "Traceback" not in r.text
    assert r.json() == {"detail": {"message": "ledger answered an unexpected shape", "status": 200}}


# ---- an event with a payload that is not a dict still exports ---------------------------------------------------------

@pytest.mark.parametrize("payload", ["abc", [1, "a"], 7, 1.5, True, [], None, {}])
def test_an_event_with_a_non_dict_payload_exports_as_csv_with_an_empty_clause_id(wire, payload):
    event = {**GOOD, "payload": payload}
    r = ledger_says(wire, [event]).get("/api/events/export")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    header, row = rows_of(r)
    assert header == ["ts", "event_id", "event_type", "agent_id", "clause_id", "hash", "prev_hash", "payload_json"]
    assert row[4] == ""                                          # clause_id
    shown = payload if payload else {}                           # the existing rule: a falsy payload shows as {}
    assert row[7] == json.dumps(shown, sort_keys=True)


@pytest.mark.parametrize("payload", ["abc", [1, "a"], 7, None])
def test_the_same_events_pass_through_the_json_export_and_the_events_route(wire, payload):
    event = {**GOOD, "payload": payload}
    c = ledger_says(wire, [event])
    assert c.get("/api/events").json() == [event]
    body = c.get("/api/events/export?format=json").json()
    assert body["count"] == 1 and body["events"] == [event]


# ---- well-formed answers are unchanged ----------------------------------------------------------------------------------

def test_a_well_formed_answer_exports_exactly_as_before(wire):
    r = ledger_says(wire, [GOOD, {**GOOD, "event_id": "e2", "payload": {"note": "n"}}]).get("/api/events/export")
    _, a, b = rows_of(r)
    assert a[4] == "D.scope" and b[4] == ""
    assert json.loads(a[7]) == GOOD["payload"]


def test_an_empty_ledger_answer_is_an_empty_export_not_an_error(wire):
    c = ledger_says(wire, [])
    assert c.get("/api/events").json() == []
    assert len(rows_of(c.get("/api/events/export"))) == 1       # the header only
    assert c.get("/api/events/export?format=json").json()["count"] == 0


@pytest.mark.parametrize("lead", ["=", "+", "-", "@"])
def test_the_csv_formula_neutralisation_is_untouched(wire, lead):
    event = {**GOOD, "agent_id": f"{lead}cmd|calc"}
    _, row = rows_of(ledger_says(wire, [event]).get("/api/events/export"))
    assert row[3] == "'" + f"{lead}cmd|calc"


def test_a_ledger_error_status_still_relays_as_before(wire):
    wire.answer = lambda request: httpx.Response(503, json={"detail": MARK})
    r = TestClient(create_app()).get("/api/events")
    assert r.status_code == 503 and MARK not in r.text
