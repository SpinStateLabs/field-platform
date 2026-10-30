"""tools/e_gate.py fails when a word is not backed by a test that names it (Phase E)."""
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("e_gate", ROOT / "tools" / "e_gate.py")
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

DOC = ROOT / "docs/capstone-evidence/v2-one-liners.md"


def run(tmp_path, monkeypatch, text, bad_sha=None):
    """Run the E1 check on `text`; git is stubbed (no history walk) except for `bad_sha`."""
    def fake_git(*args):
        if args[0] == "merge-base":
            return (1 if args[2] == bad_sha else 0), ""
        path = args[1].split(":", 1)[1]
        return 0, (ROOT / path).read_text(encoding="utf-8")

    doc = tmp_path / "doc.md"
    doc.write_text(text, encoding="utf-8")
    monkeypatch.setattr(g, "E1", doc)
    monkeypatch.setattr(g, "git", fake_git)
    monkeypatch.setattr(g, "errors", [])
    g.ONE.clear()
    g.check_e1()
    return g.errors


def first_enforced(text):
    return next(ln for ln in text.splitlines() if ln.startswith("| Enforced"))


def test_the_shipped_file_passes(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, DOC.read_text(encoding="utf-8")) == []


def test_a_keyword_the_test_does_not_name_fails(tmp_path, monkeypatch):
    t = DOC.read_text(encoding="utf-8")
    row = first_enforced(t)
    cells = row.split("|")
    cells[5] = " `ZZZ_NOT_IN_THE_TEST` "
    errs = run(tmp_path, monkeypatch, t.replace(row, "|".join(cells), 1))
    assert any("ZZZ_NOT_IN_THE_TEST" in e for e in errs)


def test_a_missing_test_function_fails(tmp_path, monkeypatch):
    t = DOC.read_text(encoding="utf-8")
    cite = re.search(r"`([\w./-]+\.py::\w+)`", first_enforced(t)).group(1)
    errs = run(tmp_path, monkeypatch, t.replace(cite, cite + "_gone", 1))
    assert any("is not defined" in e for e in errs)


def test_a_commit_that_is_not_an_ancestor_fails(tmp_path, monkeypatch):
    t = DOC.read_text(encoding="utf-8")
    sha = first_enforced(t).split("|")[4].strip().strip("`")
    errs = run(tmp_path, monkeypatch, t.replace(f"`{sha}`", "`" + sha + "`", 1), bad_sha=sha)
    assert any("not an ancestor" in e for e in errs)


def test_a_declared_word_turned_enforced_fails_on_the_readme_row(tmp_path, monkeypatch):
    t = DOC.read_text(encoding="utf-8")
    t = t.replace("| Declared | the caller is the named grantor |", "| Enforced | the caller is the named grantor |", 1)
    errs = run(tmp_path, monkeypatch, t)
    assert any("README row is Declared but E1 says Enforced" in e for e in errs)


def test_a_changed_old_sentence_is_not_verbatim(tmp_path, monkeypatch):
    t = DOC.read_text(encoding="utf-8")
    t = t.replace("**Old (verbatim):** \"system of record", "**Old (verbatim):** \"a made-up system of record", 1)
    assert any("not verbatim" in e for e in run(tmp_path, monkeypatch, t))
