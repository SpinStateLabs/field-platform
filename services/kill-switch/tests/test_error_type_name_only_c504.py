"""C-504: a transport failure reaches the caller as a class name, never as its text.

A transport exception's message carries what it tried: a URL, a proxy, an address.
The registry client wraps that text (``RegistryUnreachableError(str(exc))``), and
the endpoint call and the drill's restore step catch it too. Every reply, ledger
note and log line these routes write must hold the name of the failure and none of
its text. The canary below is a made-up marker put into the underlying exception;
the reply, every ledger event and the captured log must show neither the marker nor
any slice of it. Test stubs only: no network, no real host."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from field_core.clients import LedgerClient, RegistryClient, RegistryUnreachableError
from kill_switch.api import create_app as create_kill_app

from test_endpoint_and_liveness import ALLOWED, OP, FakeEndpoint, Stack

# Built from parts so the marker is not a literal in the tree.
CANARY = "tkv-" + "c504" + "-canary" + "-" + "host" + "-0f3a9c.invalid"
SLICES = sorted({CANARY[i:i + 8] for i in range(0, len(CANARY) - 7, 4)} | {CANARY})


def _boom() -> Exception:
    return ConnectionError(f"HTTPSConnectionPool(host='{CANARY}', port=443): Max retries exceeded")


def _wrapped() -> RegistryUnreachableError:
    """What field_core's RegistryClient raises on a transport failure."""
    boom = _boom()
    err = RegistryUnreachableError(str(boom))
    err.__cause__ = boom
    return err


class FailingRegistry:
    """The real registry client, with chosen calls made to fail the way a dead
    transport fails. ``skip`` lets the first n calls of that method through."""

    def __init__(self, real: RegistryClient, fail: set[str], skip: dict[str, int] | None = None):
        self._real, self._fail, self._skip = real, fail, dict(skip or {})

    def _maybe(self, name: str) -> None:
        if name in self._fail:
            if self._skip.get(name, 0) > 0:
                self._skip[name] -= 1
                return
            raise _wrapped()

    def get_agent(self, agent_id):
        self._maybe("get_agent")
        return self._real.get_agent(agent_id)

    def list_agents(self, **kw):
        self._maybe("list_agents")
        return self._real.list_agents(**kw)

    def set_status(self, agent_id, status, **kw):
        self._maybe("set_status")
        return self._real.set_status(agent_id, status, **kw)


def _stack(tmp_path, fail, skip=None):
    return Stack(tmp_path, registry_wrapper=lambda real: FailingRegistry(real, fail, skip))


def _clean(*texts: str) -> None:
    for text in texts:
        for marker in SLICES:
            assert marker not in text, f"transport text reached the output: slice of length {len(marker)}"


def _everything_written(stack, response, caplog) -> str:
    events = " ".join(str(e) for e in stack.events())
    logs = " ".join(r.getMessage() for r in caplog.records)
    return response.text + events + logs


def test_the_canary_is_not_hidden_by_the_test_double(tmp_path):
    """The marker is really in the exception text the double raises."""
    assert CANARY in str(_wrapped()) and CANARY in str(_wrapped().__cause__)


@pytest.mark.parametrize(
    "route, call, fail, skip",
    [
        ("kill: agent lookup", lambda s: s.kill.post("/kill/a1", json=OP), {"get_agent"}, None),
        ("kill: status write", lambda s: s.kill.post("/kill/a1", json=OP), {"set_status"}, None),
        ("kill domain: list", lambda s: s.kill.post("/kill/domain/finance", json=OP), {"list_agents"}, None),
        ("revive: agent lookup", lambda s: s.kill.post("/revive/a1", json=OP), {"get_agent"}, None),
        ("revive: status write", lambda s: s.kill.post("/revive/a1", json=OP), {"set_status"}, None),
        ("liveness: list", lambda s: s.kill.get("/liveness"), {"list_agents"}, None),
    ],
)
def test_a_registry_transport_failure_is_a_502_with_the_class_name_only(
        tmp_path, caplog, route, call, fail, skip):
    s = _stack(tmp_path, fail, skip)
    s.register("a1")
    with caplog.at_level(logging.DEBUG):
        r = call(s)
    assert r.status_code == 502, route
    detail = r.json()["detail"]
    assert detail.startswith("registry unreachable"), route
    assert "ConnectionError" in detail, route  # the name of what failed is kept
    _clean(_everything_written(s, r, caplog))


def test_a_registry_answer_without_a_wrapped_failure_keeps_its_status_text(tmp_path):
    """No cause: the client's own answer text (status only, field_core's
    upstream_error) is still said, so ``registry returned 503`` stays useful."""

    class Answers(FailingRegistry):
        def get_agent(self, agent_id):
            raise RegistryUnreachableError("registry returned 503")

    s = Stack(tmp_path, registry_wrapper=lambda real: Answers(real, set()))
    s.register("a1")
    r = s.kill.post("/kill/a1", json=OP)
    assert r.status_code == 502
    assert "registry returned 503" in r.json()["detail"]


def test_a_failed_halt_signal_reports_the_class_name_not_the_message(tmp_path, monkeypatch, caplog):
    """The kill itself works; the endpoint call raised: the report and the ledger
    note carry ``ConnectionError`` only."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    s = Stack(tmp_path)
    s.endpoint._handler = lambda m, u: _boom()
    s.with_endpoint("invoicing-agent", f"http://{ALLOWED}/hooks/halt")
    with caplog.at_level(logging.DEBUG):
        r = s.kill.post("/kill/invoicing-agent", json=OP)
    assert r.status_code == 200
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "failed" and result["reason"] == "transport_error"
    assert result["error"] == "ConnectionError"
    _clean(_everything_written(s, r, caplog))


def test_a_failed_drill_restore_notes_the_class_name_only(tmp_path, caplog):
    """The drill's restore step fails after the kill went through: the ledger
    note says what failed, by name."""
    s = _stack(tmp_path, {"set_status"}, {"set_status": 1})  # the kill passes, the restore fails
    s.register("a1")
    with caplog.at_level(logging.DEBUG):
        r = s.kill.post("/drill/a1", json=OP)
    notes = s.events("kill.drill.restore_failed")
    assert len(notes) == 1, r.text
    assert notes[0]["payload"]["error"] == "ConnectionError"
    _clean(_everything_written(s, r, caplog))
