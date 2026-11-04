"""`federation-broker keygen`: the private key is created 0600, and nothing existing is overwritten without --force
(scout P-19).

Before: `write_text` created the private PEM with the default umask (0644 on a typical POSIX host, readable by every
local user) and silently replaced an existing `<name>-private.pem`: a second `keygen --name X` destroyed the only copy of
a key whose public half a counterparty already held. The mode assertions are POSIX-only; the overwrite rules hold
everywhere."""

from __future__ import annotations

import os
import stat
import sys

import pytest
from typer.testing import CliRunner

from federation_broker import cli as cli_mod

runner = CliRunner()


def _keygen(tmp_path, *extra, name="synthetic-borealis"):
    return runner.invoke(cli_mod.app, ["keygen", "--out-dir", str(tmp_path), "--name", name, *extra])


posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")


@posix_only
def test_the_private_key_is_created_0600_even_under_a_permissive_umask(tmp_path):
    old = os.umask(0o000)
    try:
        r = _keygen(tmp_path)
    finally:
        os.umask(old)
    assert r.exit_code == 0, r.output
    assert stat.S_IMODE((tmp_path / "synthetic-borealis-private.pem").stat().st_mode) == 0o600


def test_a_second_keygen_with_the_same_name_is_refused_and_changes_nothing(tmp_path):
    assert _keygen(tmp_path).exit_code == 0
    private, public = tmp_path / "synthetic-borealis-private.pem", tmp_path / "synthetic-borealis-public.pem"
    first_private, first_public = private.read_bytes(), public.read_bytes()
    r = _keygen(tmp_path)
    assert r.exit_code != 0 and "--force" in r.output, r.output
    assert private.read_bytes() == first_private and public.read_bytes() == first_public


@pytest.mark.parametrize("which", ["private", "public"])
def test_either_existing_file_blocks_a_new_pair_and_neither_is_written(tmp_path, which):
    existing = tmp_path / f"synthetic-borealis-{which}.pem"
    existing.write_bytes(b"keep me")
    r = _keygen(tmp_path)
    assert r.exit_code != 0, r.output
    assert existing.read_bytes() == b"keep me"
    other = "public" if which == "private" else "private"
    assert not (tmp_path / f"synthetic-borealis-{other}.pem").exists()


def test_the_refusal_prints_no_key_material(tmp_path):
    assert _keygen(tmp_path).exit_code == 0
    pem = (tmp_path / "synthetic-borealis-private.pem").read_text(encoding="ascii")
    body = [ln for ln in pem.splitlines() if ln and not ln.startswith("-----")][0]
    r = _keygen(tmp_path)
    assert body not in r.output and "BEGIN" not in r.output


def test_force_replaces_the_pair(tmp_path):
    assert _keygen(tmp_path).exit_code == 0
    private = tmp_path / "synthetic-borealis-private.pem"
    old = private.read_bytes()
    r = _keygen(tmp_path, "--force")
    assert r.exit_code == 0, r.output
    assert private.read_bytes() != old and private.read_bytes().startswith(b"-----BEGIN")


@posix_only
def test_force_over_a_world_readable_file_leaves_0600(tmp_path):
    private = tmp_path / "synthetic-borealis-private.pem"
    private.write_text("old", encoding="ascii")
    os.chmod(private, 0o644)
    assert _keygen(tmp_path, "--force").exit_code == 0
    assert stat.S_IMODE(private.stat().st_mode) == 0o600


def test_a_fresh_name_in_the_same_directory_is_not_blocked(tmp_path):
    assert _keygen(tmp_path, name="one").exit_code == 0
    assert _keygen(tmp_path, name="two").exit_code == 0
