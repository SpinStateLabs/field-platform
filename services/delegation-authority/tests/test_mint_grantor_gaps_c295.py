"""C-295 (reviewer C-293 F-C293-1/-2): two LOW gaps in the mint grantor rule.

F-C293-1: `check_granted_by` is ENFORCE-only by design. An AUTHENTICATED caller in LOG-ONLY (or OFF) who
names a foreign `granted_by` still mints (201); dropping the mode check from `check_granted_by`, leaving
`if not auth.authenticated: return False`, made that a 403 and survived 175 tests.

F-C293-2: an alias mint for an agent whose record has NO `manifest_ref` is a 403 end to end (the agent
bounds the alias grant, and a record without a manifest names nobody); `check_explicitly_listed`'s
`no_ref` branch was pinned only in field-core.
"""

from __future__ import annotations

import pytest

from field_core import operator_auth as oa
from test_machine_verifier_reach import (ALIAS, CANARY, FORBIDDEN, KEY_DON, KEY_PLAIN, KEY_VER, PLAIN_ALIAS,
                                         VERIFIER, hdr, mint, mint_events, spine, tokens, _clean)  # noqa: F401

NO_REF = "agent-without-manifest"
FOREIGN = ["Somebody Else", "Don Hagell", ALIAS]                  # a stranger, another's alias, the verifier's alias


# --- F-C293-1: the grantor rule is ENFORCE-only -----------------------------------------------------------


@pytest.mark.parametrize("granted_by", FOREIGN)
@pytest.mark.parametrize("mode", ["log-only", "log_only"])
def test_log_only_an_authenticated_caller_may_name_a_foreign_grantor(spine, mode, granted_by):
    spine.arm(mode)
    m0 = len(mint_events(spine))
    r = mint(spine, CANARY, granted_by, "plain-op", KEY_PLAIN)
    assert r.status_code == 201, r.text
    assert r.json()["granted_by"] == granted_by
    assert len(tokens(spine, CANARY)) == 1 and len(mint_events(spine)) == m0 + 1


def test_log_only_the_authenticated_verifier_may_name_a_foreign_grantor_for_a_non_canary_agent(spine):
    from test_machine_verifier_reach import SSL
    spine.arm("log-only")
    r = mint(spine, SSL, "Somebody Else", VERIFIER, KEY_VER)
    assert r.status_code == 201, r.text


def test_the_same_foreign_grantor_is_refused_under_enforce(spine):
    """The control for the two above: ENFORCE is where the rule bites."""
    spine.arm("enforce")
    r = mint(spine, CANARY, "Somebody Else", "plain-op", KEY_PLAIN)
    assert r.status_code == 403 and r.json() == FORBIDDEN, r.text
    assert tokens(spine, CANARY) == []


@pytest.mark.parametrize("granted_by", FOREIGN + ["plain-op", PLAIN_ALIAS])
def test_check_granted_by_is_false_outside_enforce_and_for_an_unauthenticated_caller(granted_by):
    """The unit the service relies on: no refusal and never an alias grant outside ENFORCE."""
    for mode in (oa.OFF, oa.LOG_ONLY):
        for authenticated in (True, False):
            auth = oa.OperatorAuth(mode, operator_id="plain-op" if authenticated else None,
                                   names=(PLAIN_ALIAS,), scopes=("mint",))
            assert auth.authenticated is authenticated
            assert oa.check_granted_by(auth, granted_by) is False, (mode, authenticated, granted_by)


# --- F-C293-2: an alias mint for an agent with no manifest_ref ---------------------------------------------


@pytest.fixture()
def no_ref_agent(spine):
    r = spine.registry.post("/agents", json={"agent_id": NO_REF, "name": NO_REF, "owner": "Don Hagell",
                                             "domain": "canary"})
    assert r.status_code == 201, r.text
    assert r.json().get("manifest_ref") in (None, ""), r.json()
    return NO_REF


def test_enforce_an_alias_mint_for_an_agent_with_no_manifest_ref_is_refused_and_writes_nothing(spine, no_ref_agent):
    spine.arm("enforce")
    m0 = len(mint_events(spine))
    r = mint(spine, no_ref_agent, ALIAS, VERIFIER, KEY_VER)
    assert r.status_code == 403 and r.json() == FORBIDDEN, r.text
    assert tokens(spine, no_ref_agent) == [] and len(mint_events(spine)) == m0


def test_enforce_the_verifier_own_id_mint_for_an_agent_with_no_manifest_ref_is_refused_too(spine, no_ref_agent):
    spine.arm("enforce")
    r = mint(spine, no_ref_agent, VERIFIER, VERIFIER, KEY_VER)
    assert r.status_code == 403 and r.json() == FORBIDDEN, r.text
    assert tokens(spine, no_ref_agent) == []


def test_an_agent_with_no_manifest_ref_still_mints_for_an_identity_that_is_not_bound_to_a_list(spine, no_ref_agent):
    """Control: the refusal is the alias rule's, not a general block on the agent. Don holds
    mint_for_others and is not list-bound, so the record without a manifest does not stop the mint."""
    spine.arm("enforce")
    r = mint(spine, no_ref_agent, "Don Hagell, Spin State Labs", "don", KEY_DON)
    assert r.status_code == 201, r.text


def test_log_only_an_alias_mint_for_an_agent_with_no_manifest_ref_is_not_refused(spine, no_ref_agent):
    spine.arm("log-only")
    assert mint(spine, no_ref_agent, ALIAS, VERIFIER, KEY_VER).status_code == 201


@pytest.mark.parametrize("granted_by", FOREIGN + [PLAIN_ALIAS])
def test_check_granted_by_for_an_unauthenticated_enforce_caller_is_false_the_guard_owns_the_401(granted_by):
    """Unauthenticated under ENFORCE never reaches an alias grant or a 403 from this function: the
    `guard_mint` dependency has already answered 401 (see test_enforce_an_unauthenticated_mint_is_401)."""
    auth = oa.OperatorAuth(oa.ENFORCE, names=(PLAIN_ALIAS,))
    assert auth.authenticated is False
    assert oa.check_granted_by(auth, granted_by) is False
