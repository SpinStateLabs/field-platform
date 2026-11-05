"""S2-23: an unreachable registry, ledger or delegation, or one malformed token, must not be an unhandled 500.

Mid-incident the replay is the thing asked for. A registry failure degrades the report (named, never "unregistered");
a ledger or delegation failure is a 502 naming only the dependency (without ledger events there is no post-mortem);
one unreadable token record is skipped and counted, the rest is built. No upstream body ever reaches the answer."""

import httpx
import pytest
from fastapi.testclient import TestClient

from field_core.clients import RegistryClient
from incident_replay.api import create_app
from incident_replay.engine import LedgerQueryClient, ReplayEngine, TokenQueryClient

WINDOW = {"since": "2020-01-01T00:00:00+00:00", "until": "2030-01-01T00:00:00+00:00"}
BODY = {"agent_id": "a1", **WINDOW}
LEAK = "UPSTREAM-SECRET-BODY-xyz"
GOOD_TOKEN = {"token_id": "t-good", "granted_by": "Controller", "scope": ["draft"], "revoked": False,
              "issued_at": "2026-01-01T00:00:00+00:00", "expires_at": "2029-01-01T00:00:00+00:00"}
RECORD = {"agent_id": "a1", "name": "A One", "owner": "AP Lead", "domain": "finance", "status": "active"}


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok(payload):
    return lambda request: httpx.Response(200, json=payload)


def _boom(status=500):
    return lambda request: httpx.Response(status, text=LEAK)


def _down(request):
    raise httpx.ConnectError(LEAK)


def served(*, registry=None, verify=None, events=None, tokens=None):
    def ledger(request):
        if request.url.path == "/verify":
            return (verify or _ok({"ok": True, "length": 0}))(request)
        if request.url.path == "/events":
            return (events or _ok([]))(request)
        return httpx.Response(200, json={})
    engine = ReplayEngine(
        ledger=LedgerQueryClient(client=_client(ledger), base_url="http://l"),
        registry=RegistryClient(client=_client(registry or _ok(RECORD)), base_url="http://r"),
        delegation=TokenQueryClient(client=_client(tokens or _ok([GOOD_TOKEN])), base_url="http://d"),
    )
    return TestClient(create_app(engine=engine), raise_server_exceptions=False)


@pytest.mark.parametrize("registry", [_down, _boom(500), _boom(503)], ids=["transport", "500", "503"])
def test_an_unreachable_registry_degrades_the_report_and_is_not_called_unregistered(registry):
    r = served(registry=registry).post("/replay", json=BODY)
    assert r.status_code == 200
    pm = r.json()
    assert pm["raci"]["Responsible"] == "<registry unreachable>"
    assert any("registry unreachable" in n for n in pm["integrity_notes"])
    assert "unregistered" not in pm["raci"]["Responsible"]
    assert LEAK not in r.text
    md = served(registry=registry).post("/replay/markdown", json=BODY)
    assert md.status_code == 200 and "not found in registry" not in md.text and LEAK not in md.text


@pytest.mark.parametrize("path", ["/replay", "/replay/markdown"])
@pytest.mark.parametrize("which, text", [
    ("verify", "ledger unavailable"), ("events", "ledger unavailable"), ("tokens", "delegation unavailable")])
@pytest.mark.parametrize("failure", [_down, _boom(500), _boom(502)], ids=["transport", "500", "502"])
def test_a_ledger_or_delegation_failure_is_a_502_naming_only_the_dependency(path, which, text, failure):
    r = served(**{which: failure}).post(path, json=BODY)
    assert r.status_code == 502
    assert r.json() == {"detail": text}
    assert LEAK not in r.text


@pytest.mark.parametrize("bad", [
    {k: v for k, v in GOOD_TOKEN.items() if k != "token_id"},
    {k: v for k, v in GOOD_TOKEN.items() if k != "granted_by"},
    {k: v for k, v in GOOD_TOKEN.items() if k != "scope"},
    {k: v for k, v in GOOD_TOKEN.items() if k != "issued_at"},
    {k: v for k, v in GOOD_TOKEN.items() if k != "expires_at"},
    {k: v for k, v in GOOD_TOKEN.items() if k != "revoked"},
    {**GOOD_TOKEN, "issued_at": "not a time"},
    {**GOOD_TOKEN, "expires_at": None},
    "not a dict",
], ids=["token_id", "granted_by", "scope", "issued_at", "expires_at", "revoked", "bad-issued", "null-expires", "string"])
def test_one_unreadable_token_is_skipped_and_counted_and_the_healthy_one_is_listed(bad):
    r = served(tokens=_ok([bad, GOOD_TOKEN])).post("/replay", json=BODY)
    assert r.status_code == 200
    pm = r.json()
    assert [g["token_id"] for g in pm["authority"]] == ["t-good"]
    assert "1 delegation token record(s) unreadable, not shown" in pm["integrity_notes"]


def test_no_unreadable_token_means_no_such_note():
    pm = served().post("/replay", json=BODY).json()
    assert not any("unreadable" in n for n in pm["integrity_notes"])


def test_a_registry_record_without_an_owner_is_not_a_keyerror():
    record = {k: v for k, v in RECORD.items() if k != "owner"}
    for path in ("/replay", "/replay/markdown"):
        r = served(registry=_ok(record)).post(path, json=BODY)
        assert r.status_code == 200
    assert served(registry=_ok(record)).post("/replay", json=BODY).json()["raci"]["Responsible"] == \
        "<owner not recorded> (agent owner)"
