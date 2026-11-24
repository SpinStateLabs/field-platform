"""S10-28: `environment_anchors.py --fix` never ends in a traceback, never half-writes, never leaves a .tmp file.

Three holes, each driven through `main(['--fix', '--root', ...])`:
- a row whose anchor text appears twice in its cell made `_rewrite_last_cell` raise an uncaught ValueError (exit 1,
  the same status as "wrong anchors");
- a row with more cells than the table has columns was analysed at cell 4 but rewritten at the LAST cell;
- `_write_atomic` left `ENVIRONMENT.md.tmp` behind when the write or the rename failed.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "environment_anchors.py"
_spec = importlib.util.spec_from_file_location("environment_anchors_s10", TOOL)
ea = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ea)

SOURCE = "import os\n\nX = os.environ.get('FIELD_S10')\n"   # the first read is line 3
HEADER = ("| Variable | Component | Default | Accepted values | Security impact | First read |\n"
          "|---|---|---|---|---|---|\n")


def _repo(tmp_path: Path, rows: str) -> Path:
    src = tmp_path / "packages" / "demo" / "src" / "demo"
    src.mkdir(parents=True)
    (src / "mod.py").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ENVIRONMENT.md").write_text("# Env\n\n" + HEADER + rows, encoding="utf-8")
    return tmp_path


def _doc(root: Path) -> bytes:
    return (root / "docs" / "ENVIRONMENT.md").read_bytes()


EXTRA = "| `FIELD_S10` | demo | none | any | none | demo/mod.py:1 | note |\n"
SEVEN = "| `FIELD_S10` | demo | none | any | none | demo/mod.py:1 | a | b |\n"


def _break_the_rewrite(monkeypatch):
    """After the extra-column guard no row reaches the ValueError through `main` (the anchor cell is the last cell and
    matches `path:LINE` exactly), so the handler is driven by forcing the raise."""
    def raising(line, rel, old, new):
        raise ValueError("'" + rel + ":" + str(old) + "' appears 2 times in the anchor cell")
    monkeypatch.setattr(ea, "_rewrite_last_cell", raising)


def test_a_rewrite_refusal_is_a_named_line_not_a_traceback_and_writes_nothing(tmp_path, capsys, monkeypatch):
    root = _repo(tmp_path, "| `FIELD_S10` | demo | none | any | none | demo/mod.py:1 |\n")
    before = _doc(root)
    _break_the_rewrite(monkeypatch)
    rc = ea.main(["--fix", "--root", str(root)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "cannot rewrite FIELD_S10" in out and "doc line" in out
    assert _doc(root) == before
    assert not (root / "docs" / "ENVIRONMENT.md.tmp").exists()


def test_a_rewrite_refusal_writes_nothing_even_when_another_row_is_fixable(tmp_path, capsys, monkeypatch):
    rows = ("| `FIELD_OK` | demo | none | any | none | demo/mod.py:1 |\n"
            "| `FIELD_S10` | demo | none | any | none | demo/mod.py:1 |\n")
    root = _repo(tmp_path, rows)
    (root / "packages/demo/src/demo/mod.py").write_text(SOURCE + "Y = os.environ.get('FIELD_OK')\n", encoding="utf-8")
    before = _doc(root)
    real = ea._rewrite_last_cell

    def pick(line, rel, old, new):
        if "FIELD_S10" in line:
            raise ValueError("ambiguous")
        return real(line, rel, old, new)
    monkeypatch.setattr(ea, "_rewrite_last_cell", pick)
    assert ea.main(["--fix", "--root", str(root)]) == 1
    assert _doc(root) == before


@pytest.mark.parametrize("row", [EXTRA, SEVEN])
def test_a_row_with_extra_cells_is_reported_and_left_untouched(tmp_path, capsys, row):
    root = _repo(tmp_path, row)
    before = _doc(root)
    rc = ea.main(["--fix", "--root", str(root)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FIELD_S10" in out and "extra" in out
    assert "Traceback" not in out
    assert _doc(root) == before


@pytest.mark.parametrize("row", [EXTRA, SEVEN])
def test_check_reports_the_extra_column_row_too(tmp_path, capsys, row):
    root = _repo(tmp_path, row)
    assert ea.main(["--check", "--root", str(root)]) == 1
    assert "extra" in capsys.readouterr().out


def test_a_normal_row_is_still_fixed(tmp_path, capsys):
    root = _repo(tmp_path, "| `FIELD_S10` | demo | none | any | none | demo/mod.py:1 |\n")
    assert ea.main(["--fix", "--root", str(root)]) == 0
    assert b"demo/mod.py:3" in _doc(root)


def test_a_failed_write_removes_its_tmp_file(tmp_path, monkeypatch):
    target = tmp_path / "ENVIRONMENT.md"
    target.write_text("old", encoding="utf-8")

    def boom(self, dest):
        raise OSError("replace refused")
    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError):
        ea._write_atomic(target, "new")
    assert not (tmp_path / "ENVIRONMENT.md.tmp").exists()
    assert target.read_text(encoding="utf-8") == "old"


def test_a_failed_write_inside_the_file_removes_its_tmp_file(tmp_path, monkeypatch):
    target = tmp_path / "ENVIRONMENT.md"
    target.write_text("old", encoding="utf-8")
    real_open = open

    class Bad:
        def __init__(self, fh):
            self.fh = fh
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return self.fh.__exit__(*a)
        def write(self, _):
            raise OSError("disk full")

    monkeypatch.setattr("builtins.open", lambda p, *a, **k: Bad(real_open(p, *a, **k)) if str(p).endswith(".tmp") else real_open(p, *a, **k))
    with pytest.raises(OSError):
        ea._write_atomic(target, "new")
    assert not (tmp_path / "ENVIRONMENT.md.tmp").exists()


def test_the_rewrite_error_never_echoes_the_cell_text():
    line = "| `FIELD_S10` | demo | none | any | none | LEAKY demo/mod.py:1 demo/mod.py:1 |"
    with pytest.raises(ValueError) as e:
        ea._rewrite_last_cell(line, "demo/mod.py", 1, 3)
    assert "LEAKY" not in str(e.value)
    assert "demo/mod.py:1" in str(e.value)
