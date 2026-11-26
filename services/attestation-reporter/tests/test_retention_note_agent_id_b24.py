"""B24 — a well-formed retention record whose ``agent_id`` is not a string (a dict, list, number, bool
or null) must never be interpolated raw into the SIGNED retention note. The record still counts (it is
an offender / unresolvable manifest); its id prints as a fixed placeholder, as the distinct-agents row
treats a non-string id as missing."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from attestation_reporter.engine import PackEngine

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
COUNT = "Manifests declaring more retention than the estate keeps"
MARK = "zz-b24-marker"
PLACEHOLDER = "(no agent_id)"
ODD = [{"k": MARK}, [MARK], 12345, True, False, None, 1.5, {}, []]
RAW = ("{", "[", "None", "True", "False", "12345", "1.5")


class Answer:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class Stub:
    def __init__(self, **routes):
        self.routes = routes

    def get(self, target):
        return Answer(self.routes.get(target.split("?")[0], []))


def _count(offending, unresolvable):
    body = {"status": "ok", "estate_retention_days": 365, "manifests_checked": 3,
            "offending": offending, "unresolvable": unresolvable}
    ledger = Stub(**{"/events": [], "/verify": {"ok": True, "length": 0}, "/health": {},
                     "/retention/check": body})
    eng = PackEngine(registry=Stub(**{"/agents": []}), ledger=ledger,
                     delegation=Stub(**{"/tokens": []}), governor=Stub(**{"/escalations": []}))
    return {m.name: m for m in eng.build(now=NOW).all_metrics()}[COUNT]


@pytest.mark.parametrize("odd", ODD, ids=repr)
def test_a_non_string_offending_agent_id_is_not_printed_raw(odd):
    m = _count([{"agent_id": odd, "retention_days": 4000}, {"agent_id": "a1", "retention_days": 4000}], [])
    assert m.status == "ok" and m.value == 2                 # still counted
    assert MARK not in m.note
    for raw in RAW:
        assert raw not in m.note, raw
    assert f"{PLACEHOLDER} (4000 d)" in m.note and "a1 (4000 d)" in m.note


@pytest.mark.parametrize("odd", ODD, ids=repr)
def test_a_non_string_unresolvable_agent_id_is_not_printed_raw(odd):
    m = _count([], [{"agent_id": odd, "reason": "unreadable"}, {"agent_id": "a2", "reason": "unreadable"}])
    assert MARK not in m.note
    for raw in RAW:
        assert raw not in m.note, raw
    assert f"{PLACEHOLDER} (unreadable)" in m.note and "a2 (unreadable)" in m.note
    assert "a lower bound: 2 manifest ref(s)" in m.note


def test_a_record_without_agent_id_prints_the_placeholder():
    m = _count([{"retention_days": 4000}], [])
    assert m.value == 1 and f"{PLACEHOLDER} (4000 d)" in m.note


def test_string_ids_are_unchanged():
    m = _count([{"agent_id": "a1", "retention_days": 4000}], [{"agent_id": "a2", "reason": "unreadable"}])
    assert m.note.startswith("offending: a1 (4000 d); unresolvable: a2 (unreadable)")
