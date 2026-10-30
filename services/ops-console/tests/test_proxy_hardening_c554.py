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


def test_the_drill_500_report_is_still_relayed_because_the_page_reads_it(wire):
    report = {"total_ms": 55.0, "restored": False, "restored_status": 500, "kill_confirmed_ms": 40.0}
    wire.answer = lambda request: httpx.Response(500, json={"detail": report})
    r = TestClient(create_app()).post("/api/agents/a1/drill", json=BODY, headers=_pair())
    assert r.status_code == 500 and r.json() == {"detail": {"detail": report}}


def test_a_5xx_registry_or_ledger_read_does_not_relay_the_body_either(wire):
    wire.answer = lambda request: httpx.Response(500, json={"detail": f"boom {MARK}"})
    c = TestClient(create_app())
    for path in ("/api/events", "/api/agents/a1/manifest"):
        r = c.get(path)
        assert r.status_code == 500 and MARK not in r.text, path
