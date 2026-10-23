"""Phase G: operator_auth unit tests. Each refusal test names the check it
pins; the mutation run that proves each goes red is in
docs/runbooks/v1.2-deploy-rollback.md (Phase G section)."""

from __future__ import annotations

import json

import pytest

from field_core import operator_auth as oa

KEY_DON = "fok_don-key-0123456789abcdef"
KEY_SVC = "fok_svc-key-0123456789abcdef"


def _write(tmp_path, rows):
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


def rows():
    return [
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON),
         "status": "active", "created_at": "2026-10-01", "scopes": ["*"]},
        {"operator_id": "svc-lifecycle", "key_sha256": oa.key_sha256(KEY_SVC),
         "status": "active", "created_at": "2026-10-01", "scopes": ["kill"]},
        {"operator_id": "old", "key_sha256": oa.key_sha256("fok_old"),
         "status": "revoked", "created_at": "2026-01-01", "scopes": ["*"]},
    ]


@pytest.fixture()
def reg(tmp_path, monkeypatch):
    monkeypatch.delenv(oa.ENV_REQUIRE, raising=False)
    monkeypatch.delenv(oa.ENV_REGISTRY, raising=False)
    p = _write(tmp_path, rows())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    return p


@pytest.fixture()
def enforce(reg, monkeypatch):
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def H(op=None, key=None):
    h = {}
    if op is not None:
        h[oa.HEADER_OPERATOR] = op
    if key is not None:
        h[oa.HEADER_KEY] = key
    return h


def test_off_by_default_ignores_headers(monkeypatch):
    monkeypatch.delenv(oa.ENV_REQUIRE, raising=False)
    monkeypatch.delenv(oa.ENV_REGISTRY, raising=False)
    assert oa.mode() == oa.OFF
    auth = oa.authenticate(H("don", "wrong"), "kill")
    assert auth is oa.NO_AUTH and auth.ledger_fields() == {}


def test_good_key_authenticates(enforce):
    a = oa.authenticate(H("don", KEY_DON), "kill")
    assert a.operator_id == "don" and a.authenticated
    assert a.ledger_fields() == {
        "operator_id_authenticated": "don", "operator_claimed": "don",
        "operator_key_fp": oa.key_sha256(KEY_DON)[:8]}


def test_no_key_is_401(enforce):
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate({}, "kill")
    assert e.value.status == 401


def test_name_without_key_is_401(enforce):
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(H("don"), "kill")
    assert e.value.status == 401


def test_wrong_key_is_403(enforce):
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(H("don", "fok_wrong"), "kill")
    assert e.value.status == 403


def test_id_key_mismatch_is_403(enforce):
    # svc's valid key presented under don's id (and vice versa)
    for op, key in (("don", KEY_SVC), ("svc-lifecycle", KEY_DON)):
        with pytest.raises(oa.OperatorRefused) as e:
            oa.authenticate(H(op, key), "kill")
        assert e.value.status == 403


def test_spoofed_operator_id_unknown_and_revoked_is_403(enforce):
    for op, key in (("nobody", KEY_DON), ("old", "fok_old")):
        with pytest.raises(oa.OperatorRefused) as e:
            oa.authenticate(H(op, key), "kill")
        assert e.value.status == 403


def test_all_403_bodies_are_identical(enforce):
    bodies = set()
    for op, key, action in (("don", "fok_wrong", "kill"), ("don", KEY_SVC, "kill"),
                            ("nobody", KEY_DON, "kill"), ("old", "fok_old", "kill"),
                            ("svc-lifecycle", KEY_SVC, "rotate")):
        with pytest.raises(oa.OperatorRefused) as e:
            oa.authenticate(H(op, key), action)
        bodies.add((e.value.status, e.value.detail))
    assert bodies == {(403, oa.FORBIDDEN_DETAIL)}


def test_scope_is_enforced(enforce):
    assert oa.authenticate(H("svc-lifecycle", KEY_SVC), "kill").authenticated
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(H("svc-lifecycle", KEY_SVC), "mint")
    assert e.value.status == 403


@pytest.mark.parametrize("op,key", [
    ("doné", KEY_DON),           # non-ASCII id
    ("don", "fok_kéy"),          # non-ASCII key
    ("don, evil", KEY_DON),           # comma-joined multi-value
    ("don", KEY_DON + ",x"),
    ("x" * 65, KEY_DON),              # over length cap
    ("don", "k" * 257),
    ("don\r\nx-evil: 1", KEY_DON),    # smuggling attempt
    (" don", KEY_DON),                # surrounding whitespace
])
def test_malformed_headers_are_400(enforce, op, key):
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(H(op, key), "kill")
    assert e.value.status == 400


def test_duplicate_headers_are_400(enforce):
    class Dup:
        def getlist(self, name):
            return ["don", "don"] if name == oa.HEADER_OPERATOR else [KEY_DON]

    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(Dup(), "kill")
    assert e.value.status == 400


def test_header_name_case_is_irrelevant_for_dict_clients(enforce):
    a = oa.authenticate({"X-Field-Operator": "don", "X-FIELD-OPERATOR-KEY": KEY_DON}, "kill")
    assert a.authenticated


def test_unreadable_registry_is_503_never_allow(enforce, reg):
    reg.write_text("{not json", encoding="utf-8")
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(H("don", KEY_DON), "kill")
    assert e.value.status == 503


def test_missing_registry_file_is_503(enforce, reg):
    reg.unlink()
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(H("don", KEY_DON), "kill")
    assert e.value.status == 503


def test_require_without_registry_path_is_503_not_open(monkeypatch):
    monkeypatch.delenv(oa.ENV_REGISTRY, raising=False)
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(H("don", KEY_DON), "kill")
    assert e.value.status == 503


def test_malformed_registry_row_is_503(enforce, reg):
    reg.write_text(json.dumps([{"operator_id": "don", "key_sha256": "short"}]))
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(H("don", KEY_DON), "kill")
    assert e.value.status == 503


def test_log_only_never_refuses_and_records_failure(reg):
    assert oa.mode() == oa.LOG_ONLY
    a = oa.authenticate({}, "kill")
    assert not a.authenticated and a.failure == "no_credential"
    b = oa.authenticate(H("don", "fok_wrong"), "kill")
    assert not b.authenticated and b.failure == "bad_credential"
    assert b.ledger_fields()["operator_id_authenticated"] is None
    c = oa.authenticate(H("don", KEY_DON), "kill")
    assert c.authenticated


def test_log_only_unreadable_registry_is_recorded_not_authenticated(reg):
    reg.write_text("garbage")
    a = oa.authenticate(H("don", KEY_DON), "kill")
    assert not a.authenticated and a.failure == "registry_unavailable"


def test_authorized_operators_list(enforce):
    a = oa.authenticate(H("don", KEY_DON), "kill")
    oa.check_authorized(a, None)
    oa.check_authorized(a, [])
    oa.check_authorized(a, ["don", "x"])
    with pytest.raises(oa.OperatorRefused) as e:
        oa.check_authorized(a, ["someone-else"])
    assert (e.value.status, e.value.detail) == (403, oa.FORBIDDEN_DETAIL)


def test_granted_by_must_equal_authenticated_id(enforce):
    a = oa.authenticate(H("don", KEY_DON), "mint")
    oa.check_granted_by(a, "don")
    with pytest.raises(oa.OperatorRefused) as e:
        oa.check_granted_by(a, "Jane Roe")
    assert e.value.status == 403


def test_mint_for_others_scope_lets_a_provisioner_name_a_grantor(tmp_path, monkeypatch):
    r = rows() + [{"operator_id": "prov", "key_sha256": oa.key_sha256("fok_prov"),
                   "status": "active", "scopes": ["mint", "mint_for_others"]}]
    monkeypatch.setenv(oa.ENV_REGISTRY, str(_write(tmp_path, r)))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    a = oa.authenticate(H("prov", "fok_prov"), "mint")
    oa.check_granted_by(a, "Jane Roe")  # no raise
    s = oa.authenticate(H("svc-lifecycle", KEY_SVC), "kill")
    with pytest.raises(oa.OperatorRefused):
        oa.check_granted_by(s, "Jane Roe")


def test_lookup_hashes_and_compares_for_unknown_ids(enforce, monkeypatch):
    """No timing oracle: an unknown id still hashes the key and compares it to
    every stored hash, exactly as a known id does."""
    calls = []
    real = oa.hmac.compare_digest
    monkeypatch.setattr(oa.hmac, "compare_digest",
                        lambda a, b: calls.append(1) or real(a, b))
    with pytest.raises(oa.OperatorRefused):
        oa.authenticate(H("nobody", "fok_x"), "kill")
    unknown = len(calls)
    calls.clear()
    with pytest.raises(oa.OperatorRefused):
        oa.authenticate(H("don", "fok_x"), "kill")
    assert unknown == len(calls) and unknown >= 2 * len(rows())
    # ...and a SUCCESSFUL match does not stop the scan early either
    calls.clear()
    assert oa.authenticate(H("don", KEY_DON), "kill").authenticated
    assert len(calls) == unknown


def test_keys_never_leak_into_refusal_text(enforce):
    for op, key in (("don", "fok_SECRETVALUE"), ("doné", "fok_SECRETVALUE")):
        with pytest.raises(oa.OperatorRefused) as e:
            oa.authenticate(H(op, key), "kill")
        assert "SECRETVALUE" not in e.value.detail and "SECRETVALUE" not in repr(e.value)


def test_operator_headers_from_env(monkeypatch):
    monkeypatch.delenv(oa.ENV_OPERATOR, raising=False)
    monkeypatch.delenv(oa.ENV_OPERATOR_KEY, raising=False)
    assert oa.operator_headers() == {}
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, "k")
    assert oa.operator_headers() == {oa.HEADER_OPERATOR: "svc", oa.HEADER_KEY: "k"}
    from field_core.authn import auth_headers

    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    assert auth_headers() == {oa.HEADER_OPERATOR: "svc", oa.HEADER_KEY: "k"}
