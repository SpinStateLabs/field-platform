"""The gateway's 422s never repeat the caller's text (C-1114, reviewer C-1109 F-C1109-1).

FastAPI's default 422 puts the rejected input back in the reply. The service installs the field-core handler, as the
crosswalk does (C-1018). The marker is made up."""

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import create_app

MARK = "MADE-UP-MARKER-0123456789"


@pytest.mark.parametrize("body", [MARK, [MARK]])    # the route needs an object: the default reply repeats the body
def test_a_messages_422_does_not_repeat_what_was_sent(body):
    r = TestClient(create_app()).post("/v1/messages", json=body)
    assert r.status_code == 422
    assert MARK not in r.text, r.text
