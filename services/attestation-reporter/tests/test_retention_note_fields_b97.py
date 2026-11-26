"""B97 - after B24 (agent_id), the other fields the SIGNED retention note prints (retention_days, reason,
agents_without_manifest, manifests_checked) are never interpolated with a non-conforming type. Each
prints as a fixed placeholder, every record stays counted, and the note says how many records carried a
malformed field. Well-formed answers produce exactly the note they produced before."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from attestation_reporter.engine import PackEngine

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
COUNT = "Manifests declaring more retention than the estate keeps"
MARK = "zz-b97-marker"
# wrong types for a count of days or agents; the strings here are what must never reach the note
ODD_COUNTS = [{"k": MARK}, [MARK], MARK, True, 1.5, -3, "7"]
ODD_REASONS = [{"k": MARK}, [MARK], 12345, True, 1.5]
RAW = ("{", "[", "True", "12345", "1.5", "-3", "'7'")


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


def _count(offending=(), unresolvable=(), **extra):
    body = {"status": "ok", "estate_retention_days": 365, "manifests_checked": 3,
            "offending": list(offending), "unresolvable": list(unresolvable), **extra}
    ledger = Stub(**{"/events": [], "/verify": {"ok": True, "length": 0}, "/health": {},
                     "/retention/check": body})
    eng = PackEngine(registry=Stub(**{"/agents": []}), ledger=ledger,
                     delegation=Stub(**{"/tokens": []}), governor=Stub(**{"/escalations": []}))
    return {m.name: m for m in eng.build(now=NOW).all_metrics()}[COUNT]


def _clean(note: str) -> None:
    assert MARK not in note
    for raw in RAW:
        assert raw not in note, raw


@pytest.mark.parametrize("odd", ODD_COUNTS, ids=repr)
def test_a_malformed_retention_days_prints_a_placeholder_and_is_counted(odd):
    m = _count([{"agent_id": "a0", "retention_days": odd}, {"agent_id": "a1", "retention_days": 4000}])
    assert m.status == "ok" and m.value == 2
    _clean(m.note)
    assert "a0 (no retention_days)" in m.note and "a1 (4000 d)" in m.note
    assert "1 record(s) with a malformed field, printed as a placeholder" in m.note


def test_a_missing_retention_days_is_malformed_too():
    m = _count([{"agent_id": "a0"}])
    assert m.value == 1 and "a0 (no retention_days)" in m.note and "1 record(s) with a malformed field" in m.note


@pytest.mark.parametrize("odd", ODD_REASONS + [None], ids=repr)
def test_a_malformed_reason_prints_a_placeholder_and_is_counted(odd):
    m = _count([], [{"agent_id": "a2", "reason": odd}, {"agent_id": "a3", "reason": "unreadable"}])
    _clean(m.note)
    assert "a2 ((no reason))" in m.note and "a3 (unreadable)" in m.note
    assert "a lower bound: 2 manifest ref(s)" in m.note
    assert "1 record(s) with a malformed field" in m.note


@pytest.mark.parametrize("odd", ODD_COUNTS + [False, ""], ids=repr)
def test_a_malformed_agents_without_manifest_is_not_printed(odd):
    m = _count([{"agent_id": "a1", "retention_days": 4000}], agents_without_manifest=odd)
    _clean(m.note)
    assert "agents without a manifest_ref not checked (the ledger's count is malformed)" in m.note


@pytest.mark.parametrize("odd", ODD_COUNTS + [None], ids=repr)
def test_a_malformed_manifests_checked_is_not_printed(odd):
    m = _count(manifests_checked=odd)
    _clean(m.note)
    assert m.value == 0 and m.note == "none among the resolvable manifests (the ledger's count is malformed)"


def test_one_record_with_two_malformed_fields_counts_once():
    m = _count([{"agent_id": [MARK], "retention_days": {"k": MARK}}, {"agent_id": "a1", "retention_days": 30}],
               [{"agent_id": 7, "reason": 8}])
    _clean(m.note)
    assert "(no agent_id) (no retention_days)" in m.note and "(no agent_id) ((no reason))" in m.note
    assert "2 record(s) with a malformed field" in m.note


def test_well_formed_answers_are_unchanged():
    m = _count([{"agent_id": "a1", "retention_days": 4000}], [{"agent_id": "a2", "reason": "unreadable"}],
               agents_without_manifest=2)
    assert m.note == ("offending: a1 (4000 d); unresolvable: a2 (unreadable); "
                      "a lower bound: 1 manifest ref(s) could not be read; "
                      "2 agent(s) without a manifest_ref not checked")
    assert _count(agents_without_manifest=0).note == "none among 3 resolvable manifest(s)"
    assert _count(agents_without_manifest=None).note == "none among 3 resolvable manifest(s)"
    assert _count([{"agent_id": "a1", "retention_days": 0}]).note == "offending: a1 (0 d)"
