"""Backlog B16: an unreachable registry is still a BLOCK (fail closed), but under its own clause
``R.registry_unreachable``, never ``R.unregistered``. ``R.unregistered`` stays for what it says: the registry
answered that there is no such agent. A dead pooled connection on the registry read is retried exactly once, so the
one-off race that made an active agent look unregistered no longer decides a verdict. Every value is made up."""
from __future__ import annotations

import httpx
import pytest

from field_core.conformance import CLAUSES
from tests.conftest import AGENT_ID
from tests.test_fail_closed_pins_c168 import Http, check, engine

STALE = [httpx.RemoteProtocolError("Server disconnected without sending a response."),
         httpx.ReadError("[Errno 104] Connection reset by peer"),
         httpx.WriteError("[Errno 32] Broken pipe")]


class Flaky:
    """An httpx-like client whose GETs raise the given errors in order, then delegate to ``then``."""

    def __init__(self, errors, then=None):
        self.errors, self.then, self.gets = list(errors), then, 0

    def get(self, url, **kw):
        self.gets += 1
        if self.errors:
            raise self.errors.pop(0)
        return self.then.get(url, **kw)


def active(stack):
    return {"agent_id": AGENT_ID, "status": "active", "manifest_ref": str(stack.manifest_path)}


def test_the_clause_is_registered_and_distinct():
    assert "R.registry_unreachable" in CLAUSES and "R.unregistered" in CLAUSES
    assert CLAUSES["R.registry_unreachable"] != CLAUSES["R.unregistered"]


@pytest.mark.parametrize("exc", [*STALE, httpx.ConnectError("refused"), httpx.ReadTimeout("slow")],
                         ids=["remote-protocol", "read-reset", "write-pipe", "connect", "timeout"])
def test_a_registry_that_cannot_be_reached_is_block_registry_unreachable(stack, exc):
    token = stack.mint_token()
    stack.set_cap()
    engine(stack).registry._client = Flaky([exc, exc])           # every attempt fails
    v = check(stack, token)
    assert v["decision"] == "BLOCK" and v["clause_id"] == "R.registry_unreachable", v
    assert "registry unreachable" in " ".join(v["reasons"])


@pytest.mark.parametrize("status", [500, 502, 503])
def test_an_unusable_registry_answer_is_block_registry_unreachable(stack, status):
    token = stack.mint_token()
    stack.set_cap()
    engine(stack).registry._client = Http({("GET", "/agents/"): (status, active(stack))})
    v = check(stack, token)
    assert v["decision"] == "BLOCK" and v["clause_id"] == "R.registry_unreachable", v


def test_a_registry_body_that_is_not_an_agent_object_is_block_registry_unreachable(stack):
    token = stack.mint_token()
    stack.set_cap()
    engine(stack).registry._client = Http({("GET", "/agents/"): (200, ["not", "an", "object"])})
    v = check(stack, token)
    assert v["decision"] == "BLOCK" and v["clause_id"] == "R.registry_unreachable", v


def test_a_real_404_is_still_r_unregistered(stack):
    r = stack.sentinel.post("/check", json={"agent_id": "ghost-b16", "action": "anything", "token_id": "x"})
    v = r.json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "R.unregistered", v


@pytest.mark.parametrize("exc", STALE, ids=["remote-protocol", "read-reset", "write-pipe"])
def test_one_dead_pooled_connection_is_retried_once_and_the_check_goes_on(stack, exc):
    """The race of main 7e14f136: one registry read on a connection the server had just closed. It no longer
    decides the verdict: the read is sent once more and the check continues past the registry step."""
    token = stack.mint_token()
    stack.set_cap()
    good = Http({("GET", "/agents/"): (200, active(stack))})
    flaky = Flaky([exc], then=good)
    engine(stack).registry._client = flaky
    v = check(stack, token)
    assert flaky.gets == 2 and len(good.calls) == 1
    assert v["clause_id"] not in ("R.registry_unreachable", "R.unregistered"), v
    assert v["decision"] == "ALLOW", v


def test_a_timeout_is_not_retried(stack):
    token = stack.mint_token()
    stack.set_cap()
    good = Http({("GET", "/agents/"): (200, active(stack))})
    flaky = Flaky([httpx.ReadTimeout("slow")], then=good)
    engine(stack).registry._client = flaky
    v = check(stack, token)
    assert flaky.gets == 1 and good.calls == []
    assert v["decision"] == "BLOCK" and v["clause_id"] == "R.registry_unreachable"


def test_the_governor_status_read_is_retried_once_on_a_dead_connection(stack):
    token = stack.mint_token()
    stack.set_cap()
    real = engine(stack).governor._client
    flaky = Flaky([httpx.RemoteProtocolError("closed")], then=real)
    engine(stack).governor._client = flaky
    v = check(stack, token)
    assert flaky.gets == 2 and v["decision"] == "ALLOW", v
