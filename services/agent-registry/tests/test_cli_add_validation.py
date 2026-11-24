"""S7-15 — `registry add`: an invalid field is `error: invalid <fields>` (exit 2, nothing
written, no input text echoed), and a successful add says it is not on the ledger."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from agent_registry import cli
from agent_registry.store import RegistryStore

SECRET = "SENTINEL-VALUE-123"


def _add(db, *args):
    return CliRunner().invoke(cli.app, ["add", *args, "--path", str(db)])


def _rows(db):
    s = RegistryStore(db)
    try:
        return s.list()
    finally:
        s.close()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("FIELD_LEDGER_URL", raising=False)
    monkeypatch.delenv("FIELD_MANIFEST_DIR", raising=False)


def test_bad_id_is_a_named_exit_2_not_a_traceback(tmp_path):
    db = tmp_path / "a.sqlite3"
    r = _add(db, f"Bad Id! {SECRET}", "--name", "X", "--owner", "Y")
    assert r.exit_code == 2, r.output
    assert "error: invalid agent_id" in r.output
    assert SECRET not in r.output and "Bad Id" not in r.output
    assert r.exception is None or isinstance(r.exception, SystemExit)
    assert _rows(db) == []


def test_empty_name_is_named(tmp_path):
    db = tmp_path / "a.sqlite3"
    r = _add(db, "ok-agent", "--name", "", "--owner", "Y")
    assert r.exit_code == 2 and "error: invalid name" in r.output
    assert _rows(db) == []


def test_several_bad_fields_are_all_named_once(tmp_path):
    db = tmp_path / "a.sqlite3"
    r = _add(db, "BAD", "--name", "", "--owner", "Y")
    assert r.exit_code == 2
    assert "agent_id" in r.output and "name" in r.output
    assert "input" not in r.output.lower().replace("invalid", "")


def test_success_says_it_is_not_on_the_ledger(tmp_path):
    db = tmp_path / "a.sqlite3"
    r = _add(db, "good-agent", "--name", "X", "--owner", "Y")
    assert r.exit_code == 0, r.output
    assert "FIELD_LEDGER_URL" in r.output
    assert "registration is NOT on the ledger" in r.output
    assert [a.agent_id for a in _rows(db)] == ["good-agent"]


def test_duplicate_still_exits_1(tmp_path):
    db = tmp_path / "a.sqlite3"
    assert _add(db, "dup", "--name", "X", "--owner", "Y").exit_code == 0
    r = _add(db, "dup", "--name", "X", "--owner", "Y")
    assert r.exit_code == 1 and "already registered" in r.output
