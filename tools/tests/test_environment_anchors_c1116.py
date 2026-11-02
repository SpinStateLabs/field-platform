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
    assert "FIELD_ALPHA: demo/mod.py:5 does not name it; the first read is 8" in capsys.readouterr().out
    assert ea.main(["--fix", "--root", str(root)]) == 0
    after = _doc(root)
    assert after == before.replace(b"demo/mod.py:5 |", b"demo/mod.py:8 |")
    assert ea.main(["--check", "--root", str(root)]) == 0


def test_an_anchor_on_a_docstring_line_is_wrong_even_though_the_line_names_the_variable(tmp_path, capsys):
    root = _repo(tmp_path, SOURCE, _row("FIELD_ALPHA", 3))
    assert ea.main(["--check", "--root", str(root)]) == 1
    assert "only mentions it (docstring, comment, longer name or text); the first read is 8" in capsys.readouterr().out
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
    assert "the file has no line reading it; not touched" in capsys.readouterr().out
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


@pytest.mark.parametrize("stale", [9, 4, 6, 40])
def test_a_wrong_anchor_moves_to_the_first_read_not_the_nearest(tmp_path, stale):
    """C-1121 F1: 9 is nearer to the second read (11) and 4 to the first (2); both must land on the first read."""
    root = _repo(tmp_path, TWO_READS, _row("FIELD_ALPHA", stale))
    assert ea.main(["--fix", "--root", str(root)]) == 0
    assert b"demo/mod.py:2 |" in _doc(root)


def test_an_anchor_on_a_later_read_is_wrong_and_check_says_so(tmp_path, capsys):
    root = _repo(tmp_path, TWO_READS, _row("FIELD_ALPHA", 11))   # line 11 IS a read, but not the first
    assert ea.main(["--check", "--root", str(root)]) == 1
    assert "FIELD_ALPHA: demo/mod.py:11 is a later use; the first read is 2" in capsys.readouterr().out
    assert ea.main(["--fix", "--root", str(root)]) == 0
    assert b"demo/mod.py:2 |" in _doc(root) and ea.main(["--check", "--root", str(root)]) == 0


def test_a_longer_name_is_not_a_read_of_the_shorter_one(tmp_path, capsys):
    """C-1121 F3: `FIELD_ALPHA_FILE` contains `FIELD_ALPHA`; it must neither satisfy nor attract the anchor."""
    source = 'import os\nF = os.environ.get("FIELD_ALPHA_FILE")\nA = os.environ.get("FIELD_ALPHA")\n'
    root = _repo(tmp_path, source, _row("FIELD_ALPHA", 2))
    assert ea.main(["--check", "--root", str(root)]) == 1
    assert "only mentions it" in capsys.readouterr().out
    assert ea.main(["--fix", "--root", str(root)]) == 0
    assert b"demo/mod.py:3 |" in _doc(root)


def test_a_variable_only_named_inside_a_longer_name_has_no_read(tmp_path, capsys):
    root = _repo(tmp_path, 'import os\nF = os.environ.get("FIELD_DELTA_FILE")\n', _row("FIELD_DELTA", 2))
    before = _doc(root)
    assert ea.main(["--fix", "--root", str(root)]) == 1
    assert "the file has no line reading it; not touched" in capsys.readouterr().out
    assert _doc(root) == before


def test_help_text_that_mentions_the_variable_is_not_a_read(tmp_path):
    source = ('import os\nHELP = "(default: $FIELD_ALPHA, else nothing)"\n'
              'A = os.environ.get("FIELD_ALPHA")\n')
    root = _repo(tmp_path, source, _row("FIELD_ALPHA", 2))
    assert ea.main(["--fix", "--root", str(root)]) == 0
    assert b"demo/mod.py:3 |" in _doc(root)


def test_an_fstring_with_no_placeholder_is_a_read_and_one_with_a_placeholder_is_not(tmp_path):
    """C-1121 F6: on 3.12+ an f-string is no STRING token; the tool reads the syntax tree instead."""
    plain = _repo(tmp_path / "plain", 'import os\nA = os.environ.get(f"FIELD_ALPHA")\n', _row("FIELD_ALPHA", 2))
    assert ea.main(["--check", "--root", str(plain)]) == 0
    holed = _repo(tmp_path / "holed", 'import os\np = "x"\nA = os.environ.get(f"{p}FIELD_ALPHA")\n', _row("FIELD_ALPHA", 3))
    assert ea.main(["--check", "--root", str(holed)]) == 1


def test_a_leading_zero_anchor_is_reported_not_a_traceback(tmp_path, capsys):
    root = _repo(tmp_path, SOURCE, _row("FIELD_ALPHA", 8).replace("mod.py:8", "mod.py:08"))
    before = _doc(root)
    assert ea.main(["--fix", "--root", str(root)]) == 1
    assert "is not path.py:LINE; not touched" in capsys.readouterr().out
    assert _doc(root) == before


def test_a_missing_doc_exits_3_with_one_line_not_a_traceback_and_not_the_wrong_anchor_code(tmp_path, capsys):
    (tmp_path / "docs").mkdir()
    assert ea.main(["--check", "--root", str(tmp_path)]) == 3
    out = capsys.readouterr().out
    assert out.startswith("cannot read ") and len(out.strip().splitlines()) == 1


def test_fix_writes_through_a_temporary_file_that_is_gone_afterwards(tmp_path):
    root = _repo(tmp_path, SOURCE, _row("FIELD_ALPHA", 5))
    assert ea.main(["--fix", "--root", str(root)]) == 0
    assert not (root / "docs" / "ENVIRONMENT.md.tmp").exists()
    assert b"demo/mod.py:8 |" in _doc(root)


def test_a_table_like_row_inside_a_code_fence_is_not_touched(tmp_path):
    fence = "```\n" + _row("FIELD_ALPHA", 5) + "```\n"
    root = _repo(tmp_path, SOURCE, _row("FIELD_ALPHA", 8) + fence)
    before = _doc(root)
    assert ea.main(["--check", "--root", str(root)]) == 0
    assert ea.main(["--fix", "--root", str(root)]) == 0
    assert _doc(root) == before


def test_two_source_files_ending_in_the_cited_path_are_refused(tmp_path, capsys):
    """C-1121 S1: the docstring promises not to guess when the named file is not unique."""
    root = _repo(tmp_path, SOURCE, _row("FIELD_ALPHA", 5))
    other = root / "packages" / "other" / "src" / "demo"
    other.mkdir(parents=True)
    (other / "mod.py").write_text(SOURCE, encoding="utf-8")
    before = _doc(root)
    assert ea.main(["--fix", "--root", str(root)]) == 1
    assert "'demo/mod.py' matches 2 source files; not touched" in capsys.readouterr().out
    assert _doc(root) == before


def test_a_unicode_line_separator_in_an_earlier_row_does_not_shift_the_rewrite(tmp_path):
    """C-1121 S2: split on LF only; `splitlines` would count U+2028 as a break and fix the wrong row."""
    first = _row("FIELD_BETA", 9).replace("any ", "any  ")
    root = _repo(tmp_path, SOURCE, first + _row("FIELD_ALPHA", 5))
    assert ea.main(["--fix", "--root", str(root)]) == 0
    text = _doc(root).decode("utf-8")
    assert "demo/mod.py:9 |" in text and "demo/mod.py:8 |" in text and "demo/mod.py:5 |" not in text
    assert " " in text


def test_a_row_with_four_cells_is_reported_not_an_index_error(tmp_path, capsys):
    """C-1121 S3."""
    row = "| `FIELD_ALPHA` | demo | none | any | none |\n"
    root = _repo(tmp_path, SOURCE, row)
    before = _doc(root)
    assert ea.main(["--fix", "--root", str(root)]) == 1
    assert "FIELD_ALPHA: no First read cell; not touched" in capsys.readouterr().out
    assert _doc(root) == before


def test_an_anchor_with_no_digits_is_reported_not_a_value_error(tmp_path, capsys):
    """C-1121 S4."""
    root = _repo(tmp_path, SOURCE, "| `FIELD_ALPHA` | demo | none | any | none | demo/mod.py: |\n")
    before = _doc(root)
    assert ea.main(["--fix", "--root", str(root)]) == 1
    assert "is not path.py:LINE; not touched" in capsys.readouterr().out
    assert _doc(root) == before


# C-1173 (non-blocking test gaps G1 to G4 from the C-1124 review of PR 438): each pins one behaviour a mutant could change unseen.
def test_a_failed_write_exits_3_and_leaves_the_doc_as_it_was(tmp_path, monkeypatch):   # G1
    root = _repo(tmp_path, SOURCE, _row("FIELD_ALPHA", 3))                              # line 3 is the docstring: a stale anchor
    before = _doc(root)

    def _refuse(path, text):
        raise OSError("disk full")
    monkeypatch.setattr(ea, "_write_atomic", _refuse)
    assert ea.main(["--fix", "--root", str(root)]) == 3
    assert _doc(root) == before


def test_the_rewrite_changes_only_the_last_cell_even_if_another_cell_repeats_the_anchor_text(tmp_path):   # G2
    row = "| `FIELD_ALPHA` | see demo/mod.py:3 | none | any string | none | demo/mod.py:3 |\n"
    root = _repo(tmp_path, SOURCE, row)
    assert ea.main(["--fix", "--root", str(root)]) == 0
    out = _doc(root).decode("utf-8")
    assert "| see demo/mod.py:3 |" in out                                               # the other cell is untouched
    assert out.rstrip().endswith("| demo/mod.py:8 |")                                   # the anchor cell moved to the first read


def test_the_fallback_for_unparseable_source_skips_comment_lines():                     # G3
    text = "# FIELD_X is read below\nvalue = (\nFIELD_X\n"                              # the open bracket makes it a syntax error
    with pytest.raises(SyntaxError):
        compile(text, "m", "exec")
    assert ea.read_lines_naming(text, "FIELD_X") == [3]


def test_a_source_path_must_sit_under_a_src_directory_to_match_an_anchor():             # G4
    sources = {"packages/demo/src/demo/mod.py": "x", "packages/demo/lib/demo/mod.py": "y"}
    assert ea._resolve(sources, "demo/mod.py") == ["packages/demo/src/demo/mod.py"]
    assert ea._resolve({"packages/demo/lib/demo/mod.py": "y"}, "demo/mod.py") == []
