"""S10-21: the CLI can deactivate (and reactivate) a contract.

The 409 text and the README tell the operator to deactivate the first contract before a second one for the same
org, and the only CLI verb hard-coded active=True, so the operator needed a hand-written PUT with the full body
(including the pasted key). `fedbroker deactivate ID` / `activate ID` GET the stored contract and re-PUT it with
only `active` changed (same id, key, scopes, ref), through the operator-guarded write headers."""

from __future__ import annotations

from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from federation_broker import cli
from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore
from field_core.signing import generate_keypair
from test_federation_broker import COUNTERPARTY, crossing

RUNNER = CliRunner()
BASE = "http://broker.invalid"


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_ORG_NAME", "Spin State Labs")
    monkeypatch.setenv("FIELD_FEDERATION_URL", BASE)
    client = TestClient(create_app(engine=BrokerEngine(store=ContractStore(tmp_path / "c.sqlite3"))))
    sent: list[tuple[str, str]] = []

    def make(method):
        def fake(url, **kw):
            path = url.removeprefix(BASE)
            sent.append((method, path))
            resp = client.request(method, path, json=kw.get("json"))
            return httpx.Response(resp.status_code, content=resp.content,
                                  headers={"content-type": "application/json"},
                                  request=httpx.Request(method, url))
        return fake
    for m in ("get", "put", "post"):
        monkeypatch.setattr(httpx, m, make(m.upper()))
    return client, sent


def _add(*args):
    return RUNNER.invoke(cli.app, ["add-contract", *args])


def _contracts(client):
    return {c["contract_id"]: c for c in client.get("/contracts").json()}


def test_deactivate_flips_only_active_and_keeps_everything_else(stack):
    client, sent = stack
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
    assert ("PUT", "/contracts/FED-1") in sent


def test_a_crossing_for_a_deactivated_org_is_blocked_for_no_active_contract(stack):
    client, _ = stack
    assert _add("FED-1", "--org", COUNTERPARTY, "--scope", "exchange invoice status",
                "--data-class", "invoice metadata").exit_code == 0
    assert "no active federation contract" not in crossing(client).text
    assert RUNNER.invoke(cli.app, ["deactivate", "FED-1"]).exit_code == 0
    verdict = crossing(client).json()
    assert verdict["decision"] == "BLOCK"
    assert any("no active federation contract" in r for r in verdict["reasons"]), verdict


def test_a_deactivated_org_can_move_to_a_new_contract_id(stack):
    client, _ = stack
    assert _add("FED-OLD", "--org", COUNTERPARTY, "--scope", "s", "--data-class", "d").exit_code == 0
    refused = _add("FED-NEW", "--org", COUNTERPARTY, "--scope", "s", "--data-class", "d")
    assert refused.exit_code == 1 and "409" in refused.stderr and "deactivate" in refused.stderr
    assert RUNNER.invoke(cli.app, ["deactivate", "FED-OLD"]).exit_code == 0
    assert _add("FED-NEW", "--org", COUNTERPARTY, "--scope", "s", "--data-class", "d").exit_code == 0
    assert sorted(i for i, c in _contracts(client).items() if c["active"]) == ["FED-NEW"]


def test_activate_turns_it_back_on_and_a_conflict_is_the_409_line(stack):
    client, _ = stack
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
    client, sent = stack
    r = RUNNER.invoke(cli.app, ["deactivate", "NOPE"])
    assert r.exit_code == 1
    assert r.stderr.strip() == "error: no contract with id 'NOPE'"
    assert "Traceback" not in r.output
    assert not [s for s in sent if s[0] == "PUT"] and _contracts(client) == {}


def test_the_id_is_one_url_quoted_path_segment(stack):
    client, sent = stack
    odd = "FED x&y#1"
    body = {"contract_id": odd, "counterparty_org": COUNTERPARTY, "allowed_scopes": ["s"],
            "allowed_data_classes": ["d"], "active": True}
    assert client.put(f"/contracts/{quote(odd, safe='')}", json=body).status_code == 200
    r = RUNNER.invoke(cli.app, ["deactivate", odd])
    assert r.exit_code == 0, r.output
    assert [p for m, p in sent if m == "PUT"] == [f"/contracts/{quote(odd, safe='')}"]
    assert _contracts(client)[odd]["active"] is False
