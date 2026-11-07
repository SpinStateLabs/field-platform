"""One unreadable timestamp must not lose the whole sweep (scout proposal P-1).

``sweep`` used to call ``_parse_ts`` unguarded on a token's ``expires_at`` and an
agent's ``attested_at`` / ``created_at``: one bad value raised and every other
finding of the sweep was lost. The bad record is now skipped and named in
``report.unreadable_timestamps`` (record id and field name only, never the value).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from lifecycle_manager.engine import LifecycleEngine

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
ROSTER = "owner,department\nAP Team Lead,finance\n"
MARKER = "zz-marker-do-not-echo"


class _Registry:
    def __init__(self, agents):
        self._agents = agents

    def list_agents(self):
        return self._agents


class _Delegation:
    def __init__(self, tokens):
        self._tokens = tokens

    def get(self, path):
        assert path == "/tokens"
        return self._tokens


def _token(token_id, expires_at, agent_id="a-good"):
    return {"token_id": token_id, "agent_id": agent_id, "granted_by": "AP Team Lead",
            "expires_at": expires_at, "scope": ["read"], "revoked": False}


def _agent(agent_id, created_at, attested_at=None):
    return {"agent_id": agent_id, "owner": "AP Team Lead", "status": "active",
            "created_at": created_at, "attested_at": attested_at, "attested_by": None}


def _engine(agents, tokens):
    return LifecycleEngine(registry=_Registry(agents), delegation=_Delegation(tokens))


GOOD_EXPIRING = (NOW + timedelta(days=10)).isoformat()
GOOD_STALE = (NOW - timedelta(days=400)).isoformat()


def test_a_garbage_expires_at_is_skipped_named_and_the_neighbour_still_reported():
    tokens = [_token("t-bad", MARKER), _token("t-good", GOOD_EXPIRING)]
    report = _engine([], tokens).sweep(ROSTER, now=NOW)
    assert [e.token_id for e in report.expiring] == ["t-good"]
    assert [(u.kind, u.record_id, u.field) for u in report.unreadable_timestamps] == [
        ("token", "t-bad", "expires_at")]
    assert report.tokens_scanned == 2


@pytest.mark.parametrize("bad", ["None", None, "", 12345])
def test_a_bad_created_at_is_skipped_named_and_the_neighbour_still_reported(bad):
    agents = [_agent("a-bad", bad), _agent("a-good", GOOD_STALE)]
    report = _engine(agents, []).sweep(ROSTER, now=NOW)
    assert [r.agent_id for r in report.reattestation_due] == ["a-good"]
    assert [(u.kind, u.record_id, u.field) for u in report.unreadable_timestamps] == [
        ("agent", "a-bad", "created_at")]


def test_a_bad_attested_at_names_attested_at():
    agents = [_agent("a-bad", GOOD_STALE, attested_at=MARKER)]
    report = _engine(agents, []).sweep(ROSTER, now=NOW)
    assert [(u.kind, u.record_id, u.field) for u in report.unreadable_timestamps] == [
        ("agent", "a-bad", "attested_at")]
    assert report.reattestation_due == []


def test_a_token_with_no_expires_at_key_is_named_not_a_crash():
    tok = _token("t-nokey", GOOD_EXPIRING)
    del tok["expires_at"]
    report = _engine([], [tok]).sweep(ROSTER, now=NOW)
    assert [u.record_id for u in report.unreadable_timestamps] == ["t-nokey"]


def test_the_report_never_carries_the_bad_value():
    report = _engine([_agent("a-bad", MARKER)], [_token("t-bad", MARKER)]).sweep(ROSTER, now=NOW)
    assert len(report.unreadable_timestamps) == 2
    assert MARKER not in report.model_dump_json()


def test_clean_data_has_an_empty_list_and_an_old_report_still_validates():
    report = _engine([_agent("a-good", GOOD_STALE)], [_token("t-good", GOOD_EXPIRING)]).sweep(
        ROSTER, now=NOW)
    assert report.unreadable_timestamps == []
    data = report.model_dump(mode="json")
    del data["unreadable_timestamps"]
    type(report).model_validate(data)


def test_the_markdown_report_names_a_skipped_record_but_not_its_value():
    from lifecycle_manager.engine import render_markdown

    md = render_markdown(_engine([], [_token("t-bad", MARKER)]).sweep(ROSTER, now=NOW))
    assert "t-bad" in md and "expires_at" in md and MARKER not in md
    clean = render_markdown(_engine([], [_token("t-good", GOOD_EXPIRING)]).sweep(ROSTER, now=NOW))
    assert "unreadable timestamp" not in clean


# ---- R-PR489-53c30a0 condition C3: the record id is caller data, and it goes into markdown --------------------------------

FORGED = "a" + chr(96) + chr(10) + "## FORGED HEADING" + chr(10) + "- agent " + chr(96) + "ok" + chr(96)


@pytest.mark.parametrize("kind", ["token", "agent"])
def test_a_forged_record_id_cannot_add_a_heading_or_leave_its_code_span(kind):
    from lifecycle_manager.engine import render_markdown

    if kind == "token":
        report = _engine([], [_token(FORGED, MARKER)]).sweep(ROSTER, now=NOW)
    else:
        report = _engine([_agent(FORGED, MARKER)], []).sweep(ROSTER, now=NOW)
    md = render_markdown(report)
    lines = md.split(chr(10))
    assert not any(line.startswith("## FORGED") for line in lines), md
    assert len([ln for ln in lines if "FORGED" in ln]) == 1                  # one line carries it, as inline text
    (line,) = [ln for ln in lines if "is not a readable time" in ln]
    assert line == f"- {kind} " + chr(96) + "a' ## FORGED HEADING - agent 'ok'" + chr(96) + ": " + chr(96) + report.unreadable_timestamps[0].field + chr(96) + " is not a readable time"
    assert md.count("## Skipped: unreadable timestamp") == 1 and MARKER not in md


@pytest.mark.parametrize("raw,want", [
    ("a" + chr(10) + chr(9) + "  b", "a b"),                     # runs of whitespace collapse
    ("a" + chr(0) + "b", "a b"), ("a" + chr(0x1B) + "b", "a b"),  # Cc
    ("a" + chr(0x200B) + "b", "a b"), ("a" + chr(0x202E) + "b", "a b"),   # Cf
    ("a" + chr(0x2028) + "b", "a b"),                            # Zl
    ("  x  ", "x"), (chr(96) * 2, "''"), (7, "7"),
])
def test_skipped_id_is_one_inline_code_safe_line(raw, want):
    from lifecycle_manager.engine import _skipped_id

    assert _skipped_id(raw) == want


# --- R-PR489 C2 and U1 (ssl-ff-reviewer-8 on 1e8f7fe) ---------------------------------------------------------------


class _Ledger:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload=None, agent_id=None):
        self.events.append((event_type, payload, agent_id))


def _engine_with_ledger(agents, tokens):
    ledger = _Ledger()
    return LifecycleEngine(registry=_Registry(agents), delegation=_Delegation(tokens), ledger=ledger), ledger


@pytest.mark.parametrize("bad", [12345, None, ["2026-01-01"], {"a": 1}, b"2026-01-01T00:00:00"])
def test_a_timestamp_that_is_not_a_string_is_skipped_and_named(bad):
    # U1: TypeError / AttributeError from a non-string value must not abort the sweep
    report = _engine([_agent("a-num", bad)], [_token("t-num", bad)]).sweep(ROSTER, now=NOW)
    assert {(u.kind, u.record_id) for u in report.unreadable_timestamps} == {("token", "t-num"), ("agent", "a-num")}


def test_every_unreadable_record_writes_one_escalation_naming_the_record_and_field_never_the_value():
    engine, ledger = _engine_with_ledger([_agent("a-bad", MARKER)], [_token("t-bad", MARKER)])
    report = engine.sweep(ROSTER, now=NOW)
    got = sorted((e, p["kind"], p["record_id"], p["field"]) for e, p, _ in ledger.events)
    assert got == [("lifecycle.unreadable_timestamp", "agent", "a-bad", "created_at"),
                   ("lifecycle.unreadable_timestamp", "token", "t-bad", "expires_at")]
    assert MARKER not in repr(ledger.events)
    assert report.escalations_written == 2


def test_a_clean_sweep_writes_no_unreadable_escalation():
    engine, ledger = _engine_with_ledger([_agent("a-ok", (NOW - timedelta(days=1)).isoformat())], [])
    engine.sweep(ROSTER, now=NOW)
    assert [e for e, _, _ in ledger.events if e == "lifecycle.unreadable_timestamp"] == []


def _cli_run(monkeypatch, tmp_path, agents, tokens):
    from typer.testing import CliRunner

    from lifecycle_manager import cli

    ledger = _Ledger()
    clients = {"registry": _Registry(agents), "delegation": _Delegation(tokens), "ledger": ledger, "killswitch": None}
    monkeypatch.setattr(cli, "estate_clients", lambda pair, timeout=20.0: clients)
    monkeypatch.setattr(cli, "operator_pair", lambda *a, **k: None)
    roster = tmp_path / "owners.csv"
    roster.write_text(ROSTER, encoding="utf-8")
    return CliRunner().invoke(cli.app, ["sweep", "--roster", str(roster)]), ledger


def test_a_sweep_that_skipped_a_record_exits_3_not_0(monkeypatch, tmp_path):
    res, ledger = _cli_run(monkeypatch, tmp_path, [], [_token("t-bad", MARKER)])
    assert res.exit_code == 3, res.output
    assert MARKER not in res.output
    assert [e for e, _, _ in ledger.events] == ["lifecycle.unreadable_timestamp"]


def test_a_sweep_with_nothing_skipped_and_no_finding_still_exits_0(monkeypatch, tmp_path):
    fresh = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()        # the CLI sweeps at the real time
    res, _ = _cli_run(monkeypatch, tmp_path, [_agent("a-ok", fresh)], [])
    assert res.exit_code == 0, res.output
