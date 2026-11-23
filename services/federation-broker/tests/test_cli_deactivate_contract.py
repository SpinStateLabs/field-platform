"""S10-21: the CLI can deactivate (and reactivate) a contract.

The 409 text and the README tell the operator to deactivate the first contract before a second one for the same
org, and the only CLI verb hard-coded active=True, so the operator needed a hand-written PUT with the full body
(including the pasted key). `fedbroker deactivate ID` / `activate ID` GET the stored contract and re-PUT it with
only `active` changed (same id, key, scopes, ref), through the operator-guarded write headers."""

from __future__ import annotations

import json
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from federation_broker import cli
from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore
from field_core import authn
from field_core import operator_auth as oa
from field_core.signing import generate_keypair
from test_federation_broker import COUNTERPARTY, crossing

RUNNER = CliRunner()
_REAL = httpx.Client
BASE = "http://broker.invalid"
SECRET = "made-up-perimeter-secret"
OP, KEY = "made-up-operator", "fok_made-up-key-0123456789abcdef"


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    """The CLI is wired to the in-process broker through the REAL ``httpx.Client`` construction: ``httpx.Client`` is
    wrapped so each construction is recorded (its kwargs) and handed a transport that bridges to the app. The
    module-level ``httpx.get/put/post`` are made to FAIL, so a call that bypasses the client (and so reads the
    proxy environment) is seen. The other verbs keep their own module-level stand-ins (``add-contract``)."""
    monkeypatch.setenv("FIELD_ORG_NAME", "Spin State Labs")
    monkeypatch.setenv("FIELD_FEDERATION_URL", BASE)
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    monkeypatch.setenv(oa.ENV_OPERATOR, OP)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY)
    # The app enforces the perimeter secret (set above): the test's own reads (_contracts, crossing) send it, and both
    # stand-ins below forward exactly the x-field-* headers the CLI sent, so the app judges what the CLI really sends.
    client = TestClient(create_app(engine=BrokerEngine(store=ContractStore(tmp_path / "c.sqlite3"))),
                        headers={authn.HEADER: SECRET})
    sent: list[tuple[str, str, dict]] = []
    built: list[dict] = []
    real_client = httpx.Client

    def bridge(request: httpx.Request) -> httpx.Response:
        path = str(request.url).removeprefix(BASE)
        sent.append((request.method, path, dict(request.headers)))
        body = json.loads(request.content) if request.content else None
        resp = client.request(request.method, path, json=body, headers=_field_headers(request.headers))
        return httpx.Response(resp.status_code, content=resp.content, headers={"content-type": "application/json"})

    def make_client(*args, **kwargs):
        built.append(dict(kwargs))
        return real_client(*args, transport=httpx.MockTransport(bridge), **kwargs)

    def fake_module_level(method):
        def fake(url, **kw):
            path = url.removeprefix(BASE)
            sent.append((method, path, dict(kw.get("headers") or {})))
            resp = client.request(method, path, json=kw.get("json"), headers=_field_headers(kw.get("headers") or {}))
            return httpx.Response(resp.status_code, content=resp.content,
                                  headers={"content-type": "application/json"},
                                  request=httpx.Request(method, url))
        return fake
    monkeypatch.setattr(httpx, "Client", make_client)
    for m in ("get", "put", "post"):
        monkeypatch.setattr(httpx, m, fake_module_level(m.upper()))
    return client, sent, built


def _field_headers(headers) -> dict:
    """Only the x-field-* headers the CLI sent: the auth secret and the operator pair, never framing headers. A missing
    x-field-auth replaces the TestClient default with an empty value, so a call that sends no secret is refused 401."""
    out = {k: v for k, v in dict(headers).items() if k.lower().startswith("x-field-")}
    out.setdefault(authn.HEADER, "")
    return out


def _add(*args):
    return RUNNER.invoke(cli.app, ["add-contract", *args])


def _contracts(client):
    return {c["contract_id"]: c for c in client.get("/contracts").json()}


def test_deactivate_flips_only_active_and_keeps_everything_else(stack):
    client, sent, _ = stack
    _, pem = generate_keypair()
    keyfile = pem
    r = _add("FED-1", "--org", COUNTERPARTY, "--scope", "exchange invoice status", "--scope", "second scope",
             "--data-class", "invoice metadata", "--ref", "gc://record/1", "--pubkey", keyfile)
    assert r.exit_code == 0, r.output
    before = _contracts(client)["FED-1"]
    assert before["active"] is True

    r = RUNNER.invoke(cli.app, ["deactivate", "FED-1"])
    assert r.exit_code == 0, r.output
    after = _contracts(client)["FED-1"]
    assert after["active"] is False
    assert {k: v for k, v in after.items() if k != "active"} == {k: v for k, v in before.items() if k != "active"}
    assert ("PUT", "/contracts/FED-1") in [(m, p) for m, p, _ in sent]


def test_a_crossing_for_a_deactivated_org_is_blocked_for_no_active_contract(stack):
    client, _, _ = stack
    assert _add("FED-1", "--org", COUNTERPARTY, "--scope", "exchange invoice status",
                "--data-class", "invoice metadata").exit_code == 0
    assert "no active federation contract" not in crossing(client).text
    assert RUNNER.invoke(cli.app, ["deactivate", "FED-1"]).exit_code == 0
    verdict = crossing(client).json()
    assert verdict["decision"] == "BLOCK"
    assert any("no active federation contract" in r for r in verdict["reasons"]), verdict


def test_a_deactivated_org_can_move_to_a_new_contract_id(stack):
    client, _, _ = stack
    assert _add("FED-OLD", "--org", COUNTERPARTY, "--scope", "s", "--data-class", "d").exit_code == 0
    refused = _add("FED-NEW", "--org", COUNTERPARTY, "--scope", "s", "--data-class", "d")
    assert refused.exit_code == 1 and "409" in refused.stderr and "deactivate" in refused.stderr
    assert RUNNER.invoke(cli.app, ["deactivate", "FED-OLD"]).exit_code == 0
    assert _add("FED-NEW", "--org", COUNTERPARTY, "--scope", "s", "--data-class", "d").exit_code == 0
    assert sorted(i for i, c in _contracts(client).items() if c["active"]) == ["FED-NEW"]


def test_activate_turns_it_back_on_and_a_conflict_is_the_409_line(stack):
    client, _, _ = stack
    assert _add("FED-A", "--org", COUNTERPARTY, "--scope", "s", "--data-class", "d").exit_code == 0
    assert RUNNER.invoke(cli.app, ["deactivate", "FED-A"]).exit_code == 0
    assert RUNNER.invoke(cli.app, ["activate", "FED-A"]).exit_code == 0
    assert _contracts(client)["FED-A"]["active"] is True
    assert _add("FED-B", "--org", COUNTERPARTY, "--scope", "s", "--data-class", "d").exit_code == 1
    assert RUNNER.invoke(cli.app, ["deactivate", "FED-A"]).exit_code == 0
    assert _add("FED-B", "--org", COUNTERPARTY, "--scope", "s", "--data-class", "d").exit_code == 0
    r = RUNNER.invoke(cli.app, ["activate", "FED-A"])
    assert r.exit_code == 1 and "409" in r.stderr and "one active contract per org" in r.stderr
    assert _contracts(client)["FED-A"]["active"] is False


def test_an_unknown_id_is_one_line_exit_1_and_nothing_is_written(stack):
    client, sent, _ = stack
    r = RUNNER.invoke(cli.app, ["deactivate", "NOPE"])
    assert r.exit_code == 1
    assert r.stderr.strip() == "error: no contract with id 'NOPE'"
    assert "Traceback" not in r.output
    assert not [s for s in sent if s[0] == "PUT"] and _contracts(client) == {}


def test_the_id_is_one_url_quoted_path_segment(stack):
    client, sent, _ = stack
    odd = "FED x&y#1"
    body = {"contract_id": odd, "counterparty_org": COUNTERPARTY, "allowed_scopes": ["s"],
            "allowed_data_classes": ["d"], "active": True}
    assert client.put(f"/contracts/{quote(odd, safe='')}", json=body).status_code == 200
    r = RUNNER.invoke(cli.app, ["deactivate", odd])
    assert r.exit_code == 0, r.output
    assert [p for m, p, _ in sent if m == "PUT"] == [f"/contracts/{quote(odd, safe='')}"]
    assert _contracts(client)[odd]["active"] is False


def test_deactivate_uses_one_client_that_ignores_the_proxy_environment_and_redirects(stack, monkeypatch):
    """B1: the GET and the PUT share ONE client built with trust_env=False and follow_redirects=False and a timeout;
    no module-level httpx call is made (those read HTTP_PROXY / ALL_PROXY)."""
    client, sent, built = stack
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.invalid:3128")
    assert _add("FED-1", "--org", COUNTERPARTY, "--scope", "s", "--data-class", "d").exit_code == 0
    built.clear()
    sent.clear()
    r = RUNNER.invoke(cli.app, ["deactivate", "FED-1"])
    assert r.exit_code == 0, r.output
    assert [(m, p) for m, p, _ in sent] == [("GET", "/contracts"), ("PUT", "/contracts/FED-1")]
    assert len(built) == 1, built                                   # both calls through one client
    assert built[0].get("trust_env") is False, built[0]
    assert built[0].get("follow_redirects") is False, built[0]
    assert built[0].get("timeout"), built[0]


def test_the_put_carries_the_operator_pair_and_the_get_does_not(stack):
    """B5: the guarded write sends x-field-operator and x-field-operator-key; the read sends the perimeter secret
    alone."""
    client, sent, _ = stack
    assert _add("FED-1", "--org", COUNTERPARTY, "--scope", "s", "--data-class", "d").exit_code == 0
    sent.clear()
    assert RUNNER.invoke(cli.app, ["activate", "FED-1"]).exit_code == 0
    by = {(m, p): h for m, p, h in sent}
    put, get = by[("PUT", "/contracts/FED-1")], by[("GET", "/contracts")]
    assert put[oa.HEADER_OPERATOR] == OP and put[oa.HEADER_KEY] == KEY
    assert put[authn.HEADER] == SECRET and get[authn.HEADER] == SECRET
    assert oa.HEADER_OPERATOR not in get and oa.HEADER_KEY not in get


def test_a_refused_list_prints_the_error_line_and_writes_nothing(stack, monkeypatch):
    """B12: a non-200 GET is the `error NNN: detail` line, exit 1, and no PUT is attempted."""
    client, sent, _ = stack

    def refuse(request: httpx.Request) -> httpx.Response:
        sent.append((request.method, request.url.path, {}))
        return httpx.Response(503, json={"detail": "store unavailable"})
    monkeypatch.setattr(httpx, "Client", lambda **kw: _REAL(transport=httpx.MockTransport(refuse), **kw))
    r = RUNNER.invoke(cli.app, ["deactivate", "FED-1"])
    assert r.exit_code == 1
    assert r.stderr.strip() == "error 503: store unavailable"
    assert [m for m, _, _ in sent] == ["GET"]


@pytest.mark.parametrize("bad_id", ["NO\nPE", "NO\rPE", "x\x1b[31mred"], ids=["newline", "cr", "escape"])
def test_an_unknown_id_with_a_control_character_is_still_one_line(stack, bad_id):
    """C2 (builder-b): the unknown-id line prints the id with repr(), so a control character cannot split it."""
    r = RUNNER.invoke(cli.app, ["deactivate", bad_id])
    assert r.exit_code == 1
    line = r.stderr.strip()
    assert line == f"error: no contract with id {bad_id!r}" and "\n" not in line and "\x1b" not in line
