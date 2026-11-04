"""S6-19: a journal line that is valid JSON, says ``"event": "transition"`` and has a missing or unknown ``state`` (a hand
edit, corruption: not a torn write) used to crash ``pending()``, ``is_halted()`` and ``append()`` with a bare
KeyError/ValueError. It is now a ``JournalError`` with a fixed text, raised by ``entries()``: FAIL CLOSED. The alternative
(count it in ``torn_lines`` and skip it) would let a damaged HALTED line vanish and a halted rotation run again. Torn
(non-JSON) lines and non-object lines are still skipped and counted, as before. Also the first direct tests of
``last_transition()``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from deployment_agent.journal import Journal, JournalError  # noqa: E402
from deployment_agent.states import State  # noqa: E402

T = "fly-app-a"


def write(tmp_path, *lines):
    p = tmp_path / f"rotation-{T}.jsonl"
    p.write_bytes(b"".join((ln if isinstance(ln, bytes) else ln.encode()) + b"\n" for ln in lines))
    return p


def tr(state, seq=1):
    return json.dumps({"seq": seq, "ts": 1, "target": T, "event": "transition", "state": state})


BAD = [
    pytest.param('{"event":"transition"}', id="state-missing"),
    pytest.param('{"event":"transition","state":"bogus"}', id="state-unknown"),
    pytest.param('{"event":"transition","state":7}', id="state-int"),
    pytest.param('{"event":"transition","state":null}', id="state-null"),
    pytest.param('{"event":"transition","state":["planned"]}', id="state-list"),
    pytest.param('{"event":"transition","state":""}', id="state-empty"),
    pytest.param('{"event":"transition","state":"PLANNED"}', id="state-wrong-case"),
    pytest.param('{"event":"transition","state":{"a":1}}', id="state-object"),
]


@pytest.mark.parametrize("bad", BAD)
def test_a_bad_transition_line_is_a_journal_error_from_every_reader_and_writer(tmp_path, bad):
    write(tmp_path, tr("planned"), bad, tr("minted", 3))
    j = Journal(tmp_path, T)
    for call in (j.entries, j.pending, j.is_halted, j.last_transition,
                 lambda: j.append(event="transition", state="installed")):
        with pytest.raises(JournalError, match="line 2 is a transition with a missing or unknown state"):
            call()


@pytest.mark.parametrize("bad", BAD)
def test_the_error_names_the_line_but_never_its_content(tmp_path, bad):
    write(tmp_path, tr("planned"), bad)
    with pytest.raises(JournalError) as e:
        Journal(tmp_path, T).entries()
    assert "line 2" in str(e.value) and "bogus" not in str(e.value) and "transition\"" not in str(e.value)


def test_nothing_is_appended_when_the_journal_cannot_be_read(tmp_path):
    p = write(tmp_path, tr("planned"), '{"event":"transition","state":"bogus"}')
    before = p.read_bytes()
    with pytest.raises(JournalError):
        Journal(tmp_path, T).append(event="transition", state="minted")
    assert p.read_bytes() == before


def test_a_damaged_halted_line_cannot_silently_unhalt_the_journal(tmp_path):
    """the reason it fails closed: skipped as torn, the halt would vanish and pending() would be None."""
    write(tmp_path, tr("planned"), tr("halted", 2))
    assert Journal(tmp_path, T).is_halted()
    write(tmp_path, tr("planned"), '{"event":"transition","state":"halted "}')
    with pytest.raises(JournalError):
        Journal(tmp_path, T).is_halted()


# ---- what is still tolerated -------------------------------------------------------------------------------------------

def test_torn_and_non_object_lines_are_still_skipped_and_counted(tmp_path):
    write(tmp_path, tr("planned"), '{"event":"transition","sta', "[1,2]", '"text"', "7", b"\xff\xfe", tr("minted", 3))
    j = Journal(tmp_path, T)
    assert [e["state"] for e in j.entries()] == ["planned", "minted"]
    assert j.torn_lines == 5
    assert j.pending()["state"] == "minted"


@pytest.mark.parametrize("line", ['{"event":"note","reason":"x"}', '{"event":"halt_cleared"}', '{"state":"bogus"}',
                                  '{"event":"transition-ish","state":"bogus"}', '{"event":7,"state":"bogus"}'])
def test_a_line_that_is_not_a_transition_is_not_judged_by_its_state(tmp_path, line):
    write(tmp_path, tr("planned"), line)
    assert len(Journal(tmp_path, T).entries()) == 2


def test_a_clean_journal_reads_and_appends_as_before(tmp_path):
    j = Journal(tmp_path, T)
    j.transition(State.PLANNED)
    j.transition(State.MINTED)
    assert j.pending()["state"] == "minted" and not j.is_halted()
    j.transition(State.HALTED)
    assert j.is_halted()


# ---- last_transition(): the first direct tests ----------------------------------------------------------------------------

def test_last_transition_none_for_a_missing_or_empty_journal(tmp_path):
    assert Journal(tmp_path, T).last_transition() is None
    write(tmp_path)
    assert Journal(tmp_path, T).last_transition() is None


def test_last_transition_is_the_last_transition_entry_not_the_last_line(tmp_path):
    write(tmp_path, tr("planned"), tr("minted", 2), '{"event":"note","reason":"x"}', '{"event":"halt_cleared"}')
    assert Journal(tmp_path, T).last_transition()["state"] == "minted"


def test_last_transition_ignores_non_transition_entries_only(tmp_path):
    write(tmp_path, '{"event":"note","reason":"x"}')
    assert Journal(tmp_path, T).last_transition() is None


def test_last_transition_after_a_torn_tail(tmp_path):
    write(tmp_path, tr("planned"), tr("installed", 2), '{"event":"transition","state":"ver')
    assert Journal(tmp_path, T).last_transition()["state"] == "installed"
