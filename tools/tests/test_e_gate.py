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


# ---- a failing fixture per check (C-493 F-PR308-2, Lane 10 probe): check_citation on a
# made-up test file, git stubbed to return the same file as the cited commit's content.

def cite(tmp_path, monkeypatch, test_src, kw="owner", shown=None):
    (tmp_path / "t").mkdir(exist_ok=True)
    (tmp_path / "t" / "test_x.py").write_text(test_src, encoding="utf-8")
    monkeypatch.setattr(g, "ROOT", tmp_path)
    monkeypatch.setattr(g, "git", lambda *a: (0, test_src if shown is None else shown))
    monkeypatch.setattr(g, "errors", [])
    g._ast_cache.clear()
    g.check_citation("w", "t/test_x.py::test_a", "deadbeef", kw)
    return g.errors


def test_a_gutted_test_with_the_keyword_in_a_comment_fails(tmp_path, monkeypatch):
    errs = cite(tmp_path, monkeypatch, "def test_a():\n    assert True  # owner\n")
    assert errs == ["w: test_a does not name 'owner' in an assert or raises block"]


def test_the_keyword_only_in_a_docstring_fails(tmp_path, monkeypatch):
    src = 'def test_a():\n    """the owner is required"""\n    assert 1 == 1\n'
    assert any("does not name 'owner'" in e for e in cite(tmp_path, monkeypatch, src))


def test_the_keyword_only_in_set_up_code_fails(tmp_path, monkeypatch):
    src = 'def test_a():\n    r = post(json={"owner": ""})\n    assert r.status_code == 422\n'
    assert any("does not name 'owner'" in e for e in cite(tmp_path, monkeypatch, src))


def test_the_word_assert_inside_a_string_is_not_an_assertion(tmp_path, monkeypatch):
    src = 'def test_a():\n    x = "pytest.raises owner assert"\n'
    assert any("contains no assertion" in e for e in cite(tmp_path, monkeypatch, src))


def test_the_keyword_in_an_assert_passes(tmp_path, monkeypatch):
    src = 'def test_a():\n    r = make()\n    assert r.owner == "x"\n'
    assert cite(tmp_path, monkeypatch, src) == []


def test_the_keyword_in_a_raises_block_passes(tmp_path, monkeypatch):
    src = "def test_a():\n    with pytest.raises(ValueError):\n        check_owner('')\n"
    assert cite(tmp_path, monkeypatch, src, kw="check_owner") == []


def test_a_commit_that_defines_only_a_longer_name_fails(tmp_path, monkeypatch):
    src = "def test_a():\n    assert owner\n"
    errs = cite(tmp_path, monkeypatch, src, shown="def test_a_other():\n    assert owner\n")
    assert errs == ["w: commit deadbeef does not define test_a in t/test_x.py"]


def test_an_enforced_word_turned_declared_fails_on_the_readme_row(tmp_path, monkeypatch):
    t = DOC.read_text(encoding="utf-8")
    row = next(ln for ln in t.splitlines()
               if ln.startswith("| Enforced") and not ln.rstrip().endswith("| — |"))
    errs = run(tmp_path, monkeypatch, t.replace(row, row.replace("| Enforced |", "| Declared |", 1), 1))
    assert any("README row is Enforced but E1 says Declared" in e for e in errs)


# ---- banned phrases (C-493 F-PR308-3): a negation anywhere on the line used to exempt it.

def words(tmp_path, monkeypatch, *lines):
    f = tmp_path / "pub.md"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(g, "PUBLIC", [f])
    monkeypatch.setattr(g, "errors", [])
    g.check_words()
    return g.errors


def test_a_claim_with_never_elsewhere_on_the_line_fails(tmp_path, monkeypatch):
    errs = words(tmp_path, monkeypatch, "We are certified and compliant with ISO 42001, never in doubt.")
    assert [e.split(": ")[-1] for e in errs] == ["'certified'", "'compliant with'"]


def test_a_claim_with_not_a_elsewhere_on_the_line_fails(tmp_path, monkeypatch):
    errs = words(tmp_path, monkeypatch, "Not a problem: the product is certified.")
    assert len(errs) == 1 and "'certified'" in errs[0]


def test_a_negation_directly_before_the_phrase_is_exempt(tmp_path, monkeypatch):
    assert words(tmp_path, monkeypatch,
                 "The pack is not certified by anyone.",
                 "It does not guarantee compliance and is never compliant with a law by itself.",
                 "No part is certified.") == []


def test_a_negation_more_than_two_words_before_is_not_an_exemption(tmp_path, monkeypatch):
    errs = words(tmp_path, monkeypatch, "It is never going to be anything but certified.")
    assert len(errs) == 1 and "'certified'" in errs[0]
