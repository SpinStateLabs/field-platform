"""S10-26 (scout card B-S10-26): ``regwatch set-stale --reason`` / ``--new-version`` are bounded plain text.

The reason is stored in the flag and printed into the pack-blocked error (evidence_pack.py), so a blank, over-long or
control/format/line-break value is refused: one ``REFUSED (nothing written)`` line on stderr, exit 2, nothing stored.
(The traceback half of the card, unknown framework and clear of an unflagged one, is open PR 600.)"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from compliance_crosswalk.cli import app

runner = CliRunner()
FW = "osfi-e23"

BAD_REASONS = [
    "", "   ", "\t\n",
    "a\nb", "a\rb", "a\x1b[31mb", "a\x00b", "a\x7fb", "a\x85b",
    "a\u200bb", "a\u202eb", "a b", "a b",
    "x" * 501,
]


def _run(tmp_path, monkeypatch, *args):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path))
    return runner.invoke(app, ["regwatch", "set-stale", FW, *args])


def _stored(tmp_path) -> bool:
    return any(tmp_path.glob("*.json"))


@pytest.mark.parametrize("reason", BAD_REASONS, ids=repr)
def test_a_bad_reason_is_refused_and_nothing_is_written(tmp_path, monkeypatch, reason):
    r = _run(tmp_path, monkeypatch, "--reason", reason)
    assert r.exit_code == 2
    assert "REFUSED (nothing written)" in r.output
    assert "Traceback" not in r.output
    assert not _stored(tmp_path)


@pytest.mark.parametrize("version", ["v" * 101, "1.0\n2", "1.0\x1b", "1\u200b0"], ids=repr)
def test_a_bad_new_version_is_refused(tmp_path, monkeypatch, version):
    r = _run(tmp_path, monkeypatch, "--reason", "guideline revised", "--new-version", version)
    assert r.exit_code == 2
    assert "REFUSED (nothing written)" in r.output
    assert not _stored(tmp_path)


def test_a_refusal_does_not_echo_the_value(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, "--reason", "SECRETTEXT\x1b[31m")
    assert r.exit_code == 2
    assert "SECRETTEXT" not in r.output


def test_a_plain_reason_at_the_bound_is_accepted_and_stored(tmp_path, monkeypatch):
    reason = "r" * 500
    r = _run(tmp_path, monkeypatch, "--reason", reason, "--new-version", "v" * 100)
    assert r.exit_code == 0, r.output
    flags = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert flags["active"][FW]["reason"] == reason
