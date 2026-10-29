"""C-198 (reviewer C-194 F-C194-3/-4/-5/-6): exact-now expiry boundaries, the designed 502 when the
registry is unreachable, the field names of the `delegation.mint` and `delegation.revoke` evidence
rows, and the request-model minimums. Time is frozen in `delegation_authority.api` so "now" is exact
to the microsecond."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from delegation_authority import api as api_mod
from delegation_authority.api import create_app
from delegation_authority.clients import LedgerClient, RegistryClient
from delegation_authority.store import TokenStore
from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from test_redteam_mint_matrix import (AGENT_ID, GRANTOR, ROSTER_SCOPE, Spine, clause, detail,
                                      write_manifest, write_roster)

US = timedelta(microseconds=1)
NOW = datetime(2099, 6, 30, 0, 0, 0, tzinfo=timezone.utc)   # == midnight UTC of the manifest expiry date


def freeze(monkeypatch, instant):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant if tz is None else instant.astimezone(tz)

    monkeypatch.setattr(api_mod, "datetime", Frozen)


@pytest.fixture(autouse=True)
def _no_secret(monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.delenv("FIELD_DOA_ROSTER", raising=False)


# --- F-C194-3: the token's own expiry boundary (api.py `expires <= now`) ------------------------


@pytest.mark.parametrize(("offset", "status"), [(-US, 422), (timedelta(0), 422), (US, 201)])
def test_a_token_expiring_at_or_before_now_is_refused(tmp_path, monkeypatch, offset, status):
    s = Spine(tmp_path, None)
    freeze(monkeypatch, NOW)
    r = s.mint(ttl_seconds=None, expires_at=(NOW + offset).isoformat())
    assert r.status_code == status, r.text
    if status == 422:
        assert detail(r) == "expires_at is in the past"
        s.assert_no_side_effects()


# --- F-C194-3: the manifest's expiry boundary (api.py `manifest_expiry <= now`) -----------------


def armed(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path)))
    return Spine(tmp_path, write_manifest(tmp_path, expiry="2099-06-30"))


@pytest.mark.parametrize(("offset", "in_the_past"), [(-US, False), (timedelta(0), True), (US, True)])
def test_a_manifest_expiring_at_or_before_now_is_in_the_past(tmp_path, monkeypatch, offset, in_the_past):
    """At now == the manifest expiry the refusal says "in the past"; a microsecond earlier the
    manifest is live and the token (an hour long) is refused for outliving it instead."""
    s = armed(tmp_path, monkeypatch)
    freeze(monkeypatch, NOW + offset)
    r = s.mint(ttl_seconds=3600)
    assert (r.status_code, clause(r)) == (422, "D.manifest_expired"), r.text
    message = detail(r)["message"]
    assert ("is in the past" in message) is in_the_past, message
    if not in_the_past:
        assert "is after the agent manifest's delegation.expiry" in message
    s.assert_no_side_effects()


def test_a_token_ending_exactly_at_the_manifest_expiry_is_accepted(tmp_path, monkeypatch):
    s = armed(tmp_path, monkeypatch)
    freeze(monkeypatch, NOW - timedelta(hours=1))
    assert s.mint(ttl_seconds=3600).status_code == 201           # expires == manifest expiry
    freeze(monkeypatch, NOW - timedelta(hours=1) + US)
    r = s.mint(ttl_seconds=3600)                                  # one microsecond past it
    assert (r.status_code, clause(r)) == (422, "D.manifest_expired")


# --- F-C194-5: the registry is unreachable ------------------------------------------------------


class DownClient:
    def post(self, *a, **k):
        raise ConnectionError("service down")

    def get(self, *a, **k):
        raise ConnectionError("service down")


def test_an_unreachable_registry_is_the_designed_502_and_mints_nothing(tmp_path):
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    client = TestClient(
        create_app(store=TokenStore(tmp_path / "tokens.sqlite3"),
                   ledger=LedgerClient(client=ledger, base_url="http://t"),
                   registry=RegistryClient(client=DownClient(), base_url="http://t")),
        raise_server_exceptions=False)
    r = client.post("/tokens", json={"agent_id": AGENT_ID, "granted_by": GRANTOR,
                                     "scope": ["read timesheets"], "ttl_seconds": 3600})
    assert r.status_code == 502
    assert r.json()["detail"].startswith("registry unreachable — refusing to mint")
    assert client.get("/tokens").json() == []
    assert ledger.get("/events", params={"event_type": "delegation.mint"}).json() == []


# --- F-C194-4: the evidence rows' field names ---------------------------------------------------


def test_the_mint_event_carries_its_pinned_fields(tmp_path):
    s = Spine(tmp_path, None)
    token = s.mint(ttl_seconds=3600).json()
    [event] = s.mint_events()
    assert set(event["payload"]) == {"token_id", "granted_by", "scope", "expires_at",
                                     "doa_checked", "doa_row"}
    p = event["payload"]
    assert p["token_id"] == token["token_id"] and p["granted_by"] == GRANTOR
    assert p["scope"] == token["scope"] == ["read timesheets", "draft invoices"]
    assert datetime.fromisoformat(p["expires_at"]) == datetime.fromisoformat(
        token["expires_at"].replace("Z", "+00:00"))
    assert p["doa_checked"] is False and p["doa_row"] is None
    assert event["agent_id"] == AGENT_ID


def test_the_mint_event_records_the_roster_row_when_armed(tmp_path, monkeypatch):
    s = armed(tmp_path, monkeypatch)
    assert s.mint(ttl_seconds=3600).status_code == 201
    [event] = s.mint_events()
    assert event["payload"]["doa_checked"] is True and event["payload"]["doa_row"]["grantor"] == GRANTOR


def test_the_revoke_event_carries_the_revocation_id(tmp_path):
    s = Spine(tmp_path, None)
    token = s.mint(ttl_seconds=3600).json()
    r = s.delegation.post(f"/tokens/{token['token_id']}/revoke")
    assert r.status_code == 200
    revocation_id = r.json()["revocation_id"]
    assert revocation_id
    [event] = s.ledger.get("/events", params={"event_type": "delegation.revoke"}).json()
    assert event["payload"] == {"token_id": token["token_id"], "revocation_id": revocation_id}
    assert event["agent_id"] == AGENT_ID
    # idempotent: a second revoke writes no second event
    s.delegation.post(f"/tokens/{token['token_id']}/revoke")
    assert len(s.ledger.get("/events", params={"event_type": "delegation.revoke"}).json()) == 1


# --- F-C194-6: request-model minimums -----------------------------------------------------------


@pytest.mark.parametrize(("field", "value"), [
    ("agent_id", ""), ("granted_by", ""), ("scope", []), ("ttl_seconds", 0), ("ttl_seconds", -1)])
def test_request_model_minimums_are_a_validation_error_not_a_handler_refusal(tmp_path, field, value):
    s = Spine(tmp_path, None)
    r = s.mint(**{field: value})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list), r.text          # pydantic, before any handler logic
    s.assert_no_side_effects()


def test_the_smallest_valid_values_pass_the_model(tmp_path):
    s = Spine(tmp_path, None)
    assert s.mint(ttl_seconds=1, scope=["x"]).status_code == 201
