"""force-gateway's 422s never repeat the caller's text (C-1114; reviewer C-1109 F-C1109-1).

FastAPI's default 422 puts the rejected input back in an `input` field, and the field-core handler that stops that
(C-1018) was installed in one service only. Every value here is a made-up marker."""

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import create_app
from force_gateway.store import GatewayStore

MARK = "MADE-UP-MARKER-0123456789"


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=GatewayStore(tmp_path / "g.sqlite3")))


@pytest.mark.parametrize("path,body", [
    ("/v1/messages", MARK),                      # a JSON string where an object belongs
])
def test_a_422_does_not_repeat_what_was_sent(client, path, body):
    r = client.post(path, json=body)
    assert r.status_code == 422
    assert MARK not in r.text, r.text
