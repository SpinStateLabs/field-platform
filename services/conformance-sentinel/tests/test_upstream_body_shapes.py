"""Scout S-2-22 (HIGH CARE: the policy enforcement point). The sentinel read upstream JSON bodies unchecked, so a 200 with
the wrong SHAPE raised out of `_decide` (a 500, no verdict, no ledgered record) or, worse, failed open:

* governor `/totals`: a body without `spent_cents` counted as 0 (`int(totals.get("spent_cents", 0))`), so the token spend
  ceiling PASSED, against the method's own docstring ("an unverifiable total BLOCKs");
* delegation `/introspect`: a list or null body raised AttributeError on `.get`; a token `scope` that is a bare string made
  `req.action not in token_scope` a SUBSTRING test;
* governor `/status`: a list body raised AttributeError on `.get("state")`.

Each is now a named BLOCK through POST /check, ledgered, with a fixed reason that never echoes the upstream body (C-503).
Enforce mode (the harness default). The well-formed bodies still pass: see the controls."""
from __future__ import annotations

import pytest

from tests.conftest import AGENT_ID, SCOPE
from tests.test_fail_closed_pins_c168 import OK_SPEND, Http, engine, intro, use_governor

MARK = "UPSTREAM-BODY-MARKER-7731"
SINCE = "2026-01-01T00:00:00+00:00"


def ceiling_intro(**over):
    return intro(max_spend_usd=100, issued_at=SINCE, **over)


def post(stack, token="tok", action="draft invoices"):
    """POST /check without the harness's status assertion: a 500 must show as a failure here."""
    return stack.sentinel.post("/check", json={"agent_id": AGENT_ID, "action": action, "token_id": token,
                                               "irreversible": False})


def ledgered(stack, clause_id):
    rows = stack.ledger.get("/events", params={"event_type": "conformance.block"}).json()
    return [r for r in rows if r["payload"].get("clause_id") == clause_id]


def govern(stack, *, totals=None, status=None, introspect=None):
    stack.mint_token()
    engine(stack).delegation._client = Http({("POST", "/introspect"): (200, introspect if introspect is not None
                                                                     else ceiling_intro())})
    routes = {("GET", "/status/"): (200, OK_SPEND if status is None else status), ("POST", "/spend"): (201, {})}
    if totals is not ...:
        routes[("GET", "/totals/")] = (200, totals)
    use_governor(stack, routes)


# ---- (a) the token spend ceiling: /totals -----------------------------------------------------------------------------

TOTALS_BAD = [
    {},
    {"currency": "USD"},                                    # the fail-open: no spent_cents
    {"spent_cents": 5},                                      # no currency (already refused: pinned)
    [],
    [{"currency": "USD", "spent_cents": 5}],
    "spent_cents=5",
    5,
    None,
    {"currency": "USD", "spent_cents": "x"},
    {"currency": "USD", "spent_cents": None},
    {"currency": "USD", "spent_cents": "5"},                 # a string is not a number, even a numeric one
    {"currency": "USD", "spent_cents": 5.5},
    {"currency": "USD", "spent_cents": float("nan")},
    {"currency": "USD", "spent_cents": True},                # a bool is not an amount
    {"currency": "USD", "spent_cents": [5]},
    {"currency": "USD", "spent_cents": {"a": 1}},
    {"currency": "USD", "spent_cents": -1},
    {"currency": "USD", "spent_cents": -10**9},
]


@pytest.mark.parametrize("totals", TOTALS_BAD, ids=[repr(t)[:40] for t in TOTALS_BAD])
def test_an_unusable_totals_body_blocks_a_token_with_a_ceiling(stack, totals):
    govern(stack, totals=totals)
    r = post(stack)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "E.spend_cap"
    assert len(ledgered(stack, "E.spend_cap")) == 1


@pytest.mark.parametrize("bad", [{"currency": "USD", "spent_cents": MARK}, {"currency": MARK, "spent_cents": 5}])
def test_the_reason_never_echoes_the_upstream_value_for_the_shapes_added_here(stack, bad):
    govern(stack, totals=bad)
    v = post(stack).json()
    if bad["currency"] == "USD":                             # the new branch: a fixed text
        assert MARK not in " ".join(v["reasons"])


def test_a_missing_spent_cents_is_not_counted_as_zero(stack):
    """The fail-open in one line: currency USD, no spent_cents, a 100-dollar ceiling: used to ALLOW."""
    govern(stack, totals={"currency": "USD"})
    v = post(stack).json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "E.spend_cap"


@pytest.mark.parametrize("spent,decision", [(0, "ALLOW"), (1, "ALLOW"), (9999, "ALLOW"), (10000, "BLOCK"), (10001, "BLOCK")])
def test_well_formed_totals_still_decide_on_the_ceiling(stack, spent, decision):
    govern(stack, totals={"currency": "USD", "spent_cents": spent})
    v = post(stack).json()
    assert v["decision"] == decision
    if decision == "BLOCK":
        assert v["clause_id"] == "E.spend_cap" and "ceiling reached" in " ".join(v["reasons"])


def test_a_usd_total_with_extra_fields_is_still_read(stack):
    govern(stack, totals={"currency": " usd ", "spent_cents": 3, "period": "daily", "extra": [1]})
    assert post(stack).json()["decision"] == "ALLOW"


# ---- (b) delegation /introspect -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("body", [[], [{"active": True}], None, "active", 5, True], ids=repr)
def test_an_introspect_body_that_is_not_an_object_blocks_d_token(stack, body):
    stack.mint_token()
    engine(stack).delegation._client = Http({("POST", "/introspect"): (200, body)})
    use_governor(stack, {("GET", "/status/"): (200, OK_SPEND), ("POST", "/spend"): (201, {})})
    r = post(stack)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "D.token"
    assert len(ledgered(stack, "D.token")) == 1


@pytest.mark.parametrize("scope", ["draft invoices", "draft invoices and more", "", "x", 5, {"draft invoices": 1}, True,
                                   [1, 2], ["draft invoices", 5], ["draft invoices", None], [["draft invoices"]]],
                         ids=repr)
def test_a_token_scope_that_is_not_a_list_of_strings_blocks_d_scope(stack, scope):
    govern(stack, totals={"currency": "USD", "spent_cents": 0}, introspect=intro(scope=scope))
    r = post(stack)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "D.scope"
    assert len(ledgered(stack, "D.scope")) == 1


def test_a_bare_string_scope_is_not_a_substring_test(stack):
    """'draft invoices' IS a substring of the string 'draft invoices and delete everything': it used to be in scope."""
    govern(stack, totals={"currency": "USD", "spent_cents": 0},
           introspect=intro(scope="draft invoices and delete everything"))
    v = post(stack).json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "D.scope"


@pytest.mark.parametrize("scope", [None, [], [""]])
def test_a_missing_or_empty_scope_is_still_the_ordinary_out_of_scope_block(stack, scope):
    body = intro()
    body["scope"] = scope
    govern(stack, totals={"currency": "USD", "spent_cents": 0}, introspect=body)
    v = post(stack).json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "D.scope"


def test_the_scope_reason_never_echoes_a_non_string_scope(stack):
    govern(stack, totals={"currency": "USD", "spent_cents": 0}, introspect=intro(scope=[MARK, 5]))
    assert MARK not in " ".join(post(stack).json()["reasons"])


def test_a_proper_list_scope_still_allows(stack):
    govern(stack, totals={"currency": "USD", "spent_cents": 0}, introspect=intro(scope=["draft invoices", "other"]))
    assert post(stack).json()["decision"] == "ALLOW"


# ---- (c) governor /status ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("body", [[], [OK_SPEND], "OK", 5, True], ids=repr)
def test_a_status_body_that_is_not_an_object_blocks_e_spend_cap(stack, body):
    token = stack.mint_token()                               # the real delegation service answers this one
    use_governor(stack, {("GET", "/status/"): (200, body), ("POST", "/spend"): (201, {})})
    r = post(stack, token)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "E.spend_cap"
    assert len(ledgered(stack, "E.spend_cap")) == 1


def test_a_status_object_still_decides_as_before(stack):
    token = stack.mint_token()                               # the real delegation service answers this one
    use_governor(stack, {("GET", "/status/"): (200, {"state": "OK"}), ("POST", "/spend"): (201, {})})
    assert post(stack, token).json()["decision"] == "ALLOW"
    use_governor(stack, {("GET", "/status/"): (200, {"state": "BLOCK", "detail": "cap reached"})})
    v = post(stack, token).json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "E.spend_cap" and "cap reached" in v["reasons"]


# ---- review conditions (F-R606-1, F-R606-2, F-R606-3): the helper's no-echo promise and its exception shape -------------

from conformance_sentinel.engine import _object_body  # noqa: E402


class _Resp:
    def __init__(self, value=None, exc=None):
        self._value, self._exc = value, exc

    def json(self):
        if self._exc is not None:
            raise self._exc
        return self._value


@pytest.mark.parametrize("value", [[MARK], MARK, 5, None, True, [{"a": MARK}]], ids=["list", "str", "int", "none", "bool", "nested"])
def test_a_body_that_is_not_an_object_raises_a_fixed_text_that_never_carries_it(value):
    with pytest.raises(ConnectionError) as e:
        _object_body(_Resp(value), "governor /status")
    assert MARK not in str(e.value) and str(e.value) == "governor /status answered with an unusable body (not an object)"


@pytest.mark.parametrize("exc", [ValueError(MARK), RuntimeError(MARK), KeyError(MARK), UnicodeDecodeError("utf-8", b"x", 0, 1, MARK)],
                         ids=lambda e: type(e).__name__)
def test_a_body_that_is_not_json_is_a_connection_error_without_the_cause_or_its_text(exc):
    with pytest.raises(ConnectionError) as e:
        _object_body(_Resp(exc=exc), "governor /totals")
    assert str(e.value) == "governor /totals answered with a body that is not JSON"
    assert MARK not in str(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__ is True      # `from None`: no chained original


def test_an_empty_object_is_an_object_and_is_returned_for_the_callers_own_checks():
    assert _object_body(_Resp({}), "x") == {}
    assert _object_body(_Resp({"a": 1}), "x") == {"a": 1}


def test_a_status_body_holding_the_marker_never_reaches_the_verdict_reasons(stack):
    token = stack.mint_token()
    use_governor(stack, {("GET", "/status/"): (200, [MARK]), ("POST", "/spend"): (201, {})})
    v = post(stack, token).json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "E.spend_cap"
    assert MARK not in " ".join(v["reasons"])


# ---- R-PR606-9bf0bc9 conditions C1 and C2 ----------------------------------------------------------------------------------

#: An object /status body without one of the governor's four exact states used to fall through to ALLOW.
STATUS_UNKNOWN_STATE = [
    {}, {"state": None}, {"state": 5}, {"state": ["BLOCK"]}, {"state": "block"}, {"state": "BLOCK "},
    {"state": "EXHAUSTED"}, {"stat": "BLOCK"}, {"ok": True, "service": "x"}, {"state": ""}, {"state": True},
    {"state": {"a": "BLOCK"}},
]


@pytest.mark.parametrize("body", STATUS_UNKNOWN_STATE, ids=repr)
def test_a_status_object_without_a_known_state_blocks_e_spend_cap_not_allow(stack, body):
    token = stack.mint_token()
    use_governor(stack, {("GET", "/status/"): (200, body), ("POST", "/spend"): (201, {})})
    v = post(stack, token).json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "E.spend_cap", v
    assert "missing or unknown state" in " ".join(v["reasons"])


@pytest.mark.parametrize("state,decision,clause", [("OK", "ALLOW", None), ("BLOCK", "BLOCK", "E.spend_cap"),
                                                     ("THROTTLED", "BLOCK", "E.rate_limit"),
                                                     ("ESCALATE", "ESCALATE", "E.spend_threshold")])
def test_each_of_the_four_governor_states_still_decides_as_before(stack, state, decision, clause):
    token = stack.mint_token()
    body = {"state": state, "detail": "d", "period": "daily", "retry_after_seconds": 3}
    use_governor(stack, {("GET", "/status/"): (200, body), ("POST", "/spend"): (201, {})})
    v = post(stack, token).json()
    assert (v["decision"], v["clause_id"]) == (decision, clause)      # the clause tells THROTTLED from an unknown state


@pytest.mark.parametrize("active", ["true", "false", "True", "0", "1", 1, 0, 1.0, [], {}, None, "yes"], ids=repr)
def test_an_introspect_active_that_is_not_a_json_true_blocks_d_token(stack, active):
    govern(stack, totals={"currency": "USD", "spent_cents": 0}, introspect=intro(active=active))
    v = post(stack).json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "D.token", v


def test_an_introspect_active_true_still_allows(stack):
    govern(stack, totals={"currency": "USD", "spent_cents": 0}, introspect=intro(active=True))
    assert post(stack).json()["decision"] == "ALLOW"


def test_an_inactive_token_keeps_its_specific_clause(stack):
    govern(stack, introspect=intro(active=False, status="revoked"))
    assert post(stack).json()["clause_id"] == "D.revoked"
