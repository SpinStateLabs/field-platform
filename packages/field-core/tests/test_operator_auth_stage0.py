"""Phase G Stage 0, field-core slice: C-1 (FIELD_OPERATOR_KEY_FILE), C-10 (the
assert_operator scope split: ledger_attribute + event_prefixes,
bypass_operator_list, the ledger's operator.* policy), C-15 (the unauthenticated
record keeps the claimed id; registry failures logged once) and C-18 (strict
registry rows, zero active rows under ENFORCE is a 503).

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import json
import logging
import threading
from types import SimpleNamespace

import pytest

from field_core import operator_auth as oa

KEY_DON = "tkv-don-key-0123456789abcdef"
KEY_SVC = "tkv-svc-key-0123456789abcdef"
KEY_REG = "tkv-reg-key-0123456789abcdef"
KEY_KS = "tkv-ks-key-0123456789abcdef"
KEY_BG = "tkv-bg-key-0123456789abcdef"


def _row(oid, key, scopes, **kw):
    return {"operator_id": oid, "key_sha256": oa.key_sha256(key), "status": "active",
            "created_at": "2026-10-25", "scopes": scopes, **kw}


def base_rows():
    return [
        _row("don", KEY_DON, ["*"], names=["Don Hagell"]),
        _row("svc-lifecycle", KEY_SVC, ["kill"]),
        _row("svc-registry", KEY_REG, ["ledger_attribute"], event_prefixes=["registry."]),
        _row("svc-killswitch", KEY_KS, ["kill", "revive", "drill", "bypass_operator_list",
                                        "ledger_attribute"], event_prefixes=["kill."]),
        _row("don-breakglass", KEY_BG, ["kill", "revive", "bypass_operator_list"]),
    ]


def H(op=None, key=None):
    h = {}
    if op is not None:
        h[oa.HEADER_OPERATOR] = op
    if key is not None:
        h[oa.HEADER_KEY] = key
    return h


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in ("FIELD_OPERATOR_REGISTRY", "FIELD_OPERATOR_REQUIRE", "FIELD_OPERATOR",
              "FIELD_OPERATOR_KEY", "FIELD_OPERATOR_KEY_FILE"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr(oa, "_logged_once", set(), raising=False)
    monkeypatch.setattr(oa, "_registry_failures_logged", set(), raising=False)
    monkeypatch.setattr(oa, "_warned", False)
    yield
    oa.bind(oa.NO_AUTH)
    oa._body_claim.set(None)


def _write(tmp_path, doc, name="operators.json"):
    p = tmp_path / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


@pytest.fixture()
def reg(tmp_path, monkeypatch):
    p = _write(tmp_path, base_rows())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    return p


@pytest.fixture()
def enforce(reg, monkeypatch):
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    return reg


# --- C-1: FIELD_OPERATOR_KEY_FILE --------------------------------------------------


def test_key_file_supplies_the_key_and_is_read_on_every_call(tmp_path, monkeypatch):
    kf = tmp_path / "svc.key"
    kf.write_text("tkv-first-0123456789\n", encoding="utf-8")
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-killswitch")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY_FILE, str(kf))
    assert oa.operator_headers() == {oa.HEADER_OPERATOR: "svc-killswitch",
                                     oa.HEADER_KEY: "tkv-first-0123456789"}
    kf.write_text("  tkv-rotated-0123456789  \r\n", encoding="utf-8")   # rotation: no restart
    assert oa.operator_headers()[oa.HEADER_KEY] == "tkv-rotated-0123456789"
    from field_core.authn import auth_headers

    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    assert auth_headers()[oa.HEADER_KEY] == "tkv-rotated-0123456789"


def test_key_file_wins_over_the_env_key(tmp_path, monkeypatch, caplog):
    kf = tmp_path / "svc.key"
    kf.write_text("tkv-from-file-0123456789", encoding="utf-8")
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, "tkv-from-env-0123456789")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY_FILE, str(kf))
    caplog.set_level(logging.WARNING, logger="field_core.operator_auth")
    assert oa.operator_headers()[oa.HEADER_KEY] == "tkv-from-file-0123456789"
    assert oa.operator_headers()[oa.HEADER_KEY] == "tkv-from-file-0123456789"
    warned = [r for r in caplog.records if "is ignored" in r.getMessage()]
    assert len(warned) == 1
    assert "tkv-" not in caplog.text


@pytest.mark.parametrize("content", [
    None,                                   # file missing
    b"",                                    # empty
    b"   \n\t\n",                           # whitespace only
    b"tkv-a-0123456789 tkv-b-0123456789",   # two tokens
    b"tkv-line1-0123456789\ntkv-line2-0123456789\n",
    b"-----BEGIN TEST BLOCK-----\nbm90LWEta2V5LWp1c3QtYS1ibG9jaw\n-----END TEST BLOCK-----\n",
    b"\xff\xfe\x00k",                        # not UTF-8
    b"tkv-" + b"a" * 5000,                  # oversize
], ids=["missing", "empty", "whitespace", "two-tokens", "two-lines", "armored-block", "not-utf8", "oversize"])
def test_an_unusable_key_file_sends_no_headers_and_never_falls_back(tmp_path, monkeypatch, caplog, content):
    kf = tmp_path / "svc.key"
    if content is not None:
        kf.write_bytes(content)
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, "tkv-env-fallback-0123456789")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY_FILE, str(kf))
    caplog.set_level(logging.ERROR, logger="field_core.operator_auth")
    assert oa.operator_headers() == {}
    assert oa.operator_headers() == {}
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1                                   # once, not per call
    assert oa.ENV_OPERATOR_KEY_FILE in errors[0].getMessage()
    # the file content and the env key never reach the log
    assert "tkv-" not in caplog.text and "TEST BLOCK" not in caplog.text and "bm90" not in caplog.text


def test_an_oversize_key_file_is_refused_by_size_before_it_is_parsed(tmp_path, monkeypatch, caplog):
    kf = tmp_path / "big.key"
    kf.write_bytes(b"x" * (oa.MAX_KEY_FILE_BYTES + 1))
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY_FILE, str(kf))
    caplog.set_level(logging.ERROR, logger="field_core.operator_auth")
    assert oa.operator_headers() == {}
    assert "larger than a key" in caplog.text


@pytest.mark.parametrize("blank", ["", "  ", "\t"])
def test_a_blank_key_file_variable_is_unset(monkeypatch, blank):
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, "tkv-env-0123456789")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY_FILE, blank)
    assert oa.operator_headers() == {oa.HEADER_OPERATOR: "svc",
                                     oa.HEADER_KEY: "tkv-env-0123456789"}


@pytest.mark.parametrize("op", [None, "", "   "])
def test_key_file_without_an_operator_id_sends_nothing(tmp_path, monkeypatch, op):
    kf = tmp_path / "svc.key"
    kf.write_text("tkv-x-0123456789", encoding="utf-8")
    if op is not None:
        monkeypatch.setenv(oa.ENV_OPERATOR, op)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY_FILE, str(kf))
    assert oa.operator_headers() == {}


def test_key_file_identity_authenticates_end_to_end(tmp_path, monkeypatch, enforce):
    kf = tmp_path / "ks.key"
    kf.write_text(KEY_KS + "\n", encoding="utf-8")
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-killswitch")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY_FILE, str(kf))
    a = oa.authenticate(oa.operator_headers(), "kill")
    assert a.operator_id == "svc-killswitch" and a.key_fp == oa.key_fingerprint(KEY_KS)


# --- C-18: strict rows ----------------------------------------------------------------


def test_a_row_without_status_makes_the_registry_unavailable(tmp_path, monkeypatch):
    r = base_rows()
    del r[0]["status"]
    p = _write(tmp_path, r)
    with pytest.raises(oa.RegistryUnavailable) as e:
        oa.load_registry(str(p))
    assert "status is missing" in str(e.value) and "row 1 ('don')" in str(e.value)
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    a = oa.authenticate(H("don", KEY_DON), "kill")                # LOG-ONLY: recorded
    assert not a.authenticated and a.failure == "registry_unavailable"
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    with pytest.raises(oa.OperatorRefused) as e2:                 # ENFORCE: 503
        oa.authenticate(H("don", KEY_DON), "kill")
    assert e2.value.status == 503


@pytest.mark.parametrize("bad", ["Active", "ACTIVE", "active ", "disabled", "", None, 1, True,
                                 ["active"], {"s": "active"}])
def test_status_must_be_exactly_active_or_revoked(tmp_path, bad):
    r = base_rows()
    r[1]["status"] = bad
    with pytest.raises(oa.RegistryUnavailable) as e:
        oa.load_registry(str(_write(tmp_path, r)))
    assert "row 2 ('svc-lifecycle')" in str(e.value) and "status" in str(e.value)


def test_revoked_rows_load_and_never_authenticate(tmp_path, monkeypatch):
    r = base_rows()
    r[0]["status"] = "revoked"
    p = _write(tmp_path, r)
    assert [x["status"] for x in oa.load_registry(str(p))][0] == "revoked"
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(H("don", KEY_DON), "kill")
    assert e.value.status == 403


@pytest.mark.parametrize("bad", ["A" * 64, "a" * 63, "a" * 65, "g" * 64, "a" * 64 + "\n",
                                 None, 7])
def test_key_sha256_must_be_64_lower_case_hex(tmp_path, bad):
    r = base_rows()
    r[2]["key_sha256"] = bad
    with pytest.raises(oa.RegistryUnavailable) as e:
        oa.load_registry(str(_write(tmp_path, r)))
    assert "key_sha256" in str(e.value)
    if isinstance(bad, str):
        assert bad.strip() not in str(e.value)                    # never echoes hash material


@pytest.mark.parametrize("doc", [[], {"operators": []},
                                 [{**_row("old", "tkv-old-0123456789", ["*"]), "status": "revoked"}]])
def test_zero_active_rows_under_enforce_is_503_not_a_silent_403(tmp_path, monkeypatch, doc):
    p = _write(tmp_path, doc)
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(H("don", KEY_DON), "kill")
    assert e.value.status == 503
    with pytest.raises(oa.RegistryUnavailable, match="no active rows"):
        oa.load_registry()


def test_zero_active_rows_outside_enforce_still_loads(tmp_path, monkeypatch):
    p = _write(tmp_path, {"operators": []})
    assert oa.load_registry(str(p)) == []                         # OFF
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))                   # LOG-ONLY
    assert oa.load_registry() == []
    a = oa.authenticate(H("don", KEY_DON), "kill")
    assert not a.authenticated and a.failure == "bad_credential"
    with pytest.raises(oa.RegistryUnavailable, match="no active rows"):
        oa.load_registry(str(p), require_active=True)             # explicit (keygen --check)


# --- C-15: registry failures logged once; the claimed id survives ------------------------


def test_registry_failure_is_logged_once_per_distinct_failure(tmp_path, monkeypatch, caplog):
    p = tmp_path / "operators.json"
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    caplog.set_level(logging.ERROR, logger="field_core.operator_auth")

    def errors():
        return [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]

    p.write_text("garbage", encoding="utf-8")
    for _ in range(3):
        oa.authenticate(H("don", KEY_DON), "kill")
    assert len(errors()) == 1 and "unreadable" in errors()[0]
    r = base_rows()
    del r[1]["status"]
    p.write_text(json.dumps(r), encoding="utf-8")
    for _ in range(3):
        oa.authenticate(H("don", KEY_DON), "kill")
    assert len(errors()) == 2 and "status is missing" in errors()[1]
    # a good load ends the episode; the same failure later is logged again
    p.write_text(json.dumps(base_rows()), encoding="utf-8")
    assert oa.authenticate(H("don", KEY_DON), "kill").authenticated
    p.write_text("garbage", encoding="utf-8")
    oa.authenticate(H("don", KEY_DON), "kill")
    assert len(errors()) == 3
    for m in errors():
        assert oa.key_sha256(KEY_DON) not in m and "tkv-" not in m


def test_ambiguous_registry_reason_is_in_the_exception_and_logged_once(tmp_path, monkeypatch, caplog):
    r = base_rows() + [_row("don", "tkv-dup-0123456789", ["kill"])]
    p = _write(tmp_path, r)
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    caplog.set_level(logging.ERROR, logger="field_core.operator_auth")
    with pytest.raises(oa.RegistryUnavailable, match="duplicate operator_id 'don'"):
        oa.load_registry()
    oa.authenticate(H("don", KEY_DON), "kill")
    assert len([x for x in caplog.records if x.levelno == logging.ERROR]) == 1


class _MergingLedger:
    """Mimics a caller-side append wrapper that merges operator fields (and so
    strips caller-supplied reserved keys) before the event leaves the process,
    then the remote ledger's strip for a caller that may not attribute."""

    def __init__(self):
        self.events = []
        self.seen_in_thread = []
        self.done = threading.Event()

    def append(self, event_type, payload, agent_id=None):
        self.seen_in_thread.append(oa.current())
        merged = oa.merge_payload(dict(payload))
        self.events.append((event_type, oa._strip_reserved(merged)))
        self.done.set()


def test_unauthenticated_record_keeps_the_claimed_id_through_reserved_key_stripping(reg):
    led = _MergingLedger()
    a = oa.authorize_sync(H("don", "tkv-wrong-0123456789"), "kill", "/kill/x", led)
    assert led.done.wait(5) and not a.authenticated
    et, payload = led.events[0]
    assert et == "operator.unauthenticated"
    assert payload["claimed_id"] == "don"
    assert payload["reason"] == "bad_credential" and payload["action"] == "kill"
    assert "operator_claimed" not in payload            # reserved: stripped, as the finding said


def test_unauthenticated_record_thread_sees_the_bound_context(reg):
    led = _MergingLedger()
    oa.authorize_sync(H("don", "tkv-wrong-0123456789"), "kill", "/kill/x", led)
    assert led.done.wait(5)
    seen = led.seen_in_thread[0]
    assert seen.mode == oa.LOG_ONLY and seen.claimed == "don" and not seen.authenticated


# --- C-10: the scope split -------------------------------------------------------------


def test_split_scopes_exist_and_star_implies_neither():
    assert {"ledger_attribute", "bypass_operator_list"} <= oa.ACTIONS
    star = oa.OperatorAuth(oa.ENFORCE, operator_id="don", scopes=("*",))
    assert star.has_scope("kill")
    assert not star.has_scope("ledger_attribute") and not star.has_scope("bypass_operator_list")


def test_event_prefixes_are_loaded_onto_the_authenticated_identity(enforce):
    a = oa.authenticate(H("svc-registry", KEY_REG), "ledger_attribute")
    assert a.event_prefixes == ("registry.",)
    k = oa.authenticate(H("svc-killswitch", KEY_KS), "kill")
    assert k.event_prefixes == ("kill.",)


@pytest.mark.parametrize("bad", ["kill.", ["kill"], [""], ["."], ["operator."], ["operator.x."],
                                 ["Kill."], ["kill.*"], [" kill."], [5], ["a." * 40]])
def test_malformed_event_prefixes_make_the_registry_unavailable(tmp_path, bad):
    r = base_rows()
    r[2]["event_prefixes"] = bad
    with pytest.raises(oa.RegistryUnavailable, match="event_prefixes"):
        oa.load_registry(str(_write(tmp_path, r)))


def test_neither_split_scope_grants_an_action_by_itself(tmp_path, monkeypatch):
    p = _write(tmp_path, base_rows() + [_row("bypass-only", "tkv-bp-0123456789",
                                             ["bypass_operator_list"])])
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    for who, key in (("svc-registry", KEY_REG), ("bypass-only", "tkv-bp-0123456789")):
        for action in ("kill", "revive", "drill", "mint", "registry_edit"):
            with pytest.raises(oa.OperatorRefused) as e:
                oa.authenticate(H(who, key), action)
            assert e.value.status == 403, (who, action)


def test_may_attribute_is_confined_to_the_rows_event_prefixes(enforce):
    reg_id = oa.authenticate(H("svc-registry", KEY_REG), "ledger_attribute")
    assert reg_id.may_attribute("registry.status_changed")
    assert not reg_id.may_attribute("kill.agent")
    assert not reg_id.may_attribute("Registry.status_changed")
    assert not reg_id.may_attribute("operator.mode_changed")
    don = oa.authenticate(H("don", KEY_DON), "kill")
    assert not don.may_attribute("registry.status_changed")     # "*" is not ledger_attribute
    no_scope = oa.OperatorAuth(oa.ENFORCE, operator_id="x", scopes=("kill",),
                               event_prefixes=("registry.",))
    assert not no_scope.may_attribute("registry.status_changed")
    unauth = oa.OperatorAuth(oa.ENFORCE, scopes=("ledger_attribute",), event_prefixes=("registry.",))
    assert not unauth.may_attribute("registry.status_changed")
    sneaky = oa.OperatorAuth(oa.ENFORCE, operator_id="x", scopes=("ledger_attribute",),
                             event_prefixes=("operator.", "Operator."))   # cannot load; still refused
    for et in ("operator.mode_changed", "Operator.mode_changed"):
        assert not sneaky.may_attribute(et)


FORGED = {"operator_id_authenticated": "don", "operator_claimed": "don",
          "operator_key_fp": "abcd1234", "operator_body_claimed": "x"}


@pytest.mark.parametrize("mode_env", ["log-only", "enforce"])
def test_admit_keeps_reserved_keys_only_within_the_attributing_reach(monkeypatch, reg, mode_env):
    if mode_env == "enforce":
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    p = {"x": 1, **FORGED, "nested": {"operator_id_authenticated": "don"}}
    assert oa.admit_ledger_event("registry.status_changed", p, H("svc-registry", KEY_REG)) is p
    stripped = {"x": 1, "nested": {}}
    assert oa.admit_ledger_event("kill.agent", p, H("svc-registry", KEY_REG)) == stripped
    assert oa.admit_ledger_event("registry.x", p, H("don", KEY_DON)) == stripped
    assert oa.admit_ledger_event("registry.x", p, {}) == stripped
    assert oa.admit_ledger_event("registry.x", p, H("svc-registry", "tkv-wrong-0123")) == stripped
    assert oa.admit_ledger_event("kill.agent", p, H("svc-killswitch", KEY_KS)) is p
    # bypass_operator_list does not attribute
    assert oa.admit_ledger_event("kill.agent", p, H("don-breakglass", KEY_BG)) == stripped
    # malformed credential headers never refuse an append: just not attributed
    assert oa.admit_ledger_event("registry.x", p, H("bad id!", KEY_REG)) == stripped


@pytest.mark.parametrize("et", ["operator.mode_changed", "operator.registry_changed", "operator.x",
                                "Operator.unauthenticated", " operator.unauthenticated",
                                "operator.unauthenticated ", "OPERATOR.REFUSED"])
@pytest.mark.parametrize("who", ["none", "don", "svc-registry", "svc-killswitch"])
def test_admit_refuses_every_other_operator_type_from_every_caller(enforce, et, who):
    h = {"none": {}, "don": H("don", KEY_DON), "svc-registry": H("svc-registry", KEY_REG),
         "svc-killswitch": H("svc-killswitch", KEY_KS)}[who]
    with pytest.raises(oa.OperatorRefused) as e:
        oa.admit_ledger_event(et, {"a": 1}, h)
    assert (e.value.status, e.value.detail) == (403, oa.FORBIDDEN_DETAIL)


def test_self_reportable_types_are_exactly_the_two_guard_records():
    assert oa.SELF_REPORTABLE_EVENT_TYPES == {"operator.unauthenticated", "operator.refused"}


@pytest.mark.parametrize("et", ["operator.refused", "operator.unauthenticated"])
def test_admit_accepts_self_reported_records_from_any_caller(enforce, et):
    p = {"action": "kill", "claimed_id": "don", "self_reported": False, **FORGED}
    out = oa.admit_ledger_event(et, p, {})
    assert out == {"action": "kill", "claimed_id": "don", "self_reported": True}
    assert oa.admit_ledger_event(et, p, H("don", KEY_DON))["self_reported"] is True
    attributed = oa.admit_ledger_event(et, p, H("svc-registry", KEY_REG))
    assert attributed == {"action": "kill", "claimed_id": "don", "self_reported": False}
    assert p["self_reported"] is False and "operator_claimed" in p    # input not mutated


def test_admit_self_reported_record_survives_an_unusable_registry(enforce):
    enforce.write_text("garbage", encoding="utf-8")
    out = oa.admit_ledger_event("operator.unauthenticated", {"claimed_id": "don"},
                                H("svc-registry", KEY_REG))
    assert out == {"claimed_id": "don", "self_reported": True}


def test_admit_does_not_read_the_registry_for_an_ordinary_event(reg, monkeypatch):
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")

    def boom(*a, **k):
        raise AssertionError("registry read on the hot path")

    monkeypatch.setattr(oa, "load_registry", boom)
    p = {"x": 1, "deep": [{"y": 2}]}
    assert oa.admit_ledger_event("kill.agent", p, H("svc-killswitch", KEY_KS)) is p


def test_admit_flags_off_is_byte_identical():
    p = {"x": 1, **FORGED}
    assert oa.admit_ledger_event("registry.x", p, {}) is p
    assert oa.admit_ledger_event("operator.mode_changed", p, {}) is p


def test_admit_logs_attribution_loss_once(enforce, caplog):
    caplog.set_level(logging.WARNING, logger="field_core.operator_auth")
    oa.admit_ledger_event("registry.x", dict(FORGED), {})
    oa.admit_ledger_event("registry.x", dict(FORGED), {})
    assert len([r for r in caplog.records if "attribution LOST" in r.getMessage()]) == 1


def _fake_manifest(listed):
    return SimpleNamespace(enforcement=SimpleNamespace(
        kill_switch=SimpleNamespace(authorized_operators=listed)))


def test_bypass_operator_list_exempts_and_ledger_attribute_does_not(enforce, monkeypatch):
    import field_core.clients as clients

    monkeypatch.setattr(clients, "resolve_manifest_detail",
                        lambda ref, manifest_dir=None: (_fake_manifest(["Someone Else"]), "ok"))
    ks = oa.authenticate(H("svc-killswitch", KEY_KS), "kill")
    oa.check_record_authorized(ks, "manifests/x.yaml")             # bypass: no raise
    bg = oa.authenticate(H("don-breakglass", KEY_BG), "kill")
    oa.check_record_authorized(bg, "manifests/x.yaml")
    don = oa.authenticate(H("don", KEY_DON), "kill")
    with pytest.raises(oa.OperatorRefused) as e:
        oa.check_record_authorized(don, "manifests/x.yaml")
    assert e.value.status == 403
    attr_only = oa.OperatorAuth(oa.ENFORCE, operator_id="svc-registry",
                                scopes=("kill", "ledger_attribute"), event_prefixes=("registry.",))
    with pytest.raises(oa.OperatorRefused) as e2:
        oa.check_record_authorized(attr_only, "manifests/x.yaml")
    assert e2.value.status == 403
