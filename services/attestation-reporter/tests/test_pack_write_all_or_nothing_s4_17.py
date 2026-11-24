"""R-PR665-030f5c5 conditions C1 and C2.

C1: a failed SECOND write leaves no half pack: neither a new board-pack.json beside a missing or old HTML, nor stray
temporary files; an old JSON is put back as it was. C2: a lone surrogate in --org (what a POSIX argv holding invalid UTF-8
becomes) is a named refusal, exit 2, never an uncaught serialiser error."""

from __future__ import annotations

import os

import pytest
from typer.testing import CliRunner

from attestation_reporter import api as api_mod
from attestation_reporter import cli as cli_mod
from attestation_reporter.engine import PackEngine
from attestation_reporter.org import InvalidOrg, checked_org

LONE = "a" + chr(0xDCFF) + "b"


@pytest.fixture()
def cli(monkeypatch):
    monkeypatch.setattr(api_mod, "engine_from_env", lambda org="Spin State Labs": PackEngine(org=org))
    runner = CliRunner()
    return lambda *args: runner.invoke(cli_mod.app, ["render", "--no-pdf", *args])


def _names(out):
    return sorted(p.name for p in out.iterdir()) if out.exists() else []


# ---- C1 -----------------------------------------------------------------------------------------------------------------

def test_an_html_target_that_is_a_directory_leaves_no_json_and_no_temp_files(cli, tmp_path):
    out = tmp_path / "o"
    (out / "board-pack.html").mkdir(parents=True)
    r = cli("--out", str(out))
    assert r.exit_code == 2, r.output
    assert "refused: cannot write the pack into --out (IsADirectoryError)" in r.output
    assert _names(out) == ["board-pack.html"]                 # nothing else: no board-pack.json, no .tmp


def test_a_directory_html_target_leaves_an_old_json_byte_identical(cli, tmp_path):
    out = tmp_path / "o"
    (out / "board-pack.html").mkdir(parents=True)
    (out / "board-pack.json").write_bytes(b"OLD-JSON")
    r = cli("--out", str(out))
    assert r.exit_code == 2
    assert (out / "board-pack.json").read_bytes() == b"OLD-JSON"


def _fail_the_second_replace(monkeypatch):
    real, calls = os.replace, []

    def fake(src, dst, *a, **k):
        calls.append(os.fspath(dst))
        if len(calls) == 2:
            raise PermissionError("simulated: the second rename failed")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", fake)
    return calls


def test_a_failed_second_rename_removes_a_new_json(cli, tmp_path, monkeypatch):
    out = tmp_path / "o"
    calls = _fail_the_second_replace(monkeypatch)
    r = cli("--out", str(out))
    assert r.exit_code == 2 and "cannot write the pack into --out (PermissionError)" in r.output, r.output
    assert len(calls) == 2
    assert _names(out) == []                                   # no JSON, no HTML, no temporary files


def test_a_failed_second_rename_puts_an_old_json_back(cli, tmp_path, monkeypatch):
    out = tmp_path / "o"
    out.mkdir()
    (out / "board-pack.json").write_bytes(b"OLD-JSON")
    (out / "board-pack.html").write_bytes(b"OLD-HTML")
    _fail_the_second_replace(monkeypatch)
    r = cli("--out", str(out))
    assert r.exit_code == 2
    assert (out / "board-pack.json").read_bytes() == b"OLD-JSON" and (out / "board-pack.html").read_bytes() == b"OLD-HTML"
    assert _names(out) == ["board-pack.html", "board-pack.json"]


def test_a_failed_temp_write_changes_nothing(cli, tmp_path, monkeypatch):
    out = tmp_path / "o"
    out.mkdir()
    (out / "board-pack.json").write_bytes(b"OLD-JSON")
    real = type(out).write_text

    def fake(self, text, *a, **k):
        if self.name.endswith("board-pack.html.tmp"):
            raise OSError("simulated: disk full")
        return real(self, text, *a, **k)

    monkeypatch.setattr(type(out), "write_text", fake)
    r = cli("--out", str(out))
    assert r.exit_code == 2
    assert _names(out) == ["board-pack.json"] and (out / "board-pack.json").read_bytes() == b"OLD-JSON"


def test_a_good_run_writes_both_files_and_leaves_no_temporary_files(cli, tmp_path):
    out = tmp_path / "o"
    r = cli("--out", str(out))
    assert r.exit_code == 0, r.output
    assert _names(out) == ["board-pack.html", "board-pack.json"]


# ---- C2 -----------------------------------------------------------------------------------------------------------------

def test_a_lone_surrogate_org_is_refused_with_its_position():
    with pytest.raises(InvalidOrg) as info:
        checked_org(LONE)
    assert "U+DCFF at position 1" in str(info.value)
    assert LONE not in str(info.value)


def test_the_cli_refuses_a_lone_surrogate_org_with_exit_2_and_writes_nothing(cli, tmp_path):
    out = tmp_path / "o"
    r = cli("--out", str(out), "--org", LONE)
    assert r.exit_code == 2, (r.exit_code, r.output, repr(r.exception))
    assert "refused:" in r.output and "Traceback" not in r.output and "PydanticSerializationError" not in r.output
    assert _names(out) == []


@pytest.mark.parametrize("org", ["Acme" + chr(0xE000), "Acme" + chr(0x0378)])
def test_private_use_and_unassigned_code_points_stay_accepted(org):
    """The recorded decision: they serialise, so only the visual claim is affected."""
    assert checked_org(org) == org
