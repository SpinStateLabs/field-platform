"""`redacted_loc` (C-1128): the location of a validation error without a name the caller chose.

A service that keeps its own 422 handler, to keep the messages its validators write, calls this so a field NAME the
caller sent is not repeated. The handler in `install_validation_handler` uses the same function, so the two cannot
drift. Every value here is a made-up marker."""

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from field_core import http_errors

MARK = "MADE-UP-MARKER-0123456789"


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signer: str
    count: int = 1
    tags: dict[str, int] = {}


def make() -> TestClient:
    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def _own(request, exc):   # a service's own handler: it keeps whatever else it keeps
        return JSONResponse({"locs": [http_errors.redacted_loc(request.app, e) for e in exc.errors()]}, status_code=422)

    @app.post("/b")
    def b(body: Body):
        return {"ok": True}

    @app.get("/q")
    def q(n: int):
        return {"n": n}

    return TestClient(app)


def test_a_field_name_the_caller_sent_is_replaced():
    r = make().post("/b", json={"signer": "ok", MARK: "x"})
    assert r.status_code == 422 and MARK not in r.text
    assert r.json()["locs"] == [["body", http_errors.REDACTED_NAME]]


def test_a_dict_key_the_caller_chose_is_replaced_and_a_declared_name_is_kept():
    r = make().post("/b", json={"signer": {MARK: "x"}, "count": "no"})
    assert MARK not in r.text
    locs = r.json()["locs"]
    assert ["body", "count"] in locs and ["body", "signer"] in locs


def test_a_key_of_a_dict_field_is_caller_text_and_is_replaced():
    """The key sits in ``loc`` (``body, tags, <key>``) when its value is wrong: only the name-set step removes it."""
    r = make().post("/b", json={"signer": "ok", "tags": {MARK: "notanint"}})
    assert r.status_code == 422 and MARK not in r.text
    assert r.json()["locs"] == [["body", "tags", http_errors.REDACTED_NAME]]


def test_the_roots_and_a_declared_parameter_are_kept():
    r = make().get("/q?n=notanumber")
    assert r.json()["locs"] == [["query", "n"]]


@pytest.mark.parametrize("err, expected", [
    ({"type": "extra_forbidden", "loc": ("body", "anything")}, ["body", http_errors.REDACTED_NAME]),
    ({"type": "missing", "loc": ("body", "signer")}, ["body", "signer"]),
    ({"type": "missing", "loc": ("body", 3, "count")}, ["body", 3, "count"]),    # an index is not caller text
    ({"type": "extra_forbidden", "loc": ()}, []),
    # an unexpected key that happens to equal a declared field name is still caller text: the extra_forbidden branch
    # redacts it even though the name-set step would keep it
    ({"type": "extra_forbidden", "loc": ("body", "signer")}, ["body", http_errors.REDACTED_NAME]),
])
def test_one_error_at_a_time(err, expected):
    app = make().app
    assert http_errors.redacted_loc(app, err) == expected
