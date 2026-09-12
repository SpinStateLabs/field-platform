"""``POST /pack`` tests — the evidence-pack rules hold over HTTP too (A3).

The CLI (``crosswalk pack``) stays the canonical path; ``POST /pack`` is a
thin adapter over ``generate_pack``. These tests prove the adapter neither
weakens nor rewrites the rules: signer gate → 422, stale corpus → 409 that
names the framework and the affected control ids, unknown body keys → 422,
happy path byte-identical to ``generate_pack`` for the same inputs, and the
shared-secret perimeter (401) applies to the route.

``resolved_manifest()`` is copied from ``test_evidence_pack.py`` on purpose
(no cross-test imports; each suite stands alone).
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from compliance_crosswalk import api as api_module
from compliance_crosswalk.api import create_app
from compliance_crosswalk.engine import EvidenceSources
from compliance_crosswalk.evidence_pack import generate_pack
from compliance_crosswalk.staleness import StaleStore, affected_controls
from field_core.templates_api import template_data

DISCLAIMER_SENTENCE = (
    "Signature is the action — this system never asserts compliance; "
    "a named human signs, or nothing ships."
)
SIGNER = "Controller, Spin State Labs"


def resolved_manifest():
    data = template_data("default")
    data["agent"]["name"] = "evidence-pack-test-agent"
    data["agent"]["description"] = "exercises evidence-pack generation"
    data["identity"]["principal"] = "Controller, Spin State Labs"
    data["identity"]["org"] = "Spin State Labs"
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = "http://127.0.0.1:8005/kill/x"
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["enforcement"]["kill_switch"]["authorized_operators"] = ["Controller"]
    data["ledger"]["store"] = "sealed-ledger service"
    data["delegation"]["granted_by"] = "Controller, Spin State Labs"
    data["delegation"]["scope"] = ["generate evidence packs"]
    data["delegation"]["revocation"] = {"method": "HTTP POST", "endpoint": "http://x"}
    return data


@pytest.fixture
def store(tmp_path):
    return StaleStore(tmp_path / "stale_flags.json")


@pytest.fixture
def client(store):
    return TestClient(create_app(stale_store=store))


# --- happy path ---------------------------------------------------------------

def test_pack_happy_path_200_with_disclaimer_and_signer(client):
    r = client.post("/pack", json={"signer": SIGNER, "manifest": resolved_manifest()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"markdown", "pack"}
    assert DISCLAIMER_SENTENCE in body["markdown"]
    assert body["pack"]["signer"] == SIGNER
    assert f"Prepared for signature by: {SIGNER}" in body["markdown"]
    assert body["pack"]["manifest_valid"] is True
    assert body["pack"]["agent_id"] is None
    assert body["pack"]["staleness"]["active"] == []


def test_pack_equals_generate_pack_for_same_inputs(client, store):
    """Thin adapter: the HTTP result is exactly generate_pack's result for
    the same inputs. The only free variable is the clock, so the response's
    own generated_at is fed back through the ``now=`` seam (no sleeps, no
    monkeypatched datetime)."""
    manifest = resolved_manifest()
    sources = EvidenceSources(
        ledger_verify={"ok": False, "reason": "hash mismatch at index 2"},
    )
    r = client.post(
        "/pack",
        json={
            "signer": SIGNER,
            "manifest": manifest,
            "agent_id": "agent-1",
            "sources": sources.model_dump(),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    now = datetime.fromisoformat(body["pack"]["generated_at"])
    md, payload = generate_pack(
        manifest,
        signer=SIGNER,
        stale_store=store,
        agent_id="agent-1",
        sources=sources,
        now=now,
    )
    assert body["markdown"] == md
    assert body["pack"] == payload
    # the not-evidenced gap survived the HTTP round trip verbatim
    assert ("FC-L-01", "not-evidenced") in {
        (g["control_id"], g["kind"]) for g in body["pack"]["gaps"]
    }


def test_pack_signer_is_stripped_like_the_cli_path(client):
    r = client.post(
        "/pack", json={"signer": f"  {SIGNER}  ", "manifest": resolved_manifest()}
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack"]["signer"] == SIGNER


# --- adversarial: signer gate and body discipline -----------------------------

@pytest.mark.parametrize("bad", ["", "   ", " \t "])
def test_adversarial_blank_signer_422(client, bad):
    r = client.post("/pack", json={"signer": bad, "manifest": resolved_manifest()})
    assert r.status_code == 422, r.text
    assert "no pack ships without a named signer" in r.json()["detail"]


def test_adversarial_missing_signer_422(client):
    r = client.post("/pack", json={"manifest": resolved_manifest()})
    assert r.status_code == 422, r.text


def test_adversarial_missing_manifest_422(client):
    """manifest is REQUIRED — B0 landed the shared resolver, but this service
    does not yet wire the registry lookup into it; optionality lands in D4."""
    r = client.post("/pack", json={"signer": SIGNER, "agent_id": "agent-1"})
    assert r.status_code == 422, r.text


def test_adversarial_unknown_body_key_422(client):
    r = client.post(
        "/pack",
        json={"signer": SIGNER, "manifest": resolved_manifest(), "override": True},
    )
    assert r.status_code == 422, r.text
    r = client.post(
        "/pack",
        json={"signer": SIGNER, "manifest": resolved_manifest(), "force": True},
    )
    assert r.status_code == 422, r.text


# --- adversarial: stale corpus blocks over HTTP, no override -------------------

def test_adversarial_stale_flag_409_names_framework_and_affected_controls(client, store):
    store.mark("osfi-e23", "OSFI E-23 guidance page revision detected")
    r = client.post("/pack", json={"signer": SIGNER, "manifest": resolved_manifest()})
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert set(detail) == {"message", "flags", "affected_controls"}
    assert "osfi-e23" in detail["message"]
    assert "there is no override" in detail["message"]
    assert [f["framework"] for f in detail["flags"]] == ["osfi-e23"]
    assert detail["flags"][0]["reason"] == "OSFI E-23 guidance page revision detected"
    expected = affected_controls("osfi-e23")
    assert expected, "OSFI must be cited on at least one control"
    assert detail["affected_controls"] == {"osfi-e23": expected}
    assert "FC-I-01" in detail["affected_controls"]["osfi-e23"]

    # a named re-review clears the block; the flag lives on in history
    store.clear("osfi-e23", reviewed_by=SIGNER)
    r = client.post("/pack", json={"signer": SIGNER, "manifest": resolved_manifest()})
    assert r.status_code == 200, r.text
    history = r.json()["pack"]["staleness"]["history"]
    assert [h["reviewed_by"] for h in history] == [SIGNER]


def test_adversarial_two_stale_frameworks_both_reported(client, store):
    store.mark("osfi-e23", "revision")
    store.mark("eu-ai-act", "amendment", new_version="2026-Q3")
    r = client.post("/pack", json={"signer": SIGNER, "manifest": resolved_manifest()})
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert [f["framework"] for f in detail["flags"]] == ["eu-ai-act", "osfi-e23"]
    assert detail["affected_controls"] == {
        "eu-ai-act": affected_controls("eu-ai-act"),
        "osfi-e23": affected_controls("osfi-e23"),
    }


def test_default_store_path_used_when_nothing_injected(tmp_path, monkeypatch):
    """create_app() with no seam falls back to StaleStore() at request time,
    which reads $FIELD_DATA_DIR/crosswalk_stale_flags.json — the same file
    the CLI's ``regwatch`` verbs write."""
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path))
    client = TestClient(create_app())
    assert client.post(
        "/pack", json={"signer": SIGNER, "manifest": resolved_manifest()}
    ).status_code == 200
    StaleStore(tmp_path / "crosswalk_stale_flags.json").mark("nist-ai-rmf", "RMF 2.0")
    r = client.post("/pack", json={"signer": SIGNER, "manifest": resolved_manifest()})
    assert r.status_code == 409, r.text
    assert "nist-ai-rmf" in r.json()["detail"]["affected_controls"]
    assert client.get("/staleness").json()["active"][0]["framework"] == "nist-ai-rmf"


# --- evidence collection precedence mirrors the CLI ---------------------------

def test_sources_in_body_take_precedence_over_live_collection(client, monkeypatch):
    calls: list[str] = []

    def fake_collect(agent_id: str) -> EvidenceSources:
        calls.append(agent_id)
        return EvidenceSources(ledger_verify={"ok": True})

    monkeypatch.setattr(api_module, "collect_evidence", fake_collect)

    # explicit sources: no live collection
    r = client.post(
        "/pack",
        json={
            "signer": SIGNER,
            "manifest": resolved_manifest(),
            "agent_id": "agent-1",
            "sources": {"ledger_verify": {"ok": False, "reason": "broken chain"}},
        },
    )
    assert r.status_code == 200, r.text
    assert calls == []
    assert "broken chain" in r.json()["markdown"]

    # agent_id only: collect, exactly as ``crosswalk pack --agent-id`` does
    r = client.post(
        "/pack",
        json={"signer": SIGNER, "manifest": resolved_manifest(), "agent_id": "agent-1"},
    )
    assert r.status_code == 200, r.text
    assert calls == ["agent-1"]
    row = next(c for c in r.json()["pack"]["controls"] if c["control_id"] == "FC-L-01")
    assert row["evidenced"] is True

    # neither: manifest-only, nothing collected
    r = client.post("/pack", json={"signer": SIGNER, "manifest": resolved_manifest()})
    assert r.status_code == 200, r.text
    assert calls == ["agent-1"]
    assert "manifest-only" in r.json()["markdown"]


# --- perimeter and seams ------------------------------------------------------

def test_pack_401_without_shared_secret_header(monkeypatch, store):
    monkeypatch.setenv("FIELD_SHARED_SECRET", "test-secret")
    client = TestClient(create_app(stale_store=store))
    assert client.get("/health").status_code == 200  # liveness stays open
    body = {"signer": SIGNER, "manifest": resolved_manifest()}
    assert client.post("/pack", json=body).status_code == 401
    assert client.post(
        "/pack", json=body, headers={"x-field-auth": "wrong"}
    ).status_code == 401
    r = client.post("/pack", json=body, headers={"x-field-auth": "test-secret"})
    assert r.status_code == 200, r.text


def test_create_app_seams_and_description_drift_fixed(store):
    sentinel = object()
    app = create_app(stale_store=store, fetcher=sentinel)
    assert app.state.stale_store is store
    assert app.state.fetcher is sentinel  # held for D4; unused today
    assert create_app().state.stale_store is None
    assert "stub" not in app.description.lower()
    assert "16/40" in app.description
    assert "pending-purchase" in app.description
