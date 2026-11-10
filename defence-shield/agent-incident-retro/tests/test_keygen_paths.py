"""S2-18: keygen must not let --pub overwrite --out, and must not write the private key with default permissions."""

import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_incident_retro.cli import app

runner = CliRunner()


def test_the_same_path_for_out_and_pub_is_refused_and_nothing_is_written(tmp_path: Path):
    k = tmp_path / "k.pem"
    r = runner.invoke(app, ["keygen", "--out", str(k), "--pub", str(k)])
    assert r.exit_code == 1 and "--out and --pub must be different files" in r.output
    assert not k.exists()


def test_two_spellings_of_one_path_are_refused(tmp_path: Path):
    r = runner.invoke(app, ["keygen", "--out", str(tmp_path / "k.pem"), "--pub", str(tmp_path / "x" / ".." / "k.pem")])
    assert r.exit_code == 1 and "different files" in r.output
    assert not (tmp_path / "k.pem").exists()


def test_a_symlink_to_the_private_path_is_refused_even_with_force(tmp_path: Path):
    key = tmp_path / "k.pem"
    key.write_text("precious\n", encoding="utf-8")
    link = tmp_path / "link.pem"
    try:
        link.symlink_to(key)
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks here")
    r = runner.invoke(app, ["keygen", "--out", str(key), "--pub", str(link), "--force"])
    assert r.exit_code == 1 and "different files" in r.output
    assert key.read_text(encoding="utf-8") == "precious\n"


def test_distinct_paths_still_write_both_keys(tmp_path: Path):
    r = runner.invoke(app, ["keygen", "--out", str(tmp_path / "k.pem"), "--pub", str(tmp_path / "k.pub")])
    assert r.exit_code == 0
    assert "PRIVATE" in (tmp_path / "k.pem").read_text(encoding="utf-8")
    assert "PUBLIC" in (tmp_path / "k.pub").read_text(encoding="utf-8")


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes")
def test_the_private_file_is_0600(tmp_path: Path):
    k = tmp_path / "k.pem"
    assert runner.invoke(app, ["keygen", "--out", str(k)]).exit_code == 0
    assert stat.S_IMODE(k.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes")
def test_a_failed_0600_create_does_not_fall_back_to_a_default_mode_write(tmp_path: Path, monkeypatch):
    def refuse(*a, **kw):
        raise OSError("no")
    monkeypatch.setattr(os, "open", refuse)
    k = tmp_path / "k.pem"
    r = runner.invoke(app, ["keygen", "--out", str(k)])
    assert r.exit_code == 1 and not k.exists()
