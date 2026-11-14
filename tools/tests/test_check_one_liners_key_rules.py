"""S11-28: check_one_liners cannot be satisfied by a letter, a nested helper or a shadowed stub.

* a KEY of fewer than 3 non-space characters matched almost any test (`key in body`): it is now a FAIL line;
* `test_source` walked every node (nested functions included) and returned the first function of that name, though the
  docstring promises module level or a class method, and Python runs the LAST definition of a name in one scope: a stub
  shadowed by a real test passed on the stub's text, a nested helper stood in for a test that does not exist.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_one_liners_s11_28", ROOT / "tools" / "check_one_liners.py")
cl = importlib.util.module_from_spec(_spec)
sys.modules["check_one_liners_s11_28"] = cl
_spec.loader.exec_module(cl)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def make_repo(tmp_path, source):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(source, encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "t")
    return git(tmp_path, "rev-parse", "HEAD")


def document(commit, test, key, path="tests/test_a.py"):
    out = [cl.GLOBAL_LINE.capitalize() + ".", "Old wording: see v2-one-liners-source.md and the audit."]
    out += [f"## {n} — System {n}" for n in range(1, 13)]
    out += [f"qualifier: {q}" for q in cl.REQUIRED_QUALIFIERS]
    out.append(f"- ENFORCED: word | CITE: {path}::{test} @ {commit} | KEY: {key}")
    return "\n".join(out) + "\n"


def run(tmp_path, commit, test, key, capsys):
    f = tmp_path / "doc.md"
    f.write_text(document(commit, test, key), encoding="utf-8")
    code = cl.main(["--file", str(f), "--repo", str(tmp_path)])
    return code, capsys.readouterr().out


# -- the KEY length -----------------------------------------------------------------------------------------------

SRC = '''
def test_token_expires():
    """An expired token is refused."""
    assert refuse("expired")
'''


@pytest.mark.parametrize("key", ["a", "e", "ex", "e x", " e ", "  "])
def test_a_key_under_three_non_space_characters_is_a_failure(tmp_path, capsys, key):
    commit = make_repo(tmp_path, SRC)
    code, out = run(tmp_path, commit, "test_token_expires", key, capsys)
    assert code == 1, out
    assert "the key is at least 3 non-space characters" in out.split("[FAIL]")[1]


@pytest.mark.parametrize("key", ["exp", "expired", "refuse"])
def test_a_key_of_three_or_more_non_space_characters_still_passes(tmp_path, capsys, key):
    commit = make_repo(tmp_path, SRC)
    code, out = run(tmp_path, commit, "test_token_expires", key, capsys)
    assert code == 0, out


def test_a_short_key_is_never_also_reported_as_found(tmp_path, capsys):
    commit = make_repo(tmp_path, SRC)
    _, out = run(tmp_path, commit, "test_token_expires", "e", capsys)
    assert "the test mentions the key" not in out


def test_the_shipped_one_liners_keys_are_all_long_enough():
    keys = [m["key"] for m in cl.CITE_RE.finditer((ROOT / "docs/capstone-evidence/v2-one-liners.md").read_text("utf-8"))]
    assert keys and all(len("".join(k.split())) >= cl.MIN_KEY_CHARS for k in keys), keys


# -- test_source resolves like Python --------------------------------------------------------------------------------


def test_a_nested_function_is_not_a_test():
    src = "def test_outer():\n    def test_inner():\n        assert 'INNER-ONLY'\n    assert 1\n"
    assert cl.test_source(src, "test_inner") is None
    assert cl.test_source(src, "test_outer") is not None                  # the outer one is found


def test_a_nested_helper_cannot_stand_in_for_a_missing_test(tmp_path, capsys):
    src = "def test_outer():\n    def test_inner():\n        assert 'INNER-WORD'\n    assert 1\n"
    commit = make_repo(tmp_path, src)
    code, out = run(tmp_path, commit, "test_inner", "INNER-WORD", capsys)
    assert code == 1 and "test function exists" in out.split("[FAIL]")[1]


def test_the_last_definition_in_one_scope_wins():
    src = "def test_x():\n    assert 'STUB-TEXT'\n\n\ndef test_x():\n    assert 'REAL-TEXT'\n"
    body = cl.test_source(src, "test_x")
    assert "REAL-TEXT" in body and "STUB-TEXT" not in body


def test_a_shadowed_stub_cannot_carry_the_key(tmp_path, capsys):
    src = "def test_x():\n    assert 'STUB-WORD'\n\n\ndef test_x():\n    assert 'real'\n"
    commit = make_repo(tmp_path, src)
    code, out = run(tmp_path, commit, "test_x", "STUB-WORD", capsys)
    assert code == 1 and "mentions the key" in out.split("[FAIL]")[1]


def test_the_last_method_definition_in_a_class_wins():
    src = "class TestA:\n    def test_m(self):\n        assert 'OLD-M'\n    def test_m(self):\n        assert 'NEW-M'\n"
    body = cl.test_source(src, "test_m")
    assert "NEW-M" in body and "OLD-M" not in body


def test_module_level_and_class_methods_are_still_found():
    src = "def test_f():\n    assert 'F'\n\n\nclass TestC:\n    def test_g(self):\n        assert 'G'\n"
    assert "'F'" in cl.test_source(src, "test_f")
    assert "'G'" in cl.test_source(src, "test_g")


def test_an_async_test_is_found_and_the_last_async_or_sync_definition_wins():
    src = "async def test_a():\n    assert 'ASYNC-OLD'\n\n\nasync def test_a():\n    assert 'ASYNC-NEW'\n"
    body = cl.test_source(src, "test_a")
    assert "ASYNC-NEW" in body and "ASYNC-OLD" not in body


def test_a_test_defined_inside_an_if_block_at_module_level_is_found():
    src = "import sys\nif sys.platform != 'never':\n    def test_c():\n        assert 'COND'\n"
    assert "COND" in cl.test_source(src, "test_c")


def test_a_function_inside_a_function_inside_a_class_is_not_found():
    src = "class TestC:\n    def test_m(self):\n        def test_deep():\n            assert 'DEEP'\n"
    assert cl.test_source(src, "test_deep") is None


def test_a_module_level_function_wins_over_a_same_named_method():
    src = "class TestC:\n    def test_z(self):\n        assert 'METHOD'\n\n\ndef test_z():\n    assert 'MODULE'\n"
    body = cl.test_source(src, "test_z")
    assert "MODULE" in body and "METHOD" not in body


def test_unparseable_source_is_none():
    assert cl.test_source("def (:\n", "test_x") is None


def test_a_test_defined_in_try_with_or_except_blocks_at_module_level_is_found():
    src = ("try:\n    def test_t():\n        assert 'IN-TRY'\nexcept ImportError:\n    def test_e():\n        assert 'IN-EXCEPT'\n"
           "finally:\n    def test_f():\n        assert 'IN-FINALLY'\n"
           "with open(__file__):\n    def test_w():\n        assert 'IN-WITH'\n")
    for name, word in (("test_t", "IN-TRY"), ("test_e", "IN-EXCEPT"), ("test_f", "IN-FINALLY"), ("test_w", "IN-WITH")):
        assert word in cl.test_source(src, name), name


def test_a_method_of_a_class_nested_in_a_class_is_not_found():
    """The card's rule: methods of MODULE-LEVEL classes only."""
    src = "class TestOuter:\n    class TestInner:\n        def test_n(self):\n            assert 'NESTED-CLASS'\n"
    assert cl.test_source(src, "test_n") is None
