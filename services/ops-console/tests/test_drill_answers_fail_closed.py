"""The console follows the kill-switch's drill answers and stays fail-closed (kill-path hardening):

* a drill whose restore failed (500), whose flip was refused (409 / 412) or whose restore was skipped because a real
  kill overlapped it (409 with ``restore_skipped``) is an ERROR on the page, never ok;
* a 2xx answer whose shape the console does not recognise (no ``restored: true``) is an error too.
The kill-switch is a stub behind httpx.MockTransport that answers every POST with the given status and body.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from ops_console.api import ServiceClient, create_app

REPORT = {"agent_id": "invoicing-agent", "restored": False, "restored_status": "killed", "restore_skipped": True,
          "kill_confirmed_ms": 1.0, "heartbeat_confirmed_ms": 1.0, "total_ms": 2.0}
ACTION = {"operator": "CISO", "reason": "fail-closed"}


class _Dead:
    def get(self, *a, **k):
        raise ConnectionError("down")

    def post(self, *a, **k):
        raise ConnectionError("down")


def _console(status, body):
    ks = ServiceClient(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body)),
                                           base_url="http://ks"), base_url="http://ks")
    dead = ServiceClient(client=_Dead(), base_url="http://dead")
    return TestClient(create_app(killswitch=ks, registry=dead, ledger=dead, delegation=dead, governor=dead,
                                 sentinel=dead, lifecycle=dead, attest=dead, crosswalk=dead, federation=dead,
                                 replay=dead, gateway=dead))


@pytest.mark.parametrize("status", [409, 412, 500, 502])
def test_a_refused_or_failed_drill_is_an_error_on_the_single_route(status):
    r = _console(status, {"detail": REPORT}).post("/api/agents/invoicing-agent/drill", json=ACTION)
    assert r.status_code == status
    assert r.json()["detail"]["detail"]["restore_skipped"] is True        # the report still reaches the page


@pytest.mark.parametrize("status", [409, 412, 500, 502])
def test_a_refused_or_failed_drill_is_not_ok_in_the_bulk_route(status):
    body = _console(status, {"detail": REPORT}).post(
        "/api/agents/bulk", json={"action": "drill", "agent_ids": ["invoicing-agent"], **ACTION}).json()
    row = body["results"][0]
    assert row["ok"] is False and row["status"] == status
    assert body["all_ok"] is False and body["error_count"] == 1


@pytest.mark.parametrize("answer", [{}, {"restored": "yes"}, {"restored": False}, {"agent_id": "x"}, [], "ok", None],
                         ids=["empty", "string-flag", "false", "no-flag", "list", "string", "null"])
def test_a_2xx_drill_answer_the_console_does_not_recognise_is_an_error_everywhere(answer):
    c = _console(200, answer)
    single = c.post("/api/agents/invoicing-agent/drill", json=ACTION)
    assert single.status_code >= 400, "an unrecognised drill answer was shown as success"
    body = c.post("/api/agents/bulk", json={"action": "drill", "agent_ids": ["invoicing-agent"], **ACTION}).json()
    assert body["results"][0]["ok"] is False and body["all_ok"] is False


def test_a_restored_drill_is_ok_on_both_routes():
    good = {"agent_id": "invoicing-agent", "restored": True, "restored_status": "active", "kill_confirmed_ms": 1.0,
            "heartbeat_confirmed_ms": 1.0, "total_ms": 2.0}
    c = _console(200, good)
    assert c.post("/api/agents/invoicing-agent/drill", json=ACTION).status_code == 200
    body = c.post("/api/agents/bulk", json={"action": "drill", "agent_ids": ["invoicing-agent"], **ACTION}).json()
    assert body["all_ok"] is True
