"""S4-13: ResolveRequest.resolved_by was Field(min_length=1), so '   ' passed and became the recorded human resolver of the
escalation: the first-resolver-wins identity and the `resolved_by` of the spend.escalation_resolved ledger note. It is now
stripped and a blank value is a 422 (through the no-echo handler), max 200; the stripped value is what is stored, so
' alice' and 'alice' are the SAME human. With an operator file armed, the authenticated identity still replaces the body
name (bind_body_operator), and a blank body is still refused first."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from field_core import operator_auth as oa
from spend_governor import cli
from spend_governor.api import create_app
from spend_governor.core import GovernorStore

runner = CliRunner()
MARK = "MADE-UP-MARKER-0123456789"
AGENT = "invoicing-agent"
KEY_DON = "fok_don-key-0123456789abcdef"


class Ledger:
    def __init__(self):
        self.notes = []

    def append(self, event_type, payload=None, agent_id=None):
        self.notes.append((event_type, payload or {}, agent_id))

    def resolved(self):
        return [p for t, p, _ in self.notes if t == "spend.escalation_resolved"]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def stack(tmp_path):
    store = GovernorStore(tmp_path / "g.sqlite3")
    ledger = Ledger()
    client = TestClient(create_app(store=store, ledger=ledger))
    yield client, ledger, store
    store.close()


def open_escalation(client, agent=AGENT):
    assert client.put(f"/caps/{agent}", json={"agent_id": agent, "limit_cents": 10_000, "period": "total",
                                              "escalate_at_pct": 80}).status_code == 200
    assert client.post("/spend", json={"agent_id": agent, "cents": 8_000}).status_code == 201
    (esc,) = client.get("/escalations", params={"agent_id": agent}).json()
    return esc["escalation_id"]


def resolve(client, esc_id, name, **headers):
    return client.post(f"/escalations/{esc_id}/resolve", json={"resolved_by": name}, headers=headers)


@pytest.mark.parametrize("name", ["", " ", "   ", "\t", "\n", "\t\n", " \t \n "])
def test_a_blank_resolver_is_a_422_and_leaves_the_escalation_open(stack, name):
    client, ledger, _ = stack
    esc_id = open_escalation(client)
    r = resolve(client, esc_id, name)
    assert r.status_code == 422, r.text
    assert any(e["loc"][-1] == "resolved_by" for e in r.json()["detail"]), r.text
    open_now = client.get("/escalations", params={"agent_id": AGENT}).json()
    assert [e["escalation_id"] for e in open_now] == [esc_id] and not open_now[0]["resolved"]
    assert ledger.resolved() == []


def test_a_padded_name_resolves_as_the_stripped_name(stack):
    client, ledger, _ = stack
    esc_id = open_escalation(client)
    r = resolve(client, esc_id, "  alice ")
    assert r.status_code == 200 and r.json()["resolved_by"] == "alice" and r.json()["resolved"]
    assert [n["resolved_by"] for n in ledger.resolved()] == ["alice"]


def test_a_second_resolver_whose_name_differs_only_by_padding_is_the_same_human(stack):
    client, ledger, _ = stack
    esc_id = open_escalation(client)
    assert resolve(client, esc_id, "alice").status_code == 200
    again = resolve(client, esc_id, " alice")
    assert again.status_code == 200 and again.json()["resolved_by"] == "alice"       # idempotent, not a 409
    assert len(ledger.resolved()) == 1
    other = resolve(client, esc_id, "bob")
    assert other.status_code == 409 and other.json()["resolved_by"] == "alice"       # first resolver still wins


def test_the_length_bound_is_200_characters(stack):
    client, _, _ = stack
    esc_id = open_escalation(client)
    assert resolve(client, esc_id, "a" * 201).status_code == 422
    assert resolve(client, esc_id, "a" * 200).status_code == 200


def test_a_422_for_a_blank_or_long_name_repeats_nothing_it_was_sent(stack):
    client, _, _ = stack
    esc_id = open_escalation(client)
    for name in (MARK * 50, " "):
        r = resolve(client, esc_id, name)
        assert r.status_code == 422 and MARK not in r.text, r.text


def test_an_unknown_escalation_is_still_404_after_validation(stack):
    client, _, _ = stack
    assert resolve(client, "no-such-id", "alice").status_code == 404
    assert resolve(client, "no-such-id", " ").status_code == 422          # the body is refused first


# ---- with an operator file armed: the bound identity path ----------------------------------------------------------------


@pytest.fixture()
def armed(tmp_path, monkeypatch):
    rows = [{"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active", "scopes": ["*"]}]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows))
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def auth(key=KEY_DON, op="don"):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


def test_an_authenticated_resolve_is_recorded_under_the_authenticated_id_not_the_body_name(stack, armed):
    client, ledger, _ = stack
    assert client.put(f"/caps/{AGENT}", json={"agent_id": AGENT, "limit_cents": 10_000, "period": "total",
                                              "escalate_at_pct": 80}, headers=auth()).status_code == 200
    client.post("/spend", json={"agent_id": AGENT, "cents": 8_000})
    (esc,) = client.get("/escalations", params={"agent_id": AGENT}).json()
    r = resolve(client, esc["escalation_id"], "  mallory  ", **auth())
    assert r.status_code == 200, r.text
    assert r.json()["resolved_by"] == "don"                                # bind_body_operator still wins
    assert [n["resolved_by"] for n in ledger.resolved()] == ["don"]


def test_a_blank_body_name_is_refused_even_when_authenticated(stack, armed):
    client, ledger, _ = stack
    r = resolve(client, "any-id", "   ", **auth())
    assert r.status_code == 422 and ledger.resolved() == []


# ---- the CLI's message -------------------------------------------------------------------------------------------------


def test_the_cli_reports_a_blank_resolver_as_one_error_line_exit_1(stack, monkeypatch):
    client, _, _ = stack
    esc_id = open_escalation(client)
    monkeypatch.setenv("FIELD_GOVERNOR_URL", "http://gov.invalid")
    monkeypatch.setattr(cli.httpx, "post", lambda url, **kw: client.post(url.replace("http://gov.invalid", ""),
                                                                           json=kw.get("json")))
    res = runner.invoke(cli.app, ["resolve", esc_id, "--by", "   "])
    assert res.exit_code == 1, res.output
    err = res.stderr.strip()
    assert err.startswith("error 422:") and len(err.splitlines()) == 1 and "Traceback" not in res.output
    res = runner.invoke(cli.app, ["resolve", esc_id, "--by", " alice "])
    assert res.exit_code == 0 and json.loads(res.stdout)["resolved_by"] == "alice"
