"""P35 machine verifier identity (svc-verifier-<estate>): the field-core half.

Three rules, each pinned in both directions here and end to end over real HTTP
in tools/tests/test_machine_verifier_identity.py:

1. check_granted_by accepts the caller's OWN registered alias as granted_by
   (and says so by returning True); any other string without mint_for_others
   is still a 403, and an identity with mint_for_others keeps today's path.
2. check_explicitly_listed (used for that alias grant and for list-bound ids):
   the agent's manifest must NAME the identity; no manifest_ref and an empty
   authorized_operators list are a 403, never a pass.
3. check_record_authorized treats an ``svc-verifier-`` id as list-bound: the
   empty-list and no-manifest leniency every other identity keeps does not
   apply to it, unless it holds bypass_operator_list (it must not).
4. check_list_bound_reach (review F1/F2): delegation mint (every granted_by)
   and revoke (the token's agent) bound a list-bound id to the agents whose
   manifest names it; a no-op for every other identity and outside ENFORCE.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from field_core import operator_auth as oa

REPO = Path(__file__).resolve().parents[3]
CANARY = str(REPO / "manifests" / "canary-gb10.yaml")          # lists Don + the verifier alias
SSL = str(REPO / "manifests" / "ssl-invoicing-agent.yaml")      # lists Don only
EMPTY = str(REPO / "manifests" / "conformance-sentinel.yaml")   # authorized_operators: []

ALIAS = "FIELD canary (gate verification)"
VERIFIER = "svc-verifier-gb10"
VERIFIER_SCOPES = ["kill", "revive", "drill", "attest", "mint", "revoke"]
KEY_VER = "fok_verifier-unit-key-NEVER-PRINT-0123456789"
KEY_DON = "fok_don-unit-key-NEVER-PRINT-0123456789abc"
KEY_LIFE = "fok_lifecycle-unit-key-NEVER-PRINT-01234567"
KEY_PLAIN = "fok_plain-unit-key-NEVER-PRINT-0123456789ab"


def _row(oid, key, scopes, names=()):
    return {"operator_id": oid, "key_sha256": oa.key_sha256(key), "status": "active",
            "created_at": "2026-10-28T00:00:00+00:00", "scopes": list(scopes), "names": list(names)}


def _rows(verifier_scopes=VERIFIER_SCOPES, verifier_id=VERIFIER):
    return [
        _row("don", KEY_DON, ["kill", "revive", "drill", "attest", "mint", "mint_for_others", "revoke",
                              "register", "caps", "escalation"], ["Don Hagell", "Don Hagell, Spin State Labs"]),
        _row(verifier_id, KEY_VER, verifier_scopes, [ALIAS]),
        _row("svc-lifecycle", KEY_LIFE, ["kill"]),
        # same scopes and alias shape as the verifier, but NOT an svc-verifier- id
        _row("plain-canary-op", KEY_PLAIN, ["kill", "mint"], ["Plain canary operator"]),
    ]


@pytest.fixture()
def armed(tmp_path, monkeypatch):
    def arm(mode="enforce", **kw):
        p = tmp_path / "operators.json"
        p.write_text(json.dumps(_rows(**kw)), encoding="utf-8")
        monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
        if mode == "enforce":
            monkeypatch.setenv(oa.ENV_REQUIRE, "1")
        else:
            monkeypatch.delenv(oa.ENV_REQUIRE, raising=False)
    return arm


def auth(oid, key, action="kill"):
    return oa.authenticate({oa.HEADER_OPERATOR: oid, oa.HEADER_KEY: key}, action)


def refused(fn, *a, status=403):
    with pytest.raises(oa.OperatorRefused) as e:
        fn(*a)
    assert e.value.status == status
    if status == 403:
        assert e.value.detail == oa.FORBIDDEN_DETAIL


# --- the row itself ------------------------------------------------------------------------


def test_the_verifier_row_loads_and_holds_exactly_its_six_scopes(armed):
    armed()
    a = auth(VERIFIER, KEY_VER)
    assert a.authenticated and sorted(a.scopes) == sorted(VERIFIER_SCOPES) and a.names == (ALIAS,)
    assert set(VERIFIER_SCOPES) <= oa.ACTIONS
    for absent in ("bypass_operator_list", "mint_for_others", "registry_edit", "ledger_attribute",
                   "register", "decommission", "caps"):
        assert not a.has_scope(absent), absent
    assert oa.list_bound(a)


def test_list_bound_is_the_prefix_and_needs_an_authenticated_identity(armed):
    armed()
    assert not oa.list_bound(auth("don", KEY_DON))
    assert not oa.list_bound(auth("plain-canary-op", KEY_PLAIN))
    armed(mode="log-only")
    assert not oa.list_bound(oa.authenticate({}, "kill"))      # unauthenticated
    assert not oa.list_bound(auth(VERIFIER, "fok_wrong-key"))  # wrong key = not proven


# --- rule 1: granted_by ---------------------------------------------------------------------


def test_granted_by_its_own_alias_is_accepted_and_flagged(armed):
    armed()
    a = auth(VERIFIER, KEY_VER, "mint")
    assert oa.check_granted_by(a, ALIAS) is True
    assert oa.check_granted_by(a, VERIFIER) is False            # its id: today's path


def test_granted_by_anything_else_is_still_refused(armed):
    armed()
    a = auth(VERIFIER, KEY_VER, "mint")
    for other in ("Don Hagell, Spin State Labs", "Don Hagell", "FIELD canary", ALIAS.upper(), ALIAS + " ",
                  "Plain canary operator", "don"):
        refused(oa.check_granted_by, a, other)


def test_another_identitys_alias_is_refused(armed):
    """An alias is the identity's own; plain-canary-op cannot mint as the verifier's alias."""
    armed()
    refused(oa.check_granted_by, auth("plain-canary-op", KEY_PLAIN, "mint"), ALIAS)


def test_mint_for_others_keeps_its_path_and_never_triggers_the_alias_bound(armed):
    armed()
    don = auth("don", KEY_DON, "mint")
    assert oa.check_granted_by(don, "Don Hagell, Spin State Labs") is False
    assert oa.check_granted_by(don, ALIAS) is False


def test_log_only_and_off_never_refuse_or_flag(armed, monkeypatch):
    armed(mode="log-only")
    assert oa.check_granted_by(auth(VERIFIER, KEY_VER, "mint"), "anyone at all") is False
    monkeypatch.delenv(oa.ENV_REGISTRY)
    assert oa.check_granted_by(oa.authenticate({}, "mint"), "anyone at all") is False


# --- rule 2: check_explicitly_listed --------------------------------------------------------


def test_explicitly_listed_passes_only_where_the_manifest_names_the_identity(armed):
    armed()
    a = auth(VERIFIER, KEY_VER, "mint")
    oa.check_explicitly_listed(a, CANARY)
    refused(oa.check_explicitly_listed, a, SSL)
    refused(oa.check_explicitly_listed, a, EMPTY)
    refused(oa.check_explicitly_listed, a, None)


def test_explicitly_listed_an_unresolvable_manifest_is_503(armed, tmp_path):
    armed()
    refused(oa.check_explicitly_listed, auth(VERIFIER, KEY_VER), str(tmp_path / "missing.yaml"), status=503)


def test_explicitly_listed_ignores_bypass(armed):
    """The alias-grant bound holds even for a (mis-granted) bypass row: a mint is bounded by the agent."""
    armed(verifier_scopes=VERIFIER_SCOPES + ["bypass_operator_list"])
    refused(oa.check_explicitly_listed, auth(VERIFIER, KEY_VER, "mint"), SSL)


# --- rule 3: check_record_authorized ----------------------------------------------------------


def test_the_verifier_reaches_the_canary_only(armed):
    armed()
    a = auth(VERIFIER, KEY_VER)
    oa.check_record_authorized(a, CANARY)
    for ref in (SSL, EMPTY, None):
        refused(oa.check_record_authorized, a, ref)


def test_other_identities_keep_the_empty_list_and_no_manifest_leniency(armed):
    """Only narrows: svc-lifecycle (auto-kill of orphans) and a non-prefixed narrow identity are unchanged."""
    armed()
    for a in (auth("svc-lifecycle", KEY_LIFE), auth("plain-canary-op", KEY_PLAIN)):
        oa.check_record_authorized(a, EMPTY)
        oa.check_record_authorized(a, None)
        refused(oa.check_record_authorized, a, SSL)
    oa.check_record_authorized(auth("don", KEY_DON), SSL)


def test_mutant_a_bypass_row_is_not_list_bound(armed):
    """Mutant: the verifier row given bypass_operator_list reaches every agent (why it must never hold it)."""
    armed(verifier_scopes=VERIFIER_SCOPES + ["bypass_operator_list"])
    a = auth(VERIFIER, KEY_VER)
    for ref in (SSL, EMPTY, None):
        oa.check_record_authorized(a, ref)


def test_mutant_the_same_row_under_another_id_is_not_list_bound(armed):
    """Mutant: without the svc-verifier- prefix the empty-list agent is reachable again."""
    armed(verifier_id="verifier-gb10")
    a = auth("verifier-gb10", KEY_VER)
    oa.check_record_authorized(a, EMPTY)
    refused(oa.check_record_authorized, a, SSL)


def test_log_only_never_refuses_the_verifier(armed):
    armed(mode="log-only")
    a = auth(VERIFIER, KEY_VER)
    for ref in (SSL, EMPTY, None):
        oa.check_record_authorized(a, ref)
        oa.check_explicitly_listed(a, ref)


# --- rule 4 (review F1/F2): check_list_bound_reach, delegation mint and revoke --------------------


def test_list_bound_reach_is_the_canary_only_for_the_verifier(armed):
    armed()
    a = auth(VERIFIER, KEY_VER, "revoke")
    assert oa.list_bound_applies(a)
    oa.check_list_bound_reach(a, CANARY)
    for ref in (SSL, EMPTY, None):
        refused(oa.check_list_bound_reach, a, ref)


def test_list_bound_reach_is_a_no_op_for_every_other_identity(armed):
    armed()
    for a in (auth("don", KEY_DON, "revoke"), auth("svc-lifecycle", KEY_LIFE), auth("plain-canary-op", KEY_PLAIN)):
        assert not oa.list_bound_applies(a)
        for ref in (CANARY, SSL, EMPTY, None):
            oa.check_list_bound_reach(a, ref)


def test_list_bound_reach_never_refuses_outside_enforce(armed):
    armed(mode="log-only")
    a = auth(VERIFIER, KEY_VER, "revoke")
    assert not oa.list_bound_applies(a)
    for ref in (SSL, EMPTY, None):
        oa.check_list_bound_reach(a, ref)


def test_mutant_a_bypass_row_escapes_the_reach_bound_as_it_escapes_the_list(armed):
    """Mutant: the same exemption check_record_authorized honours; why the row must never hold it."""
    armed(verifier_scopes=VERIFIER_SCOPES + ["bypass_operator_list"])
    a = auth(VERIFIER, KEY_VER, "revoke")
    assert not oa.list_bound_applies(a)
    oa.check_list_bound_reach(a, SSL)
