"""B14: tools/field-rest.ps1 carries no personal mailbox and no home path, and the runbook's sha256 pin is its hash.

The shim's paths are built from ``$HOME`` (or the FIELD_TOKENS_FILE / FIELD_SECRET_FILE overrides); no account's home
directory is written into the repository. The token-renewal runbook pins the shim by sha256 (§5.2), so any edit to
the shim must re-pin it: the last test keeps the two in step.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHIM = ROOT / "tools" / "field-rest.ps1"
RUNBOOK = ROOT / "docs" / "runbooks" / "token-renewal.md"

MAILBOX = re.compile(r"[\w.+-]+(@|\uff20)[\w-]+(\.[\w-]+)+")
HOME_PATH = re.compile(r"(?i)([a-z]:[\\/]+users[\\/]+(?!public\b)[^\\/\s'\"<>$]+)|(/home/[^/\s'\"<>$]+)|(/Users/[^/\s'\"<>$]+)")


def _lines(pattern: re.Pattern[str]) -> list[int]:
    """Line numbers only: a failure never prints the value it found."""
    text = SHIM.read_text(encoding="utf-8-sig")
    return [n for n, line in enumerate(text.splitlines(), 1) if pattern.search(line)]


def test_the_shim_names_no_mailbox():
    assert _lines(MAILBOX) == []


def test_the_shim_names_no_home_directory():
    assert _lines(HOME_PATH) == []


def test_the_default_paths_are_built_from_home():
    text = SHIM.read_text(encoding="utf-8-sig")
    assert "Join-Path $HOME '.field-local\\tokens-gb10.json'" in text
    assert "Join-Path $HOME '.field-local\\gb10-estate-secret'" in text


def test_the_patterns_catch_what_they_guard_against():
    """The guards are not vacuous: synthetic values of each shape match (none is a real account)."""
    assert MAILBOX.search("someone@example.invalid")
    assert HOME_PATH.search("'C:\\Users\\someone\\.field-local\\x'")
    assert HOME_PATH.search("/home/someone/.field-local")
    assert not HOME_PATH.search("Join-Path $HOME '.field-local\\x'")


def test_the_runbook_pin_is_the_shims_hash():
    digest = hashlib.sha256(SHIM.read_bytes()).hexdigest()
    pins = re.findall(r"`([0-9a-f]{64})` for field-rest\.ps1", RUNBOOK.read_text(encoding="utf-8"))
    assert pins == [digest], "re-pin docs/runbooks/token-renewal.md §5.2 after editing tools/field-rest.ps1"
