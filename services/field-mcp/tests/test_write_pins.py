"""C-1014 port, item (b) (reviewer F-C869-4): controls that held on the head but had no failing test. Mutants: M7b the write
flag accepts true/yes/whitespace; L7 the perimeter key is dropped from a write that carries the operator pair; T6 the pair
is sent when only one half is configured; T9 reason maximum raised; T10 reason minimum dropped; A6 client-name bound raised;
R2 window edge off by one comparison; R5 wall clock instead of the monotonic clock."""
import json
import time

import pytest

from conftest import KEY
from field_mcp import audit as au
from field_mcp.config import ConfigError, load
from field_mcp.tools import REASON

from test_tier2 import OP, OPKEY, REGISTER, two, write_disp   # noqa: F401

W_ENV = {"FFMCP_SEALED_LEDGER_URL": "http://127.0.0.1:1"}


@pytest.mark.parametrize("value", ["true", "yes", "TRUE", "on", " 1", "1 ", "01", "0", "", "2", "1\n"])
def test_only_the_exact_text_1_enables_the_write_process(value):
    with pytest.raises(ConfigError, match="FFMCP_ENABLE_WRITES"):
        load(2, {**W_ENV, "FFMCP_ENABLE_WRITES": value})
    assert load(2, {**W_ENV, "FFMCP_ENABLE_WRITES": "1"}).tier == 2


def test_a_write_carries_the_perimeter_key_with_and_without_the_operator_pair(two):
    target, ledger = two
    target.routes[("POST", "/agents")] = (201, {}, {})
    target.routes[("PATCH", "/agents/a1")] = (200, {}, {})
    d = write_disp(target, ledger)
    d.call("agent_registry_create_agent", REGISTER)                                    # carries the operator pair
    d.call("agent_registry_rename_agent", {"agent_id": "a1", "body": {"name": "B"}, "reason": "rename"})   # does not
    posted, patched = target.requests[0], target.requests[1]
    assert "x-field-operator" in posted["headers"] and "x-field-operator" not in patched["headers"]
    assert posted["headers"]["x-field-auth"] == KEY and patched["headers"]["x-field-auth"] == KEY
    assert all(r["headers"]["x-field-auth"] == KEY for r in ledger.requests)


@pytest.mark.parametrize("operator,key", [(OP, ""), ("", OPKEY), ("", "")])
def test_the_operator_pair_is_never_half_sent(two, operator, key):
    target, ledger = two
    target.routes[("POST", "/agents")] = (201, {}, {})
    write_disp(target, ledger, operator=operator, operator_key=key).call("agent_registry_create_agent", REGISTER)
    h = target.requests[0]["headers"]
    assert "x-field-operator" not in h and "x-field-operator-key" not in h


def test_both_halves_present_send_both(two):
    target, ledger = two
    target.routes[("POST", "/agents")] = (201, {}, {})
    write_disp(target, ledger).call("agent_registry_create_agent", REGISTER)
    h = target.requests[0]["headers"]
    assert h["x-field-operator"] == OP and h["x-field-operator-key"] == OPKEY


def test_reason_length_bounds_are_one_and_three_hundred(two):
    target, ledger = two
    target.routes[("POST", "/agents")] = (201, {}, {})
    assert (REASON["minLength"], REASON["maxLength"]) == (1, 300)
    d = write_disp(target, ledger)
    assert d.call("agent_registry_create_agent", {**REGISTER, "reason": "r" * 300})["status"] == "ok"
    before = len(target.requests)
    for bad in ("r" * 301, ""):
        assert d.call("agent_registry_create_agent", {**REGISTER, "reason": bad}) == {"status": "error", "error": "arguments refused"}
    assert len(target.requests) == before


def test_the_client_name_is_bounded_to_one_hundred_characters(two):
    target, ledger = two
    target.routes[("POST", "/agents")] = (201, {}, {})
    d = write_disp(target, ledger)
    d.audit.client_name = "n" * 500
    d.call("agent_registry_create_agent", REGISTER)
    assert json.loads(ledger.requests[0]["body"])["payload"]["client_name"] == "n" * 100


def test_the_rate_window_edge_is_exactly_sixty_seconds():
    now = {"t": 0.0}
    rl = au.RateLimiter(1, lambda: now["t"])
    assert rl.allow() is True
    now["t"] = 59.999
    assert rl.allow() is False          # still inside the window; a refused attempt is not recorded
    now["t"] = 60.0
    assert rl.allow() is True           # the hit at t=0 is exactly 60 s old: it has left the window


def test_the_limiter_uses_the_monotonic_clock_not_the_wall_clock():
    assert au.RateLimiter(1)._clock is time.monotonic
