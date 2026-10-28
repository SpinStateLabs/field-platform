"""Signed operator events, field-core slice (GB10 Stage 1 LOG-ONLY, 2026-10-27).

Measured on the GB10: with FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1 every
LOG-ONLY ``operator.unauthenticated`` record the kill-switch tried to write was
refused 403 and nothing counted or logged the loss. Cause: the ledger verifies
a caller signature over the payload it STORES, which under an armed mode is
``operator_auth.admit_ledger_event``'s output (reserved keys stripped,
``claimed_id`` masked, ``self_reported`` stamped), while the client signed the
payload BEFORE that admission. The ledger here is simulated exactly: admission
with the headers the request carried, then ``verify_caller_signature`` over the
admitted payload (the ledger's own end-to-end check is in
tools/tests/test_signed_opev_eight_services.py).

Pins: (1) a signing client sends and signs the payload in the form the ledger
will store, so the signature verifies, for operator.unauthenticated,
operator.refused and an ordinary event carrying reserved keys, with and without
an attributing service identity; (2) an unsigned client's body is unchanged;
(3) a failed operator-record append (403 / 5xx / unreachable) is counted in
``dropped_unauthenticated_records`` / ``dropped_refused_records`` and logged as
one line with the event type and status only; (4) LOG-ONLY still allows the
guarded request when that append fails.

Test key values are throwaway constants; the Ed25519 pairs are generated per
run. Nothing here reads a real key."""
from __future__ import annotations

import json
import logging

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from field_core import operator_health
from field_core.clients import CallerSigner, LedgerClient, LedgerUnreachableError, signed_append_body
from field_core.signing import generate_keypair, load_ed25519_private_key, verify_caller_signature

KEY_DON = "tkv-don-key-0123456789abcdef"
KEY_KS = "tkv-ks-key-0123456789abcdef"
KEY_PLAIN = "tkv-plain-key-0123456789abcdef"
SECRET_HDR = "tkv-perimeter-secret-0123456789"


def _row(oid, key, scopes, **kw):
    return {"operator_id": oid, "key_sha256": oa.key_sha256(key), "status": "active",
            "created_at": "2026-10-25", "scopes": scopes, **kw}


def H(op=None, key=None):
    h = {"x-field-auth": SECRET_HDR}
    if op is not None:
        h[oa.HEADER_OPERATOR] = op
    if key is not None:
        h[oa.HEADER_KEY] = key
    return h


@pytest.fixture(scope="module")
def pair():
    priv, pub = generate_keypair()
    return CallerSigner("killswitch", load_ed25519_private_key(priv)), pub


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in ("FIELD_OPERATOR_REGISTRY", "FIELD_OPERATOR_REQUIRE", "FIELD_OPERATOR",
              "FIELD_OPERATOR_KEY", "FIELD_OPERATOR_KEY_FILE"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr(oa, "_warned", False)
    yield
    oa.bind(oa.NO_AUTH)


@pytest.fixture()
def log_only(tmp_path, monkeypatch):
    p = tmp_path / "operators.json"
    p.write_text(json.dumps([
        _row("don", KEY_DON, ["*"]),
        _row("svc-killswitch", KEY_KS, ["kill", "revive", "ledger_attribute"], event_prefixes=["kill."]),
        _row("svc-plain", KEY_PLAIN, ["kill"]),
    ]), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    assert oa.mode() == oa.LOG_ONLY
    return p


@pytest.fixture()
def enforce(log_only, monkeypatch):
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    assert oa.mode() == oa.ENFORCE


def ledger_accepts(body: dict, sent_headers: dict, pub: str) -> tuple[bool, dict]:
    """The ledger's POST /events, in the order it runs: admission with the
    request's headers, then the caller signature over the ADMITTED payload."""
    stored = oa.admit_ledger_event(body["event_type"], body["payload"], sent_headers)
    record = {**body, "payload": stored}
    return verify_caller_signature(record, pub), stored


def unauth_record(claimed=None):
    return {"action": "revive", "path": "/revive/canary-gb10", "reason": "no_credential",
            "claimed_id": claimed, "operator_claimed": claimed}


# --- (1) the signed body verifies over what the ledger stores -------------------------------


@pytest.mark.parametrize("sent,self_reported", [
    (H(), True),                                  # identity-less service
    (H("svc-plain", KEY_PLAIN), True),            # identity without ledger_attribute
    (H("svc-killswitch", KEY_KS), False),         # attributing identity (C-15)
], ids=["no-identity", "plain-identity", "attributing-identity"])
def test_log_only_unauthenticated_record_verifies_after_admission(log_only, pair, sent, self_reported):
    signer, pub = pair
    oa.bind(oa.authenticate({}, "revive"))       # the probe: no credential
    body = signed_append_body(signer, "operator.unauthenticated", unauth_record(), None, sent)
    ok, stored = ledger_accepts(body, sent, pub)
    assert ok, "the ledger would refuse this record 403 (invalid caller signature)"
    assert body["payload"] == stored              # what was signed IS what is stored
    assert stored["self_reported"] is self_reported
    assert not any(k in stored for k in oa.RESERVED_KEYS)


def test_a_key_shaped_claim_is_masked_before_signing(log_only, pair):
    signer, pub = pair
    claimed = "fok_" + "x" * 40                   # a key pasted into the id header
    oa.bind(oa.OperatorAuth(oa.LOG_ONLY, claimed=oa.NOT_SHOWN, failure="bad_credential"))
    body = signed_append_body(signer, "operator.unauthenticated", unauth_record(claimed), None, H())
    ok, stored = ledger_accepts(body, H(), pub)
    assert ok and stored["claimed_id"] == oa.NOT_SHOWN
    assert claimed not in json.dumps(body)


def test_enforce_refused_record_verifies_after_admission(enforce, pair):
    signer, pub = pair
    payload = {"action": "kill", "path": "/kill/x", "reason": "no_credential", "status": 401,
               "claimed_id": None, "operator_claimed": None}
    body = signed_append_body(signer, "operator.refused", payload, "x", H())
    ok, stored = ledger_accepts(body, H(), pub)
    assert ok and stored["self_reported"] is True


@pytest.mark.parametrize("sent,kept", [
    (H("svc-killswitch", KEY_KS), True),          # ledger_attribute covers kill.
    (H("svc-plain", KEY_PLAIN), False),           # no ledger_attribute: stripped, still signed
    (H(), False),
], ids=["attributing", "plain", "no-identity"])
def test_ordinary_event_with_reserved_keys_verifies_after_admission(log_only, pair, sent, kept):
    """C-12 / every attributed service row: a human's authenticated id merged in
    by merge_payload survives only where the ledger lets it; either way the
    signature verifies (a start-type event was refused 403, a stop-type one
    landed caller_unsigned)."""
    signer, pub = pair
    oa.bind(oa.authenticate(H("don", KEY_DON), "kill"))
    body = signed_append_body(signer, "kill.agent", {"agent": "a1"}, "a1", sent)
    ok, stored = ledger_accepts(body, sent, pub)
    assert ok
    assert (stored.get("operator_id_authenticated") == "don") is kept


def test_flags_off_signed_body_is_unchanged(pair):
    signer, pub = pair
    body = signed_append_body(signer, "kill.agent", {"agent": "a1"}, "a1", H())
    assert body["payload"] == {"agent": "a1"}
    assert verify_caller_signature(body, pub)


def test_unsigned_client_body_is_byte_identical_to_before(log_only):
    """No signer: the ledger applies the admission itself, the body is what it was."""
    oa.bind(oa.authenticate({}, "revive"))
    body = signed_append_body(None, "operator.unauthenticated", unauth_record("don"), None, H())
    assert body == {"event_type": "operator.unauthenticated", "agent_id": None,
                    "payload": oa.merge_payload(unauth_record("don"))}   # as before this change
    assert "operator_id_authenticated" in body["payload"]       # the ledger strips it, not the client
    assert "self_reported" not in body["payload"]


class _Resp:
    def __init__(self, status):
        self.status_code = status
        self.text = "refused"

    def json(self):
        return {}


class _Http:
    """An injected transport: records what was sent, answers ``status``."""

    def __init__(self, status=201, headers=None):
        self.status = status
        self.headers = headers or {}
        self.sent = []

    def post(self, url, **kw):
        self.sent.append(kw["json"])
        return _Resp(self.status)


def test_ledger_client_predicts_with_the_injected_clients_headers(log_only, pair):
    signer, pub = pair
    http = _Http(headers=H("svc-killswitch", KEY_KS))
    oa.bind(oa.authenticate({}, "revive"))
    LedgerClient(client=http, caller=signer).append("operator.unauthenticated", unauth_record())
    ok, stored = ledger_accepts(http.sent[0], http.headers, pub)
    assert ok and stored["self_reported"] is False


def test_ledger_client_own_transport_predicts_with_auth_headers(log_only, pair, monkeypatch):
    """A client built here sends auth_headers() (the service's own pair); the
    prediction uses exactly those."""
    signer, pub = pair
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-killswitch")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY_KS)
    lc = LedgerClient(base_url="http://127.0.0.1:9", caller=signer)
    http = _Http()
    lc._client = http                              # own client, no network
    oa.bind(oa.authenticate({}, "revive"))
    lc.append("operator.unauthenticated", unauth_record())
    ok, stored = ledger_accepts(http.sent[0], H("svc-killswitch", KEY_KS), pub)
    assert ok and stored["self_reported"] is False


def test_append_failure_carries_the_http_status():
    with pytest.raises(LedgerUnreachableError) as ei:
        LedgerClient(client=_Http(403)).append("kill.agent", {})
    assert ei.value.status_code == 403
    assert LedgerUnreachableError("x").status_code is None


# --- (2)/(3) a failed operator-record append is counted and logged, never silent ------------


class FailingLedger:
    def __init__(self, exc):
        self.exc = exc
        self.calls = 0

    def append(self, event_type, payload, agent_id=None):
        self.calls += 1
        raise self.exc


FAILURES = [
    (LedgerUnreachableError("ledger append returned 403: invalid caller signature", status_code=403), "403"),
    (LedgerUnreachableError("ledger append returned 503: busy", status_code=503), "503"),
    (LedgerUnreachableError("timed out"), "LedgerUnreachableError"),
    (RuntimeError("boom"), "RuntimeError"),
]


@pytest.mark.parametrize("exc,status", FAILURES, ids=["403", "503", "unreachable", "other"])
def test_failed_unauthenticated_append_is_counted_and_logged(log_only, exc, status, caplog):
    led = FailingLedger(exc)
    before = oa.dropped_unauthenticated_records
    auth = oa.authenticate(H("don", "tkv-wrong-key-0123456789abcdef"), "revive")
    with caplog.at_level(logging.WARNING, logger="field_core.operator_auth"):
        oa._record_unauthenticated(led, "revive", "/revive/x", auth)
    assert led.calls == 1
    assert oa.dropped_unauthenticated_records == before + 1
    lines = [r.getMessage() for r in caplog.records if "append failed" in r.getMessage()]
    assert lines == [f"operator.unauthenticated ledger append failed (status={status}); "
                     "counted in dropped_unauthenticated_records"]
    for leaked in ("invalid caller signature", "busy", "tkv-", SECRET_HDR, "don"):
        assert leaked not in lines[0]


def test_failed_refused_append_is_counted_and_logged(enforce, caplog):
    led = FailingLedger(LedgerUnreachableError("ledger append returned 403: x", status_code=403))
    oh = operator_health.OperatorHealth(None, lambda app: led)
    with caplog.at_level(logging.WARNING, logger="field_core.operator_auth"):
        oh.note_refused(oa.OperatorRefused(401, oa.UNAUTH_DETAIL), action="kill", path="/kill/x",
                        headers=H("don", KEY_DON))
    assert led.calls == 1
    f = oh.health_fields()
    assert f["refused_count"] == 1 and f["dropped_refused_records"] == 1
    lines = [r.getMessage() for r in caplog.records if "append failed" in r.getMessage()]
    assert lines == ["operator.refused ledger append failed (status=403); counted in dropped_refused_records"]
    assert KEY_DON not in lines[0]


def test_a_successful_append_is_not_counted(log_only):
    class Ok:
        def append(self, *a, **k):
            return {}
    before = oa.dropped_unauthenticated_records
    oa._record_unauthenticated(Ok(), "revive", "/revive/x", oa.authenticate({}, "revive"))
    assert oa.dropped_unauthenticated_records == before


# --- (4) LOG-ONLY never refuses the request because the append failed -----------------------


def test_log_only_guard_allows_the_write_when_the_append_fails(log_only):
    app = FastAPI()
    led = FailingLedger(LedgerUnreachableError("ledger append returned 403: x", status_code=403))
    oh = operator_health.install(app, ledger_getter=lambda a: led)

    @app.post("/revive/{agent_id}")
    def revive(agent_id: str, _op=Depends(oh.guard("revive"))):
        return {"revived": agent_id}

    before = oa.dropped_unauthenticated_records
    with TestClient(app) as c:
        for h in ({}, {oa.HEADER_OPERATOR: "don"}, {oa.HEADER_OPERATOR: "don",
                                                    oa.HEADER_KEY: "tkv-wrong-key-0123456789abcdef"}):
            r = c.post("/revive/a1", headers=h)
            assert r.status_code == 200 and r.json() == {"revived": "a1"}
    assert led.calls == 3
    assert oa.dropped_unauthenticated_records == before + 3
    assert oh.health_fields()["dropped_unauthenticated_records"] == before + 3
