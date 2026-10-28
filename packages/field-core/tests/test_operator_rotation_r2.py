"""Key rotation slice R2 (design v0.2 sections 2.1, 3.4, 4.3, 5.1-5.3, 8 row 2; S3, S8,
S11, S12, O3): ``POST /operator/verify-hash``, the internal ``GET /operator/rotation-state``,
the open ``/health`` additions (format, generation, roster digest, break-glass counters;
never a hash), the break-glass counters in ``operator_auth.authenticate`` and the slot
witness the ledger's observer reads.

Test key values are throwaway constants; nothing here reads a real key or secret."""

from __future__ import annotations

import hashlib
import json
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from field_core import authn
from field_core import operator_auth as oa
from field_core import operator_health as oh

KEY_DON = "tkv-r2don-key-0123456789abcdef"
KEY_KS = "tkv-r2ks-key-0123456789abcdef"
KEY_KS_NEXT = "tkv-r2ksnext-key-0123456789abcdef"
KEY_BG = "tkv-r2bg-key-0123456789abcdef"
KEY_OTHER = "tkv-r2oth-key-0123456789abcdef"
SECRET = "tkv-r2-perimeter-0123456789"
ALL_KEYS = (KEY_DON, KEY_KS, KEY_KS_NEXT, KEY_BG, KEY_OTHER)

T0 = oa.parse_time("2026-11-20T03:00:00Z")
DAY = 86400
OLD_FIELDS = {
    "operator_mode", "operator_registry_sha256_prefix", "operator_registry_rows",
    "operator_identity_id", "identity_present", "last_registry_error",
    "dropped_unauthenticated_records", "refused_count", "dropped_refused_records",
}
R2_FIELDS = {"operator_registry_format", "operator_registry_generation", "operator_roster_sha16",
             "breakglass_auth_count", "breakglass_attempt_count"}


def H(key: str) -> str:
    return oa.key_sha256(key)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE, authn.ENV_VAR):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr(oa, "clock", lambda: float(T0))
    oa.reset_retired_memory()
    yield
    oa.reset_retired_memory()


def _t(epoch: int) -> str:
    return oa.format_time(epoch)


def doc2(generation=41, next_key=True, ks_created=True, bg=True, **over):
    ks = {"operator_id": "svc-killswitch", "status": "active", "rotation": "auto",
          "scopes": ["kill", "revive"], "names": [], "event_prefixes": ["kill."],
          "created_at": "2026-10-26T01:15:00Z", "key_sha256": H(KEY_KS),
          "key_not_after": _t(T0 + 30 * DAY)}
    if ks_created:
        ks["key_created_at"] = _t(T0 - 20 * DAY)
    if next_key:
        ks["next_key"] = {"key_sha256": H(KEY_KS_NEXT), "not_before": _t(T0 - 300),
                          "not_after": _t(T0 + 75 * DAY)}
    rows = [{"operator_id": "don", "status": "active", "rotation": "auto", "scopes": ["*"],
             "names": ["Don Hagell"], "key_sha256": H(KEY_DON),
             "key_created_at": _t(T0 - 40 * DAY), "key_not_after": _t(T0 + 10 * DAY)},
            ks]
    if bg:
        rows.append({"operator_id": "don-breakglass", "status": "active", "rotation": "sealed",
                     "scopes": ["kill", "revive"], "key_sha256": H(KEY_BG)})
    rows.append({"operator_id": "other", "status": "revoked", "rotation": "auto", "scopes": [],
                 "key_sha256": H(KEY_OTHER), "key_not_after": _t(T0 + 5 * DAY)})
    d = {"format": 2, "generation": generation, "issued_at": _t(T0 - 3600),
         "issued_by": "svc-rotator-gb10", "operators": rows}
    d.update(over)
    return d


def doc1():
    return [{"operator_id": "don", "key_sha256": H(KEY_DON), "status": "active",
             "created_at": "2026-10-26", "scopes": ["*"]},
            {"operator_id": "don-breakglass", "key_sha256": H(KEY_BG), "status": "active",
             "scopes": ["kill"]},
            {"operator_id": "svc-killswitch", "key_sha256": H(KEY_KS), "status": "active",
             "scopes": ["kill"]}]


def _write(tmp_path, data, name="operators.json"):
    p = tmp_path / name
    p.write_bytes(json.dumps(data).encode("utf-8"))
    return p


@pytest.fixture()
def armed(tmp_path, monkeypatch):
    """LOG-ONLY on a format 2 file plus a perimeter secret; returns (path, set_doc)."""
    p = _write(tmp_path, doc2())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(authn.ENV_VAR, SECRET)

    def set_doc(d):
        p.write_bytes(json.dumps(d).encode("utf-8"))
    return p, set_doc


class Ledger:
    def __init__(self):
        self.rows = []

    def append(self, event_type, payload, agent_id=None):
        self.rows.append((event_type, payload, agent_id))


def _app(ledger=None):
    app = FastAPI()
    authn.install(app)
    h = oh.install(app, ledger_getter=lambda a: ledger)

    @app.get("/health")
    def health():
        return {"ok": True, **h.health_fields()}

    return app, h


def _client(ledger=None):
    app, h = _app(ledger)
    return TestClient(app), h


def vh(client, operator_id, key_sha256, secret=SECRET, **extra):
    body = {"operator_id": operator_id, "key_sha256": key_sha256, **extra}
    return client.post(oh.VERIFY_HASH_PATH, content=json.dumps(body),
                       headers={authn.HEADER: secret} if secret else {})


def _no_hash(blob: str, keys=ALL_KEYS, prefix_len=8):
    for k in keys:
        assert k not in blob
        assert H(k) not in blob
        assert H(k)[:16] not in blob
        assert H(k)[:prefix_len] not in blob


# --- the open /health (C-8 + R2): only format, generation, roster digest, break-glass counters ---


def test_open_health_adds_exactly_the_five_r2_fields(armed):
    f = oh.OperatorHealth().health_fields()
    assert set(f) == OLD_FIELDS | R2_FIELDS
    assert f["operator_registry_format"] == 2 and f["operator_registry_generation"] == 41
    assert re.fullmatch(r"[0-9a-f]{16}", f["operator_roster_sha16"])
    assert f["operator_roster_sha16"] == oh.roster_sha256(doc2())[:16]
    assert f["breakglass_auth_count"] == oa.breakglass_auth_count
    assert f["breakglass_attempt_count"] == oa.breakglass_attempt_count


@pytest.mark.parametrize("enforce", [False, True])
def test_open_health_leaks_no_hash_or_prefix_of_one(armed, monkeypatch, enforce):
    """C-8, S12: no key, key hash or prefix of one (16 or 8 hex) on the open /health,
    in either armed mode, with a NEXT key and the sealed row present."""
    if enforce:
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-killswitch")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY_KS)
    client, _ = _client()
    r = client.get("/health")
    assert r.status_code == 200
    body = r.text
    _no_hash(body)
    assert set(oh.OperatorHealthFields.model_fields) == OLD_FIELDS | R2_FIELDS
    # every 16-hex value on the open block is the file digest or the roster digest
    hexes = set(re.findall(r"[0-9a-f]{16,}", body))
    assert hexes <= {r.json()["operator_registry_sha256_prefix"], r.json()["operator_roster_sha16"]}


def test_open_health_r2_fields_are_null_when_off_or_invalid(tmp_path, monkeypatch):
    f = oh.OperatorHealth().health_fields()
    assert [f[k] for k in ("operator_registry_format", "operator_registry_generation",
                           "operator_roster_sha16")] == [None, None, None]
    bad = doc2()
    bad["operators"][0]["surprise"] = 1          # closed schema: the whole file is unavailable
    monkeypatch.setenv(oa.ENV_REGISTRY, str(_write(tmp_path, bad)))
    f = oh.OperatorHealth().health_fields()
    assert f["last_registry_error"] and f["operator_registry_rows"] is None
    assert [f[k] for k in ("operator_registry_format", "operator_registry_generation",
                           "operator_roster_sha16")] == [None, None, None]


def test_format1_file_reports_format_1_generation_0_and_parses_as_before(tmp_path, monkeypatch):
    raw = doc1()
    monkeypatch.setenv(oa.ENV_REGISTRY, str(_write(tmp_path, raw)))
    f = oh.OperatorHealth().health_fields()
    assert f["operator_registry_format"] == 1 and f["operator_registry_generation"] == 0
    assert f["operator_registry_rows"] == 3
    assert f["operator_roster_sha16"] == oh.roster_sha256(raw)[:16]
    # the verifier still reads exactly the format 1 rows
    assert oa.load_registry() == oa.parse_registry(raw)


def test_roster_digest_ignores_key_fields_and_moves_with_any_roster_change():
    base = oh.roster_sha256(doc2())
    rotated = doc2(generation=42, next_key=False)
    rotated["issued_at"], rotated["issued_by"] = "2026-12-01T00:00:00Z", "svc-rotator-fly"
    ks = rotated["operators"][1]
    ks["key_sha256"], ks["key_created_at"], ks["key_not_after"] = (
        H(KEY_KS_NEXT), "2026-12-01T00:00:00Z", "2027-02-14T00:00:00Z")
    assert oh.roster_sha256(rotated) == base
    for mutate in (lambda d: d["operators"][1]["scopes"].append("drill"),
                   lambda d: d["operators"][0].update(status="revoked"),
                   lambda d: d["operators"].reverse(),
                   lambda d: d["operators"][0]["names"].append("Alias"),
                   lambda d: d["operators"][3].update(rotation="remote"),
                   lambda d: d["operators"].pop()):
        d = doc2()
        mutate(d)
        assert oh.roster_sha256(d) != base
    # format 1: a list and the {"operators": [...]} wrapper are the same roster
    assert oh.roster_sha256(doc1()) == oh.roster_sha256({"operators": doc1()})


def test_snapshot_reads_the_same_bytes_as_load_registry(armed):
    p, _ = armed
    snap = oa.load_registry_snapshot()
    assert snap.sha256 == hashlib.sha256(p.read_bytes()).hexdigest()
    assert snap.doc.generation == 41 and snap.rows == oa.load_registry()


# --- POST /operator/verify-hash --------------------------------------------------------------


def test_verify_hash_is_absent_when_off_even_with_a_secret(monkeypatch):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    client, _ = _client()
    assert vh(client, "svc-killswitch", H(KEY_KS)).status_code == 404
    assert client.get(oh.ROTATION_STATE_PATH, headers={authn.HEADER: SECRET}).status_code == 404


def test_verify_hash_is_absent_without_a_perimeter_secret(tmp_path, monkeypatch):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(_write(tmp_path, doc2())))
    client, _ = _client()
    assert vh(client, "svc-killswitch", H(KEY_KS), secret=None).status_code == 404
    assert client.get(oh.ROTATION_STATE_PATH).status_code == 404


def test_verify_hash_needs_the_perimeter_secret(armed):
    client, _ = _client()
    assert vh(client, "svc-killswitch", H(KEY_KS), secret=None).status_code == 401
    assert vh(client, "svc-killswitch", H(KEY_KS), secret="wrong").status_code == 401
    assert client.get(oh.ROTATION_STATE_PATH).status_code == 401


@pytest.mark.parametrize("enforce", [False, True])
def test_verify_hash_current_and_next_both_valid_in_the_overlap(armed, monkeypatch, enforce):
    if enforce:
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    client, _ = _client()
    r = vh(client, "svc-killswitch", H(KEY_KS))
    assert r.status_code == 200
    assert r.json() == {"operator_id": "svc-killswitch", "matched": "current",
                        "matchable_now": True, "retired": False, "registry_format": 2,
                        "registry_generation": 41,
                        "registry_sha256_prefix": hashlib.sha256(armed[0].read_bytes()).hexdigest()[:16]}
    r = vh(client, "svc-killswitch", H(KEY_KS_NEXT)).json()
    assert (r["matched"], r["matchable_now"]) == ("next", True)


def test_verify_hash_next_only_inside_its_window(armed, monkeypatch):
    client, _ = _client()
    monkeypatch.setattr(oa, "clock", lambda: float(T0 - 301))        # before not_before
    r = vh(client, "svc-killswitch", H(KEY_KS_NEXT)).json()
    assert (r["matched"], r["matchable_now"]) == ("next", False)
    monkeypatch.setattr(oa, "clock", lambda: float(T0 + 75 * DAY))   # at not_after
    r = vh(client, "svc-killswitch", H(KEY_KS_NEXT)).json()
    assert (r["matched"], r["matchable_now"]) == ("next", False)


def test_verify_hash_never_matchable_for_an_expired_current_slot(armed, monkeypatch):
    client, _ = _client()
    monkeypatch.setattr(oa, "clock", lambda: float(T0 + 30 * DAY))   # at key_not_after
    r = vh(client, "svc-killswitch", H(KEY_KS)).json()
    assert (r["matched"], r["matchable_now"]) == ("current", False)
    r = vh(client, "svc-killswitch", H(KEY_KS_NEXT)).json()          # the successor still is
    assert (r["matched"], r["matchable_now"]) == ("next", True)


def test_verify_hash_answers_for_the_named_row_only(armed):
    client, _ = _client()
    r = vh(client, "don", H(KEY_KS)).json()                # svc-killswitch's hash under don
    assert (r["matched"], r["matchable_now"]) == ("none", False)
    r = vh(client, "nobody", H(KEY_DON)).json()
    assert (r["matched"], r["matchable_now"]) == ("none", False)
    r = vh(client, "don", "0" * 64).json()                 # the empty-slot filler never matches
    assert (r["matched"], r["matchable_now"]) == ("none", False)


def test_verify_hash_a_revoked_row_never_matchable(armed):
    client, _ = _client()
    r = vh(client, "other", H(KEY_OTHER)).json()
    assert (r["matched"], r["matchable_now"]) == ("current", False)


def test_verify_hash_after_promote_the_old_hash_is_none(armed):
    """Design 4.3 steps 9b and 10: after PROMOTE the new hash is current and the old none."""
    _, set_doc = armed
    d = doc2(generation=42, next_key=False)
    d["operators"][1]["key_sha256"] = H(KEY_KS_NEXT)
    set_doc(d)
    client, _ = _client()
    assert vh(client, "svc-killswitch", H(KEY_KS_NEXT)).json()["matched"] == "current"
    r = vh(client, "svc-killswitch", H(KEY_KS)).json()
    assert (r["matched"], r["matchable_now"], r["registry_generation"]) == ("none", False, 42)


def test_verify_hash_reports_a_retired_hash_as_not_matchable(armed):
    """Design 2.4: a hash removed at a higher generation and back in a lower one is refused
    alone by the verifier; verify-hash says so from the same memory."""
    _, set_doc = armed
    client, _ = _client()
    vh(client, "svc-killswitch", H(KEY_KS))                 # gen 41 loaded
    d = doc2(generation=43, next_key=False)
    d["operators"][1]["key_sha256"] = H(KEY_KS_NEXT)
    set_doc(d)
    vh(client, "svc-killswitch", H(KEY_KS))                 # gen 43 loaded: KEY_KS retired
    set_doc(doc2(generation=41))                            # an older file is restored
    r = vh(client, "svc-killswitch", H(KEY_KS)).json()
    assert (r["matched"], r["matchable_now"], r["retired"]) == ("current", False, True)


def test_verify_hash_refuses_the_sealed_row_and_counts_the_attempt(armed):
    client, _ = _client()
    before = (oa.breakglass_auth_count, oa.breakglass_attempt_count)
    r = vh(client, "don-breakglass", H(KEY_BG))
    assert r.status_code == 403 and r.json() == {"detail": oh.SEALED_DETAIL}
    _no_hash(r.text)
    assert (oa.breakglass_auth_count, oa.breakglass_attempt_count) == (before[0], before[1] + 1)


def test_verify_hash_refuses_any_sealed_row_whatever_its_id(armed):
    _, set_doc = armed
    d = doc2()
    d["operators"][2]["operator_id"] = "glass-2"
    set_doc(d)
    client, _ = _client()
    before = oa.breakglass_attempt_count
    r = vh(client, "glass-2", "1" * 64)
    assert r.status_code == 403 and oa.breakglass_attempt_count == before + 1
    # the sealed hash asked about under ANOTHER id is simply not that id's key
    r = vh(client, "don", H(KEY_BG))
    assert r.status_code == 200 and r.json()["matched"] == "none"


def test_verify_hash_refuses_the_breakglass_id_in_a_format1_file(tmp_path, monkeypatch):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(_write(tmp_path, doc1())))
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    client, _ = _client()
    assert vh(client, "don-breakglass", H(KEY_BG)).status_code == 403
    r = vh(client, "svc-killswitch", H(KEY_KS)).json()
    assert (r["matched"], r["matchable_now"], r["registry_format"], r["registry_generation"]) == \
        ("current", True, 1, 0)


@pytest.mark.parametrize("body", [
    b'{"operator_id": "svc-killswitch", "key": "tkv-r2ks-key-0123456789abcdef"}',
    b'{"operator_id": "svc-killswitch", "key_sha256": "tkv-r2ks-key-0123456789abcdef"}',
    b'{"operator_id": "svc-killswitch", "key_sha256": "fok_abcdefabcdefabcdefabcdefabcdefabcdefabcdefabc"}',
    b'{"operator_id": "svc-killswitch", "key_sha256": "' + b"A" * 64 + b'"}',
    b'{"operator_id": "svc-killswitch", "key_sha256": "' + b"0" * 64 + b'", "key": "x"}',
    b'{"operator_id": "fok_abcdefabcdefabcdefabcdefabcdefabcdefabcdefabc", "key_sha256": "' + b"0" * 64 + b'"}',
    b'{"key_sha256": "' + b"0" * 64 + b'"}',
    b'["svc-killswitch"]',
    b"not json",
    b"\xff\xfe",
])
def test_verify_hash_takes_a_hash_never_a_key_and_never_echoes_input(armed, body):
    client, _ = _client()
    r = client.post(oh.VERIFY_HASH_PATH, content=body, headers={authn.HEADER: SECRET})
    assert r.status_code == 422 and r.json() == {"detail": oh.BAD_BODY_DETAIL}
    assert "tkv-" not in r.text and "fok_abc" not in r.text


def test_verify_hash_caps_the_body(armed):
    client, _ = _client()
    r = client.post(oh.VERIFY_HASH_PATH, content=b"{" + b" " * 2000 + b"}",
                    headers={authn.HEADER: SECRET})
    assert r.status_code == 413


def test_verify_hash_503_when_the_registry_is_unavailable(armed):
    _, set_doc = armed
    bad = doc2()
    bad["operators"][1]["next_key"]["extra"] = 1
    set_doc(bad)
    client, _ = _client()
    r = vh(client, "svc-killswitch", H(KEY_KS))
    assert r.status_code == 503 and r.json() == {"detail": oh.UNAVAILABLE_DETAIL}


def test_verify_hash_refuses_the_breakglass_id_even_with_the_registry_down(armed):
    """Asked about the break-glass identity, the answer is the refusal (counted), never a 503
    that would say nothing about the attempt."""
    _, set_doc = armed
    set_doc({"format": 2})
    client, _ = _client()
    before = oa.breakglass_attempt_count
    r = vh(client, "don-breakglass", H(KEY_BG))
    assert r.status_code == 403 and oa.breakglass_attempt_count == before + 1
    assert vh(client, "don", H(KEY_DON)).status_code == 503


def test_verify_hash_is_never_ledgered_and_never_counted_as_a_refusal(armed, monkeypatch):
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    led = Ledger()
    client, h = _client(led)
    vh(client, "svc-killswitch", H(KEY_KS))
    vh(client, "svc-killswitch", H(KEY_OTHER))             # a "none" answer
    vh(client, "nobody", H(KEY_KS))
    vh(client, "don-breakglass", H(KEY_BG))                # refused: counted as break-glass only
    assert led.rows == [] and h.refused_count == 0


def test_verify_hash_and_rotation_state_exist_only_on_a_fastapi_app():
    app = FastAPI()
    oh.install(app)
    paths = {(r.path, tuple(sorted(r.methods))) for r in app.routes if hasattr(r, "methods")}
    assert (oh.VERIFY_HASH_PATH, ("POST",)) in paths
    assert (oh.ROTATION_STATE_PATH, ("GET",)) in paths
    from types import SimpleNamespace
    oh.install(SimpleNamespace(state=SimpleNamespace()))    # no routes, no error


# --- GET /operator/rotation-state (internal) ----------------------------------------------------


def _state(client):
    r = client.get(oh.ROTATION_STATE_PATH, headers={authn.HEADER: SECRET})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    return r.json()


def test_rotation_state_carries_the_hash_fields(armed, monkeypatch):
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-killswitch")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY_KS)
    client, _ = _client()
    s = _state(client)
    assert s["identity_id"] == "svc-killswitch"
    assert s["identity_key_fp"] == H(KEY_KS)[:16] and s["identity_key_slot"] == "current"
    assert (s["registry_format"], s["registry_generation"]) == (2, 41)
    assert s["operator_roster_sha16"] == oh.roster_sha256(doc2())[:16]
    rows = {r["operator_id"]: r for r in s["rows"]}
    ks = rows["svc-killswitch"]
    assert ks["current_fp"] == H(KEY_KS)[:16] and ks["next_fp"] == H(KEY_KS_NEXT)[:16]
    assert ks["current_matchable_now"] and ks["next_matchable_now"]
    assert ks["current_not_after"] == _t(T0 + 30 * DAY)
    assert ks["next_not_before"] == _t(T0 - 300) and ks["next_not_after"] == _t(T0 + 75 * DAY)
    assert ks["key_created_at"] == _t(T0 - 20 * DAY)
    assert rows["other"]["current_matchable_now"] is False          # revoked
    assert s["keys_next"] == 1
    assert (s["expiry_min"], s["expiry_min_operator_id"]) == (_t(T0 + 10 * DAY), "don")
    assert s["oldest_current_key_created_at"] == _t(T0 - 40 * DAY)
    assert s["oldest_current_key_age_s"] == 40 * DAY and s["key_created_at_missing"] == 0
    assert s["key_grace_active"] is False
    assert s["clock_synced"] in (True, False, None)
    assert set(s["counters"]) >= {"breakglass_auth_count", "breakglass_attempt_count",
                                  "retired_hash_seen", "refused_count"}
    # full hashes never, even here
    for k in ALL_KEYS:
        assert H(k) not in json.dumps(s)


def test_rotation_state_never_shows_any_prefix_of_the_sealed_key(armed):
    client, _ = _client()
    s = _state(client)
    bg = [r for r in s["rows"] if r["operator_id"] == "don-breakglass"][0]
    assert bg["current_fp"] == oh.SEALED_FP and bg["next_fp"] is None
    blob = json.dumps(s)
    for n in (16, 8, 6):
        assert H(KEY_BG)[:n] not in blob
    # the sealed row does not count towards expiry or age (it has neither)
    assert s["expiry_min_operator_id"] != "don-breakglass"


def test_rotation_state_identity_on_the_next_key_and_unknown_age(armed, monkeypatch):
    _, set_doc = armed
    set_doc(doc2(ks_created=False))
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-killswitch")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY_KS_NEXT)
    client, _ = _client()
    s = _state(client)
    assert s["identity_key_fp"] == H(KEY_KS_NEXT)[:16] and s["identity_key_slot"] == "next"
    # one active row without key_created_at: the oldest age is unknown, never "fresh"
    assert s["key_created_at_missing"] == 1
    assert s["oldest_current_key_age_s"] is None and s["oldest_current_key_created_at"] is None
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY_OTHER)
    assert _state(client)["identity_key_slot"] == "none"
    # before the NEXT key's not_before it is listed but would not authenticate yet
    monkeypatch.setattr(oa, "clock", lambda: float(T0 - 301))
    ks = [r for r in _state(client)["rows"] if r["operator_id"] == "svc-killswitch"][0]
    assert ks["next_fp"] == H(KEY_KS_NEXT)[:16] and ks["next_matchable_now"] is False
    assert ks["current_matchable_now"] is True


def test_rotation_state_format1_and_an_invalid_file(tmp_path, monkeypatch):
    p = _write(tmp_path, doc1())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    client, _ = _client()
    s = _state(client)
    assert (s["registry_format"], s["registry_generation"], s["keys_next"]) == (1, 0, 0)
    assert s["expiry_min"] is None and s["oldest_current_key_age_s"] is None
    assert s["key_created_at_missing"] == 2                 # don, svc-killswitch (not break-glass)
    assert [r["current_fp"] for r in s["rows"] if r["operator_id"] == "don-breakglass"] == [oh.SEALED_FP]
    p.write_text("{not json", encoding="utf-8")
    s = _state(client)
    assert s["last_registry_error"] and s["rows"] == [] and s["registry_generation"] is None


def test_clock_synced_reads_adjtimex_and_never_guesses(monkeypatch):
    import ctypes

    class Libc:
        def __init__(self, rc):
            self.rc = rc

        def adjtimex(self, buf):
            assert len(buf.raw) >= 208 and set(buf.raw) == {0}      # modes = 0: read only
            return self.rc

    monkeypatch.setattr(oh.sys, "platform", "linux")
    for rc, want in ((0, True), (1, True), (4, True), (5, False), (-1, None)):
        monkeypatch.setattr(ctypes, "CDLL", lambda *_a, rc=rc, **_k: Libc(rc))
        assert oh.clock_synced() is want, rc

    def boom(*_a, **_k):
        raise OSError("no libc")
    monkeypatch.setattr(ctypes, "CDLL", boom)
    assert oh.clock_synced() is None
    monkeypatch.setattr(oh.sys, "platform", "win32")
    assert oh.clock_synced() is None


# --- break-glass counters (design 3.4, S8) ---------------------------------------------------


def _hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


def _counts():
    return oa.breakglass_auth_count, oa.breakglass_attempt_count


@pytest.mark.parametrize("enforce", [False, True])
def test_breakglass_use_and_attempts_are_counted(armed, monkeypatch, enforce):
    if enforce:
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")

    def auth(headers, action="kill"):
        try:
            return oa.authenticate(headers, action)
        except oa.OperatorRefused:
            return None

    a0, t0 = _counts()
    assert auth(_hdr("don-breakglass", KEY_BG)).authenticated
    assert _counts() == (a0 + 1, t0)
    auth(_hdr("don-breakglass", KEY_DON))                    # wrong key
    auth({oa.HEADER_OPERATOR: "don-breakglass"})             # no key
    assert _counts() == (a0 + 1, t0 + 2)
    auth(_hdr("don-breakglass", KEY_BG), action="mint")      # authenticated, scope refused
    assert _counts() == (a0 + 2, t0 + 3)
    auth(_hdr("don", KEY_DON))
    auth(_hdr("don", KEY_KS))
    auth(_hdr("svc-killswitch", KEY_KS))
    assert _counts() == (a0 + 2, t0 + 3)                     # other ids are never counted


def test_a_sealed_row_under_another_id_is_counted(armed):
    _, set_doc = armed
    d = doc2()
    d["operators"][2]["operator_id"] = "glass-2"
    set_doc(d)
    a0, t0 = _counts()
    assert oa.authenticate(_hdr("glass-2", KEY_BG), "kill").authenticated
    oa.authenticate(_hdr("glass-2", KEY_DON), "kill")
    assert _counts() == (a0 + 1, t0 + 1)


def test_breakglass_counted_in_format1_and_with_the_registry_down(tmp_path, monkeypatch):
    p = _write(tmp_path, doc1())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    a0, t0 = _counts()
    assert oa.authenticate(_hdr("don-breakglass", KEY_BG), "kill").authenticated
    assert _counts() == (a0 + 1, t0)
    p.write_text("[", encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    with pytest.raises(oa.OperatorRefused) as exc:
        oa.authenticate(_hdr("don-breakglass", KEY_BG), "kill")
    assert exc.value.status == 503
    assert _counts() == (a0 + 1, t0 + 1)


def test_breakglass_not_counted_when_off(monkeypatch):
    a0 = _counts()
    assert oa.authenticate(_hdr("don-breakglass", KEY_BG), "kill") is oa.NO_AUTH
    assert _counts() == a0


def test_open_health_shows_the_breakglass_counters(armed):
    client, _ = _client()
    oa.authenticate(_hdr("don-breakglass", KEY_DON), "kill")
    h = client.get("/health").json()
    assert (h["breakglass_auth_count"], h["breakglass_attempt_count"]) == _counts()


# --- the observer's slot witness (design 5.1, S11) ----------------------------------------------


def test_slot_witness_lists_slot_fingerprints_and_hides_the_sealed_key(armed):
    w = oh.slot_witness()
    assert (w["format"], w["generation"]) == (2, 41)
    rows = {r["operator_id"]: r for r in w["rows"]}
    assert rows["svc-killswitch"] == {"operator_id": "svc-killswitch", "status": "active",
                                      "current_fp": H(KEY_KS)[:16], "next_fp": H(KEY_KS_NEXT)[:16]}
    assert rows["don-breakglass"]["current_fp"] == oh.SEALED_FP
    public = json.dumps({k: v for k, v in w.items() if k != "_sealed_state"})
    for n in (16, 8):
        assert H(KEY_BG)[:n] not in public
    assert H(KEY_BG) not in json.dumps(w)


def test_slot_witness_sealed_state_moves_only_with_the_sealed_key(armed):
    _, set_doc = armed
    s1 = oh.slot_witness()["_sealed_state"]
    d = doc2(generation=42, next_key=False)
    set_doc(d)
    assert oh.slot_witness()["_sealed_state"] == s1
    d["operators"][2]["key_sha256"] = "ab" * 32
    set_doc(d)
    assert oh.slot_witness()["_sealed_state"] != s1


def test_slot_witness_none_without_a_valid_file(tmp_path, monkeypatch):
    assert oh.slot_witness() is None
    monkeypatch.setenv(oa.ENV_REGISTRY, str(tmp_path / "missing.json"))
    assert oh.slot_witness() is None


# --- C-119 (reviewer C-108, operator_health.py mutants that survived every suite) ----------------------------


def test_shown_label_keeps_none_and_hides_anything_that_is_not_a_clean_label():
    assert oh.shown_label(None) is None                                  # L165: None is not "not shown"
    assert oh.shown_label("kill.agent") == "kill.agent"
    for bad in (7, b"x", "", "a b", "x" * 65, oh.KEY_PREFIX + "abc"):
        assert oh.shown_label(bad) == oh.NOT_SHOWN


def test_clip_leaves_exactly_the_maximum_length_alone_and_clips_one_more():
    assert oh._clip("a" * oh.MAX_ERROR_LEN) == "a" * oh.MAX_ERROR_LEN     # L174 boundary
    clipped = oh._clip("a" * (oh.MAX_ERROR_LEN + 1))
    assert len(clipped) == oh.MAX_ERROR_LEN and clipped.endswith("...")


def test_clock_synced_is_none_off_linux(monkeypatch):
    monkeypatch.setattr(oh.sys, "platform", "win32")                      # L531
    assert oh.clock_synced() is None
    monkeypatch.setattr(oh.sys, "platform", "darwin")
    assert oh.clock_synced() is None


def test_rotation_state_reports_the_first_operator_when_two_expire_together(armed):
    """L635: a tie keeps the FIRST soonest-expiring identity in file order (strict `<`)."""
    _, set_doc = armed
    d = doc2()
    same = _t(T0 + 3 * DAY)
    active = [r for r in d["operators"] if r["status"] == "active" and r.get("rotation") != "sealed"]
    assert len(active) >= 2
    for r in active:
        r["key_not_after"] = same
    set_doc(d)
    client, _ = _client()
    s = _state(client)
    assert (s["expiry_min"], s["expiry_min_operator_id"]) == (same, active[0]["operator_id"])


def _vh_body_of_exactly(n: int) -> bytes:
    core = json.dumps({"operator_id": "svc-killswitch", "key_sha256": "0" * 64}).encode("utf-8")
    assert len(core) <= n
    return core + b" " * (n - len(core))


def test_verify_hash_accepts_a_body_of_exactly_the_cap_and_refuses_one_byte_more(armed):
    """L699: MAX_VERIFY_BODY bytes are read; one more is a 413 (`>` not `>=`)."""
    client, _ = _client()
    at_cap = client.post(oh.VERIFY_HASH_PATH, content=_vh_body_of_exactly(oh.MAX_VERIFY_BODY),
                         headers={authn.HEADER: SECRET})
    assert at_cap.status_code == 200, at_cap.text
    over = client.post(oh.VERIFY_HASH_PATH, content=_vh_body_of_exactly(oh.MAX_VERIFY_BODY + 1),
                       headers={authn.HEADER: SECRET})
    assert over.status_code == 413
