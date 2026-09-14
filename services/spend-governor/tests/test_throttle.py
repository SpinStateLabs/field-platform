"""D1 — the governor throttle, option A/B metering, D1f and the spend migration.

Frozen clock throughout (``create_app(clock=...)``), never sleeps:

- a per-action rolling window: N allowed, N+1 THROTTLED with
  ``retry_after_seconds`` = 1 at T+period-1 s and OK at T+period; the token
  window likewise;
- precedence BLOCK (cap) > THROTTLED > ESCALATE, and a throttled spend that
  crosses the threshold still opens its escalation;
- ``?action=`` for an unlimited action is not throttled; case / whitespace
  variants and ``tool_call`` never match another action;
- the period grammar: ``session`` loads as declared-unenforced (ledgered,
  never locks out), unknown periods are refused, rate limits without a spend
  cap are refused;
- D1f: an unsupported ``spend_cap.period`` (per-run) is a named error, never
  ``total``;
- option A counting: an action checked AND self-reported counts once, an
  action only one side saw is never lost;
- an old 7-column ``spend.sqlite3`` migrates at open.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import spend_governor.cli as cli_mod
from field_core.manifest import FieldManifest
from field_core.templates_api import template_data
from spend_governor.api import create_app
from spend_governor.core import (
    GovernorStore,
    RateLimitSet,
    SpendCapConfig,
    UnknownRatePeriodError,
    UnsupportedCapPeriodError,
    action_totals,
    parse_rate_period,
    window_retry_after,
)
from spend_governor.provisioning import (
    RateLimitsRefusedError,
    load_rate_limits,
    rate_limits_from_manifest,
)

AGENT = "invoicing-agent"
T0 = datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def at(self, seconds: float) -> None:
        self.now = T0 + timedelta(seconds=seconds)


class RecordingLedger:
    def __init__(self) -> None:
        self.notes: list[tuple[str, dict, str]] = []
        self._guard = threading.Lock()

    def append(self, event_type, payload=None, agent_id=None):
        with self._guard:
            self.notes.append((event_type, payload or {}, agent_id))

    def of(self, event_type: str) -> list[dict]:
        with self._guard:
            return [p for t, p, _ in self.notes if t == event_type]


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def ledger():
    return RecordingLedger()


@pytest.fixture()
def client(tmp_path, clock, ledger):
    store = GovernorStore(tmp_path / "spend.sqlite3")
    yield TestClient(create_app(store=store, ledger=ledger, clock=clock))
    store.close()


def _cap(client, agent=AGENT, **overrides):
    body = {"agent_id": agent, "limit_cents": 50_000, "period": "daily",
            "escalate_at_pct": 80}
    body.update(overrides)
    r = client.put(f"/caps/{agent}", json=body)
    assert r.status_code == 200, r.text


def _limits(client, entries, agent=AGENT):
    r = client.put(f"/rate-limits/{agent}", json={"agent_id": agent, "rate_limits": entries})
    assert r.status_code == 200, r.text
    return r.json()


def _spend(client, agent=AGENT, **body):
    r = client.post("/spend", json={"agent_id": agent, **body})
    assert r.status_code == 201, r.text
    return r.json()


def _status(client, action=None, agent=AGENT):
    params = {"action": action} if action is not None else {}
    r = client.get(f"/status/{agent}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


# -- the period grammar --------------------------------------------------------

def test_rate_period_grammar():
    assert parse_rate_period("hourly") == 3600
    assert parse_rate_period("daily") == 86400
    assert parse_rate_period("monthly") == 30 * 86400
    assert parse_rate_period("90s") == 90
    assert parse_rate_period("5m") == 300
    assert parse_rate_period("2h") == 7200
    assert parse_rate_period("1d") == 86400
    assert parse_rate_period("366d") == 366 * 86400
    assert parse_rate_period("session") is None
    for bad in ("fortnightly", "Hourly", " hourly", "hourly ", "hourly\n", "0s",
                "10w", "1.5h", "-1h", "", "per-run", "total", "367d", "SESSION",
                "１h"):
        with pytest.raises(UnknownRatePeriodError):
            parse_rate_period(bad)


# -- the per-action rolling window --------------------------------------------

@pytest.mark.parametrize("source", ["self", "sentinel"])
def test_action_window_n_allowed_then_throttled_until_the_period_passes(client, clock, source):
    _cap(client)
    _limits(client, [{"action": "draft invoices", "max": 3, "period": "hourly"}])
    body = {"actions": 1, "action": "draft invoices", "source": source}

    for n in range(3):
        before = _status(client, "draft invoices")
        assert before["state"] == "OK", (n, before)
        assert before["retry_after_seconds"] is None and before["throttled"] is None
        _spend(client, **body)

    exhausted = _status(client, "draft invoices")  # the N+1th ask
    assert exhausted["state"] == "THROTTLED"
    assert exhausted["retry_after_seconds"] == 3600
    assert exhausted["throttled"] == {"kind": "action", "action": "draft invoices",
                                      "count": 3, "max": 3, "period": "hourly",
                                      "period_seconds": 3600}
    assert "retry after 3600s" in exhausted["detail"]

    clock.at(3599)
    last_second = _status(client, "draft invoices")
    assert last_second["state"] == "THROTTLED" and last_second["retry_after_seconds"] == 1

    clock.at(3600)
    freed = _status(client, "draft invoices")
    assert freed["state"] == "OK" and freed["retry_after_seconds"] is None


def test_retry_after_waits_for_the_oldest_rows_that_free_a_slot(client, clock):
    _cap(client)
    _limits(client, [{"action": "draft invoices", "max": 3, "period": "10m"}])
    for at in (0, 100, 200):
        clock.at(at)
        _spend(client, actions=1, action="draft invoices")
    clock.at(250)
    s = _status(client, "draft invoices")
    # only the row at T+0 has to leave: 600 - 250 = 350
    assert (s["state"], s["retry_after_seconds"]) == ("THROTTLED", 350)
    clock.at(250)
    _spend(client, actions=1, action="draft invoices")  # count 4: two must leave
    s = _status(client, "draft invoices")
    assert s["retry_after_seconds"] == 450  # the T+100 row leaves at 700
    clock.at(599.5)
    assert _status(client, "draft invoices")["retry_after_seconds"] == 101  # ceil(100.5)


def test_two_exhausted_windows_report_the_longest_wait(client, clock):
    _cap(client)
    _limits(client, [{"action": "draft invoices", "max": 1, "period": "10m"},
                     {"action": "draft invoices", "max": 2, "period": "hourly"}])
    _spend(client, actions=2, action="draft invoices")
    s = _status(client, "draft invoices")
    assert s["retry_after_seconds"] == 3600 and s["throttled"]["period"] == "hourly"
    clock.at(600)  # the 10m window has emptied; the hourly one still holds
    s = _status(client, "draft invoices")
    assert (s["retry_after_seconds"], s["throttled"]["period"]) == (3000, "hourly")


def test_window_retry_after_is_integer_and_never_zero():
    now = T0 + timedelta(microseconds=1)
    count, retry = window_retry_after([(T0, 1)], 1, 1, now)
    assert (count, retry) == (1, 1)  # 0.999999 s left rounds up, never 0
    assert window_retry_after([(T0, 1)], 2, 60, now) == (1, None)
    assert window_retry_after([], 1, 60, now) == (0, None)
    # a caller that hands in a row exactly at the edge still never gets 0
    assert window_retry_after([(T0, 1)], 1, 60, T0 + timedelta(seconds=60)) == (1, 1)


def test_token_window_likewise(client, clock):
    _cap(client)
    r = client.put(f"/policies/{AGENT}", json={
        "agent_id": AGENT, "allowed_models": [], "token_rate_limit": 1000,
        "rate_window_seconds": 60})
    assert r.status_code == 200
    usage = lambda i, o: client.post("/usage", json={  # noqa: E731
        "agent_id": AGENT, "model": "claude-haiku-4-5", "input_tokens": i,
        "output_tokens": o})

    assert usage(300, 200).json()["status"]["state"] == "OK"        # 500 at T
    clock.at(10)
    body = usage(400, 200).json()                                   # 1100 at T+10
    assert body["status"]["state"] == "THROTTLED"
    assert body["status"]["retry_after_seconds"] == 50              # T row leaves at 60
    assert body["status"]["throttled"]["kind"] == "tokens"
    assert body["status"]["throttled"]["count"] == 1100
    # the token window applies to every status read, action or not
    assert _status(client)["state"] == "THROTTLED"
    assert _status(client, "anything")["state"] == "THROTTLED"

    for esc in client.get("/escalations", params={"agent_id": AGENT}).json():
        client.post(f"/escalations/{esc['escalation_id']}/resolve",
                    json={"resolved_by": "Controller"})
    clock.at(59)
    s = _status(client)
    assert (s["state"], s["retry_after_seconds"]) == ("THROTTLED", 1)
    clock.at(60)
    s = _status(client)
    assert (s["state"], s["retry_after_seconds"]) == ("OK", None)


# -- precedence -------------------------------------------------------------------

def test_cap_block_outranks_throttled(client):
    _cap(client, limit_cents=1_000)
    _limits(client, [{"action": "draft invoices", "max": 1, "period": "hourly"}])
    _spend(client, actions=1, action="draft invoices")
    assert _status(client, "draft invoices")["state"] == "THROTTLED"
    body = _spend(client, cents=1_000, action="draft invoices")
    assert body["state"] == "BLOCK"
    assert body["retry_after_seconds"] is None and body["throttled"] is None
    assert _status(client, "draft invoices")["state"] == "BLOCK"


def test_throttled_outranks_escalate_and_the_escalation_still_opens(client, ledger):
    _cap(client, limit_cents=1_000)
    _limits(client, [{"action": "draft invoices", "max": 1, "period": "hourly"}])
    body = _spend(client, cents=850, actions=1, action="draft invoices")  # 85% AND 1/1
    assert body["state"] == "THROTTLED"
    opened = client.get("/escalations", params={"agent_id": AGENT}).json()
    assert [e["kind"] for e in opened] == ["cents"]
    assert len(ledger.of("spend.escalate")) == 1
    # without the action the same agent reads ESCALATE
    assert _status(client)["state"] == "ESCALATE"


# -- matching ---------------------------------------------------------------------

def test_unlimited_action_is_not_throttled(client):
    _cap(client)
    _limits(client, [{"action": "draft invoices", "max": 1, "period": "hourly"}])
    _spend(client, actions=5, action="draft invoices")
    assert _status(client, "draft invoices")["state"] == "THROTTLED"
    assert _status(client, "read timesheets")["state"] == "OK"
    assert _status(client)["state"] == "OK"  # no action ⇒ no per-action window


def test_case_and_whitespace_variants_are_not_matched(client):
    _cap(client)
    _limits(client, [{"action": "draft invoices", "max": 1, "period": "hourly"}])
    # rows under variant spellings never feed the exact window …
    for variant in ("Draft invoices", "draft invoices ", " draft invoices", "draft  invoices",
                    "DRAFT INVOICES"):
        _spend(client, actions=3, action=variant)
    assert _status(client, "draft invoices")["state"] == "OK"
    # … and asking with a variant never reads the exact window
    _spend(client, actions=1, action="draft invoices")
    assert _status(client, "draft invoices")["state"] == "THROTTLED"
    for variant in ("Draft invoices", "draft invoices ", "draft  invoices"):
        assert _status(client, variant)["state"] == "OK", variant


def test_tool_call_is_not_a_wildcard(client):
    _cap(client)
    _limits(client, [{"action": "tool_call", "max": 1, "period": "hourly"}])
    _spend(client, actions=4, action="draft invoices")
    _spend(client, actions=4)  # unattributed
    assert _status(client, "draft invoices")["state"] == "OK"
    assert _status(client, "tool_call")["state"] == "OK"
    _spend(client, actions=1, action="tool_call")
    assert _status(client, "tool_call")["state"] == "THROTTLED"


# -- loading ------------------------------------------------------------------------

def test_session_entry_is_declared_unenforced_ledgered_and_never_locks_out(client, ledger):
    _cap(client)
    view = _limits(client, [
        {"action": "tool_call", "max": 2, "period": "session"},
        {"action": "draft invoices", "max": 5, "period": "daily"},
    ])
    rows = {r["action"]: r for r in view["rate_limits"]}
    assert rows["tool_call"] == {"action": "tool_call", "max": 2, "period": "session",
                                 "period_seconds": None, "status": "declared_unenforced"}
    assert rows["draft invoices"]["status"] == "enforced"
    assert rows["draft invoices"]["period_seconds"] == 86400
    notes = ledger.of("spend.rate_limit_declared_unenforced")
    assert len(notes) == 1
    assert notes[0]["entries"] == [{"action": "tool_call", "max": 2, "period": "session"}]
    assert client.get(f"/rate-limits/{AGENT}").json() == view

    _spend(client, actions=50, action="tool_call")
    s = _status(client, "tool_call")
    assert s["state"] == "OK" and s["retry_after_seconds"] is None


def test_unknown_period_and_duplicates_are_rejected(client):
    _cap(client)
    for entries in ([{"action": "a", "max": 1, "period": "fortnightly"}],
                    [{"action": "a", "max": 1, "period": "Hourly"}],
                    [{"action": "a", "max": 1, "period": "per-run"}],
                    [{"action": "a", "max": 1, "period": "hourly"},
                     {"action": "a", "max": 2, "period": "hourly"}],
                    [{"action": "a", "max": 0, "period": "hourly"}]):
        r = client.put(f"/rate-limits/{AGENT}", json={"agent_id": AGENT,
                                                       "rate_limits": entries})
        assert r.status_code == 422, (entries, r.text)
    assert client.get(f"/rate-limits/{AGENT}").json()["rate_limits"] == []


def test_rate_limits_for_an_uncapped_agent_are_refused(client):
    r = client.put("/rate-limits/ghost", json={"agent_id": "ghost", "rate_limits": [
        {"action": "a", "max": 1, "period": "hourly"}]})
    assert r.status_code == 404 and "ungoverned" in r.json()["detail"]
    r = client.put(f"/rate-limits/{AGENT}", json={"agent_id": "other", "rate_limits": []})
    assert r.status_code == 422


def test_get_rate_limits_for_an_uncapped_agent_is_404(client):
    """The CLI and lifecycle loader read a non-200 here as 'holds nothing'."""
    r = client.get("/rate-limits/ghost")
    assert r.status_code == 404 and "no spend cap" in r.json()["detail"]
    _cap(client)
    assert client.get(f"/rate-limits/{AGENT}").json() == {"agent_id": AGENT, "rate_limits": []}


def test_replacing_the_set_drops_old_limits(client):
    _cap(client)
    _limits(client, [{"action": "draft invoices", "max": 1, "period": "hourly"}])
    _spend(client, actions=1, action="draft invoices")
    assert _status(client, "draft invoices")["state"] == "THROTTLED"
    _limits(client, [])
    assert _status(client, "draft invoices")["state"] == "OK"


# -- the CLI: set-cap --from-manifest ----------------------------------------------

class _Router:
    """Route the CLI's module-level httpx calls into the in-process app."""

    def __init__(self, client):
        self.client = client

    def put(self, url, json=None, timeout=None, headers=None):
        return self.client.put(url.replace("http://127.0.0.1:8006", ""), json=json)

    def get(self, url, params=None, timeout=None, headers=None):
        return self.client.get(url.replace("http://127.0.0.1:8006", ""), params=params)

    def post(self, url, json=None, timeout=None, headers=None):
        return self.client.post(url.replace("http://127.0.0.1:8006", ""), json=json)


def _manifest_file(tmp_path, mutate):
    data = template_data("financial-agent")
    mutate(data)
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture()
def run_cli(client, monkeypatch):
    monkeypatch.delenv("FIELD_GOVERNOR_URL", raising=False)
    monkeypatch.setattr(cli_mod, "httpx", _Router(client))

    def run(*args):
        return CliRunner().invoke(cli_mod.app, list(args))

    return run


def test_cli_session_entry_loads_the_cap_and_warns_loudly(run_cli, client, tmp_path):
    path = _manifest_file(tmp_path, lambda d: None)  # template: tool_call / session
    result = run_cli("set-cap", AGENT, "--from-manifest", str(path))
    assert result.exit_code == 0, result.output
    assert '"limit_cents":50000' in result.stdout.replace(" ", "")
    assert "DECLARED, NOT ENFORCED" in result.stderr
    assert "0 enforced, 1 declared-unenforced" in result.stderr
    rows = client.get(f"/rate-limits/{AGENT}").json()["rate_limits"]
    assert [(r["action"], r["status"]) for r in rows] == [("tool_call", "declared_unenforced")]


def test_cli_loads_parseable_rate_limits(run_cli, client, tmp_path):
    def add(d):
        d["enforcement"]["rate_limits"].append(
            {"action": "read timesheets", "max": 10, "period": "hourly"})
    result = run_cli("set-cap", AGENT, "--from-manifest", str(_manifest_file(tmp_path, add)))
    assert result.exit_code == 0, result.output
    assert "1 enforced, 1 declared-unenforced" in result.stderr
    rows = {r["action"]: r for r in client.get(f"/rate-limits/{AGENT}").json()["rate_limits"]}
    assert rows["read timesheets"]["period_seconds"] == 3600


def test_cli_manifest_without_rate_limits_clears_a_stale_set(run_cli, client, tmp_path):
    _cap(client)
    _limits(client, [{"action": "draft invoices", "max": 1, "period": "hourly"}])

    def drop(d):
        del d["enforcement"]["rate_limits"]
    result = run_cli("set-cap", AGENT, "--from-manifest", str(_manifest_file(tmp_path, drop)))
    assert result.exit_code == 0, result.output
    assert client.get(f"/rate-limits/{AGENT}").json()["rate_limits"] == []


def test_cli_manifest_without_rate_limits_still_works_on_a_pre_d1_governor(
        run_cli, client, tmp_path, monkeypatch):
    real_get = client.get

    def old_governor_get(url, **kwargs):
        if "/rate-limits/" in url:
            class Missing:
                status_code = 404

                @staticmethod
                def json():
                    return {"detail": "Not Found"}
            return Missing()
        return real_get(url, **kwargs)

    monkeypatch.setattr(client, "get", old_governor_get)

    def drop(d):
        del d["enforcement"]["rate_limits"]
    result = run_cli("set-cap", AGENT, "--from-manifest", str(_manifest_file(tmp_path, drop)))
    assert result.exit_code == 0, result.output
    assert real_get(f"/caps/{AGENT}").status_code == 200


def test_cli_declared_rate_limits_against_a_pre_d1_governor_exit_1(
        run_cli, client, tmp_path, monkeypatch):
    """No /rate-limits route: the cap lands but set-cap must not exit 0 as if
    the declared throttle were loaded."""
    real_put = client.put

    def old_governor_put(url, **kwargs):
        if "/rate-limits/" in url:
            return httpx.Response(404, json={"detail": "Not Found"})
        return real_put(url, **kwargs)

    monkeypatch.setattr(client, "put", old_governor_put)
    result = run_cli("set-cap", AGENT, "--from-manifest", str(_manifest_file(tmp_path, lambda d: None)))
    assert result.exit_code == 1, result.output
    assert "rate limits were NOT loaded" in result.stderr and "Not Found" in result.stderr
    assert client.get(f"/caps/{AGENT}").status_code == 200  # the cap step is not rolled back


def test_cli_unknown_period_configures_nothing(run_cli, client, tmp_path):
    def bad(d):
        d["enforcement"]["rate_limits"] = [{"action": "x", "max": 1, "period": "fortnightly"}]
    result = run_cli("set-cap", AGENT, "--from-manifest", str(_manifest_file(tmp_path, bad)))
    assert result.exit_code == 1
    assert "fortnightly" in result.stderr and "nothing was configured" in result.stderr
    assert client.get(f"/caps/{AGENT}").status_code == 404


def test_cli_rate_limits_without_spend_cap_refused_loudly(run_cli, client, tmp_path):
    def no_cap(d):
        del d["enforcement"]["spend_cap"]
    result = run_cli("set-cap", AGENT, "--from-manifest", str(_manifest_file(tmp_path, no_cap)))
    assert result.exit_code == 1
    assert "rate_limits but no enforcement.spend_cap" in result.stderr
    assert client.get(f"/caps/{AGENT}").status_code == 404


def test_cli_status_action_reads_that_actions_window(run_cli, client):
    _cap(client)
    _limits(client, [{"action": "draft invoices", "max": 1, "period": "hourly"}])
    _spend(client, actions=1, action="draft invoices")
    result = run_cli("status", AGENT, "--action", "draft invoices")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert (body["state"], body["retry_after_seconds"]) == ("THROTTLED", 3600)
    assert json.loads(run_cli("status", AGENT).stdout)["state"] == "OK"  # no window asked


def test_cli_spend_action_feeds_that_actions_window(run_cli, client):
    _cap(client)
    _limits(client, [{"action": "draft invoices", "max": 1, "period": "hourly"}])
    result = run_cli("spend", AGENT, "--actions", "1", "--action", "draft invoices")
    assert result.exit_code == 0, result.output  # THROTTLED is not BLOCK
    assert json.loads(result.stdout)["state"] == "THROTTLED"
    assert _status(client, "draft invoices")["throttled"]["count"] == 1
    unattributed = run_cli("spend", AGENT, "--actions", "1")
    assert unattributed.exit_code == 0, unattributed.output
    assert _status(client, "draft invoices")["throttled"]["count"] == 1  # totals only


# -- the shared loader (set-cap and lifecycle provision) ------------------------------

def _manifest(mutate):
    data = template_data("financial-agent")
    mutate(data)
    return FieldManifest.from_dict(data)


def test_loader_validation_refuses_before_anything_is_put():
    def bad_period(d):
        d["enforcement"]["rate_limits"] = [{"action": "x", "max": 1, "period": "fortnightly"}]
    with pytest.raises(RateLimitsRefusedError, match="fortnightly"):
        rate_limits_from_manifest(_manifest(bad_period), AGENT)

    def no_cap(d):
        del d["enforcement"]["spend_cap"]
    with pytest.raises(RateLimitsRefusedError, match="no enforcement.spend_cap"):
        rate_limits_from_manifest(_manifest(no_cap), AGENT)

    def none_declared(d):
        del d["enforcement"]["rate_limits"]
        del d["enforcement"]["spend_cap"]
    assert rate_limits_from_manifest(_manifest(none_declared), AGENT).rate_limits == []


def test_loader_loads_clears_and_leaves_a_pre_d1_governor_alone(client):
    """The loader as lifecycle provision calls it (a base-URL client's
    ``get(path)`` / ``put(path, json=)``)."""
    puts = []

    def put(path, json):
        puts.append(json)
        return client.put(path, json=json)

    declared = RateLimitSet(agent_id=AGENT, rate_limits=[
        {"action": "canary.throttle", "max": 3, "period": "hourly"},
        {"action": "tool_call", "max": 5, "period": "session"}])
    refused = load_rate_limits(client.get, put, declared)  # uncapped agent: 404
    assert (refused.outcome, refused.status_code) == ("failed", 404)
    assert "NOT loaded (404)" in refused.detail

    _cap(client)
    loaded = load_rate_limits(client.get, put, declared)
    assert (loaded.outcome, loaded.detail) == ("loaded", "1 enforced, 1 declared-unenforced")
    assert _status(client, "canary.throttle")["state"] == "OK"

    empty = RateLimitSet(agent_id=AGENT, rate_limits=[])
    cleared = load_rate_limits(client.get, put, empty)  # stale set held: cleared
    assert cleared.outcome == "loaded" and client.get(f"/rate-limits/{AGENT}").json()["rate_limits"] == []
    n = len(puts)
    assert load_rate_limits(client.get, put, empty).outcome == "unchanged"  # nothing held
    assert len(puts) == n  # and nothing PUT

    def pre_d1_get(path):
        return httpx.Response(404, json={"detail": "Not Found"})

    def pre_d1_put(path, json):
        return httpx.Response(404, json={"detail": "Not Found"})

    assert load_rate_limits(pre_d1_get, pre_d1_put, empty).outcome == "unchanged"
    assert load_rate_limits(pre_d1_get, pre_d1_put, declared).outcome == "failed"  # never silent


# -- D1f: unsupported cap periods ----------------------------------------------------

@pytest.mark.parametrize("period", ["per-run", "weekly", "Daily", "session", ""])
def test_unsupported_cap_period_is_a_named_error_never_total(period):
    data = template_data("financial-agent")
    data["enforcement"]["spend_cap"]["period"] = period
    manifest = FieldManifest.from_dict(data)
    with pytest.raises(UnsupportedCapPeriodError, match="refusing to meter it as 'total'"):
        SpendCapConfig.from_manifest(manifest, "fin-agent")


@pytest.mark.parametrize("period", ["daily", "monthly", "total"])
def test_supported_cap_periods_map_verbatim(period):
    data = template_data("financial-agent")
    data["enforcement"]["spend_cap"]["period"] = period
    cap = SpendCapConfig.from_manifest(FieldManifest.from_dict(data), "fin-agent")
    assert cap.period == period


def test_cli_per_run_cap_refused_with_the_named_error(run_cli, client, tmp_path):
    def per_run(d):
        d["enforcement"]["spend_cap"]["period"] = "per-run"
    result = run_cli("set-cap", AGENT, "--from-manifest", str(_manifest_file(tmp_path, per_run)))
    assert result.exit_code == 1
    assert "UnsupportedCapPeriodError" in result.stderr and "per-run" in result.stderr
    assert client.get(f"/caps/{AGENT}").status_code == 404


def test_rate_limit_set_from_manifest_is_verbatim():
    data = template_data("financial-agent")
    data["enforcement"]["rate_limits"].append({"action": "Draft Invoices ", "max": 2,
                                               "period": "5m"})
    limits = RateLimitSet.from_manifest(FieldManifest.from_dict(data), "a")
    assert [(e.action, e.max, e.period) for e in limits.rate_limits][-1] == (
        "Draft Invoices ", 2, "5m")


# -- option A / B counting --------------------------------------------------------------

def test_metered_a_and_self_reported_b_count_one_each(client):
    _cap(client, limit_cents=None, action_limit=100)
    _limits(client, [{"action": "read timesheets", "max": 5, "period": "hourly"}])
    _spend(client, actions=1, action="draft invoices", source="sentinel")
    _spend(client, actions=1, action="read timesheets")
    s = _status(client, "read timesheets")
    assert s["spent_actions"] == 2
    assert (s["spent_actions_self"], s["spent_actions_metered"]) == (1, 1)
    assert s["throttled"] is None
    _limits(client, [{"action": "read timesheets", "max": 1, "period": "hourly"}])
    assert _status(client, "read timesheets")["throttled"]["count"] == 1  # B counts 1


def test_the_same_action_checked_and_self_reported_counts_once(client):
    _cap(client, limit_cents=None, action_limit=100)
    _limits(client, [{"action": "draft invoices", "max": 2, "period": "hourly"}])
    _spend(client, actions=1, action="draft invoices", source="sentinel")
    _spend(client, actions=1, action="draft invoices")  # the agent_template 2x case
    s = _status(client, "draft invoices")
    assert s["spent_actions"] == 1
    assert (s["spent_actions_self"], s["spent_actions_metered"]) == (1, 1)
    assert s["state"] == "OK"  # window counts 1 of 2


def test_unattributed_rows_count_toward_totals_only(client):
    _cap(client, limit_cents=None, action_limit=100)
    _limits(client, [{"action": "draft invoices", "max": 1, "period": "hourly"}])
    _spend(client, actions=7)  # no action: 02_usage.py-style self-report
    s = _status(client, "draft invoices")
    assert s["spent_actions"] == 7 and s["state"] == "OK"


def test_window_prefers_metered_rows_while_the_cap_takes_the_max(client):
    """Option A as adopted: a window with ANY sentinel-metered row for the
    action ignores that action's self-reported rows (LIMITS: an agent that
    checks once and self-reports 3 counts 1 there); the cap counts max = 3."""
    _cap(client, limit_cents=None, action_limit=100)
    _limits(client, [{"action": "draft invoices", "max": 2, "period": "hourly"}])
    _spend(client, actions=3, action="draft invoices")
    assert _status(client, "draft invoices")["state"] == "THROTTLED"  # self only: 3
    _spend(client, actions=1, action="draft invoices", source="sentinel")
    s = _status(client, "draft invoices")
    assert s["state"] == "OK" and s["spent_actions"] == 3


def test_action_limit_cap_uses_the_deduplicated_count(client):
    _cap(client, limit_cents=None, action_limit=2)
    for _ in range(2):
        _spend(client, actions=1, action="draft invoices", source="sentinel")
        _spend(client, actions=1, action="draft invoices")
    s = _status(client)
    assert s["spent_actions"] == 2 and s["state"] == "BLOCK"


def test_action_totals_pure():
    groups = [("a", "sentinel", 2), ("a", "self", 5), ("b", "self", 1),
              (None, "self", 4), ("c", "sentinel", 3), ("a", "legacy", 1)]
    # a: max(self 5+1, metered 2) = 6; b: 1; c: 3; unattributed 4
    assert action_totals(groups) == (11, 5, 14)
    assert action_totals([]) == (0, 0, 0)


def test_sentinel_rows_must_name_the_action_and_shadowed_is_sentinel_only(client):
    _cap(client)
    for body in ({"actions": 1, "source": "sentinel"},
                 {"actions": 1, "action": "a", "shadowed": True},
                 {"actions": 1, "action": "a", "source": "gateway"},
                 {"actions": 1, "action": ""}):
        r = client.post("/spend", json={"agent_id": AGENT, **body})
        assert r.status_code == 422, (body, r.text)


def test_sentinel_rows_are_not_reledgered_as_spend_recorded(client, ledger):
    _cap(client)
    _spend(client, actions=1, action="draft invoices", source="sentinel", shadowed=True)
    assert ledger.of("spend.recorded") == []
    _spend(client, cents=5, action="draft invoices")
    _spend(client, cents=5)
    recorded = ledger.of("spend.recorded")
    assert recorded[0]["action"] == "draft invoices"
    assert "action" not in recorded[1]


# -- /totals (D1e) ------------------------------------------------------------------------

def test_totals_since_an_instant(client, clock):
    _cap(client)
    clock.at(-10)
    _spend(client, cents=100)
    clock.at(10)
    _spend(client, cents=40)
    client.post("/usage", json={"agent_id": AGENT, "model": "claude-opus-4-8",
                                "input_tokens": 1_000_000, "output_tokens": 0})  # $5 = 500c
    r = client.get(f"/totals/{AGENT}", params={"since": T0.isoformat()})
    assert r.status_code == 200
    assert r.json()["spent_cents"] == 540
    naive = client.get(f"/totals/{AGENT}", params={"since": "2026-09-13T10:00:00"})
    assert naive.json()["spent_cents"] == 540  # naive = UTC
    assert client.get(f"/totals/{AGENT}", params={"since": "yesterday"}).status_code == 422
    assert client.get("/totals/ghost", params={"since": T0.isoformat()}).status_code == 404


def test_totals_name_the_caps_currency(client):
    """The sentinel's USD token ceiling needs to know what the cents are in."""
    _cap(client)
    assert client.get(f"/totals/{AGENT}", params={"since": T0.isoformat()}).json()["currency"] == "USD"
    _cap(client, currency="CAD")
    assert client.get(f"/totals/{AGENT}", params={"since": T0.isoformat()}).json()["currency"] == "CAD"


# -- the migration ------------------------------------------------------------------------

PRE_D_SPEND = """
CREATE TABLE spend (
    event_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, ts TEXT NOT NULL,
    cents INTEGER NOT NULL, tokens INTEGER NOT NULL, actions INTEGER NOT NULL,
    note TEXT
);
CREATE INDEX idx_spend_agent_ts ON spend (agent_id, ts);
CREATE TABLE caps (
    agent_id TEXT PRIMARY KEY, currency TEXT, limit_cents INTEGER,
    token_limit INTEGER, action_limit INTEGER, period TEXT,
    escalate_at_pct INTEGER, on_breach TEXT
);
"""


def test_old_seven_column_spend_db_migrates_at_open(tmp_path, clock):
    path = tmp_path / "spend.sqlite3"
    conn = sqlite3.connect(path)
    with conn:
        conn.executescript(PRE_D_SPEND)
        conn.execute("INSERT INTO caps VALUES (?,?,?,?,?,?,?,?)",
                     (AGENT, "USD", 50_000, None, 10, "total", 80, "halt"))
        # the pre-D positional 7-value INSERT (core.py before D1)
        conn.execute("INSERT INTO spend VALUES (?,?,?,?,?,?,?)",
                     ("old-1", AGENT, (T0 - timedelta(hours=1)).isoformat(), 1_000, 0, 3, "pre-D"))
    conn.close()

    store = GovernorStore(path)
    try:
        assert store.spend_columns_added == ["action", "source"]
        columns = [r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(spend)")]
        assert columns == ["event_id", "agent_id", "ts", "cents", "tokens", "actions",
                           "note", "action", "source"]
        client = TestClient(create_app(store=store, clock=clock))
        s = _status(client)
        assert (s["spent_cents"], s["spent_actions"], s["spent_actions_self"],
                s["spent_actions_metered"]) == (1_000, 3, 3, 0)  # old row: self, unattributed
        body = _spend(client, actions=1, action="draft invoices", source="sentinel")
        assert (body["spent_actions"], body["spent_actions_metered"]) == (4, 1)
    finally:
        store.close()

    reopened = GovernorStore(path)
    try:
        assert reopened.spend_columns_added == []  # idempotent
    finally:
        reopened.close()

    # Rollback evidence for the README: after the first open, the pre-D
    # image's positional INSERT no longer fits the table.
    conn = sqlite3.connect(path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="9 columns but 7 values"):
            conn.execute("INSERT INTO spend VALUES (?,?,?,?,?,?,?)",
                         ("old-2", AGENT, T0.isoformat(), 0, 0, 1, None))
    finally:
        conn.close()


def test_fresh_db_takes_the_same_migration_path(tmp_path):
    store = GovernorStore(tmp_path / "fresh.sqlite3")
    try:
        assert store.spend_columns_added == ["action", "source"]
    finally:
        store.close()
