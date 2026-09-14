"""System-3 integration tests — self-manifest, corpus-version consistency,
and the read-only /staleness API surface."""

from fastapi.testclient import TestClient

from field_core.validation import validate_manifest_data

from compliance_crosswalk.mapping import RETRIEVED
from compliance_crosswalk.self_manifest import (
    SELF_AGENT_ID,
    load_self_manifest,
)
from compliance_crosswalk.staleness import CORPUS_VERSION

GENERATION_VERBS = ("read", "report", "suggest", "draft")


def test_self_manifest_validates_and_names_the_cto():
    data = load_self_manifest()
    assert validate_manifest_data(data).ok
    assert data["agent"]["name"] == SELF_AGENT_ID == "compliance-crosswalk"
    assert "CTO" in data["identity"]["principal"]
    cap = data["enforcement"]["spend_cap"]
    assert cap["limit"] == 5 and cap["period"] == "daily"
    assert round(cap["limit"] * 100) == 500  # cents, governor set-cap flow


def test_self_manifest_scope_is_generation_verbs_only():
    """The Crosswalk never signs, never asserts, never mutates the matrix —
    its delegated scope carries only generation verbs, plus the one egress
    ACTION (`llm.messages`, F1): the fixed action an enforcing force-gateway
    checks for the suggester's own LLM calls. It is an action name, not a
    verb, and it grants nothing beyond calling the model through the gateway."""
    scope = load_self_manifest()["delegation"]["scope"]
    assert scope
    assert "llm.messages" in scope  # F1: without it every suggester call is D.scope
    for entry in scope:
        if entry == "llm.messages":
            continue
        assert entry.split()[0] in GENERATION_VERBS, entry


def test_corpus_version_pins_the_ingestion_date():
    assert CORPUS_VERSION == f"corpus-{RETRIEVED}" == "corpus-2026-08-08"


def test_staleness_api_is_read_only_status(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path))
    from compliance_crosswalk.api import create_app

    client = TestClient(create_app())
    body = client.get("/staleness").json()
    assert body["corpus_version"] == CORPUS_VERSION
    assert body["active"] == []
    # and the API surface exposes no route that could mutate staleness
    from fastapi.routing import APIRoute

    for route in client.app.routes:
        if isinstance(route, APIRoute) and "staleness" in route.path:
            assert route.methods == {"GET"}
