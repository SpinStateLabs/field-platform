"""Phase G Stage 0, health slice: field_core.operator_health.

C-8: the operator block every flag-bearing service's GET /health carries
(mode, registry sha256 prefix + row count, own identity, last registry error,
drop and refusal counters, manifests_unresolved where a service resolves
manifest_ref). Never a key, a key hash or the registry content.

C-16: ``operator.refused {action, path, reason, operator_claimed}`` written
under ENFORCE on every refusal, bounded per window and by concurrency, with
every refusal counted whether or not its record was written.

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import hashlib
import json
import threading
from types import SimpleNamespace

import pytest
import yaml
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from field_core import operator_health as oh
from field_core.templates_api import template_data

KEY_DON = "tkv-hdon-key-0123456789abcdef"
KEY_SVC = "tkv-hsvc-key-0123456789abcdef"
KEY_OWN = "tkv-hown-key-0123456789abcdef"

FIELDS = {
    "operator_mode", "operator_registry_sha256_prefix", "operator_registry_rows",
    "operator_identity_id", "identity_present", "last_registry_error",
    "dropped_unauthenticated_records", "refused_count", "dropped_refused_records",
    # key rotation slice R2: format, generation, roster digest, break-glass counters (no hash)
    "operator_registry_format", "operator_registry_generation", "operator_roster_sha16",
    "breakglass_auth_count", "breakglass_attempt_count",
}


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


def _row(oid, key, scopes, status="active", **kw):
    return {"operator_id": oid, "key_sha256": oa.key_sha256(key), "status": status,
            "created_at": "2026-10-26", "scopes": scopes, **kw}


def _rows(status="active"):
    return [_row("don", KEY_DON, ["*"], status=status),
            _row("svc", KEY_SVC, ["kill"], status=status)]


def _write(tmp_path, data, name="operators.json") -> tuple:
    p = tmp_path / name
    raw = (data if isinstance(data, bytes)
           else (data if isinstance(data, str) else json.dumps(data)).encode("utf-8"))
    p.write_bytes(raw)
    return p, raw


def hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


class FakeLedger:
    def __init__(self, fail=False, gate: threading.Event | None = None):
        self.rows: list[tuple[str, dict]] = []
        self.agent_ids: list[str | None] = []
        self.fail = fail
        self.gate = gate
        self._lock = threading.Lock()

    def append(self, event_type, payload, agent_id=None):
        if self.gate is not None:
            self.gate.wait(5)
        if self.fail:
            raise RuntimeError("ledger down")
        with self._lock:
            self.rows.append((event_type, dict(payload)))
            self.agent_ids.append(agent_id)

    def of(self, event_type):
        return [p for t, p in self.rows if t == event_type]


def _health(ledger=None, **kw):
    app = SimpleNamespace(state=SimpleNamespace())
    return oh.install(app, ledger_getter=(lambda a: ledger), **kw)


def _no_secret(blob: str):
    for k in (KEY_DON, KEY_SVC, KEY_OWN):
        assert k not in blob
        assert oa.key_sha256(k) not in blob
        assert oa.key_sha256(k)[:16] not in blob


# --- C-8: health fields -------------------------------------------------------------


def test_off_reports_mode_off_and_nothing_about_a_registry():
    f = _health().health_fields()
    assert set(f) == FIELDS
    assert f == {"operator_mode": "off", "operator_registry_sha256_prefix": None,
                 "operator_registry_rows": None, "operator_identity_id": None,
                 "identity_present": False, "last_registry_error": None,
                 "dropped_unauthenticated_records": oa.dropped_unauthenticated_records,
                 "refused_count": 0, "dropped_refused_records": 0,
                 "operator_registry_format": None, "operator_registry_generation": None,
                 "operator_roster_sha16": None,
                 "breakglass_auth_count": oa.breakglass_auth_count,
                 "breakglass_attempt_count": oa.breakglass_attempt_count}


def test_log_only_reports_the_file_sha256_prefix_and_row_count(tmp_path, monkeypatch):
    p, raw = _write(tmp_path, _rows())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    f = _health().health_fields()
    assert f["operator_mode"] == "log-only"
    assert f["operator_registry_sha256_prefix"] == hashlib.sha256(raw).hexdigest()[:16]
    assert f["operator_registry_rows"] == 2 and f["last_registry_error"] is None
    _no_secret(json.dumps(f))
    assert "don" not in json.dumps(f)            # no row content, ids included


def test_the_prefix_tracks_the_bytes_so_an_edit_is_visible(tmp_path, monkeypatch):
    p, raw = _write(tmp_path, _rows())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    h = _health()
    before = h.health_fields()["operator_registry_sha256_prefix"]
    p.write_bytes(raw + b"\n")
    after = h.health_fields()["operator_registry_sha256_prefix"]
    assert before != after and after == hashlib.sha256(raw + b"\n").hexdigest()[:16]


def test_a_bom_written_file_is_read_like_the_guards_read_it(tmp_path, monkeypatch):
    p, raw = _write(tmp_path, b"\xef\xbb\xbf" + json.dumps(_rows()).encode())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    f = _health().health_fields()
    assert f["operator_registry_rows"] == 2 and f["last_registry_error"] is None


@pytest.mark.parametrize("content,why", [
    ("nope", "unreadable"),
    (json.dumps([_row("don", KEY_DON, ["*"], status="Active")]), "status"),
    (json.dumps([{**_row("don", KEY_DON, ["*"]), "scopes": ["assert_operator"]}]),
     "assert_operator"),
])
def test_a_malformed_registry_reports_the_error_never_the_content(tmp_path, monkeypatch,
                                                                   content, why):
    p, raw = _write(tmp_path, content)
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    f = _health().health_fields()
    assert f["operator_registry_rows"] is None
    assert f["operator_registry_sha256_prefix"] == hashlib.sha256(raw).hexdigest()[:16]
    assert why in f["last_registry_error"]
    assert len(f["last_registry_error"]) <= oh.MAX_ERROR_LEN
    _no_secret(json.dumps(f))
    assert "Active" not in f["last_registry_error"]      # a status value is never echoed


def test_zero_active_rows_is_an_error_under_enforce_only(tmp_path, monkeypatch):
    p, _ = _write(tmp_path, _rows(status="revoked"))
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    f = _health().health_fields()
    assert f["operator_registry_rows"] == 2 and f["last_registry_error"] is None
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    f = _health().health_fields()
    assert f["operator_mode"] == "enforce"
    assert f["operator_registry_rows"] is None and "active" in f["last_registry_error"]


def test_the_empty_placeholder_reports_zero_rows_then_an_error_under_enforce(tmp_path,
                                                                            monkeypatch):
    p, _ = _write(tmp_path, {"operators": []})
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    assert _health().health_fields()["operator_registry_rows"] == 0
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    f = _health().health_fields()
    assert f["operator_registry_rows"] is None and f["last_registry_error"]


def test_enforce_without_a_registry_path_says_so(monkeypatch):
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    f = _health().health_fields()
    assert f["operator_mode"] == "enforce"
    assert f["operator_registry_sha256_prefix"] is None
    assert f["last_registry_error"] == "operator registry path is not set"


def test_an_unreadable_registry_names_the_exception_type_only(tmp_path, monkeypatch):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(tmp_path / "missing.json"))
    f = _health().health_fields()
    assert f["operator_registry_sha256_prefix"] is None
    assert f["last_registry_error"] == "operator registry unreadable: FileNotFoundError"


def test_a_misspelt_require_value_reports_enforce(monkeypatch, tmp_path):
    p, _ = _write(tmp_path, _rows())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "enforce")
    assert _health().health_fields()["operator_mode"] == "enforce"


def test_own_identity_from_a_key_file_is_reported_without_the_key(tmp_path, monkeypatch):
    kf = tmp_path / "svc.key"
    kf.write_text(KEY_OWN + "\n", encoding="utf-8")
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-killswitch")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY_FILE, str(kf))
    f = _health().health_fields()
    assert f["operator_identity_id"] == "svc-killswitch" and f["identity_present"] is True
    _no_secret(json.dumps(f))


def test_an_id_without_a_usable_key_is_named_but_not_present(tmp_path, monkeypatch):
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-registry")
    f = _health().health_fields()
    assert f["operator_identity_id"] == "svc-registry" and f["identity_present"] is False
    kf = tmp_path / "empty.key"
    kf.write_text("", encoding="utf-8")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY_FILE, str(kf))
    assert _health().health_fields()["identity_present"] is False


@pytest.mark.parametrize("value", [KEY_OWN, "fok_" + "A" * 43, "has space", "x" * 65])
def test_an_operator_value_that_could_be_a_key_is_never_echoed(monkeypatch, value):
    monkeypatch.setenv(oa.ENV_OPERATOR, value)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY_OWN)
    f = _health().health_fields()
    assert f["operator_identity_id"] == oh.NOT_SHOWN
    assert value not in json.dumps(f)


def test_dropped_unauthenticated_records_mirrors_the_guard_counter(monkeypatch):
    monkeypatch.setattr(oa, "dropped_unauthenticated_records", 7)
    assert _health().health_fields()["dropped_unauthenticated_records"] == 7


def _manifest(tmp_path, name, ok=True):
    path = tmp_path / f"{name}.yaml"
    if ok:
        data = template_data("default")
        data["agent"]["name"] = name
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    else:
        path.write_text("agent: [not, a, manifest\n", encoding="utf-8")
    return str(path)


def test_manifests_unresolved_counts_missing_and_invalid_refs_when_armed(tmp_path,
                                                                        monkeypatch):
    refs = [None, _manifest(tmp_path, "good"), str(tmp_path / "gone.yaml"),
            _manifest(tmp_path, "bad", ok=False)]
    h = _health()
    assert h.health_fields(manifest_refs=lambda: refs)["manifests_unresolved"] is None  # OFF
    p, _ = _write(tmp_path, _rows())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    f = h.health_fields(manifest_refs=lambda: refs)
    assert set(f) == FIELDS | {"manifests_unresolved"}
    assert f["manifests_unresolved"] == 2


def test_manifests_unresolved_is_null_when_the_agent_list_fails(tmp_path, monkeypatch):
    p, _ = _write(tmp_path, _rows())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))

    def boom():
        raise RuntimeError("registry down")

    assert _health().health_fields(manifest_refs=boom)["manifests_unresolved"] is None


# --- C-16: operator.refused -----------------------------------------------------------


@pytest.fixture()
def enforce(tmp_path, monkeypatch):
    p, _ = _write(tmp_path, _rows())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def test_an_enforce_refusal_is_counted_and_recorded_without_the_key(enforce):
    led = FakeLedger()
    h = _health(led)
    h.note_refused(oa.OperatorRefused(403, oa.FORBIDDEN_DETAIL), action="kill",
                   path="/kill/a1", headers=hdr("don", "tkv-wrong-key-000"))
    assert h.refused_count == 1
    assert led.of("operator.refused") == [{
        "action": "kill", "path": "/kill/a1", "reason": "forbidden", "status": 403,
        "claimed_id": "don", "operator_claimed": "don"}]
    assert "tkv-wrong-key-000" not in json.dumps(led.rows)
    assert h.health_fields()["refused_count"] == 1


@pytest.mark.parametrize("status,reason", [(400, "malformed_credential"),
                                           (401, "no_credential"), (403, "forbidden"),
                                           (503, "unavailable")])
def test_each_refusal_status_has_a_fixed_reason(enforce, status, reason):
    led = FakeLedger()
    h = _health(led)
    h.note_refused(oa.OperatorRefused(status, "x"), action="mint", path="/tokens", headers={})
    assert led.of("operator.refused")[0]["reason"] == reason
    assert led.of("operator.refused")[0]["claimed_id"] is None


def test_a_malformed_claim_is_recorded_as_no_claim(enforce):
    led = FakeLedger()
    h = _health(led)
    h.note_refused(oa.OperatorRefused(400, "malformed"), action="kill", path="/k",
                   headers=hdr("bad id with spaces", KEY_DON))
    assert led.of("operator.refused")[0]["claimed_id"] is None


def test_a_claimed_id_that_could_be_a_key_is_masked(enforce):
    led = FakeLedger()
    h = _health(led)
    claim = "fok_" + "B" * 43
    h.note_refused(oa.OperatorRefused(403, oa.FORBIDDEN_DETAIL), action="kill", path="/k",
                   headers=hdr(claim, KEY_DON))
    p = led.of("operator.refused")[0]
    assert p["claimed_id"] == oh.NOT_SHOWN and claim not in json.dumps(led.rows)


@pytest.mark.parametrize("agent_id,want", [("canary-gb10", "canary-gb10"), (None, None),
                                           ("fok_" + "C" * 43, None), ("a b", None)])
def test_the_refused_routes_agent_becomes_the_event_agent_id(enforce, agent_id, want):
    led = FakeLedger()
    h = _health(led)
    h.note_refused(oa.OperatorRefused(401, "x"), action="kill", path="/k", headers={},
                   agent_id=agent_id)
    assert led.agent_ids == [want]


def test_a_handler_may_name_the_claimed_id_it_already_holds(enforce):
    led = FakeLedger()
    h = _health(led)
    h.note_refused(oa.OperatorRefused(403, "x"), action="kill", path="/k", headers={},
                   claimed="other")
    assert led.of("operator.refused")[0]["claimed_id"] == "other"


def test_log_only_refusals_are_counted_but_not_recorded(tmp_path, monkeypatch):
    p, _ = _write(tmp_path, _rows())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    led = FakeLedger()
    h = _health(led)
    h.note_refused(oa.OperatorRefused(400, "malformed"), action="kill", path="/k", headers={})
    assert h.refused_count == 1 and led.rows == []


def test_enforce_without_a_ledger_getter_counts_the_refusal_as_dropped(enforce):
    """C-52 (reviewer C-40 finding 1, proven): refused_count 1, dropped_refused_records 0."""
    app = SimpleNamespace(state=SimpleNamespace())
    h = oh.install(app)                                      # no ledger_getter
    h.note_refused(oa.OperatorRefused(401, "x"), action="kill", path="/k", headers={})
    assert (h.refused_count, h.dropped_records) == (1, 1)
    assert h.health_fields()["dropped_refused_records"] == 1


def test_enforce_with_a_raising_ledger_getter_counts_the_refusal_as_dropped(enforce):
    def boom(app):
        raise RuntimeError("no ledger")
    app = SimpleNamespace(state=SimpleNamespace())
    h = oh.install(app, ledger_getter=boom)
    h.note_refused(oa.OperatorRefused(401, "x"), action="kill", path="/k", headers={})
    assert (h.refused_count, h.dropped_records) == (1, 1)


def test_enforce_with_a_getter_returning_none_counts_the_refusal_as_dropped(enforce):
    h = _health(None)
    h.note_refused(oa.OperatorRefused(401, "x"), action="kill", path="/k", headers={})
    assert (h.refused_count, h.dropped_records) == (1, 1)


def test_off_never_counts_or_records():
    led = FakeLedger()
    h = _health(led)
    h.note_refused(oa.OperatorRefused(403, "x"), action="kill", path="/k", headers={})
    assert h.refused_count == 0 and led.rows == []


def test_the_window_cap_bounds_records_and_counts_every_drop(enforce):
    now = [1000.0]
    led = FakeLedger()
    h = _health(led, max_records_per_window=5, window_s=60.0, clock=lambda: now[0])
    for _ in range(8):
        h.note_refused(oa.OperatorRefused(401, "x"), action="kill", path="/k", headers={})
    assert len(led.of("operator.refused")) == 5
    assert h.refused_count == 8 and h.dropped_records == 3
    f = h.health_fields()
    assert f["refused_count"] == 8 and f["dropped_refused_records"] == 3
    now[0] += 60.0
    h.note_refused(oa.OperatorRefused(401, "x"), action="kill", path="/k", headers={})
    assert len(led.of("operator.refused")) == 6 and h.dropped_records == 3


def test_the_default_cap_is_documented_and_finite():
    assert 0 < oh.MAX_REFUSED_RECORDS_PER_WINDOW <= 120 and oh.REFUSED_WINDOW_S >= 1
    assert 0 < oh.MAX_CONCURRENT_REFUSED_RECORDS <= oa.MAX_CONCURRENT_UNAUTH_RECORDS


def test_a_slow_ledger_cannot_hold_more_than_the_concurrency_cap(enforce):
    gate = threading.Event()
    led = FakeLedger(gate=gate)
    h = _health(led, max_concurrent=2, append_timeout_s=0.05)
    try:
        for _ in range(4):
            h.note_refused(oa.OperatorRefused(401, "x"), action="kill", path="/k", headers={})
        assert h.refused_count == 4 and h.dropped_records == 2
    finally:
        gate.set()


def test_a_failing_ledger_never_raises_and_still_counts(enforce):
    h = _health(FakeLedger(fail=True))
    h.note_refused(oa.OperatorRefused(403, "x"), action="kill", path="/k", headers={})
    assert h.refused_count == 1


def test_no_ledger_still_counts(enforce):
    h = _health(None)
    h.note_refused(oa.OperatorRefused(403, "x"), action="kill", path="/k", headers={})
    assert h.refused_count == 1


def test_http_refusal_returns_the_same_status_and_detail(enforce):
    led = FakeLedger()
    h = _health(led)
    exc = h.http_refusal(oa.OperatorRefused(403, oa.FORBIDDEN_DETAIL), action="kill",
                         path="/kill/a1", headers={})
    assert (exc.status_code, exc.detail) == (403, oa.FORBIDDEN_DETAIL)
    assert h.refused_count == 1 and len(led.of("operator.refused")) == 1


def test_install_is_one_object_per_app():
    app = SimpleNamespace(state=SimpleNamespace())
    a = oh.install(app)
    assert app.state.operator_health is a
    assert oh.install(SimpleNamespace(state=SimpleNamespace())) is not a


# --- the guard wrapper ----------------------------------------------------------------


def _guarded_app(led):
    app = FastAPI()
    h = oh.install(app, ledger_getter=lambda a: led)
    guard_kill = h.guard("kill")

    @app.post("/kill/{agent_id}")
    def kill(agent_id: str, _op: object = Depends(guard_kill)) -> dict:
        return {"killed": agent_id, "by": oa.current().operator_id}

    return app, h


def test_the_guard_counts_and_records_every_enforce_refusal(enforce):
    led = FakeLedger()
    app, h = _guarded_app(led)
    c = TestClient(app)
    assert c.post("/kill/a1").status_code == 401
    assert c.post("/kill/a1", headers=hdr("don", "tkv-wrong-key-000")).status_code == 403
    assert c.post("/kill/a1", headers={oa.HEADER_OPERATOR: "bad id"}).status_code == 400
    r = c.post("/kill/a1", headers=hdr("don", KEY_DON))
    assert r.status_code == 200 and r.json()["by"] == "don"
    assert h.refused_count == 3
    rec = led.of("operator.refused")
    assert [(p["reason"], p["status"], p["claimed_id"]) for p in rec] == [
        ("no_credential", 401, None), ("forbidden", 403, "don"),
        ("malformed_credential", 400, None)]
    assert all(p["action"] == "kill" and p["path"] == "/kill/a1" for p in rec)
    assert led.agent_ids == ["a1", "a1", "a1"]       # the agent the refused route names
    assert "tkv-wrong-key-000" not in json.dumps(led.rows)


def test_the_guard_scope_refusal_is_recorded(enforce):
    led = FakeLedger()
    app, h = _guarded_app(led)
    c = TestClient(app)
    assert c.post("/kill/a1", headers=hdr("svc", KEY_SVC)).status_code == 200   # svc has kill
    h2_app = FastAPI()
    h2 = oh.install(h2_app, ledger_getter=lambda a: led)
    g = h2.guard("mint")

    @h2_app.post("/tokens")
    def mint(_op: object = Depends(g)) -> dict:
        return {}

    assert TestClient(h2_app).post("/tokens", headers=hdr("svc", KEY_SVC)).status_code == 403
    assert h2.refused_count == 1 and led.of("operator.refused")[-1]["action"] == "mint"


def test_the_guard_still_records_unauthenticated_in_log_only(tmp_path, monkeypatch):
    p, _ = _write(tmp_path, _rows())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    led = FakeLedger()
    app, h = _guarded_app(led)
    assert TestClient(app).post("/kill/a1").status_code == 200
    assert led.of("operator.unauthenticated")[0]["action"] == "kill"
    assert h.refused_count == 0 and led.of("operator.refused") == []


def test_the_guard_is_inert_when_off():
    led = FakeLedger()
    app, h = _guarded_app(led)
    assert TestClient(app).post("/kill/a1", headers=hdr("x", "y")).status_code == 200
    assert h.refused_count == 0 and led.rows == []


# --- PG0-CORE-R1-10: the open /health never echoes a key-shaped operator_id ---------------

#: fok_ + 43 base64url characters, inside the operator id charset: as if a field swap
#: had put a key into ``operator_id``. A test constant, never used to authenticate.
SWAPPED_ID = "fok_" + "Hn3Lq8ZrWb2Vt6Ck9Yp1Xs4Df7Gm0Ja5Ue2Ri8Oz3Ny"


@pytest.mark.parametrize("require", [None, "1"])
def test_a_key_shaped_operator_id_on_a_bad_row_never_reaches_health(tmp_path, monkeypatch,
                                                                    require):
    rows = _rows()
    rows[1]["operator_id"] = SWAPPED_ID
    rows[1]["status"] = "Active"
    p, _ = _write(tmp_path, rows)
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    if require:
        monkeypatch.setenv(oa.ENV_REQUIRE, require)
    f = _health().health_fields()
    err = f["last_registry_error"]
    assert "row 2 (id not shown)" in err and "status" in err
    blob = json.dumps(f)
    for i in range(len(SWAPPED_ID) - 4):
        assert SWAPPED_ID[i:i + 5] not in blob


# --- PG0-CORE-R1-14: the path in operator.refused is clipped and printable ----------------


@pytest.mark.parametrize("path,want", [
    ("/kill/a1", "/kill/a1"),
    ("/kill/" + "a" * 5000, None),
    ("/kill/a b\nforged: line", oh.NOT_SHOWN),
    ("/kill/café", oh.NOT_SHOWN),
    ("/kill/" + SWAPPED_ID, oh.NOT_SHOWN),
], ids=["plain", "long", "control_chars", "non_ascii", "key_shaped"])
def test_the_refused_record_path_is_clipped_and_printable(enforce, path, want):
    led = FakeLedger()
    h = _health(led)
    h.note_refused(oa.OperatorRefused(401, oa.FORBIDDEN_DETAIL), action="kill",
                   path=path, headers={})
    [p] = led.of("operator.refused")
    assert len(p["path"]) <= oa.MAX_RECORDED_PATH_LEN
    if want is None:
        assert p["path"].startswith("/kill/aaa") and p["path"].endswith("...")
    else:
        assert p["path"] == want


# --- PG0-CORE-R2-03: a long token without the key prefix is masked too ------------------

#: A 43-char base64url token without the key prefix, inside the operator id charset, as a
#: key not minted by operator_keygen.py would look. Not a key: never used to authenticate.
BARE_TOKEN = "Hn3Lq8ZrWb2Vt6Ck9Yp1Xs4Df7Gm0Ja5Ue2Ri8Oz3Ny"


def test_a_bare_token_identity_id_is_never_echoed(monkeypatch):
    assert oa._OPERATOR_RE.fullmatch(BARE_TOKEN)
    monkeypatch.setenv(oa.ENV_OPERATOR, BARE_TOKEN)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY_OWN)
    f = _health().health_fields()
    assert f["operator_identity_id"] == oh.NOT_SHOWN
    assert BARE_TOKEN not in json.dumps(f)
    assert oh.shown_id(BARE_TOKEN) == oh.NOT_SHOWN and oh.shown_id("svc-killswitch") == "svc-killswitch"


def test_a_bare_token_claimed_id_is_masked_in_the_refused_record(enforce):
    led = FakeLedger()
    h = _health(led)
    h.note_refused(oa.OperatorRefused(403, oa.FORBIDDEN_DETAIL), action="kill", path="/k",
                   headers=hdr(BARE_TOKEN, "tkv-wrong-key-000"))
    [p] = led.of("operator.refused")
    assert p["claimed_id"] == oh.NOT_SHOWN == p["operator_claimed"]
    assert BARE_TOKEN not in json.dumps(led.rows)
