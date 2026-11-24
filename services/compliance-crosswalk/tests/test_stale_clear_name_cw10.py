"""F-CW-10 (reviewer C-1082, Lane 14): the clear of a stale flag names a PLAIN human.

``StaleStore.clear`` is the one human gate on a stale pack (README: re-review is NAMED), yet it only checked that the
name was not blank: ``reviewed_by="\\x1b[31m.\\n"`` was stored raw in the history, unlike ``check-file --fetched-by``
(``regwatch._named_human``). The same rule now applies: no control, invisible-format or line-break character, at least
one letter or digit; the name is stored stripped; a refused clear leaves the flag active and the history alone."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from compliance_crosswalk.cli import app
from compliance_crosswalk.staleness import StaleStore

runner = CliRunner()
FRAMEWORK = "osfi-e23"

REFUSED = [
    "\x1b[31m.\n",            # the finding: an escape sequence, a dot and a newline
    "A\nB", "A\rB", "A\tB", "Don\x00", "\x7fDon", "Do\x85n",
    "‮Don", "​Don", "﻿Don", "Do n", "Do n",
    ".", "...", "---", "!!!", "  .  ",
    "", "   ", "\t\n",
]


def _store(tmp_path) -> StaleStore:
    s = StaleStore(tmp_path / "flags.json")
    s.mark(FRAMEWORK, "guideline revision consultation opened")
    return s


@pytest.mark.parametrize("name", REFUSED, ids=repr)
def test_a_refused_name_clears_nothing(tmp_path, name):
    s = _store(tmp_path)
    with pytest.raises(ValueError):
        s.clear(FRAMEWORK, name)
    assert [f["framework"] for f in s.active()] == [FRAMEWORK]
    assert s.status()["history"] == []


@pytest.mark.parametrize("name", ["D. Hagell", "Don Hagell", "Zoë Müller", "O'Brien", "J-P 2nd", "李雷", "R2"])
def test_a_plain_name_clears_and_is_recorded(tmp_path, name):
    s = _store(tmp_path)
    review = s.clear(FRAMEWORK, name)
    assert review["reviewed_by"] == name and s.active() == []
    assert s.status()["history"][-1]["reviewed_by"] == name


@pytest.mark.parametrize("padded", ["  D. Hagell \t", "\nD. Hagell\n", "D. Hagell\x85", " D. Hagell", "D. Hagell "])
def test_the_name_is_stored_stripped(tmp_path, padded):
    # str.strip() takes the leading and trailing whitespace, line breaks included, before the character check
    s = _store(tmp_path)
    assert s.clear(FRAMEWORK, padded)["reviewed_by"] == "D. Hagell"


def test_each_refusal_says_why_and_never_echoes_the_name(tmp_path):
    s = _store(tmp_path)
    for name, word in [("Do\nn", "plain name"), ("...", "letter or digit"), ("  ", "non-empty")]:
        with pytest.raises(ValueError) as exc:
            s.clear(FRAMEWORK, name)
        assert word in str(exc.value) and "Do" not in str(exc.value).replace("Do not", "")


def test_the_cli_refuses_a_control_name_and_the_flag_stays_active(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path))
    s = StaleStore()
    s.mark(FRAMEWORK, "guideline revision consultation opened")
    result = runner.invoke(app, ["regwatch", "clear", FRAMEWORK, "--reviewed-by", "\x1b[31m.\n"])
    assert result.exit_code != 0
    assert [f["framework"] for f in StaleStore().active()] == [FRAMEWORK]
    ok = runner.invoke(app, ["regwatch", "clear", FRAMEWORK, "--reviewed-by", "D. Hagell"])
    assert ok.exit_code == 0 and StaleStore().active() == []


@pytest.mark.parametrize("name", [None, 7, b"Don", ["Don"], {"name": "Don"}], ids=repr)
def test_a_name_that_is_not_text_is_refused_not_stringified(tmp_path, name):
    s = _store(tmp_path)
    with pytest.raises(ValueError, match="non-empty name"):
        s.clear(FRAMEWORK, name)
    assert [f["framework"] for f in s.active()] == [FRAMEWORK]
