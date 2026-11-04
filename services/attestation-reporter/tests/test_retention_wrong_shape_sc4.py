"""A /retention/check answer whose `offending` or `unresolvable` is not a list of records
must fail ONE metric closed, not raise out of build() (scout S-C4). The sibling metrics
already do this (C-247); `_retention_metrics` indexed `.get` on whatever it was given."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from attestation_reporter.engine import PackEngine

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
POLICY = "Estate ledger retention policy (days)"
COUNT = "Manifests declaring more retention than the estate keeps"
BAD = [["x"], {"a": 1}, "oops", 5, [1], [None], [["nested"]], True]


class Answer:
    def __init__(self, body):
        self.status_code = 200
        self._body = body

    def json(self):
        return self._body


class Stub:
    def __init__(self, **routes):
        self.routes = routes

    def get(self, target):
        return Answer(self.routes.get(target.split("?")[0], []))


def _metrics(retention_body):
    ledger = Stub(**{"/events": [], "/verify": {"ok": True, "length": 0}, "/health": {},
                     "/retention/check": retention_body})
    eng = PackEngine(registry=Stub(**{"/agents": []}), ledger=ledger,
                     delegation=Stub(**{"/tokens": []}), governor=Stub(**{"/escalations": []}))
    return {m.name: m for m in eng.build(now=NOW).all_metrics()}


def _body(**kw):
    return {"status": "ok", "estate_retention_days": 365, "manifests_checked": 2, **kw}


@pytest.mark.parametrize("bad", BAD, ids=repr)
def test_a_wrong_shaped_offending_makes_only_the_count_unavailable(bad):
    m = _metrics(_body(offending=bad, unresolvable=[]))
    assert m[COUNT].status == "unavailable" and m[COUNT].value is None
    assert "not a list of records" in (m[COUNT].note or "")
    assert m[POLICY].value == 365                      # the policy figure is still published


@pytest.mark.parametrize("bad", BAD, ids=repr)
def test_a_wrong_shaped_unresolvable_makes_only_the_count_unavailable(bad):
    m = _metrics(_body(offending=[], unresolvable=bad))
    assert m[COUNT].status == "unavailable" and m[COUNT].value is None
    assert m[POLICY].value == 365


def test_the_note_never_echoes_the_wrong_value():
    marker = "zz-marker-do-not-echo"
    m = _metrics(_body(offending=marker))
    assert marker not in (m[COUNT].note or "")


def test_well_formed_records_still_count():
    m = _metrics(_body(
        offending=[{"agent_id": "a1", "retention_days": 4000}],
        unresolvable=[{"agent_id": "a2", "reason": "unreadable"}]))
    assert m[COUNT].value == 1 and "a1" in m[COUNT].note and "a2" in m[COUNT].note


def test_empty_and_missing_lists_still_count_zero():
    assert _metrics(_body(offending=[], unresolvable=[]))[COUNT].value == 0
    assert _metrics(_body())[COUNT].value == 0
    assert _metrics(_body(offending=None, unresolvable=None))[COUNT].value == 0
