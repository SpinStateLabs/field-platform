"""C2: ``LedgerClient.retention_check()`` — a check that did not run is never "ok".

Any transport error or non-200 is ``LedgerUnreachableError`` (the lifecycle
sweep turns that into an ``unavailable`` finding, never into a clean sweep).
"""

from __future__ import annotations

import pytest

from field_core.clients import LedgerClient, LedgerUnreachableError


class _Resp:
    def __init__(self, status_code: int, body=None, text: str = ""):
        self.status_code = status_code
        self._body = body
        self.text = text

    def json(self):
        return self._body


class _Http:
    def __init__(self, resp=None, exc: Exception | None = None):
        self.resp, self.exc, self.urls = resp, exc, []

    def get(self, url, **kwargs):
        self.urls.append(url)
        if self.exc is not None:
            raise self.exc
        return self.resp


def test_retention_check_returns_the_body_on_200_from_the_base_url():
    body = {"ok": False, "status": "violation", "offending": [{"agent_id": "a", "retention_days": 2555}]}
    http = _Http(_Resp(200, body))
    assert LedgerClient(client=http, base_url="http://ledger:8002/").retention_check() == body
    assert http.urls == ["http://ledger:8002/retention/check"]


@pytest.mark.parametrize("status", [401, 404, 500, 503])
def test_retention_check_non_200_is_unreachable_not_ok(status):
    http = _Http(_Resp(status, {"ok": True, "status": "ok"}, text="x" * 1000))
    with pytest.raises(LedgerUnreachableError) as exc:
        LedgerClient(client=http, base_url="http://t").retention_check()
    assert f"returned {status}" in str(exc.value) and len(str(exc.value)) < 300


def test_retention_check_transport_error_is_unreachable():
    with pytest.raises(LedgerUnreachableError, match="connection refused"):
        LedgerClient(client=_Http(exc=OSError("connection refused")), base_url="http://t").retention_check()


# --- X4: LedgerClient.events() (the lifecycle witness finding reads anchor.remote) ----------


def test_events_returns_the_list_and_passes_the_event_type():
    body = [{"event_type": "anchor.remote", "payload": {"estate": "fly"}}]
    http = _Http(_Resp(200, body))
    seen = {}
    real_get = http.get

    def get(url, **kwargs):
        seen.update(kwargs)
        return real_get(url, **kwargs)

    http.get = get
    assert LedgerClient(client=http, base_url="http://ledger:8002/").events(event_type="anchor.remote") == body
    assert http.urls == ["http://ledger:8002/events"] and seen["params"] == {"event_type": "anchor.remote"}


@pytest.mark.parametrize("resp", [_Resp(401, [], text="unauthorized"), _Resp(503, []), _Resp(200, {"detail": "x"})])
def test_events_that_did_not_come_back_as_a_list_are_unreachable_never_empty(resp):
    with pytest.raises(LedgerUnreachableError):
        LedgerClient(client=_Http(resp), base_url="http://t").events(event_type="anchor.remote")


def test_events_transport_error_is_unreachable():
    with pytest.raises(LedgerUnreachableError, match="connection refused"):
        LedgerClient(client=_Http(exc=OSError("connection refused")), base_url="http://t").events()
