"""C-1205: direct tests of ``sealed_ledger.filters`` and ``sealed_ledger.retention``.

Both modules were reached only through the store, the API and the CLI. The cases below call them directly, with
made-up data, a stub store and a stub registry. Nothing here touches a file, a real ledger or the network, and neither
module deletes anything: ``retention_check`` only reports (see ``test_the_check_is_read_only``). Each test names the
mutant it is meant to kill.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from field_core.ledger import GENESIS_HASH, make_event
from sealed_ledger import retention
from sealed_ledger.filters import EventFilter, InvalidTimeBound, parse_bound, parse_instant
from sealed_ledger.retention import RETENTION_ENV, estate_retention_days, retention_check

# ------------------------------------------------------------------------------------------------ filters


def _event(ts: str, agent_id: str = "a1", event_type: str = "action"):
    return make_event(event_type, {}, prev_hash=GENESIS_HASH, agent_id=agent_id, ts=ts, event_id="e")


def test_parse_bound_none_is_none_and_names_the_bound_in_the_error():
    assert parse_bound("since", None) is None
    with pytest.raises(InvalidTimeBound) as exc:
        parse_bound("until", "next tuesday")
    assert "until" in str(exc.value) and "'next tuesday'" in str(exc.value)  # the name and the offending text
    assert isinstance(exc.value, ValueError)  # callers that catch ValueError keep working


@pytest.mark.parametrize("not_text", [20260912, 1.5, b"2026-09-12", ["2026-09-12"]])
def test_a_bound_that_is_not_text_is_refused_the_same_way(not_text):
    # kills: narrowing the except to ValueError only (fromisoformat raises TypeError for these)
    with pytest.raises(InvalidTimeBound):
        parse_bound("since", not_text)


def test_parse_instant_treats_naive_and_date_only_as_utc_and_offsets_as_the_same_instant():
    z = parse_instant("2026-09-12T10:00:00Z")
    assert z == parse_instant("2026-09-12T10:00:00+00:00") == parse_instant("2026-09-12T10:00:00")
    assert z == parse_instant("2026-09-12T06:00:00-04:00")
    assert parse_instant("2026-09-12") == parse_instant("2026-09-12T00:00:00Z")
    assert parse_instant("2026-09-12T10:00:00").tzinfo is not None


def test_both_bounds_are_inclusive_and_one_microsecond_outside_is_out():
    # kills: ``ts < since`` -> ``ts <= since`` and ``ts > until`` -> ``ts >= until``
    flt = EventFilter(since="2026-09-12T10:00:00Z", until="2026-09-12T11:00:00Z")
    assert flt.matches(0, _event("2026-09-12T10:00:00+00:00"))
    assert flt.matches(1, _event("2026-09-12T11:00:00+00:00"))
    assert not flt.matches(2, _event("2026-09-12T09:59:59.999999+00:00"))
    assert not flt.matches(3, _event("2026-09-12T11:00:00.000001+00:00"))


def test_an_inverted_window_selects_nothing_and_is_not_an_error():
    flt = EventFilter(since="2026-09-12T12:00:00Z", until="2026-09-12T10:00:00Z")
    assert not any(flt.matches(i, _event(f"2026-09-12T{h:02d}:00:00+00:00")) for i, h in enumerate((9, 10, 11, 12, 13)))


def test_agent_and_type_are_exact_matches_and_combine_with_a_window():
    flt = EventFilter(agent_id="a1", event_type="action", since="2026-09-12T00:00:00Z")
    assert flt.matches(0, _event("2026-09-12T10:00:00+00:00"))
    assert not flt.matches(0, _event("2026-09-12T10:00:00+00:00", agent_id="a1-other"))   # not a prefix match
    assert not flt.matches(0, _event("2026-09-12T10:00:00+00:00", agent_id="A1"))          # case matters
    assert not flt.matches(0, _event("2026-09-12T10:00:00+00:00", event_type="action2"))
    assert not flt.matches(0, _event("2026-09-11T23:59:59+00:00"))


def test_without_a_time_bound_the_stored_ts_is_never_parsed():
    # kills: parsing event.ts before the agent/type checks or before the "no bounds" early return
    bad = _event("yesterday")
    assert EventFilter().matches(0, bad)
    assert EventFilter(agent_id="a1").matches(0, bad)
    assert not EventFilter(agent_id="someone-else").matches(0, bad)


def test_a_non_matching_agent_is_decided_before_its_ts_is_read():
    # Current behaviour, pinned: a bad ts on a row for ANOTHER agent does not break a windowed read for this agent.
    # kills: moving the ts parse above the agent check
    flt = EventFilter(agent_id="a1", since="2026-01-01T00:00:00Z")
    assert flt.matches(0, _event("2026-09-12T10:00:00+00:00")) is True
    assert flt.matches(1, _event("yesterday", agent_id="a2")) is False


def test_a_bad_ts_on_a_candidate_row_names_its_index():
    flt = EventFilter(agent_id="a1", since="2026-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="index 7") as exc:
        flt.matches(7, _event("yesterday"))
    assert not isinstance(exc.value, InvalidTimeBound)  # a bad stored row is not a bad request


def test_bounds_are_parsed_once_at_construction_and_a_bad_bound_fails_there():
    with pytest.raises(InvalidTimeBound):
        EventFilter(since="not a time")
    with pytest.raises(InvalidTimeBound):
        EventFilter(until="")  # the empty string is a bound that does not parse, not "no bound"


def test_as_dict_returns_the_raw_text_and_exactly_four_keys():
    flt = EventFilter(agent_id="a1", event_type="t", since="2026-09-12", until="2026-09-12T10:00:00Z")
    assert flt.as_dict() == {"since": "2026-09-12", "until": "2026-09-12T10:00:00Z", "agent_id": "a1", "event_type": "t"}
    assert EventFilter().as_dict() == {"since": None, "until": None, "agent_id": None, "event_type": None}


# --------------------------------------------------------------------------------------------- retention


@pytest.mark.parametrize("raw,expected", [("365", 365), (" 365 ", 365), ("1", 1), ("\t30\n", 30)])
def test_estate_retention_days_accepts_a_plain_positive_integer(monkeypatch, raw, expected):
    monkeypatch.setenv(RETENTION_ENV, raw)
    assert estate_retention_days() == (expected, None)


def test_estate_retention_days_unset_or_blank_is_no_policy_and_no_complaint(monkeypatch):
    monkeypatch.delenv(RETENTION_ENV, raising=False)
    assert estate_retention_days() == (None, None)
    for blank in ("", "   ", "\n"):
        monkeypatch.setenv(RETENTION_ENV, blank)
        assert estate_retention_days() == (None, None)


@pytest.mark.parametrize("raw", ["0", "-5", "-1"])
def test_estate_retention_days_below_one_is_refused_with_the_number(monkeypatch, raw):
    monkeypatch.setenv(RETENTION_ENV, raw)
    days, problem = estate_retention_days()
    assert days is None and problem == f"{RETENTION_ENV}={int(raw)} must be >= 1"


@pytest.mark.parametrize("raw", ["3.5", "1e3", "seven", "12 months", "0x10"])
def test_estate_retention_days_not_an_integer_is_no_policy_with_a_reason(monkeypatch, raw):
    monkeypatch.setenv(RETENTION_ENV, raw)
    days, problem = estate_retention_days()
    assert days is None and "is not an integer" in problem and RETENTION_ENV in problem


def test_the_complaint_never_echoes_more_than_forty_characters_of_the_value(monkeypatch):
    # kills: dropping the ``[:40]`` cut (an env value is operator text; the check must not copy it whole)
    long_junk = "q" * 300
    monkeypatch.setenv(RETENTION_ENV, long_junk)
    days, problem = estate_retention_days()
    assert days is None and "q" * 40 in problem and "q" * 41 not in problem
    assert len(problem) < 120


class _Store:
    """A ledger state source that reports a fixed state and refuses everything else (the check must be read-only)."""

    def __init__(self, state=None, error=None):
        self._state, self._error = state or {}, error
        self.calls: list[str] = []

    def retention_state(self):
        self.calls.append("retention_state")
        if self._error is not None:
            raise self._error
        return dict(self._state)

    def __getattr__(self, name):  # any other store method is a call the check must never make
        raise AssertionError(f"retention_check touched store.{name}")


class _Registry:
    def __init__(self, agents=None, error=None, returns=None):
        self._agents, self._error, self._returns = agents or [], error, returns

    def list_agents(self):
        if self._error is not None:
            raise self._error
        return self._returns if self._returns is not None else self._agents


def _manifests(monkeypatch, table):
    """``table``: manifest_ref -> days (a resolved manifest) or a reason string (an unresolvable one)."""
    def fake(ref):
        value = table[ref]
        if isinstance(value, str):
            return None, value
        return SimpleNamespace(ledger=SimpleNamespace(retention_days=value)), "ok"
    monkeypatch.setattr(retention, "resolve_manifest_detail", fake)


def _agent(agent_id, ref):
    return {"agent_id": agent_id, "manifest_ref": ref}


GOOD_STATE = {"earliest_live_index": 4, "earliest_live_ts": "2026-09-12T10:00:00+00:00", "segments": 2,
              "archived_segments": 1, "pending_moves": [], "legal_hold": None}


def test_all_manifests_within_the_estate_policy_is_ok(monkeypatch):
    monkeypatch.setenv(RETENTION_ENV, "365")
    _manifests(monkeypatch, {"m1": 365, "m2": 30})
    out = retention_check(_Store(GOOD_STATE), _Registry([_agent("a", "m1"), _agent("b", "m2")]))
    assert out.ok is True and out.status == "ok" and out.detail is None
    assert out.estate_retention_days == 365 and out.policy_source == RETENTION_ENV
    assert out.manifests_checked == 2 and out.max_manifest_retention_days == 365 and out.offending == []
    assert out.earliest_live_index == 4 and out.segments == 2 and out.archived_segments == 1


def test_a_manifest_that_asks_for_exactly_the_estate_days_is_met_and_one_more_is_a_violation(monkeypatch):
    # kills: ``days > estate`` -> ``days >= estate``
    monkeypatch.setenv(RETENTION_ENV, "365")
    _manifests(monkeypatch, {"eq": 365, "over": 366})
    out = retention_check(_Store(GOOD_STATE), _Registry([_agent("a", "eq"), _agent("b", "over")]))
    assert out.status == "violation" and out.ok is False
    assert out.offending == [{"agent_id": "b", "retention_days": 366}]


def test_max_manifest_days_is_taken_over_every_resolved_manifest_not_only_the_offending(monkeypatch):
    # kills: computing the max inside the offending branch
    monkeypatch.setenv(RETENTION_ENV, "3650")
    _manifests(monkeypatch, {"m1": 30, "m2": 2555, "m3": 90})
    out = retention_check(_Store(GOOD_STATE), _Registry([_agent("a", "m1"), _agent("b", "m2"), _agent("c", "m3")]))
    assert out.status == "ok" and out.offending == [] and out.max_manifest_retention_days == 2555


def test_agents_without_a_manifest_ref_are_counted_and_skipped_for_none_and_empty(monkeypatch):
    # kills: ``if not ref`` -> ``if ref is None``
    monkeypatch.setenv(RETENTION_ENV, "365")
    _manifests(monkeypatch, {"m1": 30})
    out = retention_check(_Store(GOOD_STATE), _Registry([_agent("a", None), _agent("b", ""), _agent("c", "m1"),
                                                         {"agent_id": "d"}]))
    assert out.agents_without_manifest == 3 and out.manifests_checked == 1 and out.status == "ok"


def test_an_unresolvable_manifest_outranks_a_violation(monkeypatch):
    # kills: swapping the ``unresolvable`` and ``violation`` branches
    monkeypatch.setenv(RETENTION_ENV, "365")
    _manifests(monkeypatch, {"big": 2555, "gone": "missing"})
    out = retention_check(_Store(GOOD_STATE), _Registry([_agent("a", "big"), _agent("b", "gone")]))
    assert out.status == "unresolvable" and out.ok is False
    assert out.offending == [{"agent_id": "a", "retention_days": 2555}]  # the violation is still listed
    assert out.unresolvable == [{"agent_id": "b", "manifest_ref": "gone", "reason": "missing"}]
    assert out.manifests_checked == 1


def test_no_estate_policy_outranks_unresolvable_and_a_garbage_policy_says_why(monkeypatch):
    # kills: moving the ``unresolvable`` branch above the ``estate is None`` branch
    monkeypatch.delenv(RETENTION_ENV, raising=False)
    _manifests(monkeypatch, {"gone": "invalid"})
    unset = retention_check(_Store(GOOD_STATE), _Registry([_agent("a", "gone")]))
    assert unset.status == "no_estate_policy" and unset.ok is False and unset.policy_source is None
    assert unset.detail == f"no estate policy ({RETENTION_ENV} unset)"
    monkeypatch.setenv(RETENTION_ENV, "abc")
    garbage = retention_check(_Store(GOOD_STATE), _Registry([_agent("a", "gone")]))
    assert garbage.status == "no_estate_policy" and "is not an integer" in garbage.detail
    assert "unset" not in garbage.detail  # the complaint replaces the "unset" line, it does not add to it


def test_an_unreadable_ledger_state_is_unavailable_never_ok_and_blanks_every_ledger_field(monkeypatch):
    monkeypatch.setenv(RETENTION_ENV, "365")
    _manifests(monkeypatch, {"m1": 30})
    out = retention_check(_Store(error=OSError("disk gone")), _Registry([_agent("a", "m1")]))
    assert out.status == "unavailable" and out.ok is False
    assert "ledger state unreadable: OSError: disk gone" in out.detail
    assert (out.earliest_live_index, out.earliest_live_ts, out.segments, out.archived_segments, out.pending_moves,
            out.legal_hold) == (None, None, None, None, None, None)  # never a made-up "no hold, one segment"
    assert out.manifests_checked == 1  # the manifest half of the check still ran


def test_unavailable_outranks_no_estate_policy(monkeypatch):
    # kills: testing ``estate is None`` before the unavailable condition
    monkeypatch.delenv(RETENTION_ENV, raising=False)
    out = retention_check(_Store(error=RuntimeError("x")), _Registry([]))
    assert out.status == "unavailable"


def test_error_text_is_cut_at_two_hundred_characters(monkeypatch):
    # kills: dropping ``[:200]`` on either the ledger or the registry message
    monkeypatch.setenv(RETENTION_ENV, "365")
    out = retention_check(_Store(error=RuntimeError("s" * 500)), _Registry(error=ConnectionError("r" * 500)))
    assert "s" * 200 in out.detail and "s" * 201 not in out.detail
    assert "r" * 200 in out.detail and "r" * 201 not in out.detail


def test_a_registry_that_is_missing_raises_or_returns_a_non_list_is_unavailable(monkeypatch):
    monkeypatch.setenv(RETENTION_ENV, "365")
    cases = [(None, "registry not configured for this ledger app"),
             (_Registry(error=TimeoutError("slow")), "registry unavailable: TimeoutError: slow"),
             (_Registry(returns={"agents": []}), "registry unavailable: TypeError: list_agents returned dict")]
    for registry, expect in cases:
        out = retention_check(_Store(GOOD_STATE), registry)
        assert out.status == "unavailable" and out.ok is False and expect in out.detail, (registry, out.detail)
        assert out.manifests_checked == 0 and out.max_manifest_retention_days is None


def test_agents_are_walked_in_agent_id_order_and_an_id_that_is_none_does_not_crash(monkeypatch):
    # kills: removing ``sorted(...)`` (the served and rendered lists must not depend on the registry's order)
    monkeypatch.setenv(RETENTION_ENV, "10")
    _manifests(monkeypatch, {"m": 99, "gone": "missing"})
    agents = [_agent("zeta", "m"), _agent("alpha", "m"), _agent(None, "gone"), _agent("mid", "gone")]
    out = retention_check(_Store(GOOD_STATE), _Registry(agents))
    assert [o["agent_id"] for o in out.offending] == ["alpha", "zeta"]
    assert [u["agent_id"] for u in out.unresolvable] == [None, "mid"]  # sorted on str(): "None" < "mid" (capital N first)


def test_the_check_is_read_only(monkeypatch):
    # HIGH CARE guard: the only ledger call the check may make is ``retention_state``; any other attribute access on
    # the stub store (an apply, an archive, a hold change) raises AssertionError.
    monkeypatch.setenv(RETENTION_ENV, "365")
    _manifests(monkeypatch, {"m1": 2555})
    store = _Store(GOOD_STATE)
    out = retention_check(store, _Registry([_agent("a", "m1")]))
    assert out.status == "violation" and store.calls == ["retention_state"]
