"""S2-2: free-text request fields are bounded, so a caller cannot write an
arbitrarily large string into the stored spend/usage rows. Boundary accepted,
one over refused with a 422 that does not repeat the text."""

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import GovernorStore

AGENT = "invoicing-agent"


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=GovernorStore(tmp_path / "spend.sqlite3")))


def _spend(**over):
    return {"agent_id": AGENT, "cents": 1, **over}


def _usage(**over):
    return {"agent_id": AGENT, "model": "claude-opus-4-8", "input_tokens": 1, **over}


CASES = [
    ("/spend", _spend, "note", 1000),
    ("/spend", _spend, "action", 200),
    ("/spend", _spend, "agent_id", 128),
    ("/usage", _usage, "note", 1000),
    ("/usage", _usage, "model", 200),
    ("/usage", _usage, "agent_id", 128),
]


@pytest.mark.parametrize("path,build,field,limit", CASES,
                         ids=[f"{p}-{f}" for p, _, f, _ in CASES])
def test_text_field_accepts_its_limit_and_refuses_one_over(client, path, build, field, limit):
    # a cap for every agent id used, so the accepted case is not a 404 "no cap"
    for agent in (AGENT, "a" * limit if field == "agent_id" else AGENT):
        r = client.put(f"/caps/{agent}", json={
            "agent_id": agent, "limit_cents": 50_000, "period": "daily", "escalate_at_pct": 80})
        assert r.status_code == 200, r.text
    ok = client.post(path, json=build(**{field: "a" * limit}))
    assert ok.status_code == 201, ok.text
    over = "b" * (limit + 1)
    r = client.post(path, json=build(**{field: over}))
    assert r.status_code == 422
    assert over not in r.text          # the refusal never repeats the caller's text
