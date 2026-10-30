"""Key rotation slice R1: operators file format 2 (design
tasks/key-rotation-design-2026-10-27.md sections 2.1, 2.2, 2.4).

Every key below is an obviously fake test value. Each rule test names the
rule it pins; the mutation run that turns each red is listed in the PR body
(one mutant per rule)."""

from __future__ import annotations

import copy
import json
import os

import pytest

from field_core import operator_auth as oa

K_DON = "fok_test-don-current-not-a-real-key"
K_KS = "fok_test-killswitch-current-not-a-real-key"
K_KS_NEXT = "fok_test-killswitch-next-not-a-real-key"
K_BG = "fok_test-breakglass-not-a-real-key"
K_OLD = "fok_test-revoked-not-a-real-key"

T0 = oa.parse_time("2026-11-20T03:00:00Z")       # the test "now"
EXPIRY = "2027-01-09T01:15:00Z"                 # CURRENT keys end here
NB = "2026-11-20T03:07:09Z"                     # NEXT window start
NA = "2027-02-03T03:12:09Z"                     # NEXT window end


def h(key: str) -> str:
    return oa.key_sha256(key)


def doc() -> dict:
    return {
        "format": 2, "generation": 41, "issued_at": "2026-11-20T03:12:09Z",
        "issued_by": "svc-rotator-gb10",
        "operators": [
            {"operator_id": "don", "status": "active", "scopes": ["*"],
             "names": ["Don Hagell"], "created_at": "2026-10-26T01:15:00Z",
             "rotation": "auto", "key_sha256": h(K_DON),
             "key_created_at": "2026-10-26T01:15:00Z", "key_not_after": EXPIRY},
            {"operator_id": "svc-killswitch", "status": "active",
             "scopes": ["kill", "revive", "drill", "bypass_operator_list", "ledger_attribute"],
             "names": [], "event_prefixes": ["kill."], "created_at": "2026-10-26T01:15:00Z",
             "rotation": "auto", "key_sha256": h(K_KS),
             "key_created_at": "2026-10-26T01:15:00Z", "key_not_after": EXPIRY,
             "next_key": {"key_sha256": h(K_KS_NEXT), "not_before": NB, "not_after": NA}},
            {"operator_id": "don-breakglass", "status": "active",
             "scopes": ["kill", "revive", "bypass_operator_list"],
             "rotation": "sealed", "key_sha256": h(K_BG)},
            {"operator_id": "old", "status": "revoked", "scopes": ["*"],
             "rotation": "auto", "key_sha256": h(K_OLD), "key_not_after": EXPIRY},
        ]}


def row(d: dict, oid: str) -> dict:
    return next(r for r in d["operators"] if r["operator_id"] == oid)


def unavailable(d, *, require_active=True) -> str:
    with pytest.raises(oa.RegistryUnavailable) as e:
        oa.parse_registry(d, require_active=require_active)
    msg = str(e.value)
    for key in (K_DON, K_KS, K_KS_NEXT, K_BG, K_OLD):
        assert h(key) not in msg and key not in msg      # never a hash or a key
    return msg


def H(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv(oa.ENV_REQUIRE, raising=False)
    monkeypatch.delenv(oa.ENV_REGISTRY, raising=False)
    monkeypatch.setattr(oa, "clock", lambda: T0)
    oa.reset_retired_memory()
    yield
    oa.reset_retired_memory()


@pytest.fixture()
def enforce_file(tmp_path, monkeypatch):
    """Write a document as the ENFORCE registry; returns the writer."""
    p = tmp_path / "operators.json"

    def write(d):
        p.write_text(json.dumps(d), encoding="utf-8")
        return p

    write(doc())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    return write


def ok(op, key, action="kill"):
    return oa.authenticate(H(op, key), action).authenticated


def refused(op, key, action="kill", status=403):
    with pytest.raises(oa.OperatorRefused) as e:
        oa.authenticate(H(op, key), action)
    assert e.value.status == status
    return True


# ---------------------------------------------------------------- the good file

def test_valid_format2_parses_with_slots():
    d = oa.parse_registry_doc(doc(), require_active=True)
    assert (d.format, d.generation, d.issued_by) == (2, 41, "svc-rotator-gb10")
    assert d.issued_at == oa.parse_time("2026-11-20T03:12:09Z")
    ks = next(r for r in d.rows if r["operator_id"] == "svc-killswitch")
    assert ks["key_not_after"] == oa.parse_time(EXPIRY)
    assert ks["next_key"] == {"key_sha256": h(K_KS_NEXT), "not_before": oa.parse_time(NB),
                              "not_after": oa.parse_time(NA)}
    assert ks["auth"] == ("key",) and ks["rotation"] == "auto"
    bg = next(r for r in d.rows if r["operator_id"] == "don-breakglass")
    assert bg["key_not_after"] is None and bg["next_key"] is None


def test_parse_time_is_strict():
    assert oa.parse_time("2026-11-20T03:12:09Z") == 1795144329
    assert oa.format_time(1795144329) == "2026-11-20T03:12:09Z"
    for bad in ("2026-11-20T03:12:09+00:00", "2026-11-20 03:12:09Z", "2026-11-20T03:12:09.5Z",
                "2026-02-30T00:00:00Z", "2026-1-05T03:12:09Z", "２026-11-20T03:12:09Z",
                "2026-11-20T03:12:09Z\n", 1795144329, None):
        assert oa.parse_time(bad) is None, bad


# ------------------------------------------------------------- format 1 unchanged

F1_ROWS = [
    {"operator_id": "don", "key_sha256": h(K_DON), "status": "active",
     "created_at": "2026-10-01", "scopes": ["*"], "names": ["Don Hagell"]},
    {"operator_id": "old", "key_sha256": h(K_OLD), "status": "revoked",
     "created_at": "2026-10-01", "scopes": ["*"], "unknown_field": "ignored as before"},
]


def test_format1_rows_are_exactly_as_before():
    want = [
        {"operator_id": "don", "key_sha256": h(K_DON), "status": "active", "scopes": ("*",),
         "names": ("Don Hagell",), "event_prefixes": ()},
        {"operator_id": "old", "key_sha256": h(K_OLD), "status": "revoked", "scopes": ("*",),
         "names": (), "event_prefixes": ()},
    ]
    for raw in (F1_ROWS, {"operators": F1_ROWS}, {"operators": F1_ROWS, "comment": "x"},
                {"format": 1, "operators": F1_ROWS}):
        d = oa.parse_registry_doc(copy.deepcopy(raw), require_active=True)
        assert (d.format, d.generation) == (1, 0)
        assert d.rows == want
        assert oa.parse_registry(copy.deepcopy(raw)) == want


def test_format1_authenticates_without_expiry(tmp_path, monkeypatch):
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(F1_ROWS), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    monkeypatch.setattr(oa, "clock", lambda: 4102444800)    # 2100: format 1 has no expiry
    assert ok("don", K_DON)
    refused("old", K_OLD)


@pytest.mark.parametrize("value", ["2", 2.0, True, 3, 0, None, [2]])
def test_rule_format_must_be_the_integer_1_or_2(value):
    """A format value that is not exactly 1 or 2 never falls back to lenient
    format 1 reading (that would drop every expiry)."""
    assert "format must be" in unavailable({"format": value, "operators": F1_ROWS})
    d = doc()
    d["format"] = value
    unavailable(d)


@pytest.mark.parametrize("field,value", [("next_key", {"key_sha256": "a" * 64,
                                                       "not_before": NB, "not_after": NA}),
                                         ("key_not_after", EXPIRY), ("rotation", "auto"),
                                         ("auth", ["key"]), ("passkeys", []),
                                         ("key_created_at", EXPIRY)])
def test_rule_format2_row_fields_need_format_2(field, value):
    rows = copy.deepcopy(F1_ROWS)
    rows[0][field] = value
    assert "need" in unavailable(rows)
    assert "need" in unavailable({"operators": rows})


@pytest.mark.parametrize("field", ["generation", "issued_at", "issued_by"])
def test_rule_format2_top_fields_need_format_2(field):
    assert "need" in unavailable({"operators": F1_ROWS, field: 1})


# ---------------------------------------------------------------- closed schema

def test_rule_unknown_top_level_field_refused():
    d = doc()
    d["comment"] = "not allowed in format 2"
    assert "unknown top-level" in unavailable(d)
    d = doc()
    d[K_DON] = 1                                  # a key used as a field name is not echoed
    assert "unknown top-level" in unavailable(d)


@pytest.mark.parametrize("field", ["generation", "operators"])
def test_rule_required_top_level_fields(field):
    d = doc()
    del d[field]
    unavailable(d)


@pytest.mark.parametrize("value", [0, -1, True, "41", 41.0, None])
def test_rule_generation_is_an_integer_from_1(value):
    d = doc()
    d["generation"] = value
    assert "generation" in unavailable(d)


def test_rule_issued_fields_are_checked():
    d = doc()
    d["issued_at"] = "2026-11-20T03:12:09+00:00"
    assert "issued_at" in unavailable(d)
    d = doc()
    d["issued_by"] = K_DON
    assert "issued_by" in unavailable(d)


def test_rule_unknown_row_field_refused():
    d = doc()
    row(d, "don")["notes"] = "x"
    assert "unknown field" in unavailable(d)


@pytest.mark.parametrize("field", ["operator_id", "status", "key_sha256", "rotation", "scopes"])
def test_rule_required_row_fields(field):
    d = doc()
    del row(d, "don")[field]
    unavailable(d)


@pytest.mark.parametrize("oid", [K_DON, "Don Hagell", "a" * 65, "x" * 44])
def test_rule_operator_id_is_a_printable_id(oid):
    d = doc()
    row(d, "don")["operator_id"] = oid
    msg = unavailable(d)
    assert oid not in msg or oid == "Don Hagell"


def test_rule_rotation_values():
    d = doc()
    row(d, "don")["rotation"] = "manual"
    assert "rotation" in unavailable(d)


def test_rule_scopes_are_known_actions():
    d = doc()
    row(d, "don")["scopes"] = ["kil"]
    assert "known actions" in unavailable(d)
    d = doc()
    row(d, "don")["scopes"] = ["assert_operator"]
    assert "no longer accepted" in unavailable(d)


@pytest.mark.parametrize("field", ["created_at", "key_created_at", "key_not_after"])
def test_rule_row_times_are_strict(field):
    d = doc()
    row(d, "don")[field] = "2026-10-26T01:15:00+00:00"
    assert field in unavailable(d)


def test_format1_style_bad_values_still_refused_in_format2():
    for field, value in (("status", "Active"), ("key_sha256", h(K_DON).upper()),
                         ("names", "Don"), ("event_prefixes", ["operator."])):
        d = doc()
        row(d, "don")[field] = value
        unavailable(d)


# ------------------------------------------------------------------- key slots

@pytest.mark.parametrize("oid", ["don", "old"])
def test_rule_key_not_after_is_mandatory(oid):
    d = doc()
    del row(d, oid)["key_not_after"]
    assert "key_not_after is required" in unavailable(d)


def test_rule_next_key_exact_fields():
    for change in ({"extra": 1}, None):
        d = doc()
        nk = row(d, "svc-killswitch")["next_key"]
        if change:
            nk.update(change)
        else:
            del nk["not_after"]
        assert "next_key must have exactly" in unavailable(d)
    d = doc()
    row(d, "svc-killswitch")["next_key"] = [h(K_KS_NEXT), NB, NA]
    unavailable(d)


def test_rule_next_key_hash_is_lower_hex():
    d = doc()
    row(d, "svc-killswitch")["next_key"]["key_sha256"] = h(K_KS_NEXT).upper()
    assert "next_key.key_sha256" in unavailable(d)


def test_rule_next_key_times_strict_and_ordered():
    d = doc()
    row(d, "svc-killswitch")["next_key"]["not_before"] = "2026-11-20"
    unavailable(d)
    d = doc()
    row(d, "svc-killswitch")["next_key"]["not_before"] = NA
    assert "before not_after" in unavailable(d)
    d = doc()
    row(d, "svc-killswitch")["next_key"]["not_after"] = "2026-11-01T00:00:00Z"
    assert "before not_after" in unavailable(d)


def test_rule_no_next_key_on_a_revoked_row():
    d = doc()
    row(d, "old")["next_key"] = {"key_sha256": "b" * 64, "not_before": NB, "not_after": NA}
    assert "revoked row has no next_key" in unavailable(d)


# ------------------------------------------------------------ duplicate hashes

def test_rule_duplicate_hash_across_rows():
    d = doc()
    row(d, "old")["key_sha256"] = h(K_DON)              # also covers a revoked row
    assert "appears twice" in unavailable(d)


def test_rule_duplicate_hash_current_vs_another_rows_next():
    d = doc()
    row(d, "don")["key_sha256"] = h(K_KS_NEXT)
    assert "appears twice" in unavailable(d)


def test_rule_next_key_differs_from_current():
    d = doc()
    row(d, "svc-killswitch")["next_key"]["key_sha256"] = h(K_KS)
    assert "same hash in both slots" in unavailable(d)


def test_format1_keeps_allowing_a_shared_hash():
    """Format 1 is unchanged: the duplicate-hash rule is format 2 only."""
    rows = copy.deepcopy(F1_ROWS)
    rows[1]["key_sha256"] = rows[0]["key_sha256"]
    assert len(oa.parse_registry(rows)) == 2


# ------------------------------------------------------------------ sealed row

def test_rule_at_most_one_sealed_row():
    d = doc()
    r = row(d, "old")
    r["rotation"] = "sealed"
    r["scopes"] = ["kill"]
    del r["key_not_after"]
    assert "more than one sealed row" in unavailable(d)


@pytest.mark.parametrize("rotation", ["auto", "remote"])
def test_rule_the_breakglass_id_must_be_a_sealed_row(rotation):
    """C-34 finding 1 (proven): the literal id was accepted as an ordinary row
    (scopes '*', key+session, next_key, expiry) while is_breakglass() still
    treated it as break-glass."""
    d = doc()
    r = row(d, "don-breakglass")
    r["rotation"] = rotation
    r["scopes"] = ["*"]
    r["auth"] = ["key", "session"]
    r["key_not_after"] = EXPIRY
    r["next_key"] = {"key_sha256": h(K_KS_NEXT), "not_before": NB, "not_after": NA}
    assert "break-glass identity" in unavailable(d)


def test_rule_a_revoked_breakglass_id_must_still_be_a_sealed_row():
    d = doc()
    r = row(d, "don-breakglass")
    r["rotation"] = "auto"
    r["status"] = "revoked"
    r["key_not_after"] = EXPIRY
    assert "break-glass identity" in unavailable(d)


def test_rule_the_breakglass_id_is_not_an_alias_of_another_row():
    """C-76 alias squat (proven): with no break-glass row in the file, an ordinary row could
    carry names: ['don-breakglass'] and satisfy a list naming the break-glass identity."""
    d = doc()
    d["operators"] = [r for r in d["operators"] if r["operator_id"] != "don-breakglass"]
    row(d, "don")["names"] = ["Don Hagell", "don-breakglass"]
    assert "break-glass identity alone" in unavailable(d)


def test_rule_the_breakglass_alias_is_refused_next_to_the_real_row_too():
    d = doc()
    row(d, "svc-killswitch")["names"] = ["don-breakglass"]
    assert "break-glass identity alone" in unavailable(d)


def test_the_sealed_breakglass_row_is_still_accepted():
    assert oa.parse_registry(doc(), require_active=True) is not None


@pytest.mark.parametrize("scopes", [["*"], ["kill", "mint"], ["drill"]])
def test_rule_sealed_scopes_subset(scopes):
    d = doc()
    row(d, "don-breakglass")["scopes"] = scopes
    assert "subset" in unavailable(d)


def test_rule_sealed_row_has_no_expiry():
    d = doc()
    row(d, "don-breakglass")["key_not_after"] = EXPIRY
    assert "sealed row has no expiry" in unavailable(d)


def test_rule_sealed_row_key_only():
    d = doc()
    row(d, "don-breakglass")["auth"] = ["key", "session"]
    assert "by key only" in unavailable(d)
    d = doc()
    row(d, "don-breakglass")["auth"] = ["key"]
    assert oa.parse_registry(d)                       # explicit key-only is fine


def test_rule_sealed_row_no_next_key():
    d = doc()
    row(d, "don-breakglass")["next_key"] = {"key_sha256": "c" * 64, "not_before": NB,
                                            "not_after": NA}
    assert "sealed row has no next_key" in unavailable(d)


def test_rule_sealed_row_no_passkeys():
    d = doc()
    row(d, "don-breakglass")["passkeys"] = []
    assert "sealed row has no passkeys" in unavailable(d)


# ------------------------------------------------------- auth and credentials

def passkey(cid="cred-AAAAAAAAAAAAAAAA", **kw):
    pk = {"credential_id": cid, "public_key_spki": "M" * 60, "alg": "ES256",
          "enrolled_at": "2026-11-01T00:00:00Z", "label": "rog-command Windows Hello",
          "hardware": False}
    pk.update(kw)
    return pk


@pytest.mark.parametrize("value", [[], ["password"], ["key", "key"], "key"])
def test_rule_auth_values(value):
    d = doc()
    row(d, "don")["auth"] = value
    assert "auth must be" in unavailable(d)


def test_passkeys_shape_accepted():
    d = doc()
    row(d, "don")["auth"] = ["key", "session"]
    row(d, "don")["passkeys"] = [passkey()]
    r = next(x for x in oa.parse_registry(d) if x["operator_id"] == "don")
    assert r["auth"] == ("key", "session") and len(r["passkeys"]) == 1


def test_rule_duplicate_credential_id():
    d = doc()
    row(d, "don")["passkeys"] = [passkey()]
    row(d, "svc-killswitch")["passkeys"] = [passkey()]
    assert "credential_id appears twice" in unavailable(d)
    d = doc()
    row(d, "don")["passkeys"] = [passkey(), passkey()]
    assert "credential_id appears twice" in unavailable(d)


@pytest.mark.parametrize("bad", [
    {"alg": "RS256"}, {"hardware": "yes"}, {"hardware": 1}, {"credential_id": "short"},
    {"credential_id": K_DON + "!"}, {"public_key_spki": "-----BEGIN"},
    {"enrolled_at": "2026-11-01"}, {"label": "fok_looks-like-a-key"}, {"label": ""}])
def test_rule_passkey_fields(bad):
    d = doc()
    row(d, "don")["passkeys"] = [passkey(**bad)]
    assert "passkey" in unavailable(d)


def test_rule_passkey_exact_fields():
    d = doc()
    pk = passkey()
    pk["private_key"] = "never"
    row(d, "don")["passkeys"] = [pk]
    assert "exactly the fields" in unavailable(d)
    d = doc()
    pk = passkey()
    del pk["label"]
    row(d, "don")["passkeys"] = [pk]
    assert "exactly the fields" in unavailable(d)


def test_require_active_still_applies():
    d = doc()
    for r in d["operators"]:
        r["status"] = "revoked"
        r.pop("next_key", None)
    assert "no active rows" in unavailable(d)
    assert len(oa.parse_registry(d, require_active=False)) == 4


def test_one_bad_row_makes_the_whole_file_unavailable(enforce_file):
    assert ok("don", K_DON)
    d = doc()
    row(d, "old")["key_not_after"] = "soon"
    enforce_file(d)
    refused("don", K_DON, status=503)


# ------------------------------------------------------------- authentication

def test_current_key_valid_until_key_not_after(enforce_file, monkeypatch):
    assert ok("don", K_DON)
    end = oa.parse_time(EXPIRY)
    monkeypatch.setattr(oa, "clock", lambda: end - 1)
    assert ok("don", K_DON)
    monkeypatch.setattr(oa, "clock", lambda: end)
    refused("don", K_DON)
    monkeypatch.setattr(oa, "clock", lambda: end + 86400)
    refused("don", K_DON)


def test_next_key_only_inside_its_window(enforce_file, monkeypatch):
    nb, na = oa.parse_time(NB), oa.parse_time(NA)
    monkeypatch.setattr(oa, "clock", lambda: nb - 1)
    refused("svc-killswitch", K_KS_NEXT)                 # before not_before
    monkeypatch.setattr(oa, "clock", lambda: nb)
    assert ok("svc-killswitch", K_KS_NEXT)
    monkeypatch.setattr(oa, "clock", lambda: na - 1)
    assert ok("svc-killswitch", K_KS_NEXT)
    monkeypatch.setattr(oa, "clock", lambda: na)
    refused("svc-killswitch", K_KS_NEXT)                 # at not_after


def test_overlap_both_keys_valid(enforce_file, monkeypatch):
    monkeypatch.setattr(oa, "clock", lambda: oa.parse_time(NB) + 60)
    a = oa.authenticate(H("svc-killswitch", K_KS), "kill")
    b = oa.authenticate(H("svc-killswitch", K_KS_NEXT), "kill")
    assert a.operator_id == b.operator_id == "svc-killswitch"
    # the ledger fingerprint shows WHICH key acted
    assert a.key_fp == h(K_KS)[:8] and b.key_fp == h(K_KS_NEXT)[:8]
    assert b.scopes == a.scopes


def test_next_key_is_bound_to_its_own_id(enforce_file, monkeypatch):
    monkeypatch.setattr(oa, "clock", lambda: oa.parse_time(NB) + 60)
    refused("don", K_KS_NEXT)


def test_revoked_row_refuses_every_slot(enforce_file, monkeypatch):
    refused("old", K_OLD)
    # a row the parser would refuse (next_key on a revoked row) still never
    # authenticates by either slot: the status check covers both
    monkeypatch.setattr(oa, "clock", lambda: oa.parse_time(NB) + 60)
    rows = oa.parse_registry(doc())
    ks = next(r for r in rows if r["operator_id"] == "svc-killswitch")
    ks["status"] = "revoked"
    for key in (K_KS, K_KS_NEXT):
        assert oa._verify("svc-killswitch", key, rows)[0] is False


def test_sealed_row_has_no_expiry(enforce_file, monkeypatch):
    monkeypatch.setattr(oa, "clock", lambda: 4102444800)        # 2100
    assert ok("don-breakglass", K_BG)
    refused("don", K_DON)


def test_auth_without_key_refuses_the_bearer_key(enforce_file):
    d = doc()
    row(d, "don")["auth"] = ["session"]
    row(d, "don")["passkeys"] = [passkey()]
    enforce_file(d)
    refused("don", K_DON)
    assert ok("svc-killswitch", K_KS)


def test_log_only_reports_an_expired_key_as_bad_credential(enforce_file, monkeypatch):
    monkeypatch.delenv(oa.ENV_REQUIRE)
    monkeypatch.setattr(oa, "clock", lambda: oa.parse_time(EXPIRY))
    a = oa.authenticate(H("don", K_DON), "kill")
    assert not a.authenticated and a.failure == "bad_credential"


def test_every_slot_of_every_row_is_compared(enforce_file, monkeypatch):
    """No timing oracle and no early exit: the same number of constant-time
    compares (id + CURRENT + NEXT per row, NEXT against a dummy when the row
    has none) for an unknown id, a wrong key, a CURRENT match and a NEXT
    match."""
    monkeypatch.setattr(oa, "clock", lambda: oa.parse_time(NB) + 60)
    calls = []
    real = oa.hmac.compare_digest
    monkeypatch.setattr(oa.hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    counts = []
    for op, key, good in (("nobody", "fok_x", False), ("don", "fok_x", False),
                          ("don", K_DON, True), ("svc-killswitch", K_KS, True),
                          ("svc-killswitch", K_KS_NEXT, True)):
        calls.clear()
        if good:
            assert ok(op, key)
        else:
            refused(op, key)
        counts.append(len(calls))
    assert counts == [3 * len(doc()["operators"])] * 5


# ------------------------------------------------------ retired-hash memory

def _rotated(d, generation):
    """The file after svc-killswitch's rotation: NEXT promoted to CURRENT and
    the old CURRENT removed (retired)."""
    d = copy.deepcopy(d)
    d["generation"] = generation
    ks = row(d, "svc-killswitch")
    ks["key_sha256"] = ks.pop("next_key")["key_sha256"]
    return d


def test_retired_hash_back_in_an_older_file_is_refused_alone(enforce_file, monkeypatch):
    monkeypatch.setattr(oa, "clock", lambda: oa.parse_time(NB) + 60)
    old = doc()                                           # generation 41
    assert ok("svc-killswitch", K_KS)
    enforce_file(_rotated(old, 42))
    assert ok("svc-killswitch", K_KS_NEXT)
    refused("svc-killswitch", K_KS)                       # gone from the file anyway
    enforce_file(old)                                     # a restored backup, generation 41
    refused("svc-killswitch", K_KS)                       # the retired key: 403, never 503
    assert ok("svc-killswitch", K_KS_NEXT)               # the rest of the file still works
    assert ok("don", K_DON)
    assert oa.retired_hash_seen == 1
    refused("svc-killswitch", K_KS)                       # counted once per sighting
    assert oa.retired_hash_seen == 1


def test_retired_hash_refused_at_the_same_generation(enforce_file):
    """Stricter than the design text ("lower"): a file at the SAME generation
    that removed the hash is a conflicting copy, so the hash stays refused."""
    old = doc()
    assert ok("svc-killswitch", K_KS)
    enforce_file(_rotated(old, 42))
    assert ok("don", K_DON)
    same = copy.deepcopy(old)
    same["generation"] = 42
    enforce_file(same)
    refused("svc-killswitch", K_KS)


def test_retired_hash_readded_at_a_higher_generation_is_accepted(enforce_file):
    old = doc()
    assert ok("svc-killswitch", K_KS)
    enforce_file(_rotated(old, 42))
    assert ok("don", K_DON)
    newer = copy.deepcopy(old)
    newer["generation"] = 43
    enforce_file(newer)
    assert ok("svc-killswitch", K_KS)


def test_retired_next_hash_back_in_an_older_file_is_refused_alone(enforce_file, monkeypatch):
    """Review F1: PUBLISH at generation N adds NEXT; --abort-inflight writes N+1
    without it (how the design revokes a compromised NEXT, 2.1). A restored
    copy of N (a stale .prev, a backup) must not bring that NEXT back, while
    CURRENT keeps working."""
    monkeypatch.setattr(oa, "clock", lambda: oa.parse_time(NB) + 60)
    published = doc()                                     # generation 41, NEXT present
    assert ok("svc-killswitch", K_KS_NEXT)
    aborted = copy.deepcopy(published)
    aborted["generation"] = 42
    del row(aborted, "svc-killswitch")["next_key"]
    enforce_file(aborted)
    assert ok("svc-killswitch", K_KS)
    refused("svc-killswitch", K_KS_NEXT)                  # gone from the file anyway
    enforce_file(published)                               # the restored generation 41
    refused("svc-killswitch", K_KS_NEXT)                  # the retired NEXT: 403, never 503
    assert ok("svc-killswitch", K_KS)                     # CURRENT still works
    assert ok("don", K_DON)
    assert oa.retired_hash_seen == 1


K_B = "fok_test-killswitch-b-not-a-real-key"
K_C = "fok_test-killswitch-c-not-a-real-key"
K_D = "fok_test-killswitch-d-not-a-real-key"


def _ks_file(generation, key):
    """doc() at ``generation`` with svc-killswitch holding ``key`` alone."""
    d = doc()
    d["generation"] = generation
    ks = row(d, "svc-killswitch")
    ks["key_sha256"] = h(key)
    del ks["next_key"]
    return d


def test_retired_against_the_highest_generation_seen(enforce_file):
    """Review F3(a): gen 5 {A,B}, restored gen 3 {A,C}, gen 6 {A,D}, restored
    gen 5 {A,B}. B stays refused (gen 6 removed it relative to gen 5, the
    highest generation seen before it), and C is refused in the gen 3 copy
    (the higher gen 5 had already dropped it). A (don) works throughout."""
    enforce_file(_ks_file(5, K_B))
    assert ok("svc-killswitch", K_B)
    enforce_file(_ks_file(3, K_C))
    refused("svc-killswitch", K_C)
    assert ok("don", K_DON)
    enforce_file(_ks_file(6, K_D))
    assert ok("svc-killswitch", K_D)
    enforce_file(_ks_file(5, K_B))
    refused("svc-killswitch", K_B)
    assert ok("don", K_DON)
    enforce_file(_ks_file(6, K_B))                        # a conflicting copy of gen 6
    refused("svc-killswitch", K_B)
    assert oa.retired_hash_seen == 3
    enforce_file(_ks_file(7, K_B))                        # re-added at a higher generation
    assert ok("svc-killswitch", K_B)


K_E = "fok_test-killswitch-e-not-a-real-key"


def test_highest_generation_advances_past_a_restore(enforce_file):
    """gen 5 {B}, gen 6 {D}, restored gen 4 {C}, gen 7 {E}, restored gen 6 {D}:
    the highest generation seen moves to 7 although the last load was gen 4,
    so gen 7 retires D and the restored gen 6 cannot bring it back."""
    enforce_file(_ks_file(5, K_B))
    assert ok("svc-killswitch", K_B)
    enforce_file(_ks_file(6, K_D))
    assert ok("svc-killswitch", K_D)
    enforce_file(_ks_file(4, K_C))
    refused("svc-killswitch", K_C)
    enforce_file(_ks_file(7, K_E))
    assert ok("svc-killswitch", K_E)
    enforce_file(_ks_file(6, K_D))
    refused("svc-killswitch", K_D)
    assert ok("don", K_DON)


def test_restoring_a_file_that_only_lacks_new_hashes_refuses_nothing(enforce_file, monkeypatch):
    """Design 4.4 step-4 auto-revert (the pre-PUBLISH file renamed back): the
    older file only LACKS the new NEXT hash, so every hash in it still
    authenticates and nothing is counted."""
    monkeypatch.setattr(oa, "clock", lambda: oa.parse_time(NB) + 60)
    published = doc()                                     # generation 41, NEXT present
    prev = copy.deepcopy(published)
    prev["generation"] = 40
    del row(prev, "svc-killswitch")["next_key"]
    enforce_file(prev)
    assert ok("svc-killswitch", K_KS)
    enforce_file(published)
    assert ok("svc-killswitch", K_KS_NEXT)
    enforce_file(prev)                                    # auto-revert
    assert ok("svc-killswitch", K_KS)
    assert ok("don", K_DON)
    assert ok("don-breakglass", K_BG)
    assert oa.retired_hash_seen == 0


def test_format1_remove_and_readd_never_retires(enforce_file):
    """Review F5(a): retiring needs a HIGHER generation. Every format 1 file is
    generation 0, so removing an operator and adding it back authenticates
    exactly as before this slice."""
    both = [{"operator_id": "don", "key_sha256": h(K_DON), "status": "active", "scopes": ["*"]},
            {"operator_id": "svc-killswitch", "key_sha256": h(K_KS), "status": "active",
             "scopes": ["kill"]}]
    enforce_file(both)
    assert ok("svc-killswitch", K_KS)
    enforce_file(both[:1])
    refused("svc-killswitch", K_KS)
    assert ok("don", K_DON)
    enforce_file(both)
    assert ok("svc-killswitch", K_KS)
    assert oa.retired_hash_seen == 0


def test_non_sealed_row_without_expiry_never_matches():
    """Review F5(b), defence in depth: the parser refuses a non-sealed format 2
    row without key_not_after, and if one reached the verifier anyway its
    CURRENT key would still never match."""
    rows = oa.parse_registry(doc())
    don = next(r for r in rows if r["operator_id"] == "don")
    assert oa._verify("don", K_DON, rows, now=T0)[0] is True
    don["key_not_after"] = None
    assert oa._verify("don", K_DON, rows, now=T0)[0] is False
    don.pop("key_not_after")
    assert oa._verify("don", K_DON, rows, now=T0)[0] is False


def test_retired_hash_in_a_format1_restore_is_refused(enforce_file):
    """Format 1 counts as generation 0 for the memory only; its parsing is
    unchanged."""
    assert ok("svc-killswitch", K_KS)
    enforce_file(_rotated(doc(), 42))
    assert ok("don", K_DON)
    enforce_file([{"operator_id": "svc-killswitch", "key_sha256": h(K_KS), "status": "active",
                   "scopes": ["kill"]},
                  {"operator_id": "don", "key_sha256": h(K_DON), "status": "active",
                   "scopes": ["*"]}])
    refused("svc-killswitch", K_KS)
    assert ok("don", K_DON)


def test_retired_memory_is_per_process_and_per_path(enforce_file, tmp_path):
    assert ok("svc-killswitch", K_KS)
    enforce_file(_rotated(doc(), 42))
    assert ok("don", K_DON)
    other = tmp_path / "other.json"
    other.write_text(json.dumps(doc()), encoding="utf-8")
    assert oa._verify("svc-killswitch", K_KS, oa.load_registry(str(other)))[0]
    oa.reset_retired_memory()                             # a restart forgets
    enforce_file(doc())
    assert ok("svc-killswitch", K_KS)


def test_pure_parse_has_no_memory(enforce_file):
    """parse_registry (keygen --check, /health) never applies the memory, even
    while the service's own load refuses a retired hash."""
    assert ok("svc-killswitch", K_KS)
    enforce_file(_rotated(doc(), 42))
    assert ok("don", K_DON)
    enforce_file(doc())
    refused("svc-killswitch", K_KS)
    assert all("refused_hashes" not in r for r in oa.parse_registry(doc()))


# --- C-178 (reviewer C-172): the loader, not only the pure parser ---------------------------


def _load(tmp_path, text: str, *, require_active=True):
    f = tmp_path / "operators.json"
    f.write_text(text, encoding="utf-8")
    return oa.load_registry(str(f), require_active=require_active)


def test_loader_refuses_a_shared_alias_through_load_registry(tmp_path):
    """F-C172-1 (PROVEN): the format-2 parser ends with `validate_rows`; with that call disabled a
    file whose alias is shared by two operators loaded. Pin it through the real loader."""
    d = doc()
    row(d, "svc-killswitch")["names"] = ["Don Hagell"]          # don already holds this alias
    with pytest.raises(oa.RegistryUnavailable) as e:
        _load(tmp_path, json.dumps(d))
    assert "ambiguous" in str(e.value) and "Don Hagell" in str(e.value)


def test_loader_refuses_a_duplicate_json_key_instead_of_last_wins(tmp_path):
    """F-C172-2: `"operator_id": "don", "operator_id": "mallory"` used to load as mallory."""
    text = json.dumps(doc()).replace('"operator_id": "don",',
                                     '"operator_id": "don", "operator_id": "mallory",', 1)
    assert text.count('"operator_id": "mallory"') == 1
    with pytest.raises(oa.RegistryUnavailable) as e:
        _load(tmp_path, text)
    assert "duplicate JSON key" in str(e.value) and "operator_id" in str(e.value)
    assert [r["operator_id"] for r in _load(tmp_path, json.dumps(doc()))][:1] == ["don"]


def test_loader_takes_the_designed_refusal_for_a_deeply_nested_file(tmp_path):
    """F-C172-3: 50,000 levels raised a bare RecursionError out of authenticate; it must be
    RegistryUnavailable (the 503 and C-15 log path), like every other undecodable file."""
    # Python 3.14 parses this depth without a RecursionError and the document is then refused as
    # malformed; 3.11-3.13 raise RecursionError in json.loads. Either way the designed refusal must
    # come out: a bare RecursionError (the catch removed) is not a RegistryUnavailable and errors here.
    with pytest.raises(oa.RegistryUnavailable):
        _load(tmp_path, "[" * 50000 + "]" * 50000)


def test_generation_one_is_the_smallest_accepted_and_zero_is_refused():
    d = doc()
    d["generation"] = 1
    assert oa.parse_registry(d)
    d["generation"] = 0
    assert "generation" in unavailable(d)


# --- C-51 (reviewer C-37): format 2 ambiguity rules through the format 2 parser -------------------
# The format 1 and shared-alias cases are pinned elsewhere (stage0, C-178); these three rules are
# only pinned for format 1, so a format 2 parser that stopped calling `validate_rows` for them
# (or called an older copy) would still pass the suite.


def test_format2_duplicate_operator_id_is_refused_as_ambiguous():
    d = doc()
    clone = copy.deepcopy(row(d, "don"))
    clone["names"] = []                                      # only the id repeats
    clone["key_sha256"] = h("fok_test-clone-not-a-real-key")  # a repeated hash would trip another rule first
    d["operators"].append(clone)
    msg = unavailable(d)
    assert "ambiguous" in msg and "duplicate operator_id 'don'" in msg


def test_format2_alias_equal_to_another_rows_id_is_refused_as_ambiguous():
    d = doc()
    row(d, "svc-killswitch")["names"] = ["don"]              # would let this row satisfy a list naming don
    msg = unavailable(d)
    assert "ambiguous" in msg and "equals an operator id" in msg


def test_format2_alias_star_is_refused_as_ambiguous():
    d = doc()
    row(d, "don")["names"] = ["*"]                           # would match a list that says "*"
    msg = unavailable(d)
    assert "ambiguous" in msg and "alias '*'" in msg


# --- C-51: MAX_RETIRED_HASHES boundary -------------------------------------------------------------


def _retired_of(path) -> dict:
    return oa._retired_state[os.path.abspath(str(path))]["retired"]


def _ks_generation(d: dict, n: int) -> dict:
    """The file at generation 41 + n, svc-killswitch holding its n-th current key (no NEXT)."""
    d = copy.deepcopy(d)
    d["generation"] = 41 + n
    ks = row(d, "svc-killswitch")
    ks.pop("next_key", None)
    ks["key_sha256"] = h(f"fok_test-ks-{n}-not-a-real-key")
    return d


def _load_chain(tmp_path, monkeypatch, cap, steps):
    monkeypatch.setattr(oa, "MAX_RETIRED_HASHES", cap)
    p = tmp_path / "operators.json"
    for n in range(steps + 1):
        p.write_text(json.dumps(_ks_generation(doc(), n)), encoding="utf-8")
        oa.load_registry(str(p))
    return p


def test_retired_memory_at_exactly_the_cap_keeps_every_entry(tmp_path, monkeypatch):
    p = _load_chain(tmp_path, monkeypatch, cap=2, steps=2)           # retires two hashes
    assert sorted(_retired_of(p).values()) == [42, 43]


def test_retired_memory_over_the_cap_drops_the_oldest_generation_first(tmp_path, monkeypatch):
    p = _load_chain(tmp_path, monkeypatch, cap=2, steps=3)           # retires three, room for two
    assert sorted(_retired_of(p).values()) == [43, 44]               # generation 42 was evicted
    assert h("fok_test-ks-0-not-a-real-key") not in _retired_of(p)


# --- C-922 (reviewer C-847 F-C847-3): the sighting counter stops at MAX_RETIRED_HASHES -------------------------


def _backup_at(generation):
    d = copy.deepcopy(doc())
    d["generation"] = generation
    return d


def _sightings(enforce_file, monkeypatch, cap, restores):
    monkeypatch.setattr(oa, "MAX_RETIRED_HASHES", cap)
    assert ok("svc-killswitch", K_KS)
    enforce_file(_rotated(doc(), 42))                    # svc-killswitch's old key is retired at generation 42
    assert ok("don", K_DON)
    for g in restores:                                   # the old key comes back in files at lower generations
        enforce_file(_backup_at(g))
        refused("svc-killswitch", K_KS)
    return oa.retired_hash_seen


def test_each_distinct_sighting_of_a_retired_hash_is_counted_up_to_the_cap(enforce_file, monkeypatch):
    assert _sightings(enforce_file, monkeypatch, cap=3, restores=[41, 40, 39]) == 3


def test_sightings_beyond_the_cap_are_not_counted(enforce_file, monkeypatch):
    """`_retired_seen` is bounded: with a cap of 2, the third distinct sighting is refused as before but no longer
    counted (and no further record is kept)."""
    assert _sightings(enforce_file, monkeypatch, cap=2, restores=[41, 40, 39, 38]) == 2


def test_the_same_sighting_is_counted_once(enforce_file, monkeypatch):
    assert _sightings(enforce_file, monkeypatch, cap=3, restores=[41, 41, 41]) == 1
