"""agent-registry ``on_behalf_of`` (C-73, reviewer C-67 LOW): its own tests. The gate lives here AND in
field-core's bind_on_behalf_of, so a mutant in one is not caught by tests that go through the other. Direct
calls, no service: each condition of the function is the only difference between a recorded value and None."""

from __future__ import annotations

import pytest
from starlette.datastructures import Headers

from agent_registry.api import ON_BEHALF_HEADER, on_behalf_of
from field_core import operator_auth as oa

KEY_SHAPED = oa.KEY_PREFIX + "Hn3Lq8ZrWb2Vt6Ck9Yp1Xs4Df7Gm0Ja5Ue2Ri8Oz3Ny"
UNBROKEN = "a" * 45


def auth(scopes=("bypass_operator_list",), authenticated=True):
    return oa.OperatorAuth(mode="enforce", operator_id="svc-renewer" if authenticated else None,
                           scopes=tuple(scopes))


def headers(*values):
    return Headers(raw=[(ON_BEHALF_HEADER.encode(), v.encode()) for v in values])


def test_the_header_name_is_the_documented_one():
    assert ON_BEHALF_HEADER == "x-field-operator-on-behalf-of"


def test_an_authenticated_bypass_caller_naming_one_printable_id_is_recorded():
    assert on_behalf_of(headers("don"), auth()) == "don"
    assert on_behalf_of(headers("Don.Hagell@ssl-1"), auth()) == "Don.Hagell@ssl-1"


@pytest.mark.parametrize("who, a", [
    ("an unauthenticated caller", auth(authenticated=False)),
    ("an identity without the scope", auth(scopes=("kill", "revive"))),
    ("an identity with no scopes", auth(scopes=())),
    ("an identity holding * (does not imply bypass_operator_list)", auth(scopes=("*",))),
])
def test_only_an_authenticated_identity_holding_bypass_operator_list_may_name_a_human(who, a):
    assert on_behalf_of(headers("don"), a) is None, who


def test_an_unauthenticated_caller_with_the_scope_listed_is_still_ignored():
    """Scopes alone are not an identity: the first condition is `authenticated`, not the scope."""
    a = oa.OperatorAuth(mode="log_only", operator_id=None, claimed="svc", scopes=("bypass_operator_list",))
    assert on_behalf_of(headers("don"), a) is None


@pytest.mark.parametrize("values", [(), ("don", "alice"), ("don", "don")])
def test_zero_or_several_header_values_record_nothing(values):
    assert on_behalf_of(headers(*values), auth()) is None


@pytest.mark.parametrize("value", ["", "bad id", "a/b", "x" * 65, KEY_SHAPED, UNBROKEN, "don\x00"])
def test_a_value_that_is_not_a_printable_operator_id_records_nothing(value):
    try:
        h = headers(value)
    except (UnicodeError, ValueError):
        pytest.skip("not representable as a header")
    assert on_behalf_of(h, auth()) is None


def test_a_plain_mapping_of_headers_is_read_case_insensitively_and_rejects_none_or_two():
    assert on_behalf_of({"X-Field-Operator-On-Behalf-Of": "don"}, auth()) == "don"
    assert on_behalf_of({"other": "don"}, auth()) is None
    assert on_behalf_of({}, auth()) is None
    assert on_behalf_of({"X-Field-Operator-On-Behalf-Of": "bad id"}, auth()) is None
