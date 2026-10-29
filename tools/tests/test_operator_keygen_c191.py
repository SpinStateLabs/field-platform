"""operator_keygen (C-191, reviewer C-185): the key file's permissions and exact content, the usage
errors that must exit 2 with their own message, and the script running as a program. Test keys are
generated per test and never printed by the test."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import operator_keygen as kg  # noqa: E402

posix = pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")


@posix
def test_a_generated_key_file_has_no_group_or_other_permission_bits(tmp_path, capsys):
    """F-C185-1: the key file is owner-only (mutants 0o644, 0o666, 0o777, 0o601 at the os.open mode)."""
    kf = tmp_path / "don.key"
    assert kg.main(["--key-file", str(kf)]) == 0
    mode = stat.S_IMODE(kf.stat().st_mode)
    assert mode & 0o077 == 0, oct(mode)
    assert mode & 0o600 == 0o600, oct(mode)  # and the owner can read and write it


def test_the_key_file_holds_exactly_the_key_and_one_newline(tmp_path, capsys):
    """F-C185-3: key + newline, nothing else; its sha256 is the one printed."""
    kf = tmp_path / "don.key"
    assert kg.main(["--key-file", str(kf)]) == 0
    out = capsys.readouterr().out
    raw = kf.read_bytes()
    nl = rb"\r?\n" if os.name == "nt" else rb"\n"  # text-mode write: Windows translates the newline
    assert re.fullmatch(rb"fok_[A-Za-z0-9_-]{43}" + nl, raw), len(raw)
    key = raw.rstrip(b"\r\n")
    assert f"key_sha256: {hashlib.sha256(key).hexdigest()}" in out
    assert key.decode() not in out


def test_the_script_runs_as_a_program():
    """F-C185-3: `python tools/operator_keygen.py` runs main() (the __main__ guard), exits 0 for --help."""
    proc = subprocess.run([sys.executable, str(TOOLS / "operator_keygen.py"), "--help"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "--key-file" in proc.stdout and "--check" in proc.stdout


def test_the_program_exit_status_is_main_s_return_value():
    proc = subprocess.run([sys.executable, str(TOOLS / "operator_keygen.py"), "--scopes", "launch-missiles"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2 and "unknown scope" in proc.stderr and "fok_" not in proc.stdout


@pytest.mark.parametrize("args, message", [
    (["--scopes", "ledger_attribute", "--event-prefix", "kill"], "an --event-prefix is dotted lower-case segments"),
    (["--scopes", "ledger_attribute", "--event-prefix", "operator."], "never operator."),
    (["--scopes", "kill", "--event-prefix", "kill."], "--event-prefix applies only to the ledger_attribute scope"),
    (["--scopes", "ledger_attribute"], "ledger_attribute needs at least one --event-prefix"),
    (["--add-to", "operators.json"], "--add-to needs --operator-id"),
])
def test_a_usage_error_exits_2_with_its_own_message_and_makes_no_key(tmp_path, capsys, monkeypatch, args, message):
    """F-C185-2: each refusal returns 2 (never 0), says why on stderr, and nothing is generated or written."""
    monkeypatch.chdir(tmp_path)
    assert kg.main(args) == 2
    cap = capsys.readouterr()
    assert message in cap.err and cap.err.startswith("error: ")
    assert "fok_" not in cap.out + cap.err and not any(tmp_path.iterdir())


@pytest.mark.parametrize("other", [
    ["--key-file", "k"], ["--operator-id", "don"], ["--add-to", "o.json"], ["--alias", "Don"],
    ["--event-prefix", "kill."], ["--scopes", "kill"],
])
def test_check_takes_no_other_option(tmp_path, capsys, other):
    """F-C185-2: --check with any other option is a usage error (2), not a check."""
    f = tmp_path / "operators.json"
    f.write_text("[]", encoding="utf-8")
    assert kg.main(["--check", str(f), *other]) == 2
    cap = capsys.readouterr()
    assert "error: --check takes no other option" in cap.err and cap.out == ""
