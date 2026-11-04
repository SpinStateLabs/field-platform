"""S4-16: a timeline entry's summary is capped (300 characters, visible truncation marker); ordinary ones unchanged."""

from __future__ import annotations

import pytest

from incident_replay.engine import SUMMARY_MAX, ReplayEngine, ReplayRequest, render_markdown
from test_timeline_pins import REQ, _Delegation, _Ledger, _Registry, _event


def replay(events):
    return ReplayEngine(_Ledger(events, None), _Registry(), _Delegation(())).replay(REQ)


def marker(n):
    return f"…[truncated {n} chars]"


def test_cap_constant():
    assert SUMMARY_MAX == 300


def test_spend_payload_100kb_is_capped():
    payload = {"blob": "x" * 100_000}
    e = replay([_event("spend.throttle", payload)]).timeline[0]
    full = f"spend.throttle {payload}"
    assert e.summary == full[:SUMMARY_MAX] + marker(len(full) - SUMMARY_MAX)
    assert len(e.summary) < 400


def test_kill_reason_100kb_is_capped():
    e = replay([_event("kill.agent", {"operator": "op", "reason": "r" * 100_000})]).timeline[0]
    full = f"kill.agent by op ({'r' * 100_000})"
    assert e.summary == full[:SUMMARY_MAX] + marker(len(full) - SUMMARY_MAX)


def test_conformance_action_is_capped_too():
    e = replay([_event("conformance.block", {"action": "a" * 50_000, "clause_id": "D.scope"})]).timeline[0]
    assert e.summary.startswith("BLOCK '" + "a" * 100) and "…[truncated " in e.summary and len(e.summary) < 400


def test_exactly_at_the_cap_is_unchanged_and_one_over_is_marked():
    base = "spend.throttle {'k': '"  # + value + "'}"
    pad = SUMMARY_MAX - len(base) - len("'}")
    at = replay([_event("spend.throttle", {"k": "y" * pad})]).timeline[0].summary
    assert len(at) == SUMMARY_MAX and "truncated" not in at
    over = replay([_event("spend.throttle", {"k": "y" * (pad + 1)})]).timeline[0].summary
    assert over.endswith(marker(1))


def test_cap_counts_characters_not_bytes():
    e = replay([_event("kill.agent", {"operator": "op", "reason": "é" * 400})]).timeline[0]
    assert e.summary.startswith("kill.agent by op (" + "é" * 100)
    head = e.summary.split("…[truncated")[0]
    assert len(head) == SUMMARY_MAX
    full = "kill.agent by op (" + "é" * 400 + ")"
    assert e.summary.endswith(marker(len(full) - SUMMARY_MAX))


def test_other_fields_untouched():
    ev = _event("spend.throttle", {"blob": "x" * 100_000})
    e = replay([ev]).timeline[0]
    assert e.event_type == "spend.throttle"
    assert e.hash == "h0"


def test_markdown_is_bounded():
    md = render_markdown(replay([_event("spend.throttle", {"blob": "x" * 100_000})]))
    assert len(md) < 20_000


def test_short_summaries_byte_identical():
    assert replay([_event("spend.throttle", {"cap": 5})]).timeline[0].summary == "spend.throttle {'cap': 5}"
    assert replay([_event("kill.domain", {})]).timeline[0].summary == "kill.domain by ? ()"
