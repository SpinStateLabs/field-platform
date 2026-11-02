"""The sealed-ledger service's 422s never repeat the caller's text (C-1114, reviewer C-1109 F-C1109-1).

FastAPI's default 422 puts the rejected input back in the reply. The service installs the field-core handler, as the
crosswalk does (C-1018). The marker is made up."""

import pytest
from fastapi.testclient import TestClient
from sealed_ledger.store import LedgerStore
from sealed_ledger.api import create_app

MARK = "MADE-UP-MARKER-0123456789"


@pytest.mark.parametrize("body", [MARK, {MARK: "x"}])
def test_a_422_does_not_repeat_what_was_sent(tmp_path, body):
    r = TestClient(create_app(store=LedgerStore(tmp_path / 'e.jsonl'))).post("/events", json=body)
    assert r.status_code == 422
    assert MARK not in r.text, r.text
