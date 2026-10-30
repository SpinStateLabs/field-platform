"""C-247 (reviewer C-231 F-C231-1; R-15 F-R15-2): a 200 answer of the wrong shape fails ONE metric
closed. A scalar from the ledger's /events used to be published as the count (and signed) or to
raise out of ``build``; a token with a naive or malformed ``expires_at`` raised out of ``build``."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from attestation_reporter.engine import PackEngine

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
BAD_BODIES = [42, "oops", True, 3.5, {"a": 1}, None]


class Answer:
    def __init__(self, body):
        self.status_code = 200
        self._body = body

    def json(self):
        return self._body


class Stub:
    """An httpx-like client: ``routes`` maps a path (no query string) to a JSON body."""

    def __init__(self, **routes):
        self.routes = routes

    def get(self, target):
        return Answer(self.routes.get(target.split("?")[0], []))


UNSET = object()  # None is itself a body under test


def engine(ledger_events=UNSET, tokens=UNSET, agents=UNSET):
    ledger = Stub(**{"/events": [] if ledger_events is UNSET else ledger_events,
                     "/verify": {"ok": True, "length": 0}, "/health": {},
                     "/retention/check": {"status": "no_estate_policy"}})
    return PackEngine(
        registry=Stub(**{"/agents": [] if agents is UNSET else agents}), ledger=ledger,
        delegation=Stub(**{"/tokens": [] if tokens is UNSET else tokens}),
        governor=Stub(**{"/escalations": []}))


def by_name(pack):
    return {m.name: m for m in pack.all_metrics()}


@pytest.mark.parametrize("body", BAD_BODIES, ids=repr)
def test_a_non_list_events_answer_makes_every_event_metric_unavailable(body):
    metrics = by_name(engine(ledger_events=body).build(now=NOW))
    event_metrics = [m for m in metrics.values() if "/events" in m.source_query]
    assert len(event_metrics) >= 10
    for m in event_metrics:
        assert m.status == "unavailable" and m.value is None, (m.name, m.value)
    # the wrong shape names itself where the shared message is not the generic one
    assert "not a list" in metrics["Conformance ALLOW verdicts"].note
    assert type(body).__name__ in metrics["Conformance ALLOW verdicts"].note
    # one bad service does not take the others down
    assert metrics["Agents registered"].value == 0 and metrics["Agents registered"].status == "ok"
    assert metrics["Delegation tokens issued (all time)"].status == "ok"


def test_a_well_formed_events_answer_still_counts():
    events = [{"agent_id": "a1", "ts": "2026-07-01T00:00:00+00:00", "payload": {}}] * 3
    m = by_name(engine(ledger_events=events).build(now=NOW))["Conformance ALLOW verdicts"]
    assert m.status == "ok" and m.value == 3


@pytest.mark.parametrize("body", BAD_BODIES, ids=repr)
def test_a_non_list_agents_answer_makes_the_agent_metrics_unavailable(body):
    metrics = by_name(engine(agents=body).build(now=NOW))
    for name in ("Agents registered", "Agents in production (active)", "Agents currently killed"):
        assert metrics[name].status == "unavailable" and metrics[name].value is None
    assert metrics["Conformance ALLOW verdicts"].status == "ok"


def test_the_conformance_rate_is_unavailable_when_a_verdict_count_is():
    m = by_name(engine(ledger_events=42).build(now=NOW))
    rate = m["Conformance rate (ALLOW / all verdicts incl. shadow)"]
    assert rate.status == "unavailable" and rate.value is None


# --- R-15 F-R15-2: a token whose expires_at cannot be compared ------------------------------

SOON = (NOW + timedelta(days=5)).isoformat()


@pytest.mark.parametrize("bad", [
    {"revoked": False, "expires_at": "2026-07-20T00:00:00"},        # naive: TypeError on compare
    {"revoked": False, "expires_at": "not a date"},                 # ValueError
    {"revoked": False},                                             # KeyError
    {"revoked": False, "expires_at": None},                         # AttributeError
], ids=["naive", "malformed", "missing", "null"])
def test_a_token_with_an_unusable_expiry_makes_only_the_expiring_metric_unavailable(bad):
    tokens = [{"revoked": False, "expires_at": SOON}, bad]
    metrics = by_name(engine(tokens=tokens).build(now=NOW))
    expiring = metrics["Authorities expiring within 30 days"]
    assert expiring.status == "unavailable" and expiring.value is None
    assert "could not be computed" in expiring.note
    assert metrics["Delegation tokens issued (all time)"].value == 2
    assert metrics["Tokens revoked (all time)"].value == 0


def test_well_formed_tokens_are_still_counted_as_expiring():
    tokens = [{"revoked": False, "expires_at": SOON},
              {"revoked": False, "expires_at": (NOW + timedelta(days=90)).isoformat()},
              {"revoked": True, "expires_at": SOON}]
    m = by_name(engine(tokens=tokens).build(now=NOW))["Authorities expiring within 30 days"]
    assert m.status == "ok" and m.value == 1
