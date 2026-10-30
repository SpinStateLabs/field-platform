"""The Phase E gate: v2-one-liners.md cites only tests that exist and name the word."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import phase_e_gate as g  # noqa: E402


def test_the_one_liners_file_passes_the_gate_without_the_commit_check():
    assert g.run(g.DOC, check_commits=False) == []


def test_a_needle_that_is_not_in_the_test_body_fails(tmp_path):
    text = g.DOC.read_text(encoding="utf-8").splitlines()
    k = next(i for i, ln in enumerate(text) if ln.startswith("| ") and "::test_" in ln)
    head, _, tail = text[k].rsplit("`", 2)[0], None, text[k].rsplit("`", 2)[2]
    text[k] = head + "`ZZZ_NOT_IN_THE_TEST`" + tail
    doc = tmp_path / "doc.md"
    doc.write_text("\n".join(text), encoding="utf-8")
    assert any("ZZZ_NOT_IN_THE_TEST" in f for f in g.run(doc, check_commits=False))


def test_a_missing_test_function_fails(tmp_path):
    t = g.DOC.read_text(encoding="utf-8")
    first = next(ln for ln in t.splitlines() if ln.startswith("| ") and "::test_" in ln)
    cite = first.split("`")[1]
    doc = tmp_path / "doc.md"
    doc.write_text(t.replace(cite, cite + "_gone", 1), encoding="utf-8")
    assert any("not found" in f for f in g.run(doc, check_commits=False))


def test_a_word_listed_enforced_and_declared_fails(tmp_path):
    t = g.DOC.read_text(encoding="utf-8")
    word = next(ln for ln in t.splitlines() if ln.startswith("| ") and "::test_" in ln).split("|")[1].strip()
    doc = tmp_path / "doc.md"
    doc.write_text(t.replace("Declared:\n", f"Declared:\n\n- **{word}** — contradiction\n", 1), encoding="utf-8")
    assert any("both Enforced and Declared" in f for f in g.run(doc, check_commits=False))
