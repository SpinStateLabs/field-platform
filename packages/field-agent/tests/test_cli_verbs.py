"""S3-7: `fieldagent heartbeat | checkin | report-usage | mint` exit codes and
output, pinned from the cli.py docstrings. A fake FieldAgent is monkeypatched
into field_agent.cli; `mint` runs the real bootstrap.mint over a MockTransport.
Tests only: no source edit."""

from __future__ import annotations

import json

import httpx
import pytest
from typer.testing import CliRunner

from field_agent import AgentKilled, UsageReportError, bootstrap
from field_agent import cli
from field_agent.liveness import Heartbeat
from field_agent.usage import RogueFinding, SpendStatusLite, UsageRecordLite, UsageReport

runner = CliRunner()
NOW = "2026-11-04T00:00:00+00:00"


def hb(status="active", killed=False):
    return Heartbeat(agent_id="a1", status=status, killed=killed, checked_at=NOW)


def report(rogue=()):
    return UsageReport(
        record=UsageRecordLite(event_id="e1", model="m", input_tokens=3, output_tokens=4),
        rogue=[RogueFinding(kind="burst", detail="too fast") for _ in rogue],
        status=SpendStatusLite(agent_id="a1", state="OK"),
    )


class FakeAgent:
    behaviour = {}
    calls = []

    def __init__(self, agent_id, **kw):
        self.agent_id = agent_id

    def _do(self, name):
        r = self.behaviour[name]
        if isinstance(r, Exception):
            raise r
        return r

    def ensure_alive(self):
        return self._do("ensure_alive")

    def checkin(self):
        return self._do("checkin")

    def report_usage(self, model, **kw):
        FakeAgent.calls.append((model, kw))
        return self._do("report_usage")


@pytest.fixture()
def fake(monkeypatch):
    FakeAgent.behaviour, FakeAgent.calls = {}, []
    monkeypatch.setattr(cli, "FieldAgent", FakeAgent)
    return FakeAgent.behaviour


def test_heartbeat_active_exits_0_and_prints_the_json(fake):
    fake["ensure_alive"] = hb()
    res = runner.invoke(cli.app, ["heartbeat", "a1"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["status"] == "active"


def test_heartbeat_killed_prints_the_json_then_exit_1_with_the_message(fake):
    fake["ensure_alive"] = AgentKilled("a1 is killed", heartbeat=hb("killed", True))
    res = runner.invoke(cli.app, ["heartbeat", "a1"])
    assert res.exit_code == 1
    assert json.loads(res.stdout)["killed"] is True
    assert "a1 is killed" in res.stderr


@pytest.mark.parametrize("why", ["unknown agent", "kill-switch unreachable"])
def test_heartbeat_unknown_or_unreachable_fails_closed(fake, why):
    fake["ensure_alive"] = AgentKilled(why)  # no heartbeat object
    res = runner.invoke(cli.app, ["heartbeat", "a1"])
    assert res.exit_code == 1
    assert res.stdout == "" and why in res.stderr


def test_checkin_active_exit_0(fake):
    fake["checkin"] = hb()
    res = runner.invoke(cli.app, ["checkin", "a1"])
    assert res.exit_code == 0 and json.loads(res.stdout)["killed"] is False


def test_checkin_killed_prints_the_json_and_the_halting_line_exit_1(fake):
    fake["checkin"] = hb("killed", True)
    res = runner.invoke(cli.app, ["checkin", "a1"])
    assert res.exit_code == 1
    assert json.loads(res.stdout)["status"] == "killed"
    assert "status='killed' — halting" in res.stderr


def test_checkin_unreachable_exit_1(fake):
    fake["checkin"] = AgentKilled("liveness unknown")
    res = runner.invoke(cli.app, ["checkin", "a1"])
    assert res.exit_code == 1 and "liveness unknown" in res.stderr and res.stdout == ""


def test_report_usage_success_exit_0_and_json(fake):
    fake["report_usage"] = report()
    res = runner.invoke(cli.app, ["report-usage", "a1", "--model", "m", "--input-tokens", "3",
                                  "--output-tokens", "4", "--cache-read-tokens", "1", "--note", "n"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["record"]["event_id"] == "e1"
    assert FakeAgent.calls == [("m", {"input_tokens": 3, "output_tokens": 4,
                                      "cache_read_tokens": 1, "note": "n"})]


def test_report_usage_defaults_are_zero_tokens_and_no_note(fake):
    fake["report_usage"] = report()
    runner.invoke(cli.app, ["report-usage", "a1", "--model", "m"])
    assert FakeAgent.calls[0][1] == {"input_tokens": 0, "output_tokens": 0,
                                     "cache_read_tokens": 0, "note": None}


def test_report_usage_rogue_findings_exit_3_after_printing_the_report(fake):
    fake["report_usage"] = report(rogue=[1])
    res = runner.invoke(cli.app, ["report-usage", "a1", "--model", "m"])
    assert res.exit_code == 3
    assert json.loads(res.stdout)["rogue"][0]["kind"] == "burst"


def test_report_usage_error_is_exit_1_usage_not_metered(fake):
    fake["report_usage"] = UsageReportError("404 no cap")
    res = runner.invoke(cli.app, ["report-usage", "a1", "--model", "m"])
    assert res.exit_code == 1
    assert "usage NOT metered: 404 no cap" in res.stderr and res.stdout == ""


def test_report_usage_requires_a_model(fake):
    assert runner.invoke(cli.app, ["report-usage", "a1"]).exit_code == 2


def test_negative_token_options_are_passed_through_not_refused(fake):
    # pins today's behaviour: the CLI does no range check (the governor decides)
    fake["report_usage"] = report()
    res = runner.invoke(cli.app, ["report-usage", "a1", "--model", "m", "--input-tokens", "-5"])
    assert res.exit_code == 0 and FakeAgent.calls[0][1]["input_tokens"] == -5


# ---- mint, over the real bootstrap.mint -------------------------------------------------

TOKEN = {"token_id": "t1", "agent_id": "a1", "granted_by": "Don", "scope": ["read", "write"],
         "issued_at": NOW, "expires_at": "2026-11-04T01:00:00+00:00"}


@pytest.fixture()
def mint_transport(monkeypatch):
    seen, box = [], {"h": lambda r: httpx.Response(201, json=TOKEN)}

    def handler(request):
        seen.append(request)
        return box["h"](request)

    monkeypatch.setattr(bootstrap, "_client",
                        lambda c: bootstrap.AuthedClient(httpx.Client(transport=httpx.MockTransport(handler))))
    return seen, box


def test_mint_prints_the_token_and_repeats_scope(mint_transport):
    seen, _ = mint_transport
    res = runner.invoke(cli.app, ["mint", "a1", "--granted-by", "Don", "--scope", "read",
                                  "--scope", "write", "--ttl-seconds", "60"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["token_id"] == "t1"
    body = json.loads(seen[0].content)
    assert body["scope"] == ["read", "write"] and body["ttl_seconds"] == 60
    assert body["granted_by"] == "Don"


def test_mint_default_ttl_is_3600(mint_transport):
    seen, _ = mint_transport
    runner.invoke(cli.app, ["mint", "a1", "--granted-by", "Don", "--scope", "read"])
    assert json.loads(seen[0].content)["ttl_seconds"] == 3600


def test_mint_403_is_error_exit_1_and_never_echoes_the_upstream_body(mint_transport):
    _, box = mint_transport
    box["h"] = lambda r: httpx.Response(403, text="UPSTREAM-SECRET-BODY grantor not on roster")
    res = runner.invoke(cli.app, ["mint", "a1", "--granted-by", "Nobody", "--scope", "read"])
    assert res.exit_code == 1
    assert res.stderr.startswith("error: ") and "403" in res.stderr
    assert "UPSTREAM-SECRET-BODY" not in res.stderr + res.stdout
    assert res.stdout == ""


def test_mint_requires_granted_by_and_a_scope():
    assert runner.invoke(cli.app, ["mint", "a1", "--scope", "r"]).exit_code == 2
    assert runner.invoke(cli.app, ["mint", "a1", "--granted-by", "Don"]).exit_code == 2
