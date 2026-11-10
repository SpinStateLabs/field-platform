"""S7-28 — direct pins for four pure helpers that carry security and C-19 safety logic and had no
test naming them: _csv_cell (CSV injection), _domain_outcomes, _drill_not_restored,
_overview_digest. Tests only; current behaviour is pinned."""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient

from ops_console.api import (CSV_FORMULA_LEADS, DOMAIN_OUTCOMES, MAX_ERROR_TEXT, MAX_LISTED_ERRORS,
                             ServiceClient, _csv_cell, _domain_outcomes, _drill_not_restored,
                             _overview_digest, create_app)


# --- _csv_cell ---------------------------------------------------------------------------------------

def test_the_formula_leads_are_exactly_the_owasp_six():
    assert set(CSV_FORMULA_LEADS) == {"=", "+", "-", "@", "\t", "\r"}


@pytest.mark.parametrize("lead", CSV_FORMULA_LEADS)
def test_each_lead_gets_a_single_quote_prefix(lead):
    assert _csv_cell(f"{lead}cmd|' /C calc'!A0") == f"'{lead}cmd|' /C calc'!A0"
    assert _csv_cell(lead) == "'" + lead


@pytest.mark.parametrize("value", ["", "plain", "a=b", " =x", "'=x", "#=x", "\n=x", "x@y", "0"])
def test_other_strings_are_untouched(value):
    assert _csv_cell(value) == value


@pytest.mark.parametrize("value", [None, 0, -1, 3.5, True, ["="], {"a": "="}])
def test_non_strings_are_untouched(value):
    assert _csv_cell(value) is value


class _Stub:
    def __init__(self, body):
        self.body = body

    def get(self, path, **kw):
        body = self.body

        class R:
            status_code = 200

            def json(_):  # noqa: N805
                return body

        return R()

    post = get


def _console(events):
    s = ServiceClient(client=_Stub(events), base_url="http://t")
    others = {k: ServiceClient(client=_Stub({}), base_url="http://t") for k in (
        "registry", "delegation", "governor", "killswitch", "sentinel", "lifecycle", "attest",
        "crosswalk", "federation", "replay", "gateway")}
    return TestClient(create_app(ledger=s, **others))


def test_the_csv_export_neutralises_a_formula_in_agent_id_and_event_type():
    rows = [{"ts": "2026-01-01T00:00:00Z", "event_id": "e1", "event_type": "=HYPERLINK(\"x\")",
             "agent_id": "@evil", "payload": {"clause_id": "+cmd"}, "hash": "h", "prev_hash": "p"}]
    r = _console(rows).get("/api/events/export", params={"format": "csv"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    got = list(csv.reader(io.StringIO(r.text)))
    header, row = got[0], got[1]
    cell = dict(zip(header, row))
    assert cell["event_type"] == "'=HYPERLINK(\"x\")"
    assert cell["agent_id"] == "'@evil"
    assert cell["clause_id"] == "'+cmd"
    assert cell["payload_json"].startswith("{")  # json text, not a formula


# --- _domain_outcomes --------------------------------------------------------------------------------

def test_the_pinned_constants():
    assert MAX_LISTED_ERRORS == 50 and MAX_ERROR_TEXT == 200
    assert DOMAIN_OUTCOMES == ("killed", "already_killed", "skipped_retired", "error")


@pytest.mark.parametrize("data", [None, "x", 5, [], {}, {"results": "no"}, {"results": None},
                                  {"detail": "text"}, {"detail": {"results": 3}}])
def test_no_per_agent_results_is_none_and_empty(data):
    assert _domain_outcomes(data) == (None, [])


def test_counts_per_outcome_and_an_empty_results_list():
    assert _domain_outcomes({"results": []}) == (dict.fromkeys(DOMAIN_OUTCOMES, 0), [])
    counts, errors = _domain_outcomes({"results": [
        {"outcome": "killed"}, {"outcome": "killed"}, {"outcome": "already_killed"},
        {"outcome": "skipped_retired"}]})
    assert counts == {"killed": 2, "already_killed": 1, "skipped_retired": 1, "error": 0}
    assert errors == []


def test_results_are_read_from_detail_when_the_body_has_none():
    counts, errors = _domain_outcomes({"detail": {"results": [{"outcome": "killed"},
                                                              {"outcome": "error", "agent_id": "a", "error": "502: x"}]}})
    assert counts["killed"] == 1 and counts["error"] == 1
    assert errors == [{"agent_id": "a", "error": "502: x"}]


def test_the_body_wins_over_detail():
    counts, _ = _domain_outcomes({"results": [{"outcome": "killed"}], "detail": {"results": [{"outcome": "error"}]}})
    assert counts["killed"] == 1 and counts["error"] == 0


@pytest.mark.parametrize("row", [{"outcome": "weird"}, {"outcome": None}, {}, "string-row", None, 7, ["x"]])
def test_an_unknown_outcome_and_a_non_dict_row_count_as_errors(row):
    counts, errors = _domain_outcomes({"results": [row]})
    assert counts["error"] == 1 and sum(counts.values()) == 1
    assert len(errors) == 1


def test_an_error_row_uses_its_own_text_else_names_the_outcome():
    _, errors = _domain_outcomes({"results": [
        {"outcome": "error", "agent_id": "a1", "error": "502: down"},
        {"outcome": "weird", "agent_id": "a2"},
        "junk"]})
    assert errors[0] == {"agent_id": "a1", "error": "502: down"}
    assert errors[1] == {"agent_id": "a2", "error": "outcome 'weird'"}
    assert errors[2] == {"agent_id": None, "error": "outcome None"}


def test_errors_are_capped_at_50_listed_but_the_count_stays_exact():
    results = [{"outcome": "error", "agent_id": f"a{i}", "error": "x"} for i in range(MAX_LISTED_ERRORS + 30)]
    counts, errors = _domain_outcomes({"results": results})
    assert counts["error"] == MAX_LISTED_ERRORS + 30
    assert len(errors) == MAX_LISTED_ERRORS
    assert errors[0]["agent_id"] == "a0" and errors[-1]["agent_id"] == f"a{MAX_LISTED_ERRORS - 1}"


def test_each_error_text_is_cut_to_200_characters():
    _, errors = _domain_outcomes({"results": [{"outcome": "error", "agent_id": "a", "error": "e" * 500}]})
    assert errors[0]["error"] == "e" * MAX_ERROR_TEXT


# --- _drill_not_restored -----------------------------------------------------------------------------

def test_restored_true_is_none():
    assert _drill_not_restored({"restored": True, "restored_status": "active"}) is None


@pytest.mark.parametrize("data", [{}, {"restored": False}, {"restored": None}, {"restored": "true"},
                                  {"restored": 1}, None, "restored", [], 5])
def test_anything_but_a_true_bool_is_a_message(data):
    msg = _drill_not_restored(data)
    assert msg is not None and msg.startswith("drill did not restore the agent (restored=")


def test_the_message_names_restored_and_status():
    assert _drill_not_restored({"restored": False, "restored_status": "killed"}) == \
        "drill did not restore the agent (restored=False, restored_status=killed)"
    assert _drill_not_restored(None) == \
        "drill did not restore the agent (restored=None, restored_status=None)"


# --- _overview_digest --------------------------------------------------------------------------------

BASE = {"generated_at": "t0", "agents": [1, 2], "kill": {"a": 1, "b": 2}, "ledger": {"ok": True}}


def test_the_digest_ignores_generated_at():
    assert _overview_digest(BASE) == _overview_digest({**BASE, "generated_at": "t1"})
    no_stamp = {k: v for k, v in BASE.items() if k != "generated_at"}
    assert _overview_digest(BASE) == _overview_digest(no_stamp)


@pytest.mark.parametrize("change", [
    {"agents": [1, 2, 3]}, {"kill": {"a": 1, "b": 3}}, {"ledger": {"ok": False}}, {"extra": 1}])
def test_the_digest_changes_when_any_section_changes(change):
    assert _overview_digest({**BASE, **change}) != _overview_digest(BASE)


def test_the_digest_is_stable_across_key_order_and_is_sha256_hex():
    reordered = {"ledger": {"ok": True}, "kill": {"b": 2, "a": 1}, "agents": [1, 2], "generated_at": "z"}
    d = _overview_digest(reordered)
    assert d == _overview_digest(BASE)
    assert len(d) == 64 and int(d, 16) >= 0


def test_the_digest_survives_a_non_json_value():
    assert len(_overview_digest({"when": object.__new__(type("X", (), {}))})) == 64
