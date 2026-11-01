"""The crosswalk service's 422s never repeat the caller's text (C-1018; reviewer C-841 F-C841-1, C-986, C-1004).

`signer: str` (api.py) makes pydantic refuse a list or a dict before the evidence-pack guard runs, and FastAPI's
default reply put the offending value in an `input` field. The service installs the field-core handler. Every value
here is a made-up marker."""

import pytest
from fastapi.testclient import TestClient

from compliance_crosswalk.api import create_app

MARK = "MADE-UP-MARKER-0123456789"


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.mark.parametrize("path,body", [
    ("/pack", {"signer": [MARK], "manifest": {}}),
    ("/pack", {"signer": {"k": MARK}, "manifest": {}}),
    ("/pack", {"signer": "Ann", "manifest": MARK}),
    ("/pack", {"signer": "Ann", "manifest": {}, "agent_id": [MARK]}),
    ("/pack", {"manifest": {"k": MARK}}),                       # missing signer: the default repeats the whole body
    ("/pack", {"signer": "Ann", "manifest": {}, MARK: "x"}),    # an unexpected field name
])
def test_a_pack_422_does_not_repeat_what_was_sent(client, path, body):
    r = client.post(path, json=body)
    assert r.status_code == 422
    assert MARK not in r.text, r.text


def test_the_signer_gate_still_answers_422_over_http(client):
    """The handler changes what is repeated, not which requests are refused."""
    r = client.post("/pack", json={"signer": "", "manifest": {}})
    assert r.status_code == 422


@pytest.mark.parametrize("path", ["/pack", "/crosswalk"])
def test_a_caller_chosen_dict_key_under_sources_is_not_echoed(client, path):
    """C-1034 F-C1034-1: `sources.ledger_event_types` is a `dict[str, int]`; a bad value there put the KEY in `loc`."""
    body = {"sources": {"ledger_event_types": {MARK: "not-an-int"}}}
    if path == "/pack":
        body.update({"signer": "Ann", "manifest": {}})
    else:
        body.update({"manifest": {}})
    r = client.post(path, json=body)
    assert r.status_code == 422
    assert MARK not in r.text, r.text
