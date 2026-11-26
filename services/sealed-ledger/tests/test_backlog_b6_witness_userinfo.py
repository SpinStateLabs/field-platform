"""Backlog B6 (don.reviewer 1154 N1): ``sealed-ledger witness run`` refuses a FIELD_LEDGER_URL that carries userinfo,
as ``_served_base_url`` (every mutating verb) and ``verify-witness --events-url`` already do. The refusal is exit 2,
fixed text that never echoes the URL, and no client is built so nothing is sent. Every value is made up."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from sealed_ledger import witness as w
from sealed_ledger.cli import app as cli_app

runner = CliRunner()
FLY = "https://fly.test"
USER, PASSWORD = "witness-user-b6", "witness-PASS-b6-3e9d"


@pytest.fixture()
def no_clients(monkeypatch):
    built: list[str] = []

    def boom(*a, **k):
        built.append("client")
        raise AssertionError("no client may be built for a URL with userinfo")

    monkeypatch.setattr(w, "build_ledger_client", boom)
    monkeypatch.setattr(w, "build_fly_client", boom)
    monkeypatch.setattr(w.Witness, "tick", boom)
    return built


@pytest.mark.parametrize("url", [
    f"http://{USER}:{PASSWORD}@127.0.0.1:8002",
    f"http://{USER}@127.0.0.1:8002",
    f"https://:{PASSWORD}@ledger.example.invalid",
    f"http://{USER}:{PASSWORD}@[::1]:8002/",
    f"http://{USER}:{PASSWORD}@[::1:8002",            # unparseable: still refused by the hand check
])
def test_witness_run_refuses_a_ledger_url_with_userinfo(monkeypatch, no_clients, url):
    monkeypatch.setenv("FIELD_LEDGER_URL", url)
    r = runner.invoke(cli_app, ["witness", "run", "--once", "--estate", "gb10", "--fly-url", FLY])
    assert r.exit_code == 2
    assert "must not carry credentials" in r.output and "nothing was sent" in r.output
    assert PASSWORD not in r.output and USER not in r.output
    assert no_clients == []


def test_witness_run_refuses_userinfo_before_checking_the_fly_url(monkeypatch, no_clients):
    """The ledger URL check comes first: a bad --fly-url does not mask it."""
    monkeypatch.setenv("FIELD_LEDGER_URL", f"http://{USER}:{PASSWORD}@127.0.0.1:8002")
    r = runner.invoke(cli_app, ["witness", "run", "--once", "--estate", "gb10", "--fly-url", "http://fly.test"])
    assert r.exit_code == 2 and "must not carry credentials" in r.output and PASSWORD not in r.output


def test_witness_run_still_accepts_a_plain_ledger_url(monkeypatch):
    """A URL without userinfo goes on to build the clients (stubbed here: the tick reports appended)."""
    seen: dict[str, str] = {}

    class Outcome:
        direction1 = "appended"

    for name in ("FIELD_LEDGER_CALLER_ID", "FIELD_LEDGER_CALLER_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FIELD_LEDGER_URL", "http://127.0.0.1:8002")
    monkeypatch.setattr(w, "build_ledger_client", lambda url: seen.setdefault("ledger", url))
    monkeypatch.setattr(w, "build_fly_client", lambda: object())
    monkeypatch.setattr(w.Witness, "tick", lambda self: Outcome())
    r = runner.invoke(cli_app, ["witness", "run", "--once", "--estate", "gb10", "--fly-url", FLY])
    assert r.exit_code == 0, r.output
    assert seen == {"ledger": "http://127.0.0.1:8002"}
