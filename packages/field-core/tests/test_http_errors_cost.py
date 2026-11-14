"""S9-5: the 422 handler computes the known-name set once per request and bounds the reply.

`redacted_loc` called `_known_names(app)` (a walk of every route, parameter group and reachable model) once per error, on the
event loop, and the reply carried every error: a body with N invalid list items cost N walks and an N-item answer. Measured
before the fix (61 routes, one bad list item repeated; this machine): 500 items 0.37 s and 66 KB, 2,000 items 1.6 s and 265 KB, linear in N.
Now the set is computed once per request (an optional `known` argument keeps `redacted_loc(app, err)` working for the services
that call it from their own handler) and the reply holds the first MAX_ERRORS errors plus one final
`{"type": "too_many_errors", "loc": [], "msg": "<N> more errors"}` item. Redaction itself is unchanged."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from field_core import http_errors
from field_core.http_errors import MAX_ERRORS, REDACTED_NAME, install_validation_handler, redacted_loc


class Item(BaseModel):
    n: int


class Strict(BaseModel):
    model_config = {"extra": "forbid"}
    n: int


class Body(BaseModel):
    items: list[Strict]


def make_app():
    app = FastAPI()
    install_validation_handler(app)

    @app.post("/x")
    def x(b: Body):
        return 1
    return app


def bad(n):
    return {"items": [{"n": "bad"}] * n}


def test_one_known_name_walk_for_a_500_error_request(monkeypatch):
    calls = []
    real = http_errors._known_names
    monkeypatch.setattr(http_errors, "_known_names", lambda app: calls.append(1) or real(app))
    r = TestClient(make_app()).post("/x", json=bad(500))
    assert r.status_code == 422
    assert len(calls) == 1


def test_the_reply_is_bounded_with_a_final_count_item():
    detail = TestClient(make_app()).post("/x", json=bad(500)).json()["detail"]
    assert len(detail) == MAX_ERRORS + 1
    assert detail[-1] == {"type": "too_many_errors", "loc": [], "msg": f"{500 - MAX_ERRORS} more errors"}
    assert all(e["type"] == "int_parsing" for e in detail[:-1])


def test_exactly_the_cap_is_not_truncated_and_one_over_is():
    c = TestClient(make_app())
    exact = c.post("/x", json=bad(MAX_ERRORS)).json()["detail"]
    assert len(exact) == MAX_ERRORS and all(e["type"] == "int_parsing" for e in exact)
    over = c.post("/x", json=bad(MAX_ERRORS + 1)).json()["detail"]
    assert len(over) == MAX_ERRORS + 1 and over[-1]["msg"] == "1 more errors"


def test_the_first_errors_keep_their_order_and_their_redacted_loc():
    detail = TestClient(make_app()).post("/x", json={"items": [{"n": "bad"}, {"n": 1, "secret_key_name_x": 1}]}).json()["detail"]
    assert detail[0]["loc"] == ["body", "items", 0, "n"]
    assert detail[1]["loc"] == ["body", "items", 1, REDACTED_NAME]


def test_redacted_loc_still_works_without_a_known_argument_and_with_one():
    app = make_app()
    err = {"type": "int_parsing", "loc": ("body", "items", 0, "n")}
    assert redacted_loc(app, err) == ["body", "items", 0, "n"]
    assert redacted_loc(app, err, known=http_errors._known_names(app)) == ["body", "items", 0, "n"]
    assert redacted_loc(app, {"type": "int_parsing", "loc": ("x", "y")}, known={"x"}) == ["x", REDACTED_NAME]


def test_a_small_error_list_is_unchanged_and_has_no_count_item():
    detail = TestClient(make_app()).post("/x", json=bad(3)).json()["detail"]
    assert len(detail) == 3 and all(e["type"] == "int_parsing" for e in detail)
