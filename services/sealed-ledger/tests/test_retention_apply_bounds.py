"""S4-9: POST /retention/apply (and `ledger retention apply`) took `days` with only ge=0, so a value past timedelta's
range made `now - timedelta(days=...)` raise OverflowError, which no handler caught (500), AFTER the archive directory
had already been created; and an archive_dir holding a NUL made Path.resolve() raise ValueError (500). Now: `days`
is bounded to 0..36500 (API model, CLI, store), the cutoff is computed before anything is created, and a NUL in
archive_dir is a 422 with fixed text that does not echo the path. HIGH CARE: archive semantics are unchanged."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from ledger_c2_support import listing, three_segments
from sealed_ledger.api import create_app
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import ArchiveRefused, LedgerStore

runner = CliRunner()
BOUND = 36500
NUL = chr(0)


@pytest.fixture()
def env(monkeypatch, tmp_path):
    for name in ("FIELD_LEDGER_URL", "FIELD_SHARED_SECRET", "FIELD_LEDGER_RETENTION_DAYS", "FIELD_LEDGER_ARCHIVE_DIR",
                 "FIELD_LEDGER_CRASH_AT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    return monkeypatch


@pytest.fixture()
def ledger(tmp_path, env):
    data = tmp_path / "data"
    store, path, _ = three_segments(data / "ledger")
    return data, store, path, TestClient(create_app(store=store))


def apply(client, **kw):
    body = {"days": 0, "operator": "ops"}
    body.update(kw)
    return client.post("/retention/apply", json=body)


# ---- the API ----------------------------------------------------------------------------------------------------


def test_days_at_the_bound_is_accepted_and_archives_nothing_that_is_not_due(ledger):
    data, _, _, client = ledger
    r = apply(client, days=BOUND)
    assert r.status_code == 200, r.text
    assert r.json()["archived_segments"] == []              # nothing is 100 years old


@pytest.mark.parametrize("days", [BOUND + 1, 10**9, 10**12, 10**30])
def test_days_over_the_bound_is_422_and_creates_no_archive_dir(ledger, days):
    data, _, path, client = ledger
    before = listing(data)
    r = apply(client, days=days)
    assert r.status_code == 422, r.text
    assert listing(data) == before and not (data / "ledger-archive").exists()


def test_a_custom_archive_dir_is_not_created_by_a_refused_days_either(ledger):
    data, _, _, client = ledger
    target = data / "cold"
    assert apply(client, days=10**12, archive_dir=str(target)).status_code == 422
    assert not target.exists()


def test_a_nul_in_archive_dir_is_422_with_fixed_text_and_nothing_created(ledger):
    data, _, _, client = ledger
    before = listing(data)
    bad = str(data / "ledger-archive") + NUL + "MARKER-PATH-TEXT"
    r = apply(client, archive_dir=bad)
    assert r.status_code == 422, r.text
    assert "MARKER-PATH-TEXT" not in r.text and str(data) not in r.text
    assert listing(data) == before


def test_archive_semantics_are_unchanged_days_zero_still_archives_the_closed_segments(ledger):
    data, store, path, client = ledger
    r = apply(client, days=0)
    assert r.status_code == 200, r.text
    assert r.json()["archived_segments"] == [1, 2]
    assert (data / "ledger-archive").is_dir()
    assert store.verify().ok


def test_the_other_refusals_are_unchanged(ledger):
    _, _, _, client = ledger
    assert apply(client, days=-1).status_code == 422
    assert apply(client, operator=" ").status_code == 422


# ---- the store (direct callers) ---------------------------------------------------------------------------------


def test_the_store_refuses_an_oversize_days_before_it_creates_anything(ledger):
    data, store, _, _ = ledger
    adir = data / "ledger-archive"
    for days in (BOUND + 1, 10**12):
        with pytest.raises(ValueError):
            store.archive_closed_segments(older_than_days=days, archive_dir=adir, operator="ops", data_dir=data)
        assert not adir.exists()


def test_the_store_turns_a_nul_archive_dir_into_archive_refused(ledger):
    data, store, _, _ = ledger
    with pytest.raises(ArchiveRefused) as exc:
        store.archive_closed_segments(older_than_days=0, archive_dir=data / ("a" + NUL + "b"), operator="ops",
                                      data_dir=data)
    assert "a" + NUL not in str(exc.value)


# ---- the CLI ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("days", [BOUND + 1, 10**12])
def test_the_cli_refuses_an_oversize_days_with_one_line_and_exit_2(ledger, days):
    data, _, path, _ = ledger
    before = listing(data)
    res = runner.invoke(cli_app, ["retention", "apply", "--days", str(days), "--operator", "ops", "--offline",
                                  "--path", str(path)])
    assert res.exit_code == 2, res.output
    assert res.stderr.strip() == f"error: --days must be at most {BOUND}"
    assert listing(data) == before


def test_the_cli_accepts_the_bound(ledger):
    _, _, path, _ = ledger
    res = runner.invoke(cli_app, ["retention", "apply", "--days", str(BOUND), "--operator", "ops", "--offline",
                                  "--path", str(path)])
    assert res.exit_code == 0, res.output
