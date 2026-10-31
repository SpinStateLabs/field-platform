"""A 422 that never repeats what the caller sent (C-1018; reviewer C-841 F-C841-1, C-986, C-1004).

FastAPI's default validation response carries an ``input`` field (and, for a missing field, the WHOLE body), and the
names of unexpected fields in ``loc``. A caller who pasted a credential into the wrong field gets it back, and any
proxy or log that keeps response bodies keeps it. ``install_validation_handler`` returns only the error type, the
location and the message. Every value here is a made-up marker."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, field_validator

from field_core import http_errors

MARK = "MADE-UP-MARKER-0123456789"


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signer: str
    count: int = 1
    note: str = Field(default="x", max_length=5)


class WithValidator(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _v(cls, v):
        raise ValueError(f"bad name {v}")


def make(install=True) -> TestClient:
    app = FastAPI()
    if install:
        http_errors.install_validation_handler(app)

    @app.post("/b")
    def b(body: Body):
        return {"ok": True}

    @app.post("/v")
    def v(body: WithValidator):
        return {"ok": True}

    @app.get("/q")
    def q(n: int):
        return {"n": n}

    return TestClient(app)


def test_the_default_handler_does_echo_which_is_why_this_exists():
    r = make(install=False).post("/b", json={"signer": [MARK]})
    assert MARK in r.text


@pytest.mark.parametrize("body", [
    {"signer": [MARK]},
    {"signer": {"k": MARK}},
    {"signer": 5, "count": MARK},
    {"signer": "ok", "note": MARK * 3},
    {"count": MARK},                      # a missing field: the default handler repeats the whole body
    {"signer": "ok", MARK: "x"},          # an unexpected field: its NAME is the caller's text too
])
def test_no_shape_of_422_repeats_the_callers_text(body):
    r = make().post("/b", json=body)
    assert r.status_code == 422
    assert MARK not in r.text, r.text


def test_the_reply_keeps_type_location_and_message():
    r = make().post("/b", json={"count": 1})
    errs = r.json()["detail"]
    assert errs and all(set(e) == {"type", "loc", "msg"} for e in errs)
    assert any(e["type"] == "missing" and e["loc"] == ["body", "signer"] for e in errs)


def test_a_query_parameter_error_is_covered_too():
    r = make().get("/q", params={"n": MARK})
    assert r.status_code == 422 and MARK not in r.text


def test_a_non_json_body_is_covered():
    r = make().post("/b", content=("{" + MARK).encode(), headers={"content-type": "application/json"})
    assert r.status_code == 422 and MARK not in r.text


def test_a_valid_request_is_untouched():
    assert make().post("/b", json={"signer": "Ann"}).status_code == 200


def test_a_custom_validator_message_is_not_passed_on():
    """`ValueError(f"... {v}")` in a validator puts the value in the pydantic message: the handler drops the message
    text of a value_error and keeps only a fixed phrase."""
    r = make().post("/v", json={"name": MARK})
    assert r.status_code == 422 and MARK not in r.text
    assert json.loads(r.text)["detail"][0]["type"] == "value_error"


def test_the_extra_field_name_is_replaced_not_dropped():
    r = make().post("/b", json={"signer": "ok", MARK: "x"})
    err = [e for e in r.json()["detail"] if e["type"] == "extra_forbidden"]
    assert err and err[0]["loc"][-1] == http_errors.REDACTED_NAME


# ------------------------------------------------------------ review C-1034: a caller-chosen dict key in `loc`

class Sources(BaseModel):
    types: dict[str, int] | None = None


class Outer(BaseModel):
    signer: str = "x"
    sources: Sources | None = None


class WithAssert(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _a(cls, v):
        assert False, f"never {v}"


def make2() -> TestClient:
    app = FastAPI()
    http_errors.install_validation_handler(app)

    @app.post("/d")
    def d(body: Outer):
        return {"ok": True}

    @app.post("/a")
    def a(body: WithAssert):
        return {"ok": True}

    @app.get("/q")
    def q(n: int):
        return {"n": n}

    return TestClient(app)


def test_a_caller_chosen_dict_key_is_not_echoed_in_loc():
    r = make2().post("/d", json={"sources": {"types": {MARK: "notint"}}})
    assert r.status_code == 422 and MARK not in r.text, r.text
    locs = [e["loc"] for e in r.json()["detail"]]
    assert ["body", "sources", "types", http_errors.REDACTED_NAME] in locs


def test_model_field_and_parameter_names_stay_in_loc():
    c = make2()
    assert [e["loc"] for e in c.post("/d", json={"signer": 5}).json()["detail"]] == [["body", "signer"]]
    assert [e["loc"] for e in c.get("/q", params={"n": "x"}).json()["detail"]] == [["query", "n"]]
    nested = c.post("/d", json={"sources": {"types": 5}}).json()["detail"]
    assert [e["loc"] for e in nested] == [["body", "sources", "types"]]


def test_an_assertion_message_is_not_passed_on():
    r = make2().post("/a", json={"name": MARK})
    assert r.status_code == 422 and MARK not in r.text
    assert r.json()["detail"][0]["msg"] == http_errors.VALUE_ERROR_MESSAGE
