"""S4-17: a bad --out and a blank, control, bidi or over-long org are named refusals (CLI exit 2, API 422)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from attestation_reporter import api as api_mod
from attestation_reporter import cli as cli_mod
from attestation_reporter.api import create_app
from attestation_reporter.engine import PackEngine
from attestation_reporter.org import MAX_ORG_CHARS, InvalidOrg, checked_org
from field_core.authn import ENV_VAR

MARK = "MADE-UP-MARKER-0123456789"
BAD_ORGS = [
    "", "   ", "\t", "Acme\nCorp", "Acme\rCorp", "Acme\x00Corp", "Acme‮Corp", "Acme​Corp",
    "Acme Corp", "Acme Corp", "Acme\x7fCorp", "Acme\x85Corp", "﻿Acme",
    MARK + "x" * MAX_ORG_CHARS,
]


# ---- the helper -----------------------------------------------------------------------------------------------------

def test_checked_org_strips_and_accepts_ordinary_names():
    assert checked_org("  Acme Corp ") == "Acme Corp"
    assert checked_org("Spin State Labs") == "Spin State Labs"
    assert checked_org("Société Générale 株式会社") == "Société Générale 株式会社"
    assert checked_org("o" * MAX_ORG_CHARS) == "o" * MAX_ORG_CHARS


@pytest.mark.parametrize("bad", BAD_ORGS + [None, 5])
def test_checked_org_refuses(bad):
    with pytest.raises(InvalidOrg):
        checked_org(bad)


def test_checked_org_one_over_the_limit_and_message_never_quotes():
    with pytest.raises(InvalidOrg) as info:
        checked_org(MARK + "y" * (MAX_ORG_CHARS - len(MARK) + 1))
    assert MARK not in str(info.value)


# ---- the API --------------------------------------------------------------------------------------------------------

@pytest.fixture()
def api(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    return TestClient(create_app(engine=PackEngine()), raise_server_exceptions=False)


@pytest.mark.parametrize("route", ["/pack", "/pack.html"])
@pytest.mark.parametrize("bad", BAD_ORGS)
def test_api_refuses_a_bad_org(api, route, bad):
    r = api.get(route, params={"org": bad})
    assert r.status_code == 422, (route, repr(bad), r.status_code)
    assert MARK not in r.text
    assert len(r.text) < 400


def test_api_ordinary_org_is_served_stripped(api):
    r = api.get("/pack", params={"org": "  Acme Corp "})
    assert r.status_code == 200, r.text
    assert r.json()["org"] == "Acme Corp"


def test_api_without_org_uses_the_engine_default(api):
    assert api.get("/pack").json()["org"] == "Spin State Labs"


# ---- the CLI --------------------------------------------------------------------------------------------------------

@pytest.fixture()
def cli(monkeypatch):
    queried = []

    def engine_from_env(org="Spin State Labs"):
        queried.append(org)
        return PackEngine(org=org)

    monkeypatch.setattr(api_mod, "engine_from_env", engine_from_env)
    runner = CliRunner()

    def run(*args):
        return runner.invoke(cli_mod.app, ["render", "--no-pdf", *args])

    run.queried = queried
    return run


@pytest.mark.parametrize("bad", ["", "   ", "Acme\nCorp", "Acme‮Corp", MARK + "x" * MAX_ORG_CHARS])
def test_cli_refuses_a_bad_org_before_any_service_is_queried(cli, tmp_path, bad):
    r = cli("--out", str(tmp_path / "o"), "--org", bad)
    assert r.exit_code == 2, r.output
    assert "refused:" in r.output and MARK not in r.output and "Traceback" not in r.output
    assert cli.queried == []
    assert not (tmp_path / "o").exists()


def test_cli_out_naming_an_existing_file_is_refused_before_any_service_is_queried(cli, tmp_path):
    f = tmp_path / "afile"
    f.write_text("x", encoding="utf-8")
    r = cli("--out", str(f))
    assert r.exit_code == 2, r.output
    assert "refused:" in r.output and "Traceback" not in r.output
    assert cli.queried == []
    assert f.read_text(encoding="utf-8") == "x"


def test_cli_out_under_a_file_is_refused(cli, tmp_path):
    f = tmp_path / "afile"
    f.write_text("x", encoding="utf-8")
    r = cli("--out", str(f / "sub"))
    assert r.exit_code == 2 and "refused:" in r.output and cli.queried == []


def test_cli_write_failure_is_refused_not_a_traceback(cli, tmp_path):
    out = tmp_path / "o"
    (out / "board-pack.json").mkdir(parents=True)          # the file cannot be written: it is a directory
    r = cli("--out", str(out))
    assert r.exit_code == 2, r.output
    assert "refused:" in r.output and "Traceback" not in r.output
    assert not (out / "board-pack.html").exists()          # nothing half-written after the failure


def test_cli_happy_path_unchanged(cli, tmp_path):
    out = tmp_path / "o"
    r = cli("--out", str(out), "--org", "  Acme Corp ")
    assert r.exit_code == 0, r.output
    assert (out / "board-pack.json").exists() and (out / "board-pack.html").exists()
    assert '"org": "Acme Corp"' in (out / "board-pack.json").read_text(encoding="utf-8")
