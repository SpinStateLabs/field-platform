"""lifecycle-manager's 422s never repeat the caller's text (C-1114; reviewer C-1109 F-C1109-1).

FastAPI's default 422 puts the rejected input back in an `input` field, and the field-core handler that stops that
(C-1018) was installed in one service only. Every value here is a made-up marker."""

import pytest
from fastapi.testclient import TestClient

from lifecycle_manager.api import create_app

MARK = "MADE-UP-MARKER-0123456789"


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app())


@pytest.mark.parametrize("path,body", [
    ("/sweep", MARK),                      # a JSON string where an object belongs
    ("/sweep", {MARK: "x"}),                # an unexpected or missing field
    ("/sweep", {"a": [MARK], "b": {"k": MARK}}),
])
def test_a_422_does_not_repeat_what_was_sent(client, path, body):
    r = client.post(path, json=body)
    assert r.status_code == 422
    assert MARK not in r.text, r.text
