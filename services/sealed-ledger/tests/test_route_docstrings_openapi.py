"""The retention and hold routes' docstrings are real docstrings, so FastAPI publishes them as OpenAPI descriptions (scout P-18).

Before: in `rotate`, `place_hold`, `release_hold` and `retention_apply` the triple-quoted text came AFTER the executable
`bind_body_operator(...)` statement, so Python treated it as a bare string expression, not a docstring: the status-code
contract each text documents (423 under a legal hold, 409, 503, 500...) never reached `/openapi.json`. The AST scan keeps
a new route from doing the same."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore

API = Path(__file__).resolve().parents[1] / "src" / "sealed_ledger" / "api.py"

DESCRIBED = [
    ("/retention/apply", "post", "423 under a legal hold"),
    ("/rotate", "post", "Close the open segment"),
    ("/hold", "post", "Place the legal hold"),
    ("/hold/release", "post", "Release the legal hold"),
]


@pytest.fixture()
def openapi(tmp_path):
    return create_app(store=LedgerStore(tmp_path / "events.jsonl")).openapi()


@pytest.mark.parametrize("path,method,phrase", DESCRIBED)
def test_the_route_publishes_its_docstring_as_the_openapi_description(openapi, path, method, phrase):
    assert phrase in openapi["paths"][path][method].get("description", ""), (path, method)


def test_the_apply_description_carries_the_whole_status_contract(openapi):
    text = " ".join(openapi["paths"]["/retention/apply"]["post"]["description"].split())
    for code in ("423", "422", "503", "500"):
        assert code in text


def test_no_route_has_a_string_expression_after_its_first_statement_in_place_of_a_docstring():
    """A decorated function whose docstring slot holds something else and which has a later bare string expression."""
    tree = ast.parse(API.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.decorator_list and ast.get_docstring(node) is None:
            for st in node.body[1:]:
                if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
                    bad.append((node.name, st.lineno))
    assert bad == [], f"a string after an executable statement is not a docstring: {bad}"


def test_the_scan_sees_the_shape_it_looks_for():
    src = 'def f():\n    x = 1\n    """not a docstring"""\n'
    tree = ast.parse(src)
    fn = tree.body[0]
    assert ast.get_docstring(fn) is None
    assert any(isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant) for st in fn.body[1:])
