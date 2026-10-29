"""C-127 (reviewer R-10 F-R10-1, F-R10-2): pin the mint grantor rule end to end.

F-R10-1: ``operator_auth.check_granted_by`` returns True (the alias case) only when ``granted_by`` is one of
the caller's OWN names. Forcing ``granted_by in auth.names`` to True was killed only by the field-core unit
test: through the service the second gate (``check_explicitly_listed``) refused an unlisted manifest, so every
existing end-to-end case still answered 403. These tests use an identity that the agent's manifest DOES name
(the machine verifier and the canary agent), so the grantor rule is the only gate left: a ``granted_by`` that
is neither the caller's id nor one of its own aliases, without ``mint_for_others``, is 403 and writes nothing.

F-R10-2: outside ENFORCE an unauthenticated mint is allowed by design (OFF and LOG-ONLY are observation);
the controls pin that, so a change that makes LOG-ONLY refuse is visible.
"""

from __future__ import annotations

import pytest

from field_core import operator_auth as oa
from test_machine_verifier_reach import (  # the three apps, shipped manifests and the operators file
    ALIAS, CANARY, FORBIDDEN, KEY_VER, VERIFIER, hdr, mint, mint_events, spine, tokens, _clean,  # noqa: F401
)

NOT_MINE = [
    "Somebody Else",                      # a name nobody holds
    "Don Hagell",                         # another identity's alias
    "Don Hagell, Spin State Labs",        # another identity's second alias
    "svc-verifier-other",                 # a verifier-shaped id that is not the caller's
    "don",                                # another operator's id
    ALIAS.upper(),                        # the caller's alias in another case: not equal
    ALIAS + " ",                          # the caller's alias with a trailing space: not equal
]


@pytest.mark.parametrize("granted_by", NOT_MINE)
def test_enforce_a_grantor_that_is_not_the_callers_own_name_is_refused_and_writes_nothing(spine, granted_by):
    spine.arm("enforce")
    m0 = len(mint_events(spine))
    r = mint(spine, CANARY, granted_by, VERIFIER, KEY_VER)
    assert r.status_code == 403 and r.json() == FORBIDDEN, r.text
    assert tokens(spine, CANARY) == []
    assert len(mint_events(spine)) == m0


@pytest.mark.parametrize("granted_by", [VERIFIER, ALIAS])
def test_enforce_the_callers_own_id_and_own_alias_still_mint_for_the_agent_that_names_it(spine, granted_by):
    spine.arm("enforce")
    r = mint(spine, CANARY, granted_by, VERIFIER, KEY_VER)
    assert r.status_code == 201, r.text
    assert len(tokens(spine, CANARY)) == 1


@pytest.mark.parametrize("mode", ["off", "log-only"])
def test_outside_enforce_an_unauthenticated_mint_is_allowed_by_design(spine, mode):
    spine.arm(mode)
    r = spine.delegation.post("/tokens", json={"agent_id": CANARY, "granted_by": "Anyone", "scope": ["x"],
                                               "ttl_seconds": 3600})
    assert r.status_code == 201, r.text


def test_enforce_an_unauthenticated_mint_is_401(spine):
    spine.arm("enforce")
    r = spine.delegation.post("/tokens", json={"agent_id": CANARY, "granted_by": "Anyone", "scope": ["x"],
                                               "ttl_seconds": 3600})
    assert r.status_code == 401, r.text
    assert tokens(spine, CANARY) == []
    assert oa.ENV_REQUIRE  # the flag name the arm() helper sets: keeps the import honest


def test_enforce_the_mint_for_others_scope_is_what_lets_an_identity_name_another_grantor(spine):
    from test_machine_verifier_reach import KEY_DON, SSL
    spine.arm("enforce")
    r = mint(spine, SSL, "Somebody Else", "don", KEY_DON)
    assert r.status_code == 201, r.text
    assert len(tokens(spine, SSL)) == 1
