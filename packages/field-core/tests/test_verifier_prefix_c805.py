"""C-805 (Don ruling D-18: REJECT; reviewer C-109 F-C109): a row holding the machine verifier's scope set is refused unless
its id starts with the exact `svc-verifier-` prefix.

The list-bound rules bind ONLY that exact prefix, so `svc-verify-gb10`, `verifier-gb10` and `SVC-VERIFIER-gb10` with the
verifier's scopes would reach every agent a human-grade operator reaches. `validate_rows` (format 1 and 2 alike) now
refuses such an ACTIVE row: all of kill, revive, revoke, with mint or mint_for_others, and no `*`."""

from __future__ import annotations

import json

import pytest

from field_core import operator_auth as oa

KEY = "fok_c805-unit-key-NEVER-PRINT-0123456789abc"
SET = ["kill", "revive", "revoke", "mint"]


def row(oid, scopes=SET, status="active", **extra):
    r = {"operator_id": oid, "key_sha256": oa.key_sha256(KEY), "status": status, "scopes": list(scopes), "names": []}
    r.update(extra)
    return r


@pytest.mark.parametrize("oid", ["svc-verify-gb10", "verifier-gb10", "SVC-VERIFIER-gb10", "svc-verifier", "svc_verifier-gb10",
                                 " svc-verifier-gb10", "xsvc-verifier-gb10", "gb10-gate"])
def test_the_verifier_scope_set_under_a_non_exact_id_is_refused(oid):
    problem = oa.validate_rows([row(oid)])
    assert problem and "machine verifier" in problem and "C-805" in problem


@pytest.mark.parametrize("oid", ["svc-verifier-gb10", "svc-verifier-fly", "svc-verifier-x"])
def test_the_exact_prefix_still_binds_and_loads(oid):
    assert oa.validate_rows([row(oid)]) is None


@pytest.mark.parametrize("mint", ["mint", "mint_for_others"])
def test_either_mint_scope_completes_the_set(mint):
    assert oa.validate_rows([row("verifier-gb10", ["kill", "revive", "revoke", mint])])


@pytest.mark.parametrize("scopes", [["revive", "revoke", "mint"], ["kill", "revoke", "mint"], ["kill", "revive", "mint"],
                                    ["kill", "revive", "revoke"], ["kill"], [], ["kill", "revive", "revoke", "drill", "attest"]])
def test_a_row_short_of_the_set_is_not_refused(scopes):
    assert oa.validate_rows([row("plain-op", scopes)]) is None


def test_a_human_row_holding_star_is_not_refused():
    assert oa.validate_rows([row("don", ["*", "kill", "revive", "revoke", "mint", "mint_for_others"])]) is None


def test_a_revoked_row_cannot_authenticate_and_is_not_refused():
    assert oa.validate_rows([row("verifier-gb10", status="revoked")]) is None


def test_a_row_without_a_status_is_read_as_active():
    r = row("verifier-gb10")
    del r["status"]
    assert oa.validate_rows([r])


@pytest.mark.parametrize("scopes", ["kill", None, 5, {"kill": 1}])
def test_a_scopes_value_that_is_not_a_list_is_not_this_rules_business_and_never_raises(scopes):
    r = row("plain-op")
    r["scopes"] = scopes
    assert oa.validate_rows([r]) is None


def test_the_message_names_the_id_and_never_the_key():
    problem = oa.validate_rows([row("verifier-gb10")])
    assert "'verifier-gb10'" in problem and KEY not in problem and oa.key_sha256(KEY) not in problem


def test_the_rule_runs_first_among_row_problems_only_after_duplicates():
    assert "duplicate" in oa.validate_rows([row("a"), row("a")])
    assert "machine verifier" in oa.validate_rows([row("verifier-gb10"), row("svc-verifier-gb10")])


def test_the_loader_refuses_the_file_and_never_reaches_authentication(tmp_path, monkeypatch):
    p = tmp_path / "operators.json"
    p.write_text(json.dumps([row("verifier-gb10")]), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate({oa.HEADER_OPERATOR: "verifier-gb10", oa.HEADER_KEY: KEY}, "kill")
    assert e.value.status == 503


def test_a_clean_file_with_the_exact_prefix_authenticates(tmp_path, monkeypatch):
    p = tmp_path / "operators.json"
    p.write_text(json.dumps([row("svc-verifier-gb10")]), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    a = oa.authenticate({oa.HEADER_OPERATOR: "svc-verifier-gb10", oa.HEADER_KEY: KEY}, "kill")
    assert a.authenticated and oa.list_bound(a)


# --- Don's ruling 2026-11-08 (reviewer C-1003): a verifier-prefixed row never holds bypass_operator_list ----------------
# bypass_operator_list makes check_record_authorized return before the list-bound branch, so the machine verifier would
# reach every agent's kill, revive, revoke and mint paths with no per-agent list check. The registry refuses it at load.
BYPASS = "bypass_operator_list"


@pytest.mark.parametrize("oid", ["svc-verifier-gb10", "svc-verifier-fly", "svc-verifier-x"])
@pytest.mark.parametrize("scopes", [SET + [BYPASS], [BYPASS], ["kill", BYPASS]])
def test_a_verifier_prefixed_row_holding_bypass_operator_list_is_refused(oid, scopes):
    problem = oa.validate_rows([row(oid, scopes)])
    assert problem and BYPASS in problem and oid in problem


def test_the_refusal_names_the_id_and_the_scope_never_a_key():
    problem = oa.validate_rows([row("svc-verifier-gb10", SET + [BYPASS])])
    assert KEY not in problem and oa.key_sha256(KEY) not in problem


@pytest.mark.parametrize("oid", ["svc-verifier-gb10", "svc-verifier-fly"])
def test_the_prefixed_row_without_the_scope_still_loads(oid):
    assert oa.validate_rows([row(oid)]) is None
    assert oa.validate_rows([row(oid, SET + ["*"])]) is None        # "*" never implies the scope (operator_auth.py:457)


@pytest.mark.parametrize("oid", ["killswitch-gate", "don", "svc-verify-gb10", "verifier-gb10"])
def test_a_non_prefixed_row_may_hold_bypass_operator_list(oid):
    assert oa.validate_rows([row(oid, ["kill", BYPASS])]) is None


def test_a_revoked_prefixed_row_with_the_scope_cannot_authenticate_and_is_not_refused():
    assert oa.validate_rows([row("svc-verifier-gb10", SET + [BYPASS], status="revoked")]) is None


@pytest.mark.parametrize("scopes", ["bypass_operator_list", None, 7, {"bypass_operator_list": True}])
def test_a_prefixed_row_with_a_non_list_scopes_value_does_not_raise(scopes):
    r = row("svc-verifier-gb10")
    r["scopes"] = scopes
    oa.validate_rows([r])                                           # must not raise; the row parser refuses it elsewhere


def test_the_loader_refuses_such_a_file_and_never_reaches_authentication(tmp_path, monkeypatch):
    p = tmp_path / "operators.json"
    p.write_text(json.dumps([row("svc-verifier-gb10", SET + [BYPASS])]), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate({oa.HEADER_OPERATOR: "svc-verifier-gb10", oa.HEADER_KEY: KEY}, "kill")
    assert e.value.status == 503
    assert KEY not in str(e.value)
