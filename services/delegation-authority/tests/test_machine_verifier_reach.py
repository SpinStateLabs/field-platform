"""P35 review F1/F2: the machine verifier's delegation reach is the canaries, whatever the configuration.

The independent review of PR #55 measured two reaches the PR had declared but not enforced:

* F1: ``POST /tokens/{id}/revoke`` checked the ``revoke`` scope only, so the verifier key revoked an
  ``ssl-invoicing-agent`` token (HTTP 200) under ENFORCE;
* F2: with ``FIELD_DOA_ROSTER`` unset, a mint with ``granted_by`` equal to the verifier's OWN id never
  looked at the agent (``check_granted_by`` returns False for the own-id case), so it minted an
  ``ssl-invoicing-agent`` token (HTTP 201).

Both now go through ``operator_auth.check_list_bound_reach``: under ENFORCE a list-bound identity
(``svc-verifier-*`` without ``bypass_operator_list``) mints and revokes only for an agent whose manifest NAMES
it. These tests run the real delegation, registry and ledger apps in-process with the roster UNSET (the case
the e2e estate cannot reach: its roster is armed) against the shipped manifests. Every other identity, and
LOG-ONLY, is unchanged, which the controls below pin.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from field_core import operator_auth as oa
from test_doa_roster import Spine, write_manifest

REPO = Path(__file__).resolve().parents[3]
CANARY = "canary-gb10"                 # authorized_operators: Don + the verifier alias
SSL = "ssl-invoicing-agent"            # authorized_operators: Don only
EMPTY = "conformance-sentinel"         # authorized_operators: []
ALIAS = "FIELD canary (gate verification)"
VERIFIER = "svc-verifier-gb10"
VERIFIER_SCOPES = ["kill", "revive", "drill", "attest", "mint", "revoke"]
KEY_VER = "fok_verifier-reach-key-NEVER-PRINT-0123456789"
KEY_DON = "fok_don-reach-key-NEVER-PRINT-0123456789abcd"
KEY_PLAIN = "fok_plain-reach-key-NEVER-PRINT-0123456789ab"
KEY_DSVC = "fok_dsvc-reach-key-NEVER-PRINT-0123456789abc"
FORBIDDEN = {"detail": oa.FORBIDDEN_DETAIL}


def _row(oid, key, scopes, names=(), **kw):
    return {"operator_id": oid, "key_sha256": oa.key_sha256(key), "status": "active",
            "created_at": "2026-10-28T00:00:00+00:00", "scopes": list(scopes), "names": list(names), **kw}


def hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, "FIELD_DOA_ROSTER"):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def spine(tmp_path, monkeypatch):
    """The three apps, the three shipped manifests registered (flags OFF while registering), then
    the operators file written; ``arm(mode)`` switches the mode. The DOA roster stays UNSET."""
    s = Spine(tmp_path, write_manifest(tmp_path))
    for agent in (CANARY, SSL, EMPTY):
        r = s.registry.post("/agents", json={"agent_id": agent, "name": agent, "owner": "Don Hagell",
                                             "domain": "canary", "manifest_ref": str(REPO / "manifests" / f"{agent}.yaml")})
        assert r.status_code == 201, r.text
    ops = tmp_path / "operators.json"
    ops.write_text(json.dumps([
        _row("don", KEY_DON, ["kill", "revive", "drill", "attest", "mint", "mint_for_others", "revoke"],
             ["Don Hagell", "Don Hagell, Spin State Labs"]),
        _row(VERIFIER, KEY_VER, VERIFIER_SCOPES, [ALIAS]),
        # the verifier's scopes under an id WITHOUT the prefix: not list-bound (only narrows)
        _row("plain-op", KEY_PLAIN, VERIFIER_SCOPES, ["Plain operator"]),
        _row("dsvc", KEY_DSVC, ["ledger_attribute"], event_prefixes=["delegation."]),
    ]), encoding="utf-8")
    s.ledger.headers.update(hdr("dsvc", KEY_DSVC))

    def arm(mode):
        monkeypatch.setenv(oa.ENV_REGISTRY, str(ops))
        if mode == "enforce":
            monkeypatch.setenv(oa.ENV_REQUIRE, "1")
        else:
            monkeypatch.delenv(oa.ENV_REQUIRE, raising=False)
    s.arm = arm
    return s


def mint(s, agent, granted_by, op, key):
    return s.delegation.post("/tokens", json={"agent_id": agent, "granted_by": granted_by, "scope": ["x"],
                                              "ttl_seconds": 3600}, headers=hdr(op, key))


def revoke(s, tid, op, key):
    return s.delegation.post(f"/tokens/{tid}/revoke", headers=hdr(op, key))


def tokens(s, agent):
    return s.delegation.get("/tokens", params={"agent_id": agent}).json()


def mint_events(s):
    return s.mint_events()


def revoke_events(s):
    return s.ledger.get("/events", params={"event_type": "delegation.revoke"}).json()


def active(s, tid):
    return s.delegation.get(f"/tokens/{tid}").json()["revoked"] is False


# --- F2: own-id mint, roster unset -------------------------------------------------------------------


@pytest.mark.parametrize("agent", [SSL, EMPTY])
def test_enforce_roster_unset_the_verifier_cannot_mint_as_its_own_id_for_a_non_canary_agent(spine, agent):
    spine.arm("enforce")
    m0 = len(mint_events(spine))
    r = mint(spine, agent, VERIFIER, VERIFIER, KEY_VER)
    assert r.status_code == 403 and r.json() == FORBIDDEN, r.text
    assert tokens(spine, agent) == [] and len(mint_events(spine)) == m0


def test_enforce_roster_unset_the_verifier_own_id_mint_reaches_the_canary_only(spine):
    """The bound is the agent: the canary names the verifier (by alias), so its own-id grant is accepted there."""
    spine.arm("enforce")
    r = mint(spine, CANARY, VERIFIER, VERIFIER, KEY_VER)
    assert r.status_code == 201, r.text
    assert r.json()["granted_by"] == VERIFIER


def test_enforce_roster_unset_the_alias_mint_is_still_canary_only(spine):
    spine.arm("enforce")
    assert mint(spine, CANARY, ALIAS, VERIFIER, KEY_VER).status_code == 201
    r = mint(spine, SSL, ALIAS, VERIFIER, KEY_VER)
    assert r.status_code == 403 and r.json() == FORBIDDEN
    assert tokens(spine, SSL) == []


def test_enforce_roster_unset_other_identities_mint_as_before(spine):
    """Only narrows: the same scopes under a non-prefixed id, and Don, mint for the SSL agent as before."""
    spine.arm("enforce")
    assert mint(spine, SSL, "plain-op", "plain-op", KEY_PLAIN).status_code == 201
    assert mint(spine, SSL, "Don Hagell, Spin State Labs", "don", KEY_DON).status_code == 201


def test_log_only_the_verifier_own_id_mint_is_unchanged(spine):
    spine.arm("log-only")
    assert mint(spine, SSL, VERIFIER, VERIFIER, KEY_VER).status_code == 201


# --- F1: revoke ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("agent", [SSL, EMPTY])
def test_enforce_the_verifier_cannot_revoke_a_non_canary_token(spine, agent):
    spine.arm("enforce")
    tid = mint(spine, agent, "Don Hagell, Spin State Labs", "don", KEY_DON).json()["token_id"]
    r0 = len(revoke_events(spine))
    r = revoke(spine, tid, VERIFIER, KEY_VER)
    assert r.status_code == 403 and r.json() == FORBIDDEN, r.text
    assert active(spine, tid) and len(revoke_events(spine)) == r0
    # control: Don revokes it
    assert revoke(spine, tid, "don", KEY_DON).status_code == 200
    assert not active(spine, tid)


def test_enforce_the_verifier_revokes_canary_tokens_whoever_minted_them(spine):
    spine.arm("enforce")
    mine = mint(spine, CANARY, ALIAS, VERIFIER, KEY_VER).json()["token_id"]
    dons = mint(spine, CANARY, "Don Hagell, Spin State Labs", "don", KEY_DON).json()["token_id"]
    for tid in (mine, dons):
        r = revoke(spine, tid, VERIFIER, KEY_VER)
        assert r.status_code == 200 and r.json()["revoked"] is True, r.text


def test_enforce_an_already_revoked_non_canary_token_is_still_refused_to_the_verifier(spine):
    """The bound runs before the idempotent short-circuit: no answer about another agent's token."""
    spine.arm("enforce")
    tid = mint(spine, SSL, "Don Hagell, Spin State Labs", "don", KEY_DON).json()["token_id"]
    assert revoke(spine, tid, "don", KEY_DON).status_code == 200
    r = revoke(spine, tid, VERIFIER, KEY_VER)
    assert r.status_code == 403 and r.json() == FORBIDDEN


def test_enforce_other_identities_revoke_as_before(spine):
    """Mutant-style control: the verifier's scopes under an id without the prefix revoke the SSL token (the
    rule is the prefix; this is why the row must keep it)."""
    spine.arm("enforce")
    tid = mint(spine, SSL, "Don Hagell, Spin State Labs", "don", KEY_DON).json()["token_id"]
    assert revoke(spine, tid, "plain-op", KEY_PLAIN).status_code == 200


def test_log_only_the_verifier_revoke_is_unchanged(spine):
    spine.arm("enforce")
    tid = mint(spine, SSL, "Don Hagell, Spin State Labs", "don", KEY_DON).json()["token_id"]
    spine.arm("log-only")
    assert revoke(spine, tid, VERIFIER, KEY_VER).status_code == 200
