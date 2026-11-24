"""A free-text field holding a lone UTF-16 surrogate (JSON ``"\\ud800"``) is a 422, never a 500.

``agent_id``, ``action`` and ``model`` carry a length bound, which makes pydantic refuse a lone surrogate
(``string_unicode``). The unbounded text fields did not: ``note`` on ``POST /spend`` and ``POST /usage``,
``currency`` and ``on_breach`` on ``PUT /caps``, and each ``allowed_models`` entry on ``PUT /policies``
passed validation, and the SQLite bind (or the response encoder) then raised ``UnicodeEncodeError``: a 500.
On ``POST /spend`` and ``POST /usage`` that is a refused meter write for a caller whose cents were valid.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import GovernorStore

AGENT = "invoicing-agent"
JSON = {"content-type": "application/json"}
LONE = '"\\ud800"'  # the JSON text of one lone high surrogate


@pytest.fixture()
def store(tmp_path):
    return GovernorStore(tmp_path / "spend.sqlite3")


@pytest.fixture()
def client(store):
    c = TestClient(create_app(store=store), raise_server_exceptions=False)
    cap = {"agent_id": AGENT, "currency": "USD", "limit_cents": 100, "period": "daily",
           "escalate_at_pct": 80}
    assert c.put(f"/caps/{AGENT}", json=cap).status_code == 200
    return c


def raw(c, method, path, body):
    return c.request(method, path, content=body.encode(), headers=JSON)


def test_a_spend_note_with_a_lone_surrogate_is_a_422_and_writes_nothing(client, store):
    r = raw(client, "POST", "/spend", f'{{"agent_id": "{AGENT}", "cents": 5, "note": {LONE}}}')
    assert r.status_code == 422
    assert store.totals_since(AGENT, "1970-01-01T00:00:00+00:00") == (0, 0, 0)


def test_a_usage_note_with_a_lone_surrogate_is_a_422(client):
    body = f'{{"agent_id": "{AGENT}", "model": "claude-sonnet-4-5", "input_tokens": 10, "note": {LONE}}}'
    assert raw(client, "POST", "/usage", body).status_code == 422


@pytest.mark.parametrize("field", ["currency", "on_breach"])
def test_a_cap_text_field_with_a_lone_surrogate_is_a_422_and_the_cap_is_kept(client, store, field):
    body = f'{{"agent_id": "{AGENT}", "limit_cents": 1, "{field}": {LONE}}}'
    assert raw(client, "PUT", f"/caps/{AGENT}", body).status_code == 422
    assert store.get_cap(AGENT).limit_cents == 100


def test_an_allowed_model_with_a_lone_surrogate_is_a_422_and_no_policy_is_stored(client):
    body = f'{{"agent_id": "{AGENT}", "allowed_models": [{LONE}]}}'
    assert raw(client, "PUT", f"/policies/{AGENT}", body).status_code == 422
    assert client.get(f"/policies/{AGENT}").status_code == 404


def test_ordinary_unicode_text_is_still_accepted(client):
    r = client.post("/spend", json={"agent_id": AGENT, "cents": 5, "note": "café \U0001F600"})
    assert r.status_code == 201
