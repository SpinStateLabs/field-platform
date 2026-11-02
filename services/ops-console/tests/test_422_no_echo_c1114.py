"""The ops-console's 422s never repeat the caller's text (C-1114, reviewer C-1109 F-C1109-1).

FastAPI's default 422 puts the rejected input back in the reply. The console installs the field-core handler, as the
crosswalk does (C-1018). The marker is made up."""

import pytest
from fastapi.testclient import TestClient

from ops_console.api import create_app

MARK = "MADE-UP-MARKER-0123456789"


@pytest.mark.parametrize("body", [MARK, {MARK: "x"}])
def test_a_kill_422_does_not_repeat_what_was_sent(body):
    r = TestClient(create_app()).post("/api/agents/a1/kill", json=body)
    assert r.status_code == 422
    assert MARK not in r.text, r.text
