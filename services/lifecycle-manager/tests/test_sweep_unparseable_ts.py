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
