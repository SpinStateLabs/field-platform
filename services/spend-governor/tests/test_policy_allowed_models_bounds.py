"""S6-6: ``PUT /policies/{id}`` refuses a blank, oversized or over-long ``allowed_models`` list (422, nothing stored); a blank
entry used to normalise to '' and make EVERY model a ``rogue_model`` with a human escalation each. Entries are
canonicalised and de-duplicated. A stored legacy row still reads (the checks are on write only, C-363)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import MAX_ALLOWED_MODELS, MAX_MODEL_NAME, create_app
from spend_governor.core import GovernorStore

AGENT = "a1"
MARK = "MADE-UP-MARKER-0123456789"


@pytest.fixture()
def rig(tmp_path):
    store = GovernorStore(tmp_path / "s.sqlite3")
    c = TestClient(create_app(store=store))
    assert c.put(f"/caps/{AGENT}", json={"agent_id": AGENT, "limit_cents": 100_000, "period": "daily",
                                         "escalate_at_pct": 80}).status_code == 200
    return c, store


def put(c, models):
    return c.put(f"/policies/{AGENT}", json={"agent_id": AGENT, "allowed_models": models})


def usage(c, model="claude-haiku-4-5"):
    return c.post("/usage", json={"agent_id": AGENT, "model": model, "input_tokens": 10, "output_tokens": 10})


@pytest.mark.parametrize("models", [[""], ["  "], ["\t"], ["claude-haiku-4-5", ""], ["claude-haiku-4-5", "   "],
                                    ["\n"]], ids=repr)
def test_a_blank_entry_is_422_and_nothing_is_stored(rig, models):
    c, _ = rig
    r = put(c, models)
    assert r.status_code == 422 and "blank" in r.text
    assert c.get(f"/policies/{AGENT}").status_code == 404


def test_the_defect_it_closes_a_blank_list_made_every_model_rogue(rig):
    """with the old code PUT [''] was 200 and the next usage record flagged rogue_model."""
    c, _ = rig
    assert put(c, [""]).status_code == 422
    assert "rogue_model" not in [f["kind"] for f in usage(c).json()["rogue"]]


def test_the_list_length_bound(rig):
    c, _ = rig
    ok = put(c, [f"model-{i}" for i in range(MAX_ALLOWED_MODELS)])
    assert ok.status_code == 200
    r = put(c, [f"model-{i}" for i in range(MAX_ALLOWED_MODELS + 1)])
    assert r.status_code == 422 and str(MAX_ALLOWED_MODELS) in r.text


def test_the_entry_length_bound_and_no_echo(rig):
    c, _ = rig
    assert put(c, ["m" * MAX_MODEL_NAME]).status_code == 200
    r = put(c, [MARK + "m" * MAX_MODEL_NAME])
    assert r.status_code == 422 and MARK not in r.text


def test_oversized_list_is_422_before_any_normalisation_cost(rig):
    c, _ = rig
    assert put(c, ["claude-haiku-4-5"] * 5000).status_code == 422


def test_a_valid_list_round_trips_canonical_and_deduplicated(rig):
    c, _ = rig
    r = put(c, ["Claude Haiku 4.5", "claude-haiku-4-5", " claude_haiku_4_5 ", "claude-opus-4-8"])
    assert r.status_code == 200
    assert r.json()["allowed_models"] == ["claude-haiku-4-5", "claude-opus-4-8"]
    assert c.get(f"/policies/{AGENT}").json()["allowed_models"] == ["claude-haiku-4-5", "claude-opus-4-8"]


def test_an_empty_list_still_means_any_model(rig):
    c, _ = rig
    assert put(c, []).status_code == 200
    assert "rogue_model" not in [f["kind"] for f in usage(c).json()["rogue"]]


def test_an_allowed_model_is_not_rogue_and_another_is(rig):
    c, _ = rig
    put(c, ["claude-haiku-4-5"])
    assert "rogue_model" not in [f["kind"] for f in usage(c).json()["rogue"]]
    assert "rogue_model" in [f["kind"] for f in usage(c, "claude-opus-4-8").json()["rogue"]]


def test_a_refused_put_leaves_the_previous_policy_untouched(rig):
    c, _ = rig
    put(c, ["claude-haiku-4-5"])
    assert put(c, [""]).status_code == 422
    assert c.get(f"/policies/{AGENT}").json()["allowed_models"] == ["claude-haiku-4-5"]


def test_a_stored_legacy_row_with_a_blank_or_huge_list_still_reads(rig):
    """no re-validation on read: a row written before these bounds keeps answering 200 on GET /policies."""
    c, store = rig
    with store._lock, store._conn:
        store._conn.execute(
            "INSERT OR REPLACE INTO usage_policies (agent_id, allowed_models, token_rate_limit, rate_window_seconds) "
            "VALUES (?, ?, NULL, 3600)", (AGENT, json.dumps([""] + [f"m{i}" for i in range(500)])))
    r = c.get(f"/policies/{AGENT}")
    assert r.status_code == 200 and len(r.json()["allowed_models"]) == 501
    assert usage(c).status_code == 201
