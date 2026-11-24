"""`POST /escalations/{id}/resolve` publishes its docstring as the OpenAPI description (route-docstring sweep, follow-up to PR 536).

Before: in `resolve` the triple-quoted text sat AFTER the executable `bind_body_operator(...)` statement, so Python treated
it as a bare string expression, not a docstring: the first-resolver-wins contract (200 for the first or the same human,
409 for a different human) never reached `/openapi.json`. Found with an AST scan of every decorated function in the
repository's non-test code; this was the only occurrence outside sealed-ledger. The scan below keeps this file's routes
from repeating it."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from spend_governor.api import create_app
from spend_governor.core import GovernorStore

API = Path(__file__).resolve().parents[1] / "src" / "spend_governor" / "api.py"


@pytest.fixture()
def openapi(tmp_path):
    return create_app(store=GovernorStore(tmp_path / "spend.sqlite3")).openapi()


def test_resolve_publishes_its_docstring_as_the_openapi_description(openapi):
    desc = " ".join(openapi["paths"]["/escalations/{escalation_id}/resolve"]["post"].get("description", "").split())
    assert "First resolver wins" in desc
    assert "409" in desc and "idempotent" in desc


def test_no_decorated_route_has_a_string_expression_after_its_first_statement_in_place_of_a_docstring():
    tree = ast.parse(API.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.decorator_list and ast.get_docstring(node) is None:
            for st in node.body[1:]:
                if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
                    bad.append((node.name, st.lineno))
    assert bad == [], f"a string after an executable statement is not a docstring: {bad}"
