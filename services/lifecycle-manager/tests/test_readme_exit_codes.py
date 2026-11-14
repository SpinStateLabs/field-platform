"""S11-14: the README's per-verb exit-code table is the CLI's actual contract.

The README said `sweep` exits 0 or 3 and `provision`/`decommission` exit 0 or 1; the CLI also exits 2 (a `sweep` roster
with no owners, any operator-identity refusal through `_refuse`, `provision` with neither --grantor nor an operator
identity, `decommission` refused at the local operator gate). This test walks cli.py with `ast`, derives each verb's
code set (an implicit 0, every literal `typer.Exit(code=N)`, and 2 for any call that reaches `_refuse`, transitively),
and compares it with the table under `## Exit codes` in README.md.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SERVICE = Path(__file__).resolve().parents[1]
CLI = SERVICE / "src" / "lifecycle_manager" / "cli.py"
README = SERVICE / "README.md"


def _is_command(fn: ast.FunctionDef) -> bool:
    return any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "command"
               and isinstance(d.func.value, ast.Name) and d.func.value.id == "app" for d in fn.decorator_list)


def _literal_exit_codes(node: ast.AST) -> set[int]:
    codes = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "Exit":
            for kw in n.keywords:
                if kw.arg == "code" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int):
                    codes.add(kw.value.value)
    return codes


def _called_names(node: ast.AST) -> set[str]:
    return {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def derived() -> dict[str, set[int]]:
    tree = ast.parse(CLI.read_text(encoding="utf-8"))
    funcs = {f.name: f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)}
    own = {name: _literal_exit_codes(f) for name, f in funcs.items()}
    calls = {name: _called_names(f) & set(funcs) for name, f in funcs.items()}

    def codes(name: str, seen: frozenset[str] = frozenset()) -> set[int]:
        out = set(own[name])
        for callee in calls[name] - seen:
            out |= codes(callee, seen | {name})
        return out

    return {name: {0} | codes(name) for name, f in funcs.items() if _is_command(f)}


def documented() -> dict[str, set[int]]:
    text = README.read_text(encoding="utf-8")
    section = text.split("## Exit codes", 1)[1].split("\n## ", 1)[0]
    rows = {}
    for m in re.finditer(r"^\| `(\w+)` \| ([0-9, ]+) \|", section, re.M):
        rows[m.group(1)] = {int(x) for x in m.group(2).split(",")}
    return rows


def test_the_ast_walk_sees_every_verb_and_the_helper_chain():
    d = derived()
    assert set(d) == {"version", "sweep", "provision", "decommission", "serve"}
    assert 2 in d["sweep"] and 2 in d["provision"] and 2 in d["decommission"]   # via _refuse / operator_pair


def test_the_readme_table_covers_the_same_verbs_as_the_cli():
    assert set(documented()) == set(derived()) - {"version"}


@pytest.mark.parametrize("verb", ["sweep", "provision", "decommission", "serve"])
def test_each_verbs_documented_exit_codes_equal_the_cli_s(verb):
    assert documented()[verb] == derived()[verb], (verb, documented()[verb], derived()[verb])


def test_the_two_specific_claims_the_old_readme_got_wrong():
    d = documented()
    assert d["sweep"] == {0, 2, 3}
    assert d["provision"] == {0, 1, 2} and d["decommission"] == {0, 1, 2}


def test_the_readme_says_what_an_uncaught_error_is():
    text = README.read_text(encoding="utf-8")
    assert "uncaught" in text.split("## Exit codes", 1)[1].split("\n## ", 1)[0]


# -- the documented exit 2 paths, driven rather than only derived ------------------------------------------------


@pytest.fixture()
def no_operator(monkeypatch):
    for var in ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY", "FIELD_OPERATOR_KEY_FILE"):
        monkeypatch.delenv(var, raising=False)


def _invoke(*args):
    from typer.testing import CliRunner

    from lifecycle_manager import cli
    return CliRunner().invoke(cli.app, list(args))


def test_sweep_with_half_an_operator_identity_is_exit_2(no_operator, tmp_path):
    res = _invoke("sweep", "--roster", str(tmp_path / "r.csv"), "--operator-id", "x")
    assert res.exit_code == 2 and "go together" in res.output


def test_provision_with_neither_grantor_nor_operator_identity_is_exit_2_and_sends_nothing(no_operator, tmp_path):
    res = _invoke("provision", "--manifest", str(tmp_path / "m.yaml"), "--owner", "o", "--domain", "d", "--ttl-days", "1")
    assert res.exit_code == 2 and "give --grantor" in res.output and "nothing sent" in res.output


def test_decommission_with_half_an_operator_identity_is_exit_2(no_operator):
    res = _invoke("decommission", "a1", "--by", "b", "--reason", "r", "--operator-id", "x")
    assert res.exit_code == 2 and "go together" in res.output


def test_sweep_on_a_roster_with_no_owners_is_exit_2(no_operator, tmp_path, monkeypatch):
    from lifecycle_manager import cli
    roster = tmp_path / "r.csv"
    roster.write_text("owner\n", encoding="utf-8")

    class _Stub:
        def __getattr__(self, name):
            raise AttributeError(name)

        def append(self, *a, **k):
            raise AssertionError("no ledger write before the roster is read")

    monkeypatch.setattr(cli, "estate_clients", lambda pair, timeout=20.0: {
        "registry": _Stub(), "delegation": _Stub(), "ledger": _Stub(), "killswitch": _Stub()})
    res = _invoke("sweep", "--roster", str(roster))
    assert res.exit_code == 2, res.output
