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


# --- review findings -----------------------------------------------------------


def test_lone_surrogate_operator_id_row_is_dropped_not_a_500(enforce, reg):
    r = rows() + [{"operator_id": "\ud800x", "key_sha256": "a" * 64,
                   "status": "active", "scopes": ["*"]}]
    reg.write_text(json.dumps(r), encoding="ascii")        # ensure_ascii -> \ud800
    assert oa.authenticate(H("don", KEY_DON), "kill").authenticated
    # and the lookup path itself survives a surrogate that reaches it
    assert oa._verify("\ud800x", "k", [{"operator_id": "\ud800x", "key_sha256": "a" * 64,
                                         "status": "active", "scopes": ()}])[0] is False


def test_registry_with_a_utf8_bom_is_read(enforce, reg):
    reg.write_bytes(b"\xef\xbb\xbf" + json.dumps(rows()).encode("utf-8"))
    assert oa.authenticate(H("don", KEY_DON), "kill").authenticated


def test_empty_authorized_list_still_requires_authentication_under_enforce(enforce):
    unauth = oa.OperatorAuth(oa.ENFORCE)
    for listed in (None, [], ["don"]):
        with pytest.raises(oa.OperatorRefused) as e:
            oa.check_authorized(unauth, listed)
        assert e.value.status == 401


def test_merge_payload_drops_forged_reserved_keys_outside_a_guarded_request(enforce):
    forged = {k: "forged" for k in oa.RESERVED_KEYS}
    assert oa.merge_payload({"x": 1, **forged}) == {"x": 1}


def test_flags_off_payloads_are_byte_identical(monkeypatch):
    monkeypatch.delenv(oa.ENV_REGISTRY, raising=False)
    monkeypatch.delenv(oa.ENV_REQUIRE, raising=False)
    p = {"x": 1, "operator_id_authenticated": "whatever"}
    assert oa.merge_payload(p) is p
    assert oa.strip_reserved_unless_asserted(p, {}) is p
    oa.reject_reserved_event_type("operator.unauthenticated", {})     # no raise when OFF


def test_merge_payload_inside_a_guarded_request_sets_only_the_real_values(enforce):
    a = oa.authenticate(H("don", KEY_DON), "kill")
    tok = oa.bind(a)
    try:
        out = oa.merge_payload({"operator_id_authenticated": "mallory", "x": 1})
    finally:
        oa._current.reset(tok)
    assert out["operator_id_authenticated"] == "don" and out["x"] == 1


def test_strip_reserved_unless_asserted(tmp_path, monkeypatch, enforce):
    rs = rows() + [{"operator_id": "ksvc", "key_sha256": oa.key_sha256("fok_ksvc"),
                    "status": "active", "scopes": ["kill", "ledger_attribute"],
                    "event_prefixes": ["kill."]}]
    reg_path = tmp_path / "operators2.json"
    reg_path.write_text(json.dumps(rs))
    monkeypatch.setenv(oa.ENV_REGISTRY, str(reg_path))
    p = {"x": 1, "operator_id_authenticated": "don"}
    assert "operator_id_authenticated" not in oa.strip_reserved_unless_asserted(p, {})
    # a human with "*" does NOT hold ledger_attribute
    assert "operator_id_authenticated" not in oa.strip_reserved_unless_asserted(p, H("don", KEY_DON))
    # C-10: the deprecated wrapper has no event type, so it strips for everyone;
    # the attributing identity keeps the fields through admit_ledger_event
    assert oa.strip_reserved_unless_asserted(p, H("ksvc", "fok_ksvc")) == {"x": 1}
    assert oa.admit_ledger_event("kill.agent", p, H("ksvc", "fok_ksvc")) is p
    monkeypatch.delenv(oa.ENV_REGISTRY)
    monkeypatch.delenv(oa.ENV_REQUIRE)
    assert oa.strip_reserved_unless_asserted(p, H("ksvc", "fok_ksvc")) is p       # OFF: untouched


def test_bind_body_operator_overwrites_when_authenticated(enforce):
    a = oa.authenticate(H("don", KEY_DON), "kill")
    tok = oa.bind(a)
    try:
        assert oa.bind_body_operator("CEO Jane") == "don"
        assert oa.ledger_fields()["operator_body_claimed"] == "CEO Jane"
    finally:
        oa._current.reset(tok)
        oa._body_claim.set(None)
    assert oa.bind_body_operator("CEO Jane") == "CEO Jane"      # unauthenticated: untouched


def test_log_only_unauthenticated_record_cannot_stall_the_caller(reg, monkeypatch):
    import time

    class Slow:
        def append(self, *a, **k):
            time.sleep(5)

    monkeypatch.setattr(oa, "LEDGER_APPEND_TIMEOUT_S", 0.2)
    t0 = time.perf_counter()
    prior = oa.current()
    try:
        a = oa.authorize_sync({}, "kill", "/kill/x", Slow())
        assert time.perf_counter() - t0 < 2 and not a.authenticated
    finally:
        oa.bind(prior)           # authorize_sync binds; never leak into other tests


@pytest.fixture(autouse=True)
def _no_context_leak():
    yield
    oa.bind(oa.NO_AUTH)
    oa._body_claim.set(None)


# --- second review round ----------------------------------------------------------


def test_reserved_event_type_is_refused_to_every_caller_except_self_reported(tmp_path, monkeypatch, enforce):
    rs = rows() + [{"operator_id": "ksvc", "key_sha256": oa.key_sha256("fok_ksvc"),
                    "status": "active", "scopes": ["ledger_attribute"], "event_prefixes": ["kill."]}]
    pth = tmp_path / "o2.json"
    pth.write_text(json.dumps(rs))
    monkeypatch.setenv(oa.ENV_REGISTRY, str(pth))
    oa.reject_reserved_event_type("kill.agent", {})                       # other types: fine
    # C-10: no caller, attributing or not, may write operator.mode_changed
    for h in ({}, H("don", KEY_DON), H("don", "fok_wrong"), H("ksvc", "fok_ksvc")):
        with pytest.raises(oa.OperatorRefused) as e:
            oa.reject_reserved_event_type("operator.mode_changed", h)
        assert e.value.status == 403
        oa.reject_reserved_event_type("operator.unauthenticated", h)     # self-reported: any caller


def test_attribution_loss_is_warned_once(enforce, caplog, monkeypatch):
    import logging

    monkeypatch.setattr(oa, "_warned", False)
    caplog.set_level(logging.WARNING, logger="field_core.operator_auth")
    p = {"operator_id_authenticated": "don"}
    oa.strip_reserved_unless_asserted(p, {})
    oa.strip_reserved_unless_asserted(p, {})
    msgs = [r for r in caplog.records if "attribution LOST" in r.getMessage()]
    assert len(msgs) == 1


def test_unauthenticated_flood_cannot_exhaust_threads(reg, monkeypatch):
    import threading
    import time

    gate = threading.Event()

    class Blocked:
        def append(self, *a, **k):
            gate.wait(5)

    monkeypatch.setattr(oa, "LEDGER_APPEND_TIMEOUT_S", 0.01)
    monkeypatch.setattr(oa, "dropped_unauthenticated_records", 0)
    prior = oa.current()
    try:
        n = oa.MAX_CONCURRENT_UNAUTH_RECORDS + 12
        t0 = time.perf_counter()
        for _ in range(n):
            oa.authorize_sync({}, "kill", "/kill/x", Blocked())
        assert time.perf_counter() - t0 < 3
        assert oa.dropped_unauthenticated_records >= 12
    finally:
        gate.set()
        oa.bind(prior)
        time.sleep(0.1)


def test_registry_edit_is_implied_by_star_but_not_assert_operator(enforce):
    a = oa.authenticate(H("don", KEY_DON), "registry_edit")
    assert a.authenticated
    with pytest.raises(oa.OperatorRefused):
        oa.authenticate(H("don", KEY_DON), "assert_operator")


# --- third review round -------------------------------------------------------------

DISPLAY = "Don Hagell, Spin State Labs"


@pytest.fixture()
def aliased(tmp_path, monkeypatch, enforce):
    rs = rows() + [
        {"operator_id": "don2", "key_sha256": oa.key_sha256("fok_don2"), "status": "active",
         "scopes": ["*"], "names": ["Don Hagell", DISPLAY]},
        {"operator_id": "svc-life", "key_sha256": oa.key_sha256("fok_life"), "status": "active",
         "scopes": ["kill", "bypass_operator_list"]},
    ]
    pth = tmp_path / "aliased.json"
    pth.write_text(json.dumps(rs))
    monkeypatch.setenv(oa.ENV_REGISTRY, str(pth))


def test_alias_matches_a_display_name_in_authorized_operators(aliased):
    a = oa.authenticate(H("don2", "fok_don2"), "kill")
    oa.check_authorized(a, [DISPLAY])
    oa.check_authorized(a, ["Don Hagell"])
    with pytest.raises(oa.OperatorRefused) as e:
        oa.check_authorized(a, ["don hagell"])                  # case-sensitive
    assert e.value.status == 403


def test_operator_without_the_alias_is_refused_the_display_name(aliased):
    a = oa.authenticate(H("don", KEY_DON), "kill")              # "don" has no names
    with pytest.raises(oa.OperatorRefused) as e:
        oa.check_authorized(a, [DISPLAY])
    assert e.value.status == 403


def test_alias_cannot_be_used_as_a_login_id(aliased):
    with pytest.raises(oa.OperatorRefused):
        oa.authenticate(H(DISPLAY, "fok_don2"), "kill")


def test_malformed_names_make_the_registry_unavailable(enforce, reg):
    r = rows()
    r[0]["names"] = "Don Hagell"                                  # not a list
    reg.write_text(json.dumps(r))
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(H("don", KEY_DON), "kill")
    assert e.value.status == 503


def test_bypass_operator_list_identity_is_exempt_from_every_authorized_operators_check(aliased):
    svc = oa.authenticate(H("svc-life", "fok_life"), "kill")
    # the shared function the kill-switch AND the registry both call
    manifest_ref = None
    oa.check_record_authorized(svc, manifest_ref)
    human = oa.authenticate(H("don", KEY_DON), "kill")
    assert not human.has_scope("bypass_operator_list")


def test_nested_reserved_keys_are_stripped(enforce):
    p = {"a": {"b": [{"operator_id_authenticated": "don"}]}, "ok": 1}
    assert oa._has_reserved(p)
    assert oa.strip_reserved_unless_asserted(p, {}) == {"a": {"b": [{}]}, "ok": 1}
    assert oa.merge_payload(p) == {"a": {"b": [{}]}, "ok": 1}


def test_operator_event_type_check_ignores_case_and_whitespace(enforce):
    for et in ("Operator.unauthenticated", " operator.x", "OPERATOR.Y"):
        with pytest.raises(oa.OperatorRefused):
            oa.reject_reserved_event_type(et, {})


# --- fourth review round: identity collisions ----------------------------------------


def _reg(tmp_path, monkeypatch, extra):
    pth = tmp_path / "coll.json"
    pth.write_text(json.dumps(rows() + extra))
    monkeypatch.setenv(oa.ENV_REGISTRY, str(pth))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def _row(oid, key, **kw):
    return {"operator_id": oid, "key_sha256": oa.key_sha256(key), "status": "active",
            "scopes": ["*"], **kw}


@pytest.mark.parametrize("extra", [
    [_row("mallory", "fok_m", names=["don"])],                              # alias == another id
    [_row("mallory", "fok_m", names=["Shared"]), _row("eve", "fok_e", names=["Shared"])],
    [_row("mallory", "fok_m", names=["*"])],
    [_row("don", "fok_other_don")],                                         # duplicate id (active)
])
def test_ambiguous_registry_fails_closed_503(tmp_path, monkeypatch, extra):
    _reg(tmp_path, monkeypatch, extra)
    for who, key in (("don", KEY_DON), ("mallory", "fok_m")):
        with pytest.raises(oa.OperatorRefused) as e:
            oa.authenticate(H(who, key), "kill")
        assert e.value.status == 503


def test_revoked_duplicate_row_cannot_leave_the_active_one_authenticating(tmp_path, monkeypatch):
    dup = _row("don", "fok_old_don")
    dup["status"] = "revoked"
    _reg(tmp_path, monkeypatch, [dup])                                       # appended AFTER the active row
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(H("don", KEY_DON), "kill")
    assert e.value.status == 503


def test_collision_log_line_has_no_key_material(tmp_path, monkeypatch, caplog):
    import logging

    caplog.set_level(logging.ERROR, logger="field_core.operator_auth")
    _reg(tmp_path, monkeypatch, [_row("mallory", "fok_m", names=["don"])])
    with pytest.raises(oa.OperatorRefused):
        oa.authenticate(H("don", KEY_DON), "kill")
    text = caplog.text
    assert "alias 'don'" in text and "fail closed" in text
    assert oa.key_sha256("fok_m") not in text and "fok_m" not in text


def test_distinct_aliases_and_a_repeated_alias_within_one_row_are_fine(tmp_path, monkeypatch):
    _reg(tmp_path, monkeypatch, [_row("a", "fok_a", names=["Alpha", "Alpha"]),
                                 _row("b", "fok_b", names=["Beta"])])
    assert oa.authenticate(H("a", "fok_a"), "kill").authenticated


def test_a_charset_safe_alias_is_not_a_login_id(tmp_path, monkeypatch):
    _reg(tmp_path, monkeypatch, [_row("don-h", "fok_dh", names=["Donny"])])
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(H("Donny", "fok_dh"), "kill")
    assert e.value.status == 403
    assert oa.authenticate(H("don-h", "fok_dh"), "kill").authenticated
