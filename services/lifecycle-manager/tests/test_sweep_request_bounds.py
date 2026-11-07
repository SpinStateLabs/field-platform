"""`POST /sweep` and `lifecycle-manager sweep`: expiry_days and reattest_days are 1..3650 (scout P-11).

Before: only `ge=1`. A value near 10**9 reached `now + timedelta(days=...)` in the engine and raised OverflowError (a
500 over HTTP, a traceback from the CLI). The bound is 3650 days (ten years); Don may change the number, the two
modules and these tests move together. The scheduled tick uses the defaults, so only manual callers were exposed."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, RegistryClient
from lifecycle_manager import api as api_module
from lifecycle_manager import cli as cli_module
from lifecycle_manager.api import create_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")   # typer's rich error panel is colour-styled when CI sets GITHUB_ACTIONS
BOUND = 3650
ROSTER = "owner,department\nAP Team Lead,finance\n"
FIELDS = ("expiry_days", "reattest_days")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("FIELD_LIFECYCLE_ROSTER", raising=False)
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    delegation = TestClient(create_delegation_app(
        store=TokenStore(tmp_path / "tokens.sqlite3"),
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        registry=RegistryClient(client=registry, base_url="http://t"),
    ))
    return TestClient(create_app(
        registry=RegistryClient(client=registry, base_url="http://t"),
        delegation=delegation,
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        killswitch=None,
    ))


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("value", [BOUND + 1, 10**9, 10**18])
def test_a_value_above_the_bound_is_422(client, field, value):
    r = client.post("/sweep", json={"roster_csv": ROSTER, field: value})
    assert r.status_code == 422, (field, value, r.status_code)


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("value", [1, 30, BOUND])
def test_a_value_inside_the_bound_sweeps(client, field, value):
    r = client.post("/sweep", json={"roster_csv": ROSTER, field: value})
    assert r.status_code == 200, (field, value, r.status_code, r.text)


@pytest.mark.parametrize("field", FIELDS)
def test_zero_is_still_422(client, field):
    assert client.post("/sweep", json={"roster_csv": ROSTER, field: 0}).status_code == 422


def test_the_api_and_the_cli_share_one_bound():
    assert api_module.MAX_SWEEP_DAYS == cli_module.MAX_SWEEP_DAYS == BOUND


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    roster = tmp_path / "owners.csv"
    roster.write_text(ROSTER, encoding="utf-8")

    def reached(*a, **k):
        raise RuntimeError("estate clients reached: the options were accepted")

    monkeypatch.setattr(cli_module, "estate_clients", reached)
    runner = CliRunner()
    return lambda *args: runner.invoke(cli_module.app, ["sweep", "--roster", str(roster), *args])


@pytest.mark.parametrize("option", ["--expiry-days", "--reattest-days"])
@pytest.mark.parametrize("value", [str(BOUND + 1), str(10**9)])
def test_the_cli_refuses_a_value_above_the_bound_by_name_with_exit_2(cli, option, value):
    r = cli(option, value)
    assert r.exit_code == 2, (option, value, r.exit_code, r.output)
    plain = ANSI.sub("", r.output)
    assert option in plain, plain


@pytest.mark.parametrize("option", ["--expiry-days", "--reattest-days"])
@pytest.mark.parametrize("value", ["1", str(BOUND)])
def test_the_cli_accepts_a_value_inside_the_bound(cli, option, value):
    r = cli(option, value)
    assert isinstance(r.exception, RuntimeError), (option, value, r.exit_code, r.output)
