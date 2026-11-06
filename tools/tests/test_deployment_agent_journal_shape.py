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
MARK = "MADE-UP-MARKER-0123"


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

def test_torn_and_non_object_lines_at_the_tail_are_still_skipped_and_counted(tmp_path):
    """A crash tears at worst the final line(s): damaged lines with nothing valid after them are skipped and counted."""
    write(tmp_path, tr("planned"), tr("minted", 2), '{"event":"transition","sta', "[1,2]", '"text"', "7", bytes([255, 254]))
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


def test_the_line_number_counts_physical_lines_including_blank_ones(tmp_path):
    """Review finding 1 (M8): a human repairing the file is sent to the physical line, blanks included."""
    p = tmp_path / f"rotation-{T}.jsonl"
    p.write_bytes((tr("planned") + "\n\n\n" + '{"event":"transition","state":"bogus"}' + "\n").encode())
    with pytest.raises(JournalError, match=r"journal line 4 is a transition"):
        Journal(tmp_path, T).entries()


# ---- review C1 on PR 719: a damaged line with a valid line after it is corruption, not a crash tear --------------------

DAMAGED = [pytest.param('{"event":"transition","state":"halt', id="truncated-json"), pytest.param("[1,2]", id="array"),
           pytest.param('"text"', id="string"), pytest.param("7", id="number"), pytest.param(bytes([255, 254]), id="bad-utf8")]


@pytest.mark.parametrize("bad", DAMAGED)
def test_a_damaged_line_followed_by_a_valid_line_is_a_journal_error_from_every_reader_and_writer(tmp_path, bad):
    write(tmp_path, tr("planned"), tr("minted", 2), bad, '{"event":"note","reason":"x"}')
    j = Journal(tmp_path, T)
    for call in (j.entries, j.pending, j.is_halted, j.last_transition, lambda: j.append(event="note", reason="y")):
        with pytest.raises(JournalError, match="journal line 3 is damaged and is not the last line"):
            call()


def test_the_halted_line_corrupted_mid_file_cannot_let_the_halted_run_resume(tmp_path):
    """The review's reproduction: planned, minted, installed, halted, the halted line truncated, a later valid line."""
    halted = tr("halted", 4)
    write(tmp_path, tr("planned"), tr("minted", 2), tr("installed", 3), halted[:-5], '{"event":"note","reason":"x"}')
    j = Journal(tmp_path, T)
    with pytest.raises(JournalError):
        j.is_halted()
    with pytest.raises(JournalError):
        j.append(event="transition", state="verified")


@pytest.mark.parametrize("bad", DAMAGED)
def test_a_damaged_final_line_is_still_the_tolerated_crash_tear(tmp_path, bad):
    write(tmp_path, tr("planned"), tr("installed", 2), bad)
    j = Journal(tmp_path, T)
    assert j.pending()["state"] == "installed" and j.torn_lines == 1 and not j.is_halted()


def test_blank_lines_after_a_damaged_final_line_do_not_make_it_mid_file(tmp_path):
    nl = chr(10)
    p = tmp_path / f"rotation-{T}.jsonl"
    p.write_bytes((tr("planned") + nl + '{"event":"transition","sta' + nl + nl + nl).encode())
    assert Journal(tmp_path, T).pending()["state"] == "planned"


def test_the_error_names_the_first_damaged_line_physically_and_never_its_content(tmp_path):
    nl = chr(10)
    p = tmp_path / f"rotation-{T}.jsonl"
    p.write_bytes((tr("planned") + nl + nl + '{"event":"transition","sta' + MARK + nl + "7" + nl + tr("minted", 2) + nl).encode())
    with pytest.raises(JournalError) as e:
        Journal(tmp_path, T).entries()
    assert str(e.value).startswith("journal line 3 is damaged") and MARK not in str(e.value)


def test_with_two_damaged_non_json_lines_the_first_is_the_one_named(tmp_path):
    nl = chr(10)
    p = tmp_path / f"rotation-{T}.jsonl"
    p.write_bytes((tr("planned") + nl + '{"event":"transition","sta' + nl + '{"event":"trans' + nl + tr("minted", 2) + nl).encode())
    with pytest.raises(JournalError, match="journal line 2 is damaged"):
        Journal(tmp_path, T).entries()


# ---- resuming past a torn tail: append() records an acknowledgement, so the tear is not later read as mid-file corruption ----

def _ack(line):
    return json.dumps({"event": "torn_tail_ack", "damaged_line": line, "seq": 99, "ts": 1, "target": T})


def test_appending_past_a_torn_tail_writes_an_ack_naming_the_line_and_the_journal_stays_readable(tmp_path):
    write(tmp_path, tr("planned"), tr("installed", 2), '{"event":"transition","state":"veri')
    j = Journal(tmp_path, T)
    j.transition(State.VERIFIED)
    entries = Journal(tmp_path, T).entries()                         # a fresh reader: no error
    assert [e.get("state") for e in entries if e["event"] == "transition"] == ["planned", "installed", "verified"]
    acks = [e for e in entries if e["event"] == "torn_tail_ack"]
    assert len(acks) == 1 and acks[0]["damaged_line"] == 3
    seqs = [e["seq"] for e in entries]
    assert seqs == sorted(set(seqs)) and len(seqs) == len(set(seqs))   # strictly increasing, no repeats


def test_a_second_tear_after_a_recovery_is_acknowledged_in_turn(tmp_path):
    write(tmp_path, tr("planned"), '{"event":"transition","sta')
    Journal(tmp_path, T).transition(State.MINTED)
    with open(tmp_path / f"rotation-{T}.jsonl", "ab") as fh:
        fh.write(b'{"event":"transition","state":"inst')
    Journal(tmp_path, T).transition(State.INSTALLED)
    j = Journal(tmp_path, T)
    assert j.pending()["state"] == "installed" and len([e for e in j.entries() if e["event"] == "torn_tail_ack"]) == 2


def test_an_ack_that_names_another_line_does_not_excuse_a_mid_file_damaged_line(tmp_path):
    write(tmp_path, tr("planned"), '{"event":"transition","state":"halt', _ack(7))
    with pytest.raises(JournalError, match="journal line 2 is damaged"):
        Journal(tmp_path, T).entries()


def test_an_ack_must_come_right_after_the_damaged_line(tmp_path):
    write(tmp_path, tr("planned"), '{"event":"transition","state":"halt', tr("minted", 2), _ack(2))
    with pytest.raises(JournalError, match="journal line 2 is damaged"):
        Journal(tmp_path, T).entries()


def test_a_matching_ack_excuses_exactly_the_one_damaged_line(tmp_path):
    write(tmp_path, tr("planned"), '{"event":"transition","state":"halt', _ack(2), tr("minted", 2))
    assert [e.get("state") for e in Journal(tmp_path, T).entries() if e["event"] == "transition"] == ["planned", "minted"]


def test_an_ack_with_nothing_damaged_before_it_is_an_ordinary_entry(tmp_path):
    write(tmp_path, tr("planned"), _ack(1), tr("minted", 2))
    assert Journal(tmp_path, T).pending()["state"] == "minted"
