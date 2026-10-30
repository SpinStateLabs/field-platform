"""Lane 10 probe (PR 308, tools/e_gate.py): citations a gate for "every Enforced word cites a test that exists and says it"
must REFUSE. Each case builds a throwaway git repo; a case that PASSES the gate is a miss. Made-up names.
Run: GATE=<checkout>/tools/e_gate.py python -m pytest -q test_e_gate_evasions.py"""
import importlib.util, os, subprocess, sys, textwrap
from pathlib import Path
import pytest
spec = importlib.util.spec_from_file_location("e_gate", os.environ["GATE"]); g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

def repo(tmp_path, files):
    def sh(*a): subprocess.run(a, cwd=tmp_path, check=True, capture_output=True)
    sh("git", "init", "-q"); sh("git", "config", "user.email", "a@b.invalid"); sh("git", "config", "user.name", "x")
    for rel, text in files.items():
        p = tmp_path / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(textwrap.dedent(text))
    sh("git", "add", "-A"); sh("git", "commit", "-qm", "c")
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()[:12]

def gate(tmp_path, files, cite, kw="widget"):
    sha = repo(tmp_path, files)
    g.ROOT = tmp_path; g._ast_cache.clear(); g.errors.clear()
    g.check_citation("case", cite, sha, kw)
    return list(g.errors)

CASES = {
 "keyword only in a comment, assert True": ("tests/test_a.py", """
    def test_a():
        # widget is enforced here
        assert True
 """, "tests/test_a.py::test_a"),
 "keyword only in a docstring": ("tests/test_a.py", '''
    def test_a():
        """widget"""
        assert 1
 ''', "tests/test_a.py::test_a"),
 "assert only in a comment": ("tests/test_a.py", """
    def test_a():
        widget = 1  # assert widget
 """, "tests/test_a.py::test_a"),
 "skipped test": ("tests/test_a.py", """
    import pytest
    @pytest.mark.skip(reason="x")
    def test_a():
        assert "widget"
 """, "tests/test_a.py::test_a"),
 "xfail test": ("tests/test_a.py", """
    import pytest
    @pytest.mark.xfail
    def test_a():
        assert "widget" == "other"
 """, "tests/test_a.py::test_a"),
 "file pytest does not collect": ("tools/helper.py", """
    def test_a():
        assert "widget"
 """, "tools/helper.py::test_a"),
 "method of a class pytest does not collect": ("tests/test_a.py", """
    class Helper:
        def test_a(self):
            assert "widget"
 """, "tests/test_a.py::test_a"),
 "function nested inside another test (never run)": ("tests/test_a.py", """
    def test_outer():
        def test_a():
            assert "widget"
 """, "tests/test_a.py::test_a"),
 "defined under if False": ("tests/test_a.py", """
    if False:
        def test_a():
            assert "widget"
 """, "tests/test_a.py::test_a"),
 "first definition shadowed by a second empty one": ("tests/test_a.py", """
    def test_a():
        assert "widget"
    def test_a():
        pass
 """, "tests/test_a.py::test_a"),
 "assert on a constant after return": ("tests/test_a.py", """
    def test_a():
        return
        assert "widget"
 """, "tests/test_a.py::test_a"),
 "assert in a never-called inner function": ("tests/test_a.py", """
    def test_a():
        def inner():
            assert "widget"
 """, "tests/test_a.py::test_a"),
 "pytest.raises as a string": ("tests/test_a.py", """
    def test_a():
        x = "pytest.raises widget"
 """, "tests/test_a.py::test_a"),
}
@pytest.mark.parametrize("name", sorted(CASES))
def test_gate_refuses(tmp_path, name):
    rel, text, cite = CASES[name]
    assert gate(tmp_path, {rel: text}, cite), f"gate ACCEPTED: {name}"

def test_prefix_name_in_the_commit_is_not_the_test(tmp_path):
    """the commit check is `def <name>` as a substring: a commit that has only `def test_x_other` satisfies a citation of test_x"""
    sha = repo(tmp_path, {"tests/test_a.py": "def test_x_other():\n    assert 'widget'\n"})
    (tmp_path / "tests/test_a.py").write_text("def test_x():\n    assert 'widget'\n")
    g.ROOT = tmp_path; g._ast_cache.clear(); g.errors.clear()
    g.check_citation("case", "tests/test_a.py::test_x", sha, "widget")
    assert g.errors, "gate ACCEPTED a commit that never contained test_x"

@pytest.mark.parametrize("line", [
    "This service is never down and is certified by us.", "It is not a toy; the product is certified.",
    "Never mind: compliant with SOC 2.", "guarantees compliance (not a joke)"])
def test_banned_word_exemption_is_whole_line(tmp_path, line):
    f = tmp_path / "README.md"; f.write_text(line + "\n")
    g.PUBLIC[:] = [f]; g.ROOT = tmp_path; g.errors.clear(); g.check_words()
    assert g.errors, f"banned claim passed: {line!r}"

def test_words_are_only_scanned_in_three_files():
    assert len(g.PUBLIC) >= 6, f"only {[p.name for p in g.PUBLIC]} are scanned for certification and compliance claims"
