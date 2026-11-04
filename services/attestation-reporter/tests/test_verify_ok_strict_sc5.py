"""The ledger-integrity metric says INTACT only for `ok is True` (scout S-C5). It used to
say INTACT for any truthy `ok`: {"ok": "false"}, {"ok": 1}, {"ok": [0]}, a non-empty string
all published "INTACT" in a signed attestation pack. A verification result that is not a
boolean is "not a verification result": the metric is unavailable, never INTACT, never
BROKEN."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from attestation_reporter.engine import PackEngine

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


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


def _metric(verify_body):
    ledger = Stub(**{"/events": [], "/verify": verify_body, "/health": {},
                     "/retention/check": {"status": "no_estate_policy"}})
    eng = PackEngine(registry=Stub(**{"/agents": []}), ledger=ledger,
                     delegation=Stub(**{"/tokens": []}), governor=Stub(**{"/escalations": []}))
    return {m.name: m for m in eng.build(now=NOW).all_metrics()}["Ledger chain integrity"]


@pytest.mark.parametrize("ok", ["false", "true", "yes", 1, 2, 1.5, [0], ["x"], {"a": 1}])
def test_a_truthy_non_boolean_ok_is_never_intact(ok):
    m = _metric({"ok": ok, "length": 3, "reason": "x"})
    assert m.value != "INTACT", m
    assert m.status == "unavailable" and m.value is None
    assert "not a verification result" in (m.note or "")


@pytest.mark.parametrize("ok", [0, 0.0, "", None, [], {}])
def test_a_falsy_non_boolean_ok_is_not_a_result_either(ok):
    m = _metric({"ok": ok, "length": 3, "reason": "x"})
    assert m.status == "unavailable" and m.value is None


def test_a_missing_ok_key_is_not_a_result():
    m = _metric({"length": 3})
    assert m.status == "unavailable" and m.value is None


def test_true_is_intact():
    m = _metric({"ok": True, "length": 3})
    assert m.value == "INTACT" and m.status != "unavailable"


def test_false_with_a_reason_is_broken_as_before():
    m = _metric({"ok": False, "length": 3, "reason": "link break at index 2"})
    assert m.value == "BROKEN — link break at index 2"


def test_a_busy_ledger_is_still_unavailable_not_broken():
    m = _metric({"ok": False, "reason": "ledger busy: no consistent snapshot after 3 attempts"})
    assert m.status == "unavailable" and "ledger busy" in (m.note or "")


def test_the_note_does_not_echo_the_value():
    marker = "zz-marker-do-not-echo"
    m = _metric({"ok": marker, "length": 1})
    assert marker not in (m.note or "") and marker not in str(m.value)
