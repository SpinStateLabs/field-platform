"""B2: a board pack that could not read something says so at the top, inside the signed bytes; a pack that read
everything shows nothing new and keeps its earlier shape."""
from __future__ import annotations

from attestation_reporter.engine import (
    NO_ESTATE_POLICY,
    PERIOD_NOT_CHECKED,
    BoardPack,
    Metric,
    PackEngine,
    Section,
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


def test_the_list_is_escaped_in_the_page():
    data = PackEngine().build().model_dump(mode="json")
    data["not_read"] = ["<script>x</script>"]
    page = render_html(BoardPack.model_validate(data))
    assert "<script>x" not in page and "&lt;script&gt;x&lt;/script&gt;" in page
