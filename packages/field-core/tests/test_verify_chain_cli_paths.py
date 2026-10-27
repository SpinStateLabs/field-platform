"""`field verify-chain FILE`: every way the file can fail to open is a one-line
exit 2, never a traceback, and click's stat-then-access pre-check is gone
(ledger-cli-race review, "Other windows": the same window `ledger verify
--path` had; a rotation renames the open segment between click's os.stat()
and os.access(), or between the check and the open).

Before this change: a missing file or a rename between the check and the open
raised FileNotFoundError (traceback, exit 1); an os.access() refusal in the
rename window was exit 2 "is not readable" for a file that verifies.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from field_core.cli import app
from field_core.ledger import GENESIS_HASH, make_event

runner = CliRunner()


def _chain(path: Path, n: int = 3) -> Path:
    prev = GENESIS_HASH
    lines = []
    for i in range(n):
        e = make_event(f"event-{i}", prev_hash=prev)
        prev = e.hash
        lines.append(e.model_dump_json(exclude_none=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _no_traceback(r):
    assert isinstance(r.exception, SystemExit), repr(r.exception)


def test_the_chain_helper_verifies(tmp_path):
    f = _chain(tmp_path / "events.jsonl")
    r = runner.invoke(app, ["verify-chain", str(f)])
    assert r.exit_code == 0 and r.stdout == "OK — chain intact over 3 events\n", r.output


def test_a_missing_file_is_exit_2_not_a_traceback(tmp_path):
    missing = tmp_path / "evnets.jsonl"
    r = runner.invoke(app, ["verify-chain", str(missing)])
    _no_traceback(r)
    assert r.exit_code == 2
    assert r.stderr == f"error: no such file: {missing}; nothing verified\n"
    assert "OK" not in r.stdout and "TAMPERED" not in r.stdout


def test_a_missing_open_segment_beside_a_journal_names_ledger_verify(tmp_path):
    missing = tmp_path / "events.jsonl"
    (tmp_path / "events.segments.journal").write_text("", encoding="utf-8")
    r = runner.invoke(app, ["verify-chain", str(missing)])
    _no_traceback(r)
    assert r.exit_code == 2
    assert "error: no such file:" in r.stderr and f"ledger verify --path {missing}" in r.stderr


def test_a_rename_between_the_check_and_the_open_is_exit_2_not_a_traceback(tmp_path, monkeypatch):
    """The rotation window: the file is there for every check, then renamed away
    just before the open (rotate's rename of the open segment)."""
    f = _chain(tmp_path / "events.jsonl")
    real_open = Path.open

    def rename_then_open(self, *a, **kw):
        if self == f and f.exists():
            os.replace(f, tmp_path / "events.000001.jsonl")
        return real_open(self, *a, **kw)

    monkeypatch.setattr(Path, "open", rename_then_open)
    r = runner.invoke(app, ["verify-chain", str(f)])
    _no_traceback(r)
    assert r.exit_code == 2 and r.stderr.startswith(f"error: no such file: {f}"), r.output


def test_click_no_longer_pre_checks_access(tmp_path, monkeypatch):
    """os.access() saying no (the rename window between click's stat and access, as
    the review simulated it) must not refuse a file that opens and verifies."""
    f = _chain(tmp_path / "events.jsonl")
    monkeypatch.setattr(os, "access", lambda *a, **kw: False)
    r = runner.invoke(app, ["verify-chain", str(f)])
    assert r.exit_code == 0 and r.stdout == "OK — chain intact over 3 events\n", r.output


def test_permission_denied_is_exit_2_not_a_traceback(tmp_path, monkeypatch):
    f = _chain(tmp_path / "events.jsonl")
    real_open = Path.open

    def denied(self, *a, **kw):
        if self == f:
            raise PermissionError(13, "Permission denied", str(self))
        return real_open(self, *a, **kw)

    monkeypatch.setattr(Path, "open", denied)
    r = runner.invoke(app, ["verify-chain", str(f)])
    _no_traceback(r)
    assert r.exit_code == 2
    assert r.stderr == f"error: cannot read {f}: Permission denied; nothing verified\n"


def test_a_directory_is_exit_2_not_a_traceback(tmp_path):
    d = tmp_path / "events.jsonl"
    d.mkdir()
    r = runner.invoke(app, ["verify-chain", str(d)])
    _no_traceback(r)
    assert r.exit_code == 2 and r.stderr.startswith(f"error: cannot read {d}: "), r.output


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="POSIX non-root only: a real mode-000 file")
def test_a_real_mode_000_file_is_exit_2(tmp_path):
    f = _chain(tmp_path / "events.jsonl")
    os.chmod(f, 0)
    try:
        r = runner.invoke(app, ["verify-chain", str(f)])
    finally:
        os.chmod(f, 0o600)
    _no_traceback(r)
    assert r.exit_code == 2 and r.stderr.startswith(f"error: cannot read {f}: "), r.output
