"""Mutant survivor in UsageCursor.load (Lane R): a cursor file that parses
but is not an object of snapshot objects is corrupt, never zero."""

import json

import pytest

from claude_approver.core import UsageCursor


def test_a_valid_cursor_file_loads_its_snapshots(tmp_path):
    p = tmp_path / "cursor.json"
    p.write_text(json.dumps({"s1": {"input_tokens": 5, "output_tokens": 2}}), encoding="utf-8")
    c = UsageCursor(p)
    c.load()
    assert c.error is None
    assert c.get("s1") == {"input_tokens": 5, "output_tokens": 2, "cache_read_tokens": 0}


@pytest.mark.parametrize("text", ["[1, 2]", '"x"', "7", "null", '{"s1": [1]}', '{"s1": 3}'])
def test_valid_json_of_the_wrong_shape_is_corrupt_and_loads_nothing(tmp_path, text):
    p = tmp_path / "cursor.json"
    p.write_text(text, encoding="utf-8")
    c = UsageCursor(p)
    c.load()
    assert c.error == "usage cursor is corrupt"
    assert c.data == {}
