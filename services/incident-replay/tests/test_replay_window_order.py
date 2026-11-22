"""`ReplayRequest`: `since` later than `until` is refused (scout P-15).

Before: each bound was validated alone and nothing compared them, so an inverted window went to the ledger and came back
as an empty timeline: a clean-looking post-mortem for a window that never existed. Bounds are inclusive, so
`since == until` stays valid, and the comparison is of instants, not strings (offsets differ)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from incident_replay.engine import ReplayRequest
from test_incident_replay import stack  # noqa: F401  (fixture: ledger, registry, delegation and the replay app)

AGENT = "invoicing-agent"


def _body(since, until):
    return {"agent_id": AGENT, "since": since, "until": until}


def test_an_inverted_window_is_422_over_the_api(stack):
    replay, _, _ = stack
    r = replay.post("/replay", json=_body("2030-01-02T00:00:00Z", "2030-01-01T00:00:00Z"))
    assert r.status_code == 422, (r.status_code, r.text)
    assert "2030-01" not in r.text                          # the 422 repeats no input


def test_the_markdown_route_refuses_it_too(stack):
    replay, _, _ = stack
    r = replay.post("/replay/markdown", json=_body("2030-01-02T00:00:00Z", "2030-01-01T00:00:00Z"))
    assert r.status_code == 422, (r.status_code, r.text)


def test_the_same_instant_is_accepted(stack):
    replay, _, _ = stack
    r = replay.post("/replay", json=_body("2030-01-01T00:00:00Z", "2030-01-01T00:00:00Z"))
    assert r.status_code == 200, (r.status_code, r.text)


def test_mixed_offsets_compare_as_instants(stack):
    replay, _, _ = stack
    # 00:00-05:00 is 05:00Z, later than 04:00Z: that order is inverted, the swap is valid.
    assert replay.post("/replay", json=_body("2026-08-18T00:00:00-05:00", "2026-08-18T04:00:00Z")).status_code == 422
    assert replay.post("/replay", json=_body("2026-08-18T04:00:00Z", "2026-08-18T00:00:00-05:00")).status_code == 200
    # 00:00+05:00 is 19:00Z the day before, earlier than 04:00Z: valid
    assert replay.post("/replay", json=_body("2026-08-18T00:00:00+05:00", "2026-08-18T04:00:00Z")).status_code == 200


def test_the_model_refuses_an_inverted_window_and_its_message_names_neither_value():
    with pytest.raises(ValidationError) as e:
        ReplayRequest(agent_id=AGENT, since="2030-01-02T00:00:00Z", until="2030-01-01T00:00:00Z")
    msgs = [err["msg"] for err in e.value.errors()]
    assert msgs and all("2030" not in m for m in msgs), msgs
    ReplayRequest(agent_id=AGENT, since="2030-01-01T00:00:00Z", until="2030-01-02T00:00:00Z")
