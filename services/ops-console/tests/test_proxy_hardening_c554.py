"""C-554 (reviewer C-523 F-C523-1/-2/-3): the console's proxy of guarded writes.

* every path parameter reaches the upstream as ONE percent-encoded segment (an encoded ``?``, ``#``, ``/`` or ``..``
  cannot become a query, a fragment, another path or a collapsed one);
* a half operator pair (only the id, only the key) forwards nothing under OFF and is a 401 under ENFORCE;
* a 5xx body from an upstream is not relayed to the caller (a fixed text), a 4xx body still is, and the drill's
  structured 500 report (C-19) still is.

The app is built for real: every upstream client is the console's own httpx client talking to a recording transport.
Keys are made up per run and never printed.
"""
from __future__ import annotations

import secrets

import httpx
import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from ops_console.api import create_app

BODY = {"operator": "Don", "reason": "c554"}
MARK = "MARK-C554-env-line-FIELD_SHARED_SECRET=zz"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, "FIELD_OPERATOR_KEY_FILE"):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def wire(monkeypatch):
    """Every httpx.Client built from here on talks to a recording transport; ``wire.answer`` decides the reply."""
    class Wire:
        seen: list[httpx.Request] = []
        answer = staticmethod(lambda request: httpx.Response(200, json={"ok": True}))

    w = Wire()
    w.seen = []
    real = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        w.seen.append(request)
        return w.answer(request)

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    return w


def _pair():
    return {oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: secrets.token_urlsafe(18)}


GUARDED = [
    ("/api/agents/{i}/kill", "/kill/{e}", BODY),
    ("/api/agents/{i}/revive", "/revive/{e}", BODY),
    ("/api/agents/{i}/drill", "/drill/{e}", BODY),
    ("/api/tokens/{i}/revoke", "/tokens/{e}/revoke", None),
    ("/api/escalations/{i}/resolve", "/escalations/{e}/resolve", {"resolved_by": "Don"}),
]
IDS = [
    ("a%3Fforce%3D1", "a%3Fforce%3D1"),     # an encoded ? stays inside the segment (no query)
    ("a%23frag", "a%23frag"),               # an encoded # is not a dropped fragment
    ("%2e%2e", "%2E%2E"),                   # .. does not collapse the upstream path
    ("plain-id_1", "plain-id_1"),           # an ordinary id is unchanged
]


@pytest.mark.parametrize("route,upstream,body", GUARDED, ids=[g[1].split("/")[1] for g in GUARDED])
@pytest.mark.parametrize("sent,want", IDS)
def test_a_path_parameter_reaches_the_upstream_as_one_encoded_segment(wire, route, upstream, body, sent, want):
    c = TestClient(create_app())
    r = c.post(route.format(i=sent), json=body, headers=_pair())
    assert r.status_code in (200, 201), r.text
    (req,) = [q for q in wire.seen if q.method == "POST"]
    assert req.url.raw_path.decode() == upstream.format(e=want), req.url.raw_path
    assert req.url.query == b""


def test_an_encoded_slash_in_an_id_never_reaches_the_handler_or_the_upstream(wire):
    # the router decodes %2F before matching, so the route does not match at all: nothing is sent upstream
    r = TestClient(create_app()).post("/api/agents/a%2Fb/kill", json=BODY, headers=_pair())
    assert r.status_code == 404 and wire.seen == []


# ---- F-C523-2: a half pair ------------------------------------------------------------------------------------------

HALF = [{oa.HEADER_OPERATOR: "don"}, {oa.HEADER_KEY: "k-" + secrets.token_urlsafe(12)}]


@pytest.mark.parametrize("half", HALF, ids=["id-only", "key-only"])
def test_a_half_pair_forwards_nothing_when_the_mode_is_off(wire, half):
    r = TestClient(create_app()).post("/api/agents/a1/kill", json=BODY, headers=half)
    assert r.status_code == 200, r.text
    (req,) = [q for q in wire.seen if q.method == "POST"]
    assert not {k.lower() for k in req.headers} & {oa.HEADER_OPERATOR, oa.HEADER_KEY}


@pytest.mark.parametrize("half", HALF, ids=["id-only", "key-only"])
def test_a_half_pair_is_a_401_when_the_mode_is_enforce(wire, monkeypatch, half):
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    r = TestClient(create_app()).post("/api/agents/a1/kill", json=BODY, headers=half)
    assert r.status_code == 401, r.text
    # the refusal itself is ledgered (C-16, POST /events); nothing is sent to the kill-switch
    assert [q for q in wire.seen if q.url.path.startswith("/kill")] == []


def test_a_full_pair_is_still_forwarded_whole(wire):
    h = _pair()
    TestClient(create_app()).post("/api/agents/a1/kill", json=BODY, headers=h)
    (req,) = [q for q in wire.seen if q.method == "POST"]
    assert req.headers[oa.HEADER_OPERATOR] == "don" and req.headers[oa.HEADER_KEY] == h[oa.HEADER_KEY]


# ---- F-C523-3: upstream error bodies ------------------------------------------------------------------------------

@pytest.mark.parametrize("route,body", [(g[0].format(i="a1"), g[2]) for g in GUARDED if "drill" not in g[0]])
@pytest.mark.parametrize("status", [500, 502, 503])
def test_a_5xx_body_from_an_upstream_is_not_relayed(wire, route, body, status):
    wire.answer = lambda request: httpx.Response(status, json={"detail": f"Traceback ... {MARK}"})
    r = TestClient(create_app()).post(route, json=body, headers=_pair())
    assert r.status_code == status, r.text
    assert MARK not in r.text and "Traceback" not in r.text
    assert r.json() == {"detail": {"message": "upstream error", "status": status}}


def test_a_4xx_body_from_an_upstream_is_still_relayed(wire):
    wire.answer = lambda request: httpx.Response(409, json={"detail": "already killed"})
    r = TestClient(create_app()).post("/api/agents/a1/kill", json=BODY, headers=_pair())
    assert r.status_code == 409 and r.json() == {"detail": {"detail": "already killed"}}


def test_the_drill_500_relays_only_the_report_fields_the_page_reads(wire):
    report = {"agent_id": "a1", "total_ms": 55.0, "restored": False, "restored_status": "<restore failed>",
              "kill_confirmed_ms": 40.0, "heartbeat_confirmed_ms": 41.0,
              "note": f"Traceback ... {MARK}", "endpoint_result": {"detail": MARK}}
    wire.answer = lambda request: httpx.Response(500, json={"detail": report})
    r = TestClient(create_app()).post("/api/agents/a1/drill", json=BODY, headers=_pair())
    want = {k: report[k] for k in ("agent_id", "total_ms", "restored", "restored_status", "kill_confirmed_ms",
                                   "heartbeat_confirmed_ms")}
    assert r.status_code == 500 and r.json() == {"detail": {"detail": want}}, r.text
    assert MARK not in r.text and "Traceback" not in r.text


def test_a_drill_500_that_is_not_a_report_is_a_fixed_text(wire):
    wire.answer = lambda request: httpx.Response(500, json={"detail": f"Traceback ... {MARK}"})
    r = TestClient(create_app()).post("/api/agents/a1/drill", json=BODY, headers=_pair())
    assert r.status_code == 500 and MARK not in r.text
    assert r.json() == {"detail": {"message": "upstream error", "status": 500}}


def test_a_5xx_registry_or_ledger_read_does_not_relay_the_body_either(wire):
    wire.answer = lambda request: httpx.Response(500, json={"detail": f"boom {MARK}"})
    c = TestClient(create_app())
    for path in ("/api/events", "/api/agents/a1/manifest"):
        r = c.get(path)
        assert r.status_code == 500 and MARK not in r.text, path


# ---- C-651 F-C651-1: every other path that put an upstream body in the answer -----------------------------------------

def _all_5xx(wire, status=503):
    wire.answer = lambda request: httpx.Response(status, json={"detail": f"Traceback ... {MARK}"})


@pytest.mark.parametrize("path", ["/api/overview", "/api/platform", "/api/agents/a1"])
def test_a_5xx_upstream_body_is_not_in_a_section_error(wire, path):
    _all_5xx(wire)
    r = TestClient(create_app()).get(path)
    assert r.status_code == 200, r.text
    assert MARK not in r.text and "Traceback" not in r.text, path
    assert "status 503: upstream error" in r.text, path


def test_a_4xx_upstream_body_is_still_in_a_section_error(wire):
    wire.answer = lambda request: httpx.Response(404, json={"detail": "no such thing"})
    r = TestClient(create_app()).get("/api/overview")
    assert "status 404: {'detail': 'no such thing'}" in r.text


def test_an_unreachable_upstream_keeps_its_exception_text_in_a_section_error(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("no route to upstream")

    class T(httpx.BaseTransport):
        def handle_request(self, request):
            boom()

    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: real(*a, **{**k, "transport": T()}))
    r = TestClient(create_app()).get("/api/overview")
    assert "no route to upstream" in r.text and "status 0" not in r.text


def test_a_5xx_body_is_not_in_a_fleet_halt_row_or_the_registry_unavailable_message(wire):
    _all_5xx(wire, 500)
    c = TestClient(create_app())
    r = c.post("/api/fleet/halt", json={"domains": ["finance"], "confirm": "HALT", **BODY}, headers=_pair())
    assert r.status_code == 200 and MARK not in r.text and "Traceback" not in r.text, r.text
    row = r.json()["results"][0]
    assert row["ok"] is False and row["status"] == 500
    assert row["error"] == {"message": "upstream error", "status": 500}
    r = c.post("/api/fleet/halt", json={"confirm": "HALT", **BODY}, headers=_pair())       # registry unavailable: 502
    assert r.status_code == 502 and MARK not in r.text and "status 500: upstream error" in r.text, r.text


@pytest.mark.parametrize("action", ["kill", "revive", "drill"])
def test_a_5xx_body_is_not_in_a_bulk_row(wire, action):
    _all_5xx(wire, 500)
    r = TestClient(create_app()).post("/api/agents/bulk", json={"agent_ids": ["a1"], "action": action, **BODY},
                                      headers=_pair())
    assert r.status_code == 200 and MARK not in r.text and "Traceback" not in r.text, r.text
    row = r.json()["results"][0]
    assert row["ok"] is False and row["error"] == {"message": "upstream error", "status": 500}


def test_a_bulk_drill_row_keeps_only_the_report_fields(wire):
    report = {"agent_id": "a1", "total_ms": 5.0, "restored": False, "restored_status": "<restore failed>",
              "kill_confirmed_ms": 4.0, "heartbeat_confirmed_ms": 4.5, "note": f"Traceback {MARK}"}
    wire.answer = lambda request: httpx.Response(500, json={"detail": report})
    r = TestClient(create_app()).post("/api/agents/bulk", json={"agent_ids": ["a1"], "action": "drill", **BODY},
                                      headers=_pair())
    row = r.json()["results"][0]
    assert MARK not in r.text and row["error"]["detail"]["restored"] is False and "note" not in row["error"]["detail"]


# ---- C-651 F-C651-2: the three encodings that were not pinned ---------------------------------------------------------

@pytest.mark.parametrize("sent,want", [("a?b", "a%3Fb"), ("a#b", "a%23b"), ("..", "%2E%2E"), ("plain", "plain")])
def test_the_domain_path_of_a_fleet_halt_is_one_encoded_segment(wire, sent, want):
    TestClient(create_app()).post("/api/fleet/halt", json={"domains": [sent], "confirm": "HALT", **BODY},
                                  headers=_pair())
    (req,) = [q for q in wire.seen if q.method == "POST"]
    assert req.url.raw_path.decode() == f"/kill/domain/{want}" and req.url.query == b""


@pytest.mark.parametrize("sent,want", [("a?b", "a%3Fb"), ("a#b", "a%23b"), ("..", "%2E%2E"), ("plain", "plain")])
def test_the_per_agent_path_of_a_bulk_action_is_one_encoded_segment(wire, sent, want):
    TestClient(create_app()).post("/api/agents/bulk", json={"agent_ids": [sent], "action": "kill", **BODY},
                                  headers=_pair())
    (req,) = [q for q in wire.seen if q.method == "POST"]
    assert req.url.raw_path.decode() == f"/kill/{want}" and req.url.query == b""


@pytest.mark.parametrize("sent,want", [("a%3Fb", "a%3Fb"), ("a%23b", "a%23b"), ("%2e%2e", "%2E%2E"), ("plain", "plain")])
def test_the_registry_path_of_the_manifest_read_is_one_encoded_segment(wire, sent, want):
    TestClient(create_app()).get(f"/api/agents/{sent}/manifest")
    reads = [q for q in wire.seen if q.method == "GET" and q.url.path.startswith("/agents/")]
    assert reads and reads[0].url.raw_path.decode() == f"/agents/{want}" and reads[0].url.query == b""


# ---- C-644 F-C644-2 / -3 / -4 ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("sent,want", [("../revive/x", "..%2Frevive%2Fx"), ("a/b", "a%2Fb"), ("a:b", "a%3Ab"),
                                       ("user@corp", "user%40corp"), ("a.b", "a.b"), ("fin ance", "fin%20ance")])
def test_a_slash_or_odd_character_in_a_bulk_id_or_a_halt_domain_stays_inside_one_segment(wire, sent, want):
    c = TestClient(create_app())
    c.post("/api/agents/bulk", json={"agent_ids": [sent], "action": "kill", **BODY}, headers=_pair())
    c.post("/api/fleet/halt", json={"domains": [sent], "confirm": "HALT", **BODY}, headers=_pair())
    paths = [q.url.raw_path.decode() for q in wire.seen if q.method == "POST"]
    assert paths == [f"/kill/{want}", f"/kill/domain/{want}"], paths


@pytest.mark.parametrize("sent,want", [("a%3Fb", "a%3Fb"), ("a%23b", "a%23b"), ("a.b", "a.b"), ("%2e%2e", "%2E%2E")])
def test_the_registry_read_of_the_agent_detail_is_one_encoded_segment(wire, sent, want):
    TestClient(create_app()).get(f"/api/agents/{sent}")
    reads = [q for q in wire.seen if q.method == "GET" and q.url.path.startswith("/agents/")]
    assert reads and reads[0].url.raw_path.decode() == f"/agents/{want}", [q.url.raw_path for q in wire.seen]


def test_a_dotted_id_stays_literal_for_a_real_kill(wire):
    TestClient(create_app()).post("/api/agents/a.b/kill", json=BODY, headers=_pair())
    (req,) = [q for q in wire.seen if q.method == "POST"]
    assert req.url.raw_path.decode() == "/kill/a.b"


def test_a_non_json_upstream_answer_keeps_its_status_and_shows_a_fixed_text(wire):
    wire.answer = lambda request: httpx.Response(503, text=f"<html>proxy error {MARK}</html>",
                                                 headers={"content-type": "text/html"})
    c = TestClient(create_app())
    r = c.post("/api/agents/a1/kill", json=BODY, headers=_pair())
    assert r.status_code == 503 and MARK not in r.text, r.text            # was a 502 with the JSON parse message
    wire.answer = lambda request: httpx.Response(403, text=f"<html>forbidden {MARK}</html>")
    r = c.post("/api/agents/a1/kill", json=BODY, headers=_pair())
    assert r.status_code == 403 and MARK not in r.text and r.json() == {"detail": {"detail": "non-JSON answer"}}


def test_a_2xx_that_is_not_json_is_still_an_error(wire):
    wire.answer = lambda request: httpx.Response(200, text="not json")
    r = TestClient(create_app()).post("/api/agents/a1/kill", json=BODY, headers=_pair())
    assert r.status_code == 502
