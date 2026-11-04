"""S7-10: provision, decommission and sweep write their report file AFTER the estate was changed.
An unwritable path must not lose the report (print it, name the file, exit 4), and an overflowing
--ttl-days is a usage error (exit 2) before any call."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from lifecycle_manager import cli as cli_mod
from lifecycle_manager import engine as engine_mod
from lifecycle_manager.cli import EXIT_REPORT_NOT_WRITTEN, app

REPORT_JSON = '{"agent_id": "demo-agent", "ok": true}'


class FakeEngine:
    """Records every transition; answers a completed report."""

    calls: list[str] = []

    def __init__(self, **_kw):
        pass

    def provision(self, **_kw):
        FakeEngine.calls.append("provision")
        return SimpleNamespace(ok=ok_flag["ok"], steps=[SimpleNamespace(step="mint", outcome="failed")],
                               model_dump_json=lambda indent=None: REPORT_JSON)

    def decommission(self, agent_id, **_kw):
        FakeEngine.calls.append(f"decommission:{agent_id}")
        return SimpleNamespace(ok=ok_flag["ok"], steps=[], model_dump_json=lambda indent=None: REPORT_JSON)


ok_flag = {"ok": True}


@pytest.fixture(autouse=True)
def _fake_estate(monkeypatch):
    FakeEngine.calls = []
    ok_flag["ok"] = True
    monkeypatch.setattr(engine_mod, "LifecycleEngine", FakeEngine)
    monkeypatch.setattr(cli_mod, "_provision_clients", lambda pair=None: {})


def _provision(*extra):
    return CliRunner().invoke(app, ["provision", "--manifest", "m.yaml", "--owner", "AP Team Lead",
                                    "--domain", "finance", "--grantor", "controller", *extra])


def _decommission(*extra):
    return CliRunner().invoke(app, ["decommission", "demo-agent", "--by", "controller",
                                    "--reason", "test", *extra])


def test_decommission_with_an_unwritable_out_prints_the_report_and_exits_4(tmp_path):
    r = _decommission("--out", str(tmp_path / "missing-dir" / "report.json"))
    assert FakeEngine.calls == ["decommission:demo-agent"]          # the transition ran
    assert REPORT_JSON in r.stdout                                    # and its record is not lost
    assert "error: could not write" in r.output and "FileNotFoundError" in r.output
    assert r.exit_code == EXIT_REPORT_NOT_WRITTEN == 4


def test_provision_with_an_unwritable_out_prints_the_report_and_exits_4(tmp_path):
    r = _provision("--ttl-days", "30", "--out", str(tmp_path / "missing-dir" / "p.json"))
    assert FakeEngine.calls == ["provision"]
    assert REPORT_JSON in r.stdout
    assert "error: could not write" in r.output
    assert r.exit_code == 4


def test_an_out_that_is_a_directory_is_the_same(tmp_path):
    r = _decommission("--out", str(tmp_path))
    assert REPORT_JSON in r.stdout and r.exit_code == 4


def test_a_writable_out_is_unchanged(tmp_path):
    out = tmp_path / "report.json"
    r = _decommission("--out", str(out))
    assert r.exit_code == 0 and out.read_text(encoding="utf-8") == REPORT_JSON
    assert f"decommission report written to {out}" in r.stdout


def test_a_failed_transition_keeps_exit_1_even_when_the_write_fails(tmp_path):
    ok_flag["ok"] = False
    r = _decommission("--out", str(tmp_path / "missing-dir" / "r.json"))
    assert REPORT_JSON in r.stdout and r.exit_code == 1


def test_sweep_with_a_markdown_path_that_is_a_directory_prints_the_json_and_exits_4(tmp_path, monkeypatch):
    report = SimpleNamespace(expiring=[], reattestation_due=[], orphans=[], retention_policy=None,
                             witness=None, model_dump_json=lambda indent=None: '{"sweep": "json"}')

    class SweepEngine:
        def __init__(self, **_kw):
            pass

        def sweep(self, **_kw):
            return report
    monkeypatch.setattr(engine_mod, "LifecycleEngine", SweepEngine)
    monkeypatch.setattr(engine_mod, "render_markdown", lambda r: "# md")
    monkeypatch.setattr(cli_mod, "estate_clients", lambda *a, **k: {
        "ledger": object(), "registry": object(), "delegation": object(), "killswitch": object()})
    monkeypatch.setattr(engine_mod, "witness_watch_from_env", lambda: None)
    roster = tmp_path / "owners.csv"
    roster.write_text("owner\nAP Team Lead\n", encoding="utf-8")

    r = CliRunner().invoke(app, ["sweep", "--roster", str(roster), "--markdown", str(tmp_path)])
    assert '{"sweep": "json"}' in r.stdout and "error: could not write" in r.output
    assert r.exit_code == 4

    report.orphans = ["x"]                                           # findings keep exit 3
    r = CliRunner().invoke(app, ["sweep", "--roster", str(roster), "--markdown", str(tmp_path)])
    assert r.exit_code == 3 and '{"sweep": "json"}' in r.stdout


@pytest.mark.parametrize("days", ["1000000000", "1000001", "99999999999999999999"])
def test_an_overflowing_ttl_days_is_a_usage_error_before_any_call(days):
    r = _provision("--ttl-days", days)
    assert r.exit_code == 2
    assert "Traceback" not in r.output and not isinstance(r.exception, OverflowError)
    assert FakeEngine.calls == []


def test_the_largest_allowed_ttl_still_provisions(tmp_path):
    r = _provision("--ttl-days", str(cli_mod.MAX_TTL_DAYS), "--out", str(tmp_path / "p.json"))
    assert r.exit_code == 0 and FakeEngine.calls == ["provision"]


def test_the_ttl_bound_keeps_now_plus_ttl_inside_datetime_range():
    from datetime import datetime, timedelta, timezone
    assert (datetime.now(timezone.utc) + timedelta(days=cli_mod.MAX_TTL_DAYS)).year < 9999
