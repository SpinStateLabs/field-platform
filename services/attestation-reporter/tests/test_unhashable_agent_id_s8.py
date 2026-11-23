"""S8-19 — a row whose ``agent_id`` is a list or an object (unhashable) leaves that row uncounted or
that one metric unavailable; it never raises out of ``build`` (a 500 for the whole /pack). Covers the
canary filter and the distinct-agents key, through the engine, GET /pack and `attest render`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from attestation_reporter import api as api_mod
from attestation_reporter.api import create_app
from attestation_reporter.cli import app as cli_app
from attestation_reporter.engine import PackEngine, _without_canaries

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
ODD = [[], {}, ["canary-gb10"], {"a": 1}, [[1]]]


class Answer:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class Stub:
    def __init__(self, **routes):
        self.routes = routes

    def get(self, target):
        return Answer(self.routes.get(target.split("?")[0], []))


def engine(ledger_events=None, tokens=None, agents=None):
    ledger = Stub(**{"/events": ledger_events or [], "/verify": {"ok": True, "length": 0}, "/health": {},
                     "/retention/check": {"status": "no_estate_policy"}})
    return PackEngine(registry=Stub(**{"/agents": agents or []}), ledger=ledger,
                      delegation=Stub(**{"/tokens": tokens or []}), governor=Stub(**{"/escalations": []}))


def by_name(pack):
    return {m.name: m for m in pack.all_metrics()}


@pytest.mark.parametrize("odd", ODD, ids=repr)
def test_without_canaries_does_not_hash_the_id(odd):
    kept, dropped = _without_canaries([{"agent_id": odd}, {"agent_id": "canary-gb10"}, {"agent_id": "a1"}])
    assert dropped == 1 and kept == [{"agent_id": odd}, {"agent_id": "a1"}]


@pytest.mark.parametrize("odd", ODD, ids=repr)
@pytest.mark.parametrize("where", ["agents", "tokens", "ledger_events"])
def test_the_pack_is_built_with_an_odd_agent_id_in_any_answer(where, odd):
    rows = [{"agent_id": odd, "ts": "2026-07-01T00:00:00+00:00", "payload": {}},
            {"agent_id": "a1", "ts": "2026-07-01T00:00:00+00:00", "payload": {}}]
    pack = engine(**{where: rows}).build(now=NOW)           # must not raise
    assert by_name(pack)["Agents registered"] is not None


@pytest.mark.parametrize("odd", ODD, ids=repr)
def test_the_distinct_agents_row_counts_an_odd_id_as_missing(odd):
    events = [{"agent_id": odd, "payload": {}}, {"agent_id": "a1", "payload": {}},
              {"agent_id": "a1", "payload": {}}]
    m = by_name(engine(ledger_events=events).build(now=NOW))["Distinct agents flagged for re-attestation"]
    assert m.status == "ok" and m.value == 1
    assert "1 event(s) without agent_id not counted" in m.note


def test_canaries_are_still_excluded_and_ordinary_ids_still_counted():
    events = [{"agent_id": "canary-gb10", "payload": {}}, {"agent_id": "a1", "payload": {}},
              {"agent_id": "a2", "payload": {}}]
    m = by_name(engine(ledger_events=events).build(now=NOW))["Distinct agents flagged for re-attestation"]
    assert m.value == 2 and "excludes 1 gate-verification (canary) record(s)" in m.note


@pytest.mark.parametrize("odd", ODD, ids=repr)
def test_get_pack_answers_200(odd):
    eng = engine(agents=[{"agent_id": odd, "status": "active"}],
                 ledger_events=[{"agent_id": odd, "payload": {}}], tokens=[{"agent_id": odd}])
    r = TestClient(create_app(eng), raise_server_exceptions=False).get("/pack")
    assert r.status_code == 200, r.text


def test_attest_render_builds_the_pack(tmp_path, monkeypatch):
    eng = engine(agents=[{"agent_id": [], "status": "active"}],
                 ledger_events=[{"agent_id": {}, "payload": {}}], tokens=[{"agent_id": ["x"]}])
    monkeypatch.setattr(api_mod, "engine_from_env", lambda *a, **k: eng)
    r = CliRunner().invoke(cli_app, ["render", "--out", str(tmp_path / "pack"), "--no-pdf"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "pack" / "board-pack.json").exists()
