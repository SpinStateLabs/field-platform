"""Phase G: /rotate and /hold on the sealed ledger need an authenticated operator."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore

KEY_DON = "fok_don-key-0123456789abcdef"
KEY_SVC = "fok_svc-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def enforce(tmp_path, monkeypatch):
    rows = [
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON),
         "status": "active", "scopes": ["*"]},
        {"operator_id": "svc", "key_sha256": oa.key_sha256(KEY_SVC),
         "status": "active", "scopes": ["kill"]},
    ]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=LedgerStore(tmp_path / "e.jsonl")))


HOLD = {"by": "Don", "reason": "litigation"}


def events(client, t):
    return client.get("/events", params={"event_type": t}).json()


def test_off_by_default_hold_needs_no_headers(client):
    assert client.post("/hold", json=HOLD).status_code == 201
    p = events(client, "ledger.legal_hold.placed")[0]["payload"]
    assert "operator_id_authenticated" not in p


@pytest.mark.parametrize("path,body", [
    ("/hold", HOLD), ("/hold/release", {"by": "Don"}),
    ("/rotate", {"operator": "Don", "reason": "r"}),
])
def test_refusals_on_every_guarded_ledger_write(client, enforce, path, body):
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers=hdr("don", "fok_wrong")).status_code == 403
    assert client.post(path, json=body, headers=hdr("don", KEY_SVC)).status_code == 403
    assert client.post(path, json=body, headers=hdr("svc", KEY_SVC)).status_code == 403  # scope
    assert client.get("/hold").json()["held"] is False
    assert events(client, "ledger.legal_hold.placed") == []


def test_authenticated_hold_and_release_record_the_id_in_the_event(client, enforce):
    h = hdr("don", KEY_DON)
    assert client.post("/hold", json=HOLD, headers=h).status_code == 201
    assert client.post("/hold/release", json={"by": "Don"}, headers=h).status_code == 200
    for t in ("ledger.legal_hold.placed", "ledger.legal_hold.released"):
        p = events(client, t)[0]["payload"]
        assert p["operator_id_authenticated"] == "don"
        assert p["operator_key_fp"] == oa.key_sha256(KEY_DON)[:8]


def test_log_only_hold_is_allowed_and_ledgers_operator_unauthenticated(client, enforce, monkeypatch):
    monkeypatch.delenv(oa.ENV_REQUIRE)
    assert client.post("/hold", json=HOLD).status_code == 201
    assert events(client, "operator.unauthenticated")[0]["payload"]["action"] == "hold"


def test_unreadable_operator_registry_denies_503(client, enforce, tmp_path):
    (tmp_path / "operators.json").write_text("nope")
    assert client.post("/hold", json=HOLD, headers=hdr("don", KEY_DON)).status_code == 503
    assert client.get("/hold").json()["held"] is False


# --- review findings: retention/apply guard, forged fields on POST /events -----------

KEY_ASSERT = "fok_assert-key-0123456789abcdef"
FORGED = {"operator_id_authenticated": "don", "operator_key_fp": "deadbeef",
          "operator_claimed": "don"}


@pytest.fixture()
def enforce_assert(enforce, tmp_path, monkeypatch):
    p = tmp_path / "operators.json"
    rows = json.loads(p.read_text())
    rows.append({"operator_id": "ksvc", "key_sha256": oa.key_sha256(KEY_ASSERT),
                 "status": "active", "scopes": ["kill", "ledger_attribute"],
                 "event_prefixes": ["x."]})
    p.write_text(json.dumps(rows))


def test_retention_apply_is_guarded(client, enforce):
    body = {"operator": "Don", "days": 1}
    assert client.post("/retention/apply", json=body).status_code == 401
    assert client.post("/retention/apply", json=body,
                       headers=hdr("don", "fok_wrong")).status_code == 403
    assert client.post("/retention/apply", json=body,
                       headers=hdr("svc", KEY_SVC)).status_code == 403          # no retention scope
    assert client.post("/retention/apply", json=body,
                       headers=hdr("don", KEY_DON)).status_code != 401


def test_forged_operator_fields_on_post_events_are_dropped(client, enforce_assert):
    for h in ({}, hdr("don", KEY_DON), hdr("svc", KEY_SVC), hdr("don", "fok_wrong")):
        r = client.post("/events", json={"event_type": "x.forged", "payload": {"a": 1, **FORGED}},
                        headers=h)
        assert r.status_code == 201, h
    for ev in events(client, "x.forged"):
        assert not (set(FORGED) & set(ev["payload"])) and ev["payload"]["a"] == 1


def test_assert_operator_service_identity_may_carry_the_fields(client, enforce_assert):
    r = client.post("/events", json={"event_type": "x.real", "payload": FORGED},
                    headers=hdr("ksvc", KEY_ASSERT))
    assert r.status_code == 201
    assert events(client, "x.real")[0]["payload"]["operator_id_authenticated"] == "don"


def test_flags_off_events_are_stored_untouched(client):
    client.post("/events", json={"event_type": "x.off", "payload": FORGED})
    assert events(client, "x.off")[0]["payload"] == FORGED


def test_hold_body_name_is_replaced_by_the_authenticated_id(client, enforce):
    client.post("/hold", json={"by": "CEO Jane", "reason": "r"}, headers=hdr("don", KEY_DON))
    assert client.get("/hold").json()["hold"]["placed_by"] == "don"
    assert events(client, "ledger.legal_hold.placed")[0]["payload"]["operator_body_claimed"] == "CEO Jane"


# --- second review round -------------------------------------------------------------


def test_reserved_event_type_cannot_be_forged_on_post_events(client, enforce_assert):
    # C-10 / C-15 (design v0.4 2.3; reviewer ruling for the core + health slice):
    # an operator.* type other than the two self-reportable ones is refused to
    # every HTTP caller, the attributing identity included; operator.unauthenticated
    # is evidence any shared-secret caller may write, stamped self_reported unless
    # the caller authenticates with ledger_attribute.
    forged = {"event_type": "operator.mode_changed", "payload": {"mode": "off"}}
    assert client.post("/events", json=forged).status_code == 403
    assert client.post("/events", json=forged, headers=hdr("don", KEY_DON)).status_code == 403
    assert client.post("/events", json=forged, headers=hdr("ksvc", KEY_ASSERT)).status_code == 403
    assert events(client, "operator.mode_changed") == []
    body = {"event_type": "operator.unauthenticated", "payload": {"action": "kill"}}
    assert client.post("/events", json=body).status_code == 201
    assert client.post("/events", json=body, headers=hdr("don", KEY_DON)).status_code == 201
    assert client.post("/events", json=body, headers=hdr("ksvc", KEY_ASSERT)).status_code == 201
    assert [e["payload"]["self_reported"]
            for e in events(client, "operator.unauthenticated")] == [True, True, False]


def test_flags_off_reserved_event_type_is_accepted(client):
    body = {"event_type": "operator.unauthenticated", "payload": {}}
    assert client.post("/events", json=body).status_code == 201


def test_export_is_guarded_and_confined_to_the_export_root(client, enforce, tmp_path, monkeypatch):
    root = tmp_path / "export-root"
    monkeypatch.setenv("FIELD_EXPORT_ROOT", str(root))
    assert client.post("/export").status_code == 401
    assert client.post("/export", headers=hdr("don", "fok_wrong")).status_code == 403
    assert client.post("/export", headers=hdr("svc", KEY_SVC)).status_code == 403     # kill-only
    h = hdr("don", KEY_DON)
    outside = tmp_path / "elsewhere"
    assert client.post("/export", params={"out_dir": str(outside)}, headers=h).status_code == 422
    assert client.post("/export", params={"out_dir": str(root / ".." / "elsewhere")},
                       headers=h).status_code == 422
    assert client.post("/export", params={"out_dir": "../../etc"}, headers=h).status_code == 422
    assert not outside.exists()
    ok = client.post("/export", params={"out_dir": "sub"}, headers=h)
    assert ok.status_code == 200, ok.text
    assert (root / "sub").exists()
