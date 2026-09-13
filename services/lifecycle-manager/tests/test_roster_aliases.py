"""A1b — owners.csv `aliases` column: one human, several registry strings.

Every guard here has a test that fails when the guard is removed:
- an alias makes an agent non-orphaned, exactly like the owner string;
- a string on no row (a substring of an alias, a whitespace variant) is still
  an orphan — matching stays case-insensitive and exact after strip;
- blank alias entries never become "" (which an owner-less record would match);
- aliases on a row with no owner are ignored with the row;
- `roster_size` counts humans, not alias strings;
- an unquoted comma is refused by name instead of crashing on `list.strip`;
- an unquoted `Name, Org` that yields exactly the header's field count is
  refused too (a value starting with a space after an unquoted comma), in the
  engine, the served sweep and the CLI (which kills nothing);
- a roster WITHOUT an aliases column parses exactly as it did before A1b.

The existing suites are unmodified; the pre-A1b behaviour is pinned here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, RegistryClient
from lifecycle_manager.api import create_app
from lifecycle_manager.engine import (
    LifecycleEngine,
    RosterEntry,
    parse_roster,
    parse_roster_entries,
)
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)

# The shape A1 arms on the GB10: Don's two registry strings are ONE human.
# The comma inside the alias forces CSV quoting, exactly as on the estate.
ALIAS_ROSTER = (
    "owner,aliases\n"
    'Don Hagell,"Don Hagell, Spin State Labs;D. Hagell"\n'
)
# The pre-A1b roster used by test_lifecycle_manager.py / test_api.py.
LEGACY_ROSTER = "owner,department\nAP Team Lead,finance\nController Spin State,finance\n"


# --- fakes: the sweep needs only list_agents, GET /tokens and append ----------


class FakeRegistry:
    def __init__(self, agents: list[dict]):
        self._agents = agents

    def list_agents(self) -> list[dict]:
        return [dict(a) for a in self._agents]


class NoTokens:
    def get(self, path: str):
        assert path == "/tokens"
        return []


class RecordingLedger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str | None, dict]] = []

    def append(self, event_type, payload=None, agent_id=None):
        self.events.append((event_type, agent_id, payload or {}))


def agent(agent_id: str, owner: str, status: str = "active") -> dict:
    # created_at == now, so nothing is due for re-attestation: orphans only.
    return {"agent_id": agent_id, "owner": owner, "status": status,
            "created_at": NOW.isoformat()}


def sweep(roster_csv: str, agents: list[dict]):
    ledger = RecordingLedger()
    engine = LifecycleEngine(registry=FakeRegistry(agents), delegation=NoTokens(),
                             ledger=ledger)
    return engine.sweep(roster_csv, now=NOW), ledger


def orphan_ids(report) -> list[str]:
    return sorted(o.agent_id for o in report.orphans)


# --- the alias match ----------------------------------------------------------


def test_an_agent_owned_by_an_alias_is_not_an_orphan():
    report, ledger = sweep(ALIAS_ROSTER, [
        agent("by-owner", "Don Hagell"),
        agent("by-alias", "Don Hagell, Spin State Labs"),
        agent("by-alias-other-case", "d. hagell"),
    ])
    assert orphan_ids(report) == []
    assert [e for e in ledger.events if e[0] == "lifecycle.orphan"] == []


def test_the_alias_column_is_what_clears_the_orphan():
    """Positive control for the test above: the SAME agents against the same
    owner without the alias are orphans, so the alias is doing the work."""
    report, _ = sweep("owner\nDon Hagell\n", [
        agent("by-alias", "Don Hagell, Spin State Labs"),
        agent("by-alias-other-case", "d. hagell"),
    ])
    assert orphan_ids(report) == ["by-alias", "by-alias-other-case"]


def test_a_string_on_no_row_is_still_an_orphan():
    """Exact after strip, case-insensitive — nothing looser. A substring of an
    alias, a doubled space and an unrelated owner are all orphans."""
    report, ledger = sweep(ALIAS_ROSTER, [
        agent("substring-of-alias", "Spin State Labs"),
        agent("doubled-space", "Don Hagell,  Spin State Labs"),
        agent("unrelated", "Verifier"),
        agent("owned", "Don Hagell"),
    ])
    assert orphan_ids(report) == ["doubled-space", "substring-of-alias", "unrelated"]
    assert sorted(e[1] for e in ledger.events if e[0] == "lifecycle.orphan") == [
        "doubled-space", "substring-of-alias", "unrelated"]


def test_alias_values_are_stripped_like_owners():
    roster = 'owner,aliases\nDon Hagell,"  DH  ;  Don H  "\n'
    assert parse_roster(roster) == {"don hagell", "dh", "don h"}
    report, _ = sweep(roster, [agent("a", "DH"), agent("b", "don h")])
    assert orphan_ids(report) == []


# --- blank and owner-less entries ---------------------------------------------


def test_blank_alias_entries_are_ignored():
    """`;;`, a trailing `;` and whitespace-only entries must never become an
    empty-string alias — an agent recorded with an empty owner would match it
    and silently stop being an orphan."""
    roster = 'owner,aliases\nDon Hagell,"DH;; ;"\n'
    assert parse_roster_entries(roster) == [RosterEntry(owner="Don Hagell", aliases=("DH",))]
    assert "" not in parse_roster(roster)
    report, _ = sweep(roster, [agent("blank-owner", ""), agent("dh", "DH")])
    assert orphan_ids(report) == ["blank-owner"]


def test_aliases_on_a_row_without_an_owner_are_ignored():
    """An alias belongs to a named human. A row with a blank owner is dropped
    whole, so its aliases cannot own anything."""
    roster = 'owner,aliases\n,Ghost Owner\nDon Hagell,\n'
    assert parse_roster(roster) == {"don hagell"}
    report, _ = sweep(roster, [agent("ghost", "Ghost Owner"), agent("blank-owner", "")])
    assert orphan_ids(report) == ["blank-owner", "ghost"]
    assert report.roster_size == 1


def test_roster_size_counts_humans_not_alias_strings():
    roster = (
        "owner,aliases\n"
        'Don Hagell,"Don Hagell, Spin State Labs;D. Hagell"\n'
        "AP Team Lead,AP Lead\n"
    )
    report, _ = sweep(roster, [agent("x", "Nobody")])
    assert report.roster_size == 2
    assert len(parse_roster(roster)) == 5
    assert report.orphans[0].reason == "owner 'Nobody' not found in roster (2 entries)"


# --- malformed CSV ------------------------------------------------------------


def test_an_unquoted_comma_is_refused_by_name():
    """`Don Hagell, Spin State Labs` unquoted is three fields under a two-column
    header. Before A1b that crashed with "'list' object has no attribute
    'strip'"; now the refusal names the line and the fix."""
    roster = "owner,aliases\nDon Hagell,Don Hagell, Spin State Labs\n"
    with pytest.raises(ValueError) as exc:
        parse_roster(roster)
    assert "line 2" in str(exc.value)
    assert "quote" in str(exc.value)


def test_an_unquoted_comma_stops_the_served_sweep_and_the_tick(tmp_path, monkeypatch):
    """Where the refusal surfaces: POST /sweep answers 500 and a scheduled tick
    reports ok: false — and in both cases the sweep never ran (no ledger event,
    no findings file)."""
    from lifecycle_manager.api import scheduled_tick

    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    bad = tmp_path / "owners.csv"
    bad.write_text("owner,aliases\nDon Hagell,Don Hagell, Spin State Labs\n", encoding="utf-8")
    monkeypatch.setenv("FIELD_LIFECYCLE_ROSTER", str(bad))
    ledger = RecordingLedger()
    served = create_app(registry=FakeRegistry([agent("a", "Verifier")]),
                        delegation=NoTokens(), ledger=ledger, every=0)

    r = TestClient(served, raise_server_exceptions=False).post("/sweep", json={})
    assert r.status_code == 500
    tick = scheduled_tick(served)
    assert tick["ok"] is False
    assert "more fields than the header" in tick["error"]
    assert ledger.events == []
    assert not (tmp_path / "data" / "lifecycle" / "last_sweep.json").exists()


# --- the roster without an aliases column is unchanged ------------------------


def test_a_roster_without_an_aliases_column_parses_exactly_as_before():
    assert parse_roster(LEGACY_ROSTER) == {"ap team lead", "controller spin state"}
    assert parse_roster_entries(LEGACY_ROSTER) == [
        RosterEntry(owner="AP Team Lead"), RosterEntry(owner="Controller Spin State")]
    # the `name` fallback column still works, and extra columns stay ignored
    assert parse_roster("name,team\nJane Smith,finance\n") == {"jane smith"}
    # duplicates collapse, as the old set did
    assert parse_roster("owner\nJane Smith\njane smith\n") == {"jane smith"}

    report, ledger = sweep(LEGACY_ROSTER, [
        agent("invoicing-agent", "AP Team Lead"),
        agent("rogue-experiment", "Departed Employee"),
        agent("retired-one", "Departed Employee", status="retired"),
    ])
    assert report.roster_size == 2
    assert orphan_ids(report) == ["rogue-experiment"]
    assert report.orphans[0].reason == (
        "owner 'Departed Employee' not found in roster (2 entries)")
    assert [e[0] for e in ledger.events] == ["lifecycle.orphan"]
    assert report.escalations_written == 1


# --- served and CLI paths -----------------------------------------------------


def test_served_sweep_reads_aliases_from_the_roster_file(tmp_path, monkeypatch):
    """The path A1 arms: FIELD_LIFECYCLE_ROSTER names an owners.csv with an
    aliases column, and real registry records carry Don's two strings."""
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    roster = tmp_path / "owners.csv"
    roster.write_text(ALIAS_ROSTER, encoding="utf-8")
    monkeypatch.setenv("FIELD_LIFECYCLE_ROSTER", str(roster))

    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    delegation = TestClient(create_delegation_app(
        store=TokenStore(tmp_path / "tokens.sqlite3"),
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        registry=RegistryClient(client=registry, base_url="http://t"),
    ))
    for agent_id, owner in (("ssl-invoicing-agent", "Don Hagell, Spin State Labs"),
                            ("volatility-trader", "Don Hagell"),
                            ("smoke-agent", "Verifier")):
        r = registry.post("/agents", json={"agent_id": agent_id, "name": agent_id,
                                           "owner": owner, "domain": "finance"})
        assert r.status_code == 201, r.text

    app = TestClient(create_app(
        registry=RegistryClient(client=registry, base_url="http://t"),
        delegation=delegation,
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        every=0,
    ))
    r = app.post("/sweep", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["roster_size"] == 1
    assert [o["agent_id"] for o in body["orphans"]] == ["smoke-agent"]


def _patch_cli_clients(monkeypatch, agents: list[dict]) -> RecordingLedger:
    """`lifecycle sweep` builds its clients inside the command; replace them
    at the names it imports, so the CLI reads a real file and runs the real
    engine with no network."""
    import field_core.clients as clients
    import httpx

    ledger = RecordingLedger()
    monkeypatch.setattr(clients, "RegistryClient", lambda *a, **k: FakeRegistry(agents))
    monkeypatch.setattr(clients, "LedgerClient", lambda *a, **k: ledger)
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: NoTokens())
    return ledger


def test_cli_sweep_exits_0_when_an_alias_owns_every_agent(tmp_path, monkeypatch):
    from lifecycle_manager.cli import app

    roster = tmp_path / "owners.csv"
    roster.write_text(ALIAS_ROSTER, encoding="utf-8")
    _patch_cli_clients(monkeypatch, [agent("ssl-invoicing-agent", "Don Hagell, Spin State Labs")])
    result = CliRunner().invoke(app, ["sweep", "--roster", str(roster)])
    assert result.exit_code == 0, result.output
    assert '"orphans": []' in result.output


def test_cli_sweep_exits_3_for_an_owner_on_no_row(tmp_path, monkeypatch):
    from lifecycle_manager.cli import app

    roster = tmp_path / "owners.csv"
    roster.write_text(ALIAS_ROSTER, encoding="utf-8")
    ledger = _patch_cli_clients(monkeypatch, [agent("smoke-agent", "Verifier")])
    result = CliRunner().invoke(app, ["sweep", "--roster", str(roster)])
    assert result.exit_code == 3, result.output
    assert [e[1] for e in ledger.events if e[0] == "lifecycle.orphan"] == ["smoke-agent"]


# --- an unquoted comma with exactly the header's field count --------------------


@pytest.mark.parametrize("roster", [
    "owner,aliases\nDon Hagell, Spin State Labs\n",      # the estate string, unquoted
    "owner,department\nDon Hagell, Spin State Labs\n",   # the legacy header: owner half-read
    "owner,aliases\nJane Smith,JS\nDon Hagell, Spin State Labs\n",
    "owner,aliases\nDon Hagell,\tSpin State Labs\n",        # TAB: skipinitialspace skips only U+0020
    "owner,aliases\nDon Hagell,\u00a0Spin State Labs\n",    # NBSP (pasted from a document)
    "owner,aliases\nDon Hagell,\u3000Spin State Labs\n",    # ideographic space
], ids=["aliases-header", "legacy-header", "second-data-row", "tab", "nbsp", "ideographic-space"])
def test_an_unquoted_comma_with_exactly_the_header_field_count_is_refused(roster):
    """Two fields under a two-column header: the `None in row` guard cannot see
    it, and unguarded it becomes owner `Don Hagell` + alias `Spin State Labs`,
    which clears an agent owned by `Spin State Labs` and orphans (and, with
    --auto-kill-orphans, kills) the agents of `Don Hagell, Spin State Labs`."""
    line = roster.count("\n")  # the offending row is the last one
    with pytest.raises(ValueError) as exc:
        parse_roster_entries(roster)
    assert f"line {line}" in str(exc.value)
    assert "quote" in str(exc.value)

    ledger = RecordingLedger()
    engine = LifecycleEngine(registry=FakeRegistry([
        agent("org-owned", "Spin State Labs"),
        agent("ssl-invoicing-agent", "Don Hagell, Spin State Labs"),
    ]), delegation=NoTokens(), ledger=ledger)
    with pytest.raises(ValueError):
        engine.sweep(roster, now=NOW)
    assert ledger.events == []


def test_quoted_commas_and_blank_trailing_spaces_are_still_accepted():
    """Positive controls for the refusal above: spaces INSIDE quotes, spaces in
    the header, and a comma followed only by blank space are not the signature."""
    assert parse_roster_entries('owner,aliases\nDon Hagell,"Don Hagell, Spin State Labs"\n') == [
        RosterEntry(owner="Don Hagell", aliases=("Don Hagell, Spin State Labs",))]
    assert parse_roster_entries('owner,aliases\nDon Hagell," DH ; D. Hagell"\n') == [
        RosterEntry(owner="Don Hagell", aliases=("DH", "D. Hagell"))]
    assert parse_roster("owner, aliases\nDon Hagell,DH\n") == {"don hagell", "dh"}
    assert parse_roster("owner,aliases\nDon Hagell, \n") == {"don hagell"}
    # other blanks inside quotes, in the header, or before a line end are not the signature either
    assert parse_roster_entries('owner,\taliases\nDon Hagell,"\tDH;\u00a0D. Hagell"\n') == [
        RosterEntry(owner="Don Hagell", aliases=("DH", "D. Hagell"))]
    assert parse_roster("owner,aliases\r\nDon Hagell,\t\r\n") == {"don hagell"}


def test_an_unquoted_comma_with_exactly_the_header_field_count_stops_the_served_sweep(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    ledger = RecordingLedger()
    served = create_app(registry=FakeRegistry([agent("org-owned", "Spin State Labs")]),
                        delegation=NoTokens(), ledger=ledger, every=0)
    r = TestClient(served, raise_server_exceptions=False).post(
        "/sweep", json={"roster_csv": "owner,aliases\nDon Hagell, Spin State Labs\n"})
    assert r.status_code == 500
    assert ledger.events == []


def test_cli_sweep_refuses_an_unquoted_comma_and_kills_nothing(tmp_path, monkeypatch):
    """The README's "the CLI exits non-zero": with --auto-kill-orphans armed, a
    half-read roster would kill Don's agents. The CLI must stop before the
    sweep: non-zero (not 0, not the findings code 3), no ledger event, no kill."""
    import field_core.clients as clients
    import httpx

    from lifecycle_manager.cli import app

    roster = tmp_path / "owners.csv"
    roster.write_text("owner,aliases\nDon Hagell, Spin State Labs\n", encoding="utf-8")
    ledger = RecordingLedger()
    calls: list[tuple] = []

    class RecordingHttp(NoTokens):
        def post(self, *a, **k):
            calls.append(("post", a, k))
            raise AssertionError("no kill may be attempted")

    monkeypatch.setattr(clients, "RegistryClient", lambda *a, **k: FakeRegistry([
        agent("ssl-invoicing-agent", "Don Hagell, Spin State Labs"),
        agent("org-owned", "Spin State Labs"),
    ]))
    monkeypatch.setattr(clients, "LedgerClient", lambda *a, **k: ledger)
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: RecordingHttp())

    result = CliRunner().invoke(app, ["sweep", "--roster", str(roster), "--auto-kill-orphans"])
    assert result.exit_code == 1, result.output  # not 0 (clean), not 3 (findings)
    assert isinstance(result.exception, ValueError)
    assert "a value starts with whitespace after an unquoted comma" in str(result.exception)
    assert ledger.events == [] and calls == []
