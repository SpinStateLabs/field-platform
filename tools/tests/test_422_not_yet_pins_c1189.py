"""C-1189 (Lane 17 C-1185, Lane 15 C-1151 F-C1151-1): what the NOT_YET services of the 422 guard really are.

``test_422_handler_installed_c1114.py`` keeps four services out of the field-core handler (NOT_YET). Lane 17 read the code on main:
  * federation-broker keeps its own handler on purpose and already has a request test (services/federation-broker/tests/
    test_422_key_name_c1128.py);
  * attestation-reporter and claude-approver have no body model and no typed parameter, so a 422 by type is unreachable;
  * kill-switch was NOT in the second group (four routes take a body); main installs the handler there (cd3b7690) and the guard lists it as measured.
These pins keep the first two groups true: when one stops being true, the service must leave NOT_YET.
"""
from __future__ import annotations

import ast
import typing
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

ROOT = Path(__file__).resolve().parents[2]


def _is_str(annotation) -> bool:
    """``str`` or ``str | None`` (``Optional[str]``) and nothing else."""
    if annotation is str:
        return True
    args = typing.get_args(annotation)
    return bool(args) and set(args) <= {str, type(None)} and str in args


def untyped_surface(app: FastAPI) -> list[str]:
    """Every route parameter a client can send that is NOT a plain string, plus every body parameter. Empty means no
    request can fail validation by type (a 422 needs a body model, a non-string type, or a missing required value)."""
    found: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        dep = route.dependant
        for f in dep.body_params:
            found.append(f"{route.path}: body {f.name}")
        for group in (dep.path_params, dep.query_params, dep.header_params, dep.cookie_params):
            for f in group:
                if not _is_str(f.field_info.annotation):
                    found.append(f"{route.path}: {f.name} is {f.field_info.annotation!r}")
    return found


def test_the_check_goes_red_on_a_typed_parameter_or_a_body():
    app = FastAPI()

    @app.get("/n")
    def n(count: int) -> dict:          # a typed query parameter: a 422 is reachable
        return {}


    @app.get("/s")
    def s(name: str | None = None) -> dict:  # a plain optional string: not reachable
        return {}
    found = untyped_surface(app)
    assert any("count" in x for x in found) and not any("name" in x for x in found), found


def test_attestation_reporter_has_no_typed_parameter_and_no_body():
    from attestation_reporter.api import create_app
    assert untyped_surface(create_app()) == []


def test_claude_approver_has_no_typed_parameter_and_no_body():
    from claude_approver.api import create_app
    assert untyped_surface(create_app()) == []


def _handler_registrations(source: str) -> int:
    """How many ``@app.exception_handler(RequestValidationError)`` decorators or ``add_exception_handler(
    RequestValidationError, ...)`` calls the module has (an ``ast`` read, so a comment or string does not count)."""
    n = 0
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in ("exception_handler", "add_exception_handler"):
                first = node.args[0] if node.args else None
                if isinstance(first, ast.Name) and first.id == "RequestValidationError":
                    n += 1
    return n


def test_federation_broker_keeps_its_own_validation_handler_and_its_request_test():
    api = ROOT / "services" / "federation-broker" / "src" / "federation_broker" / "api.py"
    assert _handler_registrations(api.read_text(encoding="utf-8")) == 1
    assert (ROOT / "services" / "federation-broker" / "tests" / "test_422_key_name_c1128.py").is_file()


def test_the_handler_counter_does_not_count_a_comment_a_string_or_an_unrelated_handler():
    assert _handler_registrations("# @app.exception_handler(RequestValidationError)\n") == 0
    assert _handler_registrations('x = "app.exception_handler(RequestValidationError)"\n') == 0
    assert _handler_registrations("app.add_exception_handler(ValueError, h)\n") == 0
    assert _handler_registrations("app.add_exception_handler(RequestValidationError, h)\n") == 1
