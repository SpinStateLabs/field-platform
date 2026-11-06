"""S4-21: unique_labels gives every input its own label (the key the evidence pack and the cited-line check use)."""
from __future__ import annotations

from pathlib import Path

import pytest

from agent_incident_retro.engine import run_retro
from agent_incident_retro.parsers import unique_labels

LINE = '203.0.113.5 - - [01/Sep/2026:10:00:45 +0000] "GET /a HTTP/1.1" 200 5 "-" "ua"\n'


def labels(*names: str) -> list[str]:
    return unique_labels([Path("/d") / n for n in names])


def test_distinct_names_are_unchanged():
    assert labels("a.log", "b.log") == ["a.log", "b.log"]


def test_empty_input():
    assert unique_labels([]) == []


def test_same_name_twice():
    assert labels("a.log", "a.log") == ["a.log", "a.log#2"]


def test_same_name_three_times():
    assert labels("a.log", "a.log", "a.log") == ["a.log", "a.log#2", "a.log#3"]


def test_same_base_from_different_directories():
    assert unique_labels([Path("/x/a.log"), Path("/y/a.log")]) == ["a.log", "a.log#2"]


@pytest.mark.parametrize("names", [
    ("a.log", "a.log", "a.log#2"),            # a real file named like a generated label, last
    ("a.log#2", "a.log", "a.log"),            # ... first
    ("a.log", "a.log#2", "a.log"),            # ... between
    ("a.log", "a.log", "a.log#2", "a.log#2", "a.log"),
])
def test_a_real_name_that_looks_like_a_generated_label_never_collides(names):
    got = labels(*names)
    assert len(set(got)) == len(names), got


def test_the_first_occurrence_of_each_name_keeps_its_name_when_nothing_collides():
    got = labels("a.log", "a.log", "a.log#2")
    assert got[0] == "a.log" and got[1] == "a.log#2"
    assert got[2] not in ("a.log", "a.log#2")


def test_labels_reaching_the_input_files_are_the_unique_ones(tmp_path):
    d1, d2, d3 = (tmp_path / n for n in ("one", "two", "three"))
    for d in (d1, d2, d3):
        d.mkdir()
    (d1 / "a.log").write_text(LINE, encoding="utf-8")
    (d2 / "a.log").write_text(LINE, encoding="utf-8")
    (d3 / "a.log#2").write_text(LINE, encoding="utf-8")
    result = run_retro([d1 / "a.log", d2 / "a.log", d3 / "a.log#2"])
    got = [i.label for i in result.inputs]
    assert len(set(got)) == 3, got
    assert got[:2] == ["a.log", "a.log#2"]
