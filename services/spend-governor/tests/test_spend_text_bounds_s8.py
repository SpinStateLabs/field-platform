"""S8-10 (the part PR 585 leaves): a blank or whitespace-only `action` or `model` is a 422 on POST /spend and /usage.

PR 585 bounds the lengths (note 1000, action and model 200). `min_length=1` still lets ' ' through, and a blank model is stored
and returned by GET /usage (normalize_model returns the caller's text), a blank action feeds a rate window named ' '.
The 422 does not echo the value, and no row is written. The 1 MiB / 100,000-character cases of the card are repeated here
so this file is self-contained."""

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import GovernorStore

AGENT = "invoicing-agent"
MARK = "ZZ-MARKER"


@pytest.fixture()
def client(tmp_path):
    c = TestClient(create_app(store=GovernorStore(tmp_path / "spend.sqlite3")))
    assert c.put(f"/caps/{AGENT}", json={"agent_id": AGENT, "limit_cents": 100_000, "period": "daily",
                                         "escalate_at_pct": 80}).status_code == 200
    return c


def rows(c):
    return len(c.get(f"/usage/{AGENT}").json()["records"]) if c.get(f"/usage/{AGENT}").status_code == 200 else 0


@pytest.mark.parametrize("blank", [" ", "   ", "\t", "\n", " \t\n ", "\u00a0", "\u3000"])
def test_a_blank_action_is_refused_and_writes_nothing(client, blank):
    r = client.post("/spend", json={"agent_id": AGENT, "cents": 1, "action": blank})
    assert r.status_code == 422
    assert client.get(f"/status/{AGENT}").json()["spent_cents"] == 0


@pytest.mark.parametrize("blank", [" ", "   ", "\t", "\n", " \t\n ", "\u00a0", "\u3000"])
def test_a_blank_model_is_refused_and_writes_nothing(client, blank):
    r = client.post("/usage", json={"agent_id": AGENT, "model": blank, "input_tokens": 5})
    assert r.status_code == 422
    usage = client.get(f"/usage/{AGENT}")
    assert usage.status_code != 200 or usage.json().get("records", []) == []


def test_a_normal_action_and_model_are_unchanged(client):
    assert client.post("/spend", json={"agent_id": AGENT, "cents": 1, "action": "draft invoices"}).status_code == 201
    assert client.post("/usage", json={"agent_id": AGENT, "model": "claude-opus-4-8", "input_tokens": 1}).status_code == 201
    assert client.post("/spend", json={"agent_id": AGENT, "cents": 1}).status_code == 201          # no action: allowed


def test_a_padded_but_non_blank_action_is_accepted(client):
    assert client.post("/spend", json={"agent_id": AGENT, "cents": 1, "action": "  draft  "}).status_code == 201


def test_the_refusal_does_not_echo_the_value(client):
    r = client.post("/usage", json={"agent_id": AGENT, "model": " ", "note": MARK, "input_tokens": 1})
    assert r.status_code == 422 and MARK not in r.text


def test_a_one_mebibyte_note_and_a_100000_character_model_are_422_and_leave_no_row(client):
    assert client.post("/spend", json={"agent_id": AGENT, "cents": 1, "note": "n" * (1024 * 1024)}).status_code == 422
    assert client.post("/usage", json={"agent_id": AGENT, "model": "m" * 100_000, "input_tokens": 1}).status_code == 422
    assert client.get(f"/status/{AGENT}").json()["spent_cents"] == 0


def test_boundary_length_values_are_accepted(client):
    assert client.post("/spend", json={"agent_id": AGENT, "cents": 1, "note": "n" * 1000, "action": "a" * 200}).status_code == 201
    assert client.post("/usage", json={"agent_id": AGENT, "model": "m" * 200, "input_tokens": 1, "note": "n" * 1000}).status_code == 201
