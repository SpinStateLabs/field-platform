"""spend-governor's 422s never repeat the caller's text (C-1114; reviewer C-1109 F-C1109-1).

FastAPI's default 422 puts the rejected input back in an `input` field, and the field-core handler that stops that
(C-1018) was installed in one service only. Every value here is a made-up marker."""

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import GovernorStore

MARK = "MADE-UP-MARKER-0123456789"


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=GovernorStore(tmp_path / "s.sqlite3")))


@pytest.mark.parametrize("path,body", [
    ("/spend", MARK),                      # a JSON string where an object belongs
    ("/spend", {MARK: "x"}),                # an unexpected or missing field
    ("/spend", {"a": [MARK], "b": {"k": MARK}}),
    ("/usage", MARK),                      # a JSON string where an object belongs
    ("/usage", {MARK: "x"}),                # an unexpected or missing field
    ("/usage", {"a": [MARK], "b": {"k": MARK}}),
])
def test_a_422_does_not_repeat_what_was_sent(client, path, body):
    r = client.post(path, json=body)
    assert r.status_code == 422
    assert MARK not in r.text, r.text
