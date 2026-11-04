"""S3-1/S3-2: the CLI sweep (and LifecycleEngine.sweep) refuse a roster with no
owner, as the served path already does, instead of orphaning (and, with
--auto-kill-orphans, killing) every agent. A leading UTF-8 BOM no longer hides
the ``owner`` header. Stub clients: a zero /kill count is the assertion."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from lifecycle_manager import cli
from lifecycle_manager.engine import (
    LifecycleEngine, LifecycleError, SweepConfig, parse_roster_entries,
)

BOM = chr(0xFEFF)
AGENTS = [
    {"agent_id": "a1", "owner": "Alice", "status": "active",
     "created_at": "2099-01-01T00:00:00+00:00"},
    {"agent_id": "a2", "owner": "Bob", "status": "active",
     "created_at": "2099-01-01T00:00:00+00:00"},
]


class Registry:
    def list_agents(self):
        return list(AGENTS)


class Delegation:
    def get(self, url, **kw):
        class R:
            status_code = 200

            def json(self):
                return []
        return R()


class Ledger:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload=None, agent_id=None):
        self.events.append((event_type, agent_id))


class Kill:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, **kw):  # noqa: A002
        self.calls.append(url)

        class R:
            status_code = 200
        return R()


@pytest.fixture()
def stack(monkeypatch):
    ledger, kill = Ledger(), Kill()
    clients = {"registry": Registry(), "delegation": Delegation(),
               "ledger": ledger, "killswitch": kill}
    monkeypatch.setattr(cli, "estate_clients", lambda pair, timeout=20.0: clients)
    monkeypatch.setattr(cli, "operator_pair", lambda *a, **k: None)
    return ledger, kill


def _run(tmp_path, text, *flags):
    f = tmp_path / "owners.csv"
    f.write_text(text, encoding="utf-8")
    return CliRunner().invoke(cli.app, ["sweep", "--roster", str(f), *flags])


@pytest.mark.parametrize("text", [
    "owner\n",
    "owner,aliases\n",
    "",
    "department,team\nfinance,ap\n",
    "owner,aliases\n  ,x\n",
])
def test_an_ownerless_roster_is_refused_and_nothing_is_killed_or_ledgered(stack, tmp_path, text):
    ledger, kill = stack
    res = _run(tmp_path, text, "--auto-kill-orphans")
    assert res.exit_code == 2
    assert "no owners" in res.output
    assert kill.calls == []
    assert ledger.events == []


def test_the_engine_refuses_directly(stack):
    ledger, kill = stack
    eng = LifecycleEngine(Registry(), Delegation(), ledger=ledger, killswitch=kill)
    with pytest.raises(LifecycleError):
        eng.sweep("owner\n", SweepConfig(auto_kill_orphans=True))
    assert kill.calls == [] and ledger.events == []


def test_a_bom_before_the_owner_header_is_read(stack, tmp_path):
    assert [e.owner for e in parse_roster_entries(BOM + "owner\nAlice\n")] == ["Alice"]
    ledger, kill = stack
    res = _run(tmp_path, BOM + "owner\nAlice\nBob\n", "--auto-kill-orphans")
    assert res.exit_code == 0, res.output
    assert kill.calls == []


def test_a_healthy_roster_still_kills_only_the_real_orphan(stack, tmp_path):
    ledger, kill = stack
    res = _run(tmp_path, "owner\nAlice\n", "--auto-kill-orphans")
    assert res.exit_code == 3  # an orphan was found
    assert kill.calls == ["/kill/a2"]
