"""C-1014 port, item (a) (reviewer F-C941-2): the reason is model text that is stored for good on the ledger. Invisible
format characters (zero-width, bidi overrides) are dropped, control characters become a space, and a reason that is blank
after cleaning is refused before any network call and before it uses a rate-limit slot. Mutants: Z1 no cleaning of the
stored reason; Z2 blank-after-cleaning accepted; Z3 the blank check runs after the rate limiter."""
import json

import pytest

from test_tier2 import REGISTER, two, write_disp   # noqa: F401  (fixtures and helpers of the Tier 2 suite)


def reason_stored(ledger):
    return json.loads(ledger.requests[0]["body"])["payload"]["reason"]


@pytest.mark.parametrize("raw,clean", [
    ("plain reason", "plain reason"),
    ("ab​cd", "abcd"),                       # zero-width space
    ("a‮b‬c", "abc"),                   # bidi override and pop
    ("x⁦y⁩z﻿", "xyz"),             # bidi isolates, byte-order mark
    ("line1\nline2\tend\x00", "line1 line2 end"),  # control characters become one space each, ends are trimmed
    ("  padded  ", "padded"),
])
def test_the_stored_reason_is_cleaned(two, raw, clean):
    target, ledger = two
    target.routes[("POST", "/agents")] = (201, {}, {})
    r = write_disp(target, ledger).call("agent_registry_create_agent", {**REGISTER, "reason": raw})
    assert r["status"] == "ok" and reason_stored(ledger) == clean


@pytest.mark.parametrize("raw", ["   ", "​​", "‮", "\n\t", "\x00﻿ ⁦"])
def test_a_reason_that_is_blank_after_cleaning_is_refused_before_any_request(two, raw):
    target, ledger = two
    r = write_disp(target, ledger).call("agent_registry_create_agent", {**REGISTER, "reason": raw})
    assert r == {"status": "error", "error": "arguments refused"} and not target.requests and not ledger.requests


def test_a_refused_blank_reason_does_not_use_a_rate_limit_slot(two):
    target, ledger = two
    target.routes[("POST", "/agents")] = (201, {}, {})
    d = write_disp(target, ledger, rate=1)
    assert d.call("agent_registry_create_agent", {**REGISTER, "reason": "​"})["error"] == "arguments refused"
    assert d.call("agent_registry_create_agent", REGISTER)["status"] == "ok"      # the one slot is still free
