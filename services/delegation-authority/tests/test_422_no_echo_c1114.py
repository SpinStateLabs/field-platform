"""The delegation service's 422s never repeat the caller's text (C-1114, reviewer C-1109 F-C1109-1).

FastAPI's default 422 puts the rejected input back in the reply. The service installs the field-core handler, as
the crosswalk does (C-1018). The marker is made up."""

import pytest
from fastapi.testclient import TestClient

from delegation_authority.api import create_app
from delegation_authority.store import TokenStore

MARK = "MADE-UP-MARKER-0123456789"


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=TokenStore(tmp_path / "tokens.sqlite3")))


@pytest.mark.parametrize("body", [
    MARK,                       # a JSON string where an object is required: the default reply repeats it
    {MARK: "x"},                # an unexpected field name
    {"agent_id": [MARK]},       # a wrong type
])
def test_a_tokens_422_does_not_repeat_what_was_sent(client, body):
    r = client.post("/tokens", json=body)
    assert r.status_code == 422
    assert MARK not in r.text, r.text
