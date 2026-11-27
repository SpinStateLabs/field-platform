"""B2: a board pack that could not read something says so at the top, inside the signed bytes; a pack that read
everything shows nothing new and keeps its earlier shape."""
from __future__ import annotations

import pytest

from attestation_reporter.engine import (
    NO_ESTATE_POLICY,
    PERIOD_NOT_CHECKED,
    BoardPack,
    Metric,
    PackEngine,
    Section,
    ledger_reason,
    unread,
)
from attestation_reporter.render import INCOMPLETE_HEADLINE, render_html

QUERY = "GET http://127.0.0.1:8002/x"


def ok(name, note=None):
    return Metric(name=name, value=1, source_query=QUERY, note=note)


def gone(name, note="service not configured/reachable at generation time"):
    return Metric(name=name, source_query=QUERY, status="unavailable", note=note)


def listed(*metrics, integrity=None, retention=None):
    integrity = integrity or ok("Ledger chain integrity", "chain length 3")
    retention = retention or ok("retention count", "none among 2 resolvable manifest(s)")
    return unread([Section(title="s", metrics=[integrity, retention, *metrics])], integrity, retention)


def test_a_pack_that_read_everything_lists_nothing():
    assert listed(ok("a"), ok("b")) == []


def test_every_figure_with_no_value_is_listed_with_its_reason():
    assert listed(ok("a"), gone("Open spend escalations", "down")) == ["Open spend escalations: no value (down)"]


def test_a_figure_the_estate_sets_no_policy_for_is_not_called_unread():
    assert listed(gone("policy", f"{NO_ESTATE_POLICY} (unset)")) == []


def test_a_period_before_the_earliest_live_event_is_listed():
    note = "chain length 9; window starts before the earliest live event (segments archived: 1) — earlier not counted"
    assert listed(integrity=ok("Ledger chain integrity", note)) == [
        "Period not fully read: window starts before the earliest live event (segments archived: 1) — earlier not "
        "counted"]
    unchecked = "chain length 9; earliest-live check unavailable: ledger /health unreadable"
    assert listed(integrity=ok("Ledger chain integrity", unchecked)) == [
        "Period not fully read: earliest-live check unavailable: ledger /health unreadable"]


def test_an_unanswered_integrity_check_leaves_the_period_unchecked():
    lines = listed(integrity=gone("Ledger chain integrity", "ledger unreachable"))
    assert lines == ["Ledger chain integrity: no value (ledger unreachable)", PERIOD_NOT_CHECKED]


def test_a_lower_bound_retention_count_is_listed():
    row = ok("retention count", "unresolvable: x (r); a lower bound: 2 manifest ref(s) could not be read")
    assert listed(retention=row) == ["retention count: a lower bound: 2 manifest ref(s) could not be read"]


def test_a_whole_outage_is_headlined_incomplete_and_lists_every_unread_figure():
    pack = PackEngine().build()
    missing = [m for m in pack.all_metrics() if m.status == "unavailable"]
    assert missing and all(any(line.startswith(f"{m.name}: no value (") for line in pack.not_read) for m in missing)
    assert PERIOD_NOT_CHECKED in pack.not_read
    page = render_html(pack)
    assert INCOMPLETE_HEADLINE in page and page.index(INCOMPLETE_HEADLINE) < page.index("<h2>")
    assert pack.model_dump(mode="json")["not_read"] == pack.not_read


def test_a_complete_pack_has_no_block_and_no_key():
    full = PackEngine().build()
    data = full.model_dump(mode="json")
    data["not_read"] = []
    pack = BoardPack.model_validate(data)
    assert "not_read" not in pack.model_dump(mode="json")
    assert INCOMPLETE_HEADLINE not in render_html(pack)


class _Answer:
    status_code = 200
    headers: dict = {}

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class _Ledger:
    def __init__(self, retention):
        self.routes = {"/events": [], "/verify": {"ok": True, "length": 0}, "/health": {},
                       "/retention/check": retention}

    def get(self, target, **kwargs):
        return _Answer(self.routes[target.split("?")[0]])


def retention_lines(body):
    pack = PackEngine(ledger=_Ledger(body)).build()
    return [line for line in pack.not_read if "retention" in line.lower()]


@pytest.mark.parametrize("body", [
    {},
    {"status": "ok"},
    {"status": "ok", "estate_retention_days": "365"},
    {"status": "ok", "estate_retention_days": True},
    {"status": "violation", "estate_retention_days": None},
    {"status": "unavailable", "estate_retention_days": None},
    {"detail": "something else answered"},
], ids=repr)
def test_a_malformed_retention_answer_is_unread_not_a_missing_policy(body):
    lines = retention_lines(body)
    assert len(lines) == 2, lines
    assert not [line for line in lines if NO_ESTATE_POLICY in line]


def test_a_ledger_that_says_it_has_no_estate_policy_is_not_listed_as_unread():
    assert retention_lines({"status": "no_estate_policy", "estate_retention_days": None}) == []


@pytest.mark.parametrize("detail, reason", [
    ("FIELD_LEDGER_RETENTION_DAYS='made-up-value' is not an integer", "FIELD_LEDGER_RETENTION_DAYS=<value> is not an integer"),
    ("FIELD_LEDGER_RETENTION_DAYS=0 must be >= 1", "FIELD_LEDGER_RETENTION_DAYS=<value> must be >= 1"),
    (["odd"], "no readable reason given"),
], ids=["not-an-integer", "below-one", "unreadable"])
def test_an_invalid_estate_policy_is_unread_with_the_ledgers_reason_and_no_value(detail, reason):
    lines = retention_lines({"status": "no_estate_policy", "estate_retention_days": None, "detail": detail})
    assert len(lines) == 2, lines
    assert all(reason in line and "made-up-value" not in line for line in lines)


def test_a_value_with_both_quote_types_and_an_equals_sign_is_removed_whole():
    """The ledger quotes the value with ``repr``: with both quote types inside, the inner single quote is escaped."""
    value = "head-part'mid\"=made-up-value"
    lines = retention_lines({"status": "no_estate_policy", "estate_retention_days": None,
                             "detail": f"FIELD_LEDGER_RETENTION_DAYS={value!r} is not an integer"})
    assert len(lines) == 2, lines
    for line in lines:
        assert "FIELD_LEDGER_RETENTION_DAYS=<value> is not an integer" in line
        assert not [part for part in ("head-part", "mid", "made-up-value") if part in line], line


def test_the_plain_unset_detail_is_still_a_configured_absence():
    body = {"status": "no_estate_policy", "estate_retention_days": None,
            "detail": "no estate policy (FIELD_LEDGER_RETENTION_DAYS unset)"}
    assert retention_lines(body) == []


def test_a_long_or_multi_line_reason_stays_one_short_line():
    assert ledger_reason("a\nb\r\nc") == "a b c"
    assert len(ledger_reason("x" * 900)) == 200


def test_the_list_is_escaped_in_the_page():
    data = PackEngine().build().model_dump(mode="json")
    data["not_read"] = ["<script>x</script>"]
    page = render_html(BoardPack.model_validate(data))
    assert "<script>x" not in page and "&lt;script&gt;x&lt;/script&gt;" in page
