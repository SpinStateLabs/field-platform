"""S8-26 — GET /api/events and /api/events/export with a ledger 200 of the wrong shape (not a list, a row
that is not an object, an event whose payload is not an object) answer a fixed 502, never a 500 and
never a short or mangled export. The ledger's text is not echoed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ops_console.api import ServiceClient, create_app

LEAK = "LEDGER-TEXT-MUST-NOT-LEAK"
GOOD = {"ts": "2026-01-01T00:00:00Z", "event_id": "e1", "event_type": "x.y", "agent_id": "a1",
        "payload": {"clause_id": "D.scope", "k": 1}, "hash": "h", "prev_hash": "p"}


class Stub:
    def __init__(self, body, status=200):
        self.body, self.status = body, status

    def _answer(self, path, kw):
        class R:
            status_code = self.status

            def json(_):  # noqa: N805
                return self.body

        return R()

    def get(self, path, **kw):
        return self._answer(path, kw)

    post = get


def console(body, status=200) -> TestClient:
    ledger = ServiceClient(client=Stub(body, status), base_url="http://t")
    other = {k: ServiceClient(client=Stub({}), base_url="http://t") for k in (
        "registry", "delegation", "governor", "killswitch", "sentinel", "lifecycle", "attest",
        "crosswalk", "federation", "replay", "gateway")}
    return TestClient(create_app(ledger=ledger, **other), raise_server_exceptions=False)


BAD = [
    ("dict", {"events": LEAK}),
    ("null", None),
    ("string", LEAK),
    ("number", 5),
    ("list-of-strings", [LEAK]),
    ("list-of-numbers", [1, 2]),
    ("list-with-null", [GOOD, None]),
    ("list-in-list", [[GOOD]]),
    ("payload-string", [{**GOOD, "payload": LEAK}]),
    ("payload-list", [{**GOOD, "payload": [LEAK]}]),
    ("payload-number", [{**GOOD, "payload": 5}]),
]
ROUTES = [("/api/events", {}), ("/api/events/export", {"format": "csv"}), ("/api/events/export", {"format": "json"})]


@pytest.mark.parametrize("label, body", BAD, ids=[b[0] for b in BAD])
@pytest.mark.parametrize("path, params", ROUTES, ids=["events", "export-csv", "export-json"])
def test_a_wrong_shaped_ledger_answer_is_a_fixed_502(label, body, path, params):
    r = console(body).get(path, params=params)
    assert r.status_code == 502, (label, r.status_code, r.text)
    assert "unexpected shape" in r.text
    assert LEAK not in r.text


@pytest.mark.parametrize("path, params", ROUTES, ids=["events", "export-csv", "export-json"])
def test_good_answers_and_the_existing_edge_cases_are_unchanged(path, params):
    for body in ([], [GOOD], [{**GOOD, "payload": None}], [{**GOOD}, {k: v for k, v in GOOD.items() if k != "payload"}]):
        r = console(body).get(path, params=params)
        assert r.status_code == 200, (body, r.text)


def test_the_csv_and_json_exports_of_a_good_answer_have_the_rows():
    csv_r = console([GOOD, GOOD]).get("/api/events/export", params={"format": "csv"})
    assert csv_r.text.count("\n") == 3 and "D.scope" in csv_r.text
    js = console([GOOD, GOOD]).get("/api/events/export", params={"format": "json"}).json()
    assert js["count"] == 2 and len(js["events"]) == 2


@pytest.mark.parametrize("status", [404, 500, 502, 503])
def test_an_upstream_error_status_keeps_its_existing_mapping(status):
    r = console({"detail": "x"}, status=status).get("/api/events/export")
    assert r.status_code >= 400 and r.status_code != 200
