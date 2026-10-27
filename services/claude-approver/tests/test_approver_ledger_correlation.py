"""Client side of P30: what the approver ACTUALLY sends reaches the ledger
with the Console session id, and an approver-metered 5.5 session is priced.

The check body is run through field-core's ledger filter (the sentinel ledgers
exactly that, tests/test_caller_context_ledger.py); the usage body is posted to
the REAL spend-governor app (in-process, fake ledger)."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from approver_fakes import CONSOLE_AGENT, FIELD_AGENT, usage
from field_core.ledger_context import correlation_context
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore

SID = "sesn_01LYJ1mZ5RtNnD7hmAoyVY6V"


class _Ledger:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def append(self, event_type, payload=None, agent_id=None, **_):
        self.events.append((event_type, dict(payload or {})))


def test_the_check_context_survives_the_ledger_filter_with_the_session_id(
        console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    ev = console.ask(SID, "bash")
    console.idle(SID, event_ids=[ev.id])
    make_approver().tick()
    (check,) = field.checks()
    kept = correlation_context(check["context"])
    assert kept["console_session_id"] == SID
    assert kept["source"] == "claude-approver"
    assert kept["console_agent_id"] == CONSOLE_AGENT
    assert kept["event_id"] == ev.id


@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"])
def test_an_approver_usage_post_is_priced_and_ledgered_with_the_session_id(
        console, field, make_approver, mapped, tmp_path, model):
    ledger = _Ledger()
    gov = TestClient(create_governor_app(store=GovernorStore(tmp_path / "spend.sqlite3"),
                                         ledger=ledger))
    assert gov.put(f"/caps/{FIELD_AGENT}", json={
        "agent_id": FIELD_AGENT, "limit_cents": 50_000, "period": "daily",
        "escalate_at_pct": 80}).status_code == 200

    def forward(request: httpx.Request) -> httpx.Response:
        r = gov.post("/usage", json=json.loads(request.content))
        return httpx.Response(r.status_code, json=r.json())

    field.usage = forward
    console.add_agent(CONSOLE_AGENT, model=model)
    console.add_session(SID, CONSOLE_AGENT, status="running", model=None,
                        use=usage(1_000, 100, 50))
    a = make_approver()
    a.tick()
    assert a.stats()["usage_posts"] == 1

    recorded = [p for t, p in ledger.events if t == "usage.recorded"]
    (row,) = recorded
    assert row["model"] == model
    assert row["cost_units"] is not None
    assert row["note"] == f"console session {SID}"
    assert [t for t, _ in ledger.events if t == "usage.unpriced"] == []
