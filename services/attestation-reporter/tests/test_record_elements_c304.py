"""C-304 (reviewer C-271 F-C271-1/-2/-3): a count is a count of RECORDS. A list whose elements are not
dicts (`[1, 2]`) used to be published, and signed, as two tokens/escalations/agents/events; every
counted endpoint now makes that metric unavailable naming the element type. Also pinned: a non-list
`/tokens` and `/escalations` body (the two endpoints the C-247 file did not feed), and the `basis` and
wording of every unavailable metric."""

from __future__ import annotations

import pytest

from attestation_reporter.engine import PackEngine
from test_wrong_shape_answers_c247 import BAD_BODIES, NOW, UNSET, Stub, by_name

BAD_LISTS = [([1, 2], "int"), (["a", "b"], "str"), ([None], "NoneType"), ([[1], [2]], "list"),
             ([{"agent_id": "a1"}, 3], "int"), ([True], "bool")]
TOKEN_METRICS = ("Delegation tokens issued (all time)", "Tokens revoked (all time)",
                 "Authorities expiring within 30 days")
AGENT_METRICS = ("Agents registered", "Agents in production (active)", "Agents currently killed")
ESCALATIONS = "Open spend escalations (human queue)"
GOOD_EVENTS = [{"agent_id": "a1", "ts": "2026-07-01T00:00:00+00:00", "payload": {"token_id": "t1"}}] * 3


def engine(events=UNSET, tokens=UNSET, agents=UNSET, escalations=UNSET):
    pick = lambda v: [] if v is UNSET else v          # noqa: E731  (None is itself a body under test)
    return PackEngine(
        registry=Stub(**{"/agents": pick(agents)}),
        ledger=Stub(**{"/events": pick(events), "/verify": {"ok": True, "length": 0}, "/health": {},
                       "/retention/check": {"status": "no_estate_policy"}}),
        delegation=Stub(**{"/tokens": pick(tokens)}), governor=Stub(**{"/escalations": pick(escalations)}))


def unavailable(m, kind=None):
    assert m.status == "unavailable" and m.value is None, (m.name, m.status, m.value)
    if kind is not None:
        assert f"list holding {kind}, not records — figure not published" in m.note, m.note


# --- F-C271-2: a list of non-records ----------------------------------------------------------


@pytest.mark.parametrize(("body", "kind"), BAD_LISTS, ids=lambda v: repr(v)[:20])
def test_a_list_of_non_records_makes_every_token_metric_unavailable(body, kind):
    metrics = by_name(engine(tokens=body).build(now=NOW))
    for name in TOKEN_METRICS:
        unavailable(metrics[name], kind)
        assert metrics[name].basis == "point_in_time"
    assert metrics[ESCALATIONS].status == "ok"                  # one bad service does not take the others down


@pytest.mark.parametrize(("body", "kind"), BAD_LISTS, ids=lambda v: repr(v)[:20])
def test_a_list_of_non_records_makes_the_escalation_metric_unavailable(body, kind):
    metrics = by_name(engine(escalations=body).build(now=NOW))
    unavailable(metrics[ESCALATIONS], kind)
    assert metrics[ESCALATIONS].basis == "point_in_time"
    assert metrics["Delegation tokens issued (all time)"].status == "ok"


@pytest.mark.parametrize(("body", "kind"), BAD_LISTS, ids=lambda v: repr(v)[:20])
def test_a_list_of_non_records_makes_the_agent_metrics_unavailable(body, kind):
    metrics = by_name(engine(agents=body).build(now=NOW))
    for name in AGENT_METRICS:
        unavailable(metrics[name], kind)
    assert metrics["Delegation tokens issued (all time)"].status == "ok"


@pytest.mark.parametrize(("body", "kind"), BAD_LISTS, ids=lambda v: repr(v)[:20])
def test_a_list_of_non_records_makes_every_event_metric_unavailable(body, kind):
    """Every metric whose source is /events: the windowed counts, the sweep rows and the canary row."""
    metrics = by_name(engine(events=body).build(now=NOW))
    event_metrics = [m for m in metrics.values() if "/events" in m.source_query]
    assert len(event_metrics) >= 12
    for m in event_metrics:
        unavailable(m)
        assert m.basis == "window", (m.name, m.basis)
    assert "list holding" in metrics["Conformance ALLOW verdicts"].note
    assert kind in metrics["Conformance ALLOW verdicts"].note
    for name in ("Re-attestation due (sweep events)", "Distinct tokens flagged as expiring"):
        unavailable(metrics[name], kind)
    assert metrics["Agents registered"].status == "ok"


def test_the_sweep_rows_refuse_a_list_of_non_records():
    metrics = by_name(engine(events=[1, 2]).build(now=NOW))
    sweep = [m for m in metrics.values() if "sweep" in m.name.lower() or "flagged" in m.name.lower()]
    assert len(sweep) >= 2
    for m in sweep:
        unavailable(m, "int")


def test_the_gate_verification_row_refuses_a_list_of_non_records():
    metrics = by_name(engine(events=[1, 2]).build(now=NOW))
    [row] = [m for m in metrics.values() if m.name.startswith("Gate-verification events")]
    unavailable(row)


@pytest.mark.parametrize("name", [*TOKEN_METRICS, ESCALATIONS, *AGENT_METRICS])
def test_well_formed_records_and_empty_lists_still_count(name):
    tokens = [{"revoked": False, "expires_at": "2026-07-20T00:00:00+00:00"}, {"revoked": True,
              "expires_at": "2026-07-20T00:00:00+00:00"}]
    full = by_name(engine(tokens=tokens, escalations=[{"agent_id": "a"}], agents=[{"agent_id": "a",
                   "status": "active"}]).build(now=NOW))
    assert full[name].status == "ok" and full[name].value is not None
    empty = by_name(engine().build(now=NOW))
    assert empty[name].status == "ok" and empty[name].value == 0


def test_well_formed_events_still_count():
    m = by_name(engine(events=GOOD_EVENTS).build(now=NOW))["Conformance ALLOW verdicts"]
    assert m.status == "ok" and m.value == 3


# --- F-C271-1: a non-list body on /tokens and /escalations -------------------------------------


@pytest.mark.parametrize("body", BAD_BODIES, ids=repr)
def test_a_non_list_tokens_answer_makes_all_three_token_metrics_unavailable(body):
    metrics = by_name(engine(tokens=body).build(now=NOW))
    for name in TOKEN_METRICS:
        unavailable(metrics[name])
        assert "not a list" in metrics[name].note and type(body).__name__ in metrics[name].note
    assert metrics["Agents registered"].status == "ok" and metrics[ESCALATIONS].status == "ok"


@pytest.mark.parametrize("body", BAD_BODIES, ids=repr)
def test_a_non_list_escalations_answer_makes_the_escalation_metric_unavailable(body):
    metrics = by_name(engine(escalations=body).build(now=NOW))
    unavailable(metrics[ESCALATIONS])
    assert "not a list" in metrics[ESCALATIONS].note and type(body).__name__ in metrics[ESCALATIONS].note
    assert metrics["Delegation tokens issued (all time)"].status == "ok"


# --- F-C271-3: basis and wording of the unavailable metrics ------------------------------------


@pytest.mark.parametrize(("kwargs", "name", "basis"), [
    ({"tokens": 42}, "Delegation tokens issued (all time)", "point_in_time"),
    ({"escalations": 42}, ESCALATIONS, "point_in_time"),
    ({"agents": 42}, "Agents registered", "point_in_time"),
    ({"events": 42}, "Conformance ALLOW verdicts", "window")])
def test_an_unavailable_wrong_shape_metric_keeps_its_basis_and_says_it_was_not_published(kwargs, name, basis):
    m = by_name(engine(**kwargs).build(now=NOW))[name]
    unavailable(m)
    assert m.basis == basis
    assert m.note == "answered 200 with a int, not a list — figure not published"
