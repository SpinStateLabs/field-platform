"""ChainVerification's C2 keys (segments, archived_segments, verified_events,
break_segment) exist only for a segmented ledger.

A single-file chain must serialise to exactly the four pre-C2 keys on every
path — model_dump, model_dump_json, nested in another model, and a FastAPI
response_model — because the C1 export bundle pins that dict. Deleting the
wrap serializer fails every single-file assertion here.
"""

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from field_core.ledger import ChainVerification, make_event, verify_chain

FOUR = {"ok", "length", "first_break_index", "reason"}
EIGHT = FOUR | {"segments", "archived_segments", "verified_events", "break_segment"}

single = ChainVerification(ok=True, length=2)
segmented = ChainVerification(ok=True, length=12, segments=3, archived_segments=0, verified_events=12)
broken = ChainVerification(ok=False, length=7, first_break_index=6, reason="segment 2: …",
                           segments=3, archived_segments=0, verified_events=7, break_segment=2)


class Wrapper(BaseModel):
    verification: ChainVerification


def test_single_file_serialises_to_the_four_pre_c2_keys_everywhere():
    assert set(single.model_dump()) == FOUR
    assert set(json.loads(single.model_dump_json())) == FOUR
    assert set(single.model_dump(mode="json")) == FOUR
    assert set(Wrapper(verification=single).model_dump()["verification"]) == FOUR
    assert set(json.loads(Wrapper(verification=single).model_dump_json())["verification"]) == FOUR
    assert verify_chain([make_event("a")]).model_dump() == {
        "ok": True, "length": 1, "first_break_index": None, "reason": None,
    }


def test_segmented_keeps_all_eight_keys_and_round_trips():
    for v in (segmented, broken):
        assert set(v.model_dump()) == EIGHT
        assert set(json.loads(v.model_dump_json())) == EIGHT
        assert ChainVerification.model_validate(v.model_dump()) == v
        assert ChainVerification.model_validate_json(v.model_dump_json()) == v
    assert set(Wrapper(verification=broken).model_dump()["verification"]) == EIGHT


def test_fastapi_response_model_and_openapi_schema():
    app = FastAPI()

    @app.get("/single", response_model=ChainVerification)
    def _single():
        return single

    @app.get("/segmented", response_model=ChainVerification)
    def _segmented():
        return segmented

    client = TestClient(app)
    assert client.get("/single").json() == {"ok": True, "length": 2, "first_break_index": None,
                                            "reason": None}
    assert set(client.get("/segmented").json()) == EIGHT
    schema = client.get("/openapi.json").json()["components"]["schemas"]["ChainVerification"]
    assert set(schema["properties"]) == EIGHT  # the serializer does not erase the documented shape
