"""S12-20: `ledger export` on a busy or unreadable ledger is the exit-4 BUSY / UNREADABLE every sibling verb gives, never a
traceback; a corrupt ledger or an unfilterable stored event is exit 1 naming only the class. No bundle is written."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import UNREADABLE_PREFIX, LedgerBusy, LedgerCorrupt, LedgerStore, LedgerUnreadable

runner = CliRunner()


@pytest.fixture()
def store(tmp_path):
    s = LedgerStore(tmp_path / "events.jsonl")
    s.append("action", {"n": 1}, agent_id="a")
    return s


def _export(store, tmp_path):
    out = tmp_path / "out"
    res = runner.invoke(cli_app, ["export", "--path", str(store.path), "--out-dir", str(out)])
    assert "Traceback" not in res.output
    assert not out.exists() or not any(out.iterdir())  # no bundle directory written
    return res


def _raise(exc):
    def boom(self, *a, **kw):
        raise exc
    return boom


def _raise_when(exc, *, opening: bool):
    """_take_snapshot raising only while the store is being opened (open_only=True) or only for the export read."""
    def boom(self, *a, **kw):
        if bool(kw.get("open_only")) == opening:
            raise exc
        return real(self, *a, **kw)
    real = LedgerStore._take_snapshot
    return boom


@pytest.mark.parametrize("opening", [False, True], ids=["at-export-read", "at-store-open"])
def test_a_busy_ledger_is_exit_4_busy(store, tmp_path, monkeypatch, opening):
    monkeypatch.setattr(LedgerStore, "_take_snapshot", _raise_when(
        LedgerBusy("ledger busy: no consistent snapshot after 3 attempts"), opening=opening))
    res = _export(store, tmp_path)
    assert res.exit_code == 4 and "BUSY" in res.output and "retry" in res.output
    assert res.exception is None or isinstance(res.exception, SystemExit)


@pytest.mark.parametrize("opening", [False, True], ids=["at-export-read", "at-store-open"])
def test_an_unreadable_ledger_is_exit_4_unreadable_without_retry(store, tmp_path, monkeypatch, opening):
    monkeypatch.setattr(LedgerStore, "_take_snapshot", _raise_when(
        LedgerUnreadable(UNREADABLE_PREFIX + "permission denied, not a sharing violation"), opening=opening))
    res = _export(store, tmp_path)
    assert res.exit_code == 4 and "UNREADABLE" in res.output and "retry" not in res.output
    assert res.exception is None or isinstance(res.exception, SystemExit)


def test_a_corrupt_ledger_is_exit_1_naming_only_the_class(store, tmp_path, monkeypatch):
    monkeypatch.setattr(LedgerStore, "export", _raise(LedgerCorrupt("chain broken at SECRET-LINE-TEXT")))
    res = _export(store, tmp_path)
    assert res.exit_code == 1 and "LedgerCorrupt" in res.output and "SECRET-LINE-TEXT" not in res.output


def test_an_unfilterable_stored_event_is_exit_1_naming_only_the_class(store, tmp_path, monkeypatch):
    monkeypatch.setattr(LedgerStore, "export", _raise(
        ValueError("event at index 3 has a ts that is not ISO 8601: 'SECRET-TS'")))
    res = _export(store, tmp_path)
    assert res.exit_code == 1 and "ValueError" in res.output and "SECRET-TS" not in res.output


def test_a_bad_time_bound_is_still_exit_2(store, tmp_path):
    out = tmp_path / "out"
    res = runner.invoke(cli_app, ["export", "--path", str(store.path), "--out-dir", str(out), "--since", "not-a-date"])
    assert res.exit_code == 2 and "Traceback" not in res.output
