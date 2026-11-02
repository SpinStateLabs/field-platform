"""C-1116: tools/environment_anchors.py checks and repairs the `First read` anchors of docs/ENVIRONMENT.md.

Each test builds a throw-away repository in tmp_path (one source file, one doc) and runs the tool's `main`. The last
test runs the tool's check on this repository's own doc, so a stale or docstring anchor can no longer merge unseen.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "environment_anchors.py"
_spec = importlib.util.spec_from_file_location("environment_anchors", TOOL)
ea = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ea)

HEADER = ("| Variable | Component | Default | Accepted values | Security impact | First read |\n"
          "|---|---|---|---|---|---|\n")


def _row(name: str, line: int, path: str = "demo/mod.py") -> str:
    return f"| `{name}` | demo | none | any `a\\|b` string | none | {path}:{line} |\n"


def _repo(tmp_path: Path, source: str, rows: str, eol: str = "\n") -> Path:
    src = tmp_path / "packages" / "demo" / "src" / "demo"
    src.mkdir(parents=True)
    (src / "mod.py").write_text(source, encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    text = "# Environment variables\n\n" + HEADER + rows
    (docs / "ENVIRONMENT.md").write_bytes(text.replace("\n", eol).encode("utf-8"))
    return tmp_path


def _doc(root: Path) -> bytes:
    return (root / "docs" / "ENVIRONMENT.md").read_bytes()


SOURCE = (
    '"""demo module.\n'                         # 1
    "\n"                                       # 2
    'It reads FIELD_ALPHA and FIELD_BETA.\n'   # 3 (docstring)
    '"""\n'                                    # 4
    "import os\n"                              # 5
    "\n"                                       # 6
    "# FIELD_GAMMA is read below\n"            # 7 (comment)
    'ALPHA = os.environ.get("FIELD_ALPHA")\n'  # 8
    'BETA = os.environ.get("FIELD_BETA")\n'    # 9
    'GAMMA = os.environ.get("FIELD_GAMMA")\n'  # 10
)


def test_a_stale_anchor_is_reported_then_fixed_and_only_the_number_changes(tmp_path, capsys):
    rows = _row("FIELD_ALPHA", 5) + _row("FIELD_BETA", 9)
    root = _repo(tmp_path, SOURCE, rows)
    before = _doc(root)
    assert ea.main(["--check", "--root", str(root)]) == 1
    assert _doc(root) == before, "--check must not write"
    assert "FIELD_ALPHA: demo/mod.py:5 does not name it; nearest code line naming it is 8" in capsys.readouterr().out
    assert ea.main(["--fix", "--root", str(root)]) == 0
    after = _doc(root)
    assert after == before.replace(b"demo/mod.py:5 |", b"demo/mod.py:8 |")
    assert ea.main(["--check", "--root", str(root)]) == 0


def test_an_anchor_on_a_docstring_line_is_wrong_even_though_the_line_names_the_variable(tmp_path, capsys):
    root = _repo(tmp_path, SOURCE, _row("FIELD_ALPHA", 3))
    assert ea.main(["--check", "--root", str(root)]) == 1
    assert "names it only in a docstring or comment; nearest code line naming it is 8" in capsys.readouterr().out
    assert ea.main(["--fix", "--root", str(root)]) == 0
    assert b"demo/mod.py:8 |" in _doc(root)


def test_an_anchor_on_a_comment_line_is_wrong(tmp_path, capsys):
    root = _repo(tmp_path, SOURCE, _row("FIELD_GAMMA", 7))
    assert ea.main(["--check", "--root", str(root)]) == 1
    assert "FIELD_GAMMA" in capsys.readouterr().out
    assert ea.main(["--fix", "--root", str(root)]) == 0
    assert b"demo/mod.py:10 |" in _doc(root)


def test_a_valid_anchor_is_left_alone_and_two_rows_may_share_a_line(tmp_path):
    source = 'import os\nA, B = os.environ.get("FIELD_ALPHA"), os.environ.get("FIELD_BETA")\n'
    root = _repo(tmp_path, source, _row("FIELD_ALPHA", 2) + _row("FIELD_BETA", 2))
    before = _doc(root)
    assert ea.main(["--check", "--root", str(root)]) == 0
    assert ea.main(["--fix", "--root", str(root)]) == 0
    assert _doc(root) == before


def test_fix_changes_nothing_but_the_line_numbers_and_keeps_the_row_order(tmp_path):
    rows = _row("FIELD_GAMMA", 1) + _row("FIELD_ALPHA", 2) + _row("FIELD_BETA", 3)
    root = _repo(tmp_path, SOURCE, rows)
    before = _doc(root).decode("utf-8")
    assert ea.main(["--fix", "--root", str(root)]) == 0
    after = _doc(root).decode("utf-8")
    mask = lambda s: re.sub(r"(demo/mod\.py):\d+ \|$", r"\1:N |", s, flags=re.M)   # noqa: E731
    assert mask(after) == mask(before), "wording, columns and row order are untouched"
    names = lambda s: re.findall(r"^\| `(\w+)`", s, flags=re.M)   # noqa: E731
    assert names(after) == names(before) == ["FIELD_GAMMA", "FIELD_ALPHA", "FIELD_BETA"]
    assert re.findall(r"demo/mod\.py:(\d+) \|$", after, flags=re.M) == ["10", "8", "9"]


def test_a_variable_with_two_rows_is_reported_and_never_touched(tmp_path, capsys):
    rows = _row("FIELD_ALPHA", 1) + _row("FIELD_BETA", 9) + _row("FIELD_ALPHA", 2)
    root = _repo(tmp_path, SOURCE, rows)
    before = _doc(root)
    assert ea.main(["--check", "--root", str(root)]) == 1
    assert "FIELD_ALPHA: 2 rows; not touched" in capsys.readouterr().out
    assert ea.main(["--fix", "--root", str(root)]) == 1
    assert _doc(root) == before


@pytest.mark.parametrize("cell, expect", [
    ("none", "is not path.py:LINE"),
    ("demo/missing.py:3", "matches 0 source files"),
])
def test_an_anchor_the_tool_cannot_resolve_is_reported_and_left_alone(tmp_path, capsys, cell, expect):
    row = f"| `FIELD_ALPHA` | demo | none | any | none | {cell} |\n"
    root = _repo(tmp_path, SOURCE, row)
    before = _doc(root)
    assert ea.main(["--fix", "--root", str(root)]) == 1
    assert expect in capsys.readouterr().out
    assert _doc(root) == before


def test_a_variable_with_no_code_line_in_its_file_is_not_guessed(tmp_path, capsys):
    root = _repo(tmp_path, SOURCE, _row("FIELD_DELTA", 5))
    before = _doc(root)
    assert ea.main(["--fix", "--root", str(root)]) == 1
    assert "the file has no code line naming it; not touched" in capsys.readouterr().out
    assert _doc(root) == before


def test_crlf_line_endings_are_kept_byte_for_byte(tmp_path):
    root = _repo(tmp_path, SOURCE, _row("FIELD_ALPHA", 5) + _row("FIELD_BETA", 9), eol="\r\n")
    before = _doc(root)
    assert ea.main(["--fix", "--root", str(root)]) == 0
    after = _doc(root)
    assert after == before.replace(b"demo/mod.py:5 |", b"demo/mod.py:8 |")
    assert after.count(b"\r\n") == before.count(b"\r\n") and b"\n" not in after.replace(b"\r\n", b"")


def test_an_escaped_pipe_in_another_cell_does_not_move_the_edit(tmp_path):
    root = _repo(tmp_path, SOURCE, _row("FIELD_ALPHA", 5))
    assert b"a\\|b" in _doc(root)
    assert ea.main(["--fix", "--root", str(root)]) == 0
    assert b"any `a\\|b` string" in _doc(root) and b"demo/mod.py:8 |" in _doc(root)


def test_this_repositorys_own_first_read_anchors_are_all_right():
    """The doc on this branch has no wrong anchor (FORCE_GATEWAY_MOCK cited a docstring line before C-1116)."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "docs" / "ENVIRONMENT.md").read_text(encoding="utf-8")
    assert ea.analyse(text, ea.source_files(root)) == []


TWO_READS = ("import os\n" + 'A = os.environ.get("FIELD_ALPHA")\n' + "\n" * 8 + 'B = os.environ.get("FIELD_ALPHA")\n'
             + "\n" * 3)   # code lines 2 and 11


@pytest.mark.parametrize("stale, expected", [
    (9, 11),    # nearer to the second read
    (4, 2),     # nearer to the first read
    (6, 2),     # 2 is 4 away, 11 is 5 away
])
def test_a_wrong_anchor_moves_to_the_nearest_code_line_naming_the_variable(tmp_path, stale, expected):
    root = _repo(tmp_path, TWO_READS, _row("FIELD_ALPHA", stale))
    assert ea.main(["--fix", "--root", str(root)]) == 0
    assert f"demo/mod.py:{expected} |".encode() in _doc(root)


def test_a_tie_between_two_code_lines_goes_to_the_lower_one(tmp_path):
    source = "import os\n" + 'A = os.environ.get("FIELD_ALPHA")\n' + "\n" * 5 + 'B = os.environ.get("FIELD_ALPHA")\n'   # lines 2 and 8
    root = _repo(tmp_path, source, _row("FIELD_ALPHA", 5))   # 3 from each
    assert ea.main(["--fix", "--root", str(root)]) == 0
    assert b"demo/mod.py:2 |" in _doc(root)
