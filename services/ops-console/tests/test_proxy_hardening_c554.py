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


@pytest.mark.parametrize("path", ["/api/overview", "/api/platform", "/api/agents/a1"])
def test_a_4xx_upstream_body_is_not_in_a_section_error_either(wire, path):
    # C-763 F-C763-1: a read shows the status and a fixed text; a validation error can echo what the caller sent
    wire.answer = lambda request: httpx.Response(422, json={"detail": [{"input": MARK, "msg": "bad"}]})
    r = TestClient(create_app()).get(path)
    assert MARK not in r.text and "status 422: upstream refused" in r.text, path


@pytest.mark.parametrize("path", ["/api/events", "/api/agents/a1/manifest"])
def test_a_4xx_upstream_body_is_not_in_a_read_route_error(wire, path):
    wire.answer = lambda request: httpx.Response(404, json={"detail": f"no such {MARK}"})
    r = TestClient(create_app()).get(path)
    assert r.status_code == 404 and MARK not in r.text
    assert r.json() == {"detail": {"message": "upstream refused", "status": 404}}


def test_the_lifecycle_404_detail_is_not_relayed(wire):
    wire.answer = lambda request: (httpx.Response(404, json={"detail": f"no sweep {MARK}"})
                                   if request.url.path == "/findings" else httpx.Response(200, json={}))
    r = TestClient(create_app()).get("/api/platform").json()
    assert r["lifecycle"]["available"] is True and r["lifecycle"]["data"] == {"no_sweep_yet": True}
    assert MARK not in str(r)


@pytest.mark.parametrize("route,body", [("/api/agents/a1/kill", BODY), ("/api/tokens/t1/revoke", None)])
def test_a_write_route_still_relays_the_4xx_refusal_the_operator_acts_on(wire, route, body):
    # the stated policy, pinned: a refusal from the service the operator addressed is shown whole
    wire.answer = lambda request: httpx.Response(409, json={"detail": "already done"})
    r = TestClient(create_app()).post(route, json=body, headers=_pair())
    assert r.status_code == 409 and r.json() == {"detail": {"detail": "already done"}}


def test_the_section_source_names_the_call_and_never_the_base_url(wire):
    wire.answer = lambda request: httpx.Response(200, json=[] if request.url.path in ("/agents", "/events") else {"ok": True})
    c = TestClient(create_app())
    o = c.get("/api/overview").json()
    p = c.get("/api/platform").json()
    srcs = [v["source"] for v in o.values() if isinstance(v, dict) and "source" in v]
    srcs += [v["source"] for v in p["health"].values()] + [p[k]["source"] for k in ("lifecycle", "federation", "crosswalk")]
    assert srcs and all(x.startswith("GET /") and "://" not in x and "127.0.0.1" not in x for x in srcs), srcs
    exp = c.get("/api/events/export?format=json").json()
    assert exp["source"] == "GET /events"


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


@pytest.mark.parametrize("sent", ["plain", "a.b", "a-1_x", "9z"])
def test_the_per_agent_path_of_a_bulk_action_is_the_registry_id_unchanged(wire, sent):
    TestClient(create_app()).post("/api/agents/bulk", json={"agent_ids": [sent], "action": "kill", **BODY},
                                  headers=_pair())
    (req,) = [q for q in wire.seen if q.method == "POST"]
    assert req.url.raw_path.decode() == f"/kill/{sent}" and req.url.query == b""


@pytest.mark.parametrize("sent,want", [("a%3Fb", "a%3Fb"), ("a%23b", "a%23b"), ("%2e%2e", "%2E%2E"), ("plain", "plain")])
def test_the_registry_path_of_the_manifest_read_is_one_encoded_segment(wire, sent, want):
    TestClient(create_app()).get(f"/api/agents/{sent}/manifest")
    reads = [q for q in wire.seen if q.method == "GET" and q.url.path.startswith("/agents/")]
    assert reads and reads[0].url.raw_path.decode() == f"/agents/{want}" and reads[0].url.query == b""


# ---- C-644 F-C644-2 / -3 / -4 ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("sent,want", [("a:b", "a%3Ab"), ("user@corp", "user%40corp"), ("a.b", "a.b"),
                                       ("fin ance", "fin%20ance"), ("a?b", "a%3Fb"), ("..", "%2E%2E"), (".", "%2E")])
def test_an_odd_character_in_a_halt_domain_stays_inside_one_segment(wire, sent, want):
    TestClient(create_app()).post("/api/fleet/halt", json={"domains": [sent], "confirm": "HALT", **BODY},
                                  headers=_pair())
    (req,) = [q for q in wire.seen if q.method == "POST"]
    assert req.url.raw_path.decode() == f"/kill/domain/{want}", req.url.raw_path


# ---- C-936 F-C936-1: the upstream DECODES an encoded slash, so the console must not send one ------------------------

@pytest.fixture()
def decoding_upstream(monkeypatch):
    """A Starlette app with the kill-switch's two kill routes (same templates and order); every console upstream call
    goes to it through real routing, which decodes the path. ``matched`` records which route answered."""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    matched: list[tuple[str, str]] = []

    async def kill_agent(request):
        matched.append(("agent", request.path_params["agent_id"]))
        return JSONResponse({"ok": True})

    async def kill_domain(request):
        matched.append(("domain", request.path_params["domain"]))
        return JSONResponse({"ok": True, "results": []})

    up = TestClient(Starlette(routes=[Route("/kill/{agent_id}", kill_agent, methods=["POST"]),
                                      Route("/kill/domain/{domain}", kill_domain, methods=["POST"])]))
    real = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        r = up.request(request.method, request.url.raw_path.decode(), content=request.content)
        return httpx.Response(r.status_code, content=r.content)

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)}))
    return matched


def test_the_premise_the_upstream_decodes_an_encoded_slash(decoding_upstream):
    c = httpx.Client(base_url="http://x")                                # httpx.Client is patched: goes to the app
    c.post("/kill/domain%2Ffin", json={})
    assert decoding_upstream == [("domain", "fin")]


@pytest.mark.parametrize("bad", ["domain/fin", "../revive/x", "a/b", "", "A1", "a b", "a?b", "a#b", "..", ".", "-a", "é"])
def test_a_bulk_id_that_is_not_a_registry_id_is_a_422_and_reaches_no_route(decoding_upstream, bad):
    r = TestClient(create_app()).post("/api/agents/bulk", json={"agent_ids": ["a1", bad], "action": "kill", **BODY},
                                      headers=_pair())
    assert r.status_code == 422, r.text
    assert decoding_upstream == []                       # not even the valid id beside it: the whole request is refused


@pytest.mark.parametrize("bad", ["a/b", "domain/fin", "../x", ""])
def test_a_halt_domain_with_a_slash_or_empty_is_a_422_and_reaches_no_route(decoding_upstream, bad):
    r = TestClient(create_app()).post("/api/fleet/halt", json={"domains": ["finance", bad], "confirm": "HALT", **BODY},
                                      headers=_pair())
    assert r.status_code == 422, r.text
    assert decoding_upstream == []


def test_a_good_bulk_id_reaches_the_agent_route_and_a_good_domain_the_domain_route(decoding_upstream):
    c = TestClient(create_app())
    c.post("/api/agents/bulk", json={"agent_ids": ["fin-1"], "action": "kill", **BODY}, headers=_pair())
    c.post("/api/fleet/halt", json={"domains": ["fin ance"], "confirm": "HALT", **BODY}, headers=_pair())
    assert decoding_upstream == [("agent", "fin-1"), ("domain", "fin ance")]


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


# ---- C-936 F-C936-2 / -3 / -5 / -6 ----------------------------------------------------------------------------------

def test_a_5xx_body_is_not_logged_at_any_level(wire, caplog):
    caplog.set_level("DEBUG")
    _all_5xx(wire, 503)
    TestClient(create_app()).post("/api/agents/a1/kill", json=BODY, headers=_pair())
    TestClient(create_app()).get("/api/overview")
    assert MARK not in caplog.text and "Traceback" not in caplog.text
    assert "upstream answered 503" in caplog.text                    # the status is


def test_a_halt_row_error_text_is_the_kill_switch_line_cut_to_200_characters(wire):
    long = "502: " + "x" * 500 + MARK
    wire.answer = lambda request: httpx.Response(500, json={"detail": {"results": [
        {"agent_id": "a1", "outcome": "error", "error": long}]}})
    r = TestClient(create_app()).post("/api/fleet/halt", json={"domains": ["finance"], "confirm": "HALT", **BODY},
                                      headers=_pair())
    err = r.json()["results"][0]["errors"][0]["error"]
    assert err == long[:200] and MARK not in r.text                  # C-19 exception, capped


def test_the_drill_restored_status_is_cut_to_64_characters(wire):
    rep = {"agent_id": "a1", "total_ms": 1.0, "restored": False, "restored_status": "s" * 300,
           "kill_confirmed_ms": 1.0, "heartbeat_confirmed_ms": 1.0}
    wire.answer = lambda request: httpx.Response(500, json={"detail": rep})
    r = TestClient(create_app()).post("/api/agents/a1/drill", json=BODY, headers=_pair())
    assert r.json()["detail"]["detail"]["restored_status"] == "s" * 64


def test_a_single_dot_id_is_encoded_not_dropped_by_the_client(wire):
    TestClient(create_app()).post("/api/agents/./kill", json=BODY, headers=_pair())
    reqs = [q for q in wire.seen if q.method == "POST"]
    assert all(q.url.raw_path.decode() != "/kill/" for q in reqs)
    c = TestClient(create_app())
    wire.seen.clear()
    c.post("/api/fleet/halt", json={"domains": ["."], "confirm": "HALT", **BODY}, headers=_pair())
    (req,) = [q for q in wire.seen if q.method == "POST"]
    assert req.url.raw_path.decode() == "/kill/domain/%2E"


def test_the_dry_run_check_carries_no_operator_pair(wire):
    r = TestClient(create_app()).post("/api/check", json={"agent_id": "a1", "action": "x"}, headers=_pair())
    reqs = [q for q in wire.seen if q.method == "POST"]
    assert reqs, r.text
    for q in reqs:
        assert not {k.lower() for k in q.headers} & {oa.HEADER_OPERATOR, oa.HEADER_KEY}


@pytest.mark.parametrize("status", [301, 302, 307])
def test_an_upstream_redirect_is_a_502_with_no_location(wire, status):
    wire.answer = lambda request: httpx.Response(status, json={"detail": MARK}, headers={"location": "http://elsewhere/"})
    c = TestClient(create_app())
    r = c.post("/api/agents/a1/kill", json=BODY, headers=_pair())
    assert r.status_code == 502 and MARK not in r.text and "location" not in {k.lower() for k in r.headers}
    r = c.get("/api/events")
    assert r.status_code == 502 and MARK not in r.text
