"""S8-14 — scan_n8n_export tolerates nothing silently: a wrong-shaped workflow is a named ScanInputError
(POST /discover 422, CLI exit 2), never a 500 and never a quiet skip (a skipped node could hide an AI node
and read as 'no shadow agents'). The n8n input is size-capped like every other scanner input."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.discover import scan_n8n_export
from agent_registry.redaction import MAX_SCAN_BYTES, ScanInputError
from agent_registry.store import RegistryStore

FIXTURES = Path(__file__).parent / "fixtures"
LEAK = "VALUE-MUST-NOT-LEAK"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    store = RegistryStore(tmp_path / "agents.sqlite3")
    yield TestClient(create_app(store=store), raise_server_exceptions=False)
    store.close()


AI = {"name": "AI step", "type": "n8n-nodes-langchain.agent"}

BAD = [
    ("nodes-null", {"name": "x", "nodes": None}),
    ("nodes-string", {"name": "x", "nodes": LEAK}),
    ("nodes-number", {"name": "x", "nodes": 5}),
    ("nodes-object", {"name": "x", "nodes": {"a": 1}}),
    ("node-string", {"name": "x", "nodes": [LEAK]}),
    ("node-number", {"name": "x", "nodes": [1]}),
    ("node-null", {"name": "x", "nodes": [None]}),
    ("node-list", {"name": "x", "nodes": [[1]]}),
    ("type-number", {"name": "x", "nodes": [{"name": "n", "type": 5}]}),
    ("type-object", {"name": "x", "nodes": [{"name": "n", "type": {"a": LEAK}}]}),
    ("second-workflow-bad", None),  # filled below
]


@pytest.mark.parametrize("label, wf", [b for b in BAD if b[1] is not None], ids=lambda v: v if isinstance(v, str) else "")
def test_a_wrong_shaped_workflow_is_a_named_422_not_a_500(client, label, wf):
    r = client.post("/discover", json={"n8n_export": wf})
    assert r.status_code == 422, (label, r.status_code, r.text)
    assert "n8n_export" in r.json()["detail"]
    assert LEAK not in r.text


def test_the_same_through_the_library_is_scan_input_error_not_type_or_attribute_error():
    for _, wf in BAD:
        if wf is None:
            continue
        with pytest.raises(ScanInputError, match="n8n_export"):
            scan_n8n_export(wf, [])


def test_a_bad_workflow_in_a_list_names_its_position(client):
    r = client.post("/discover", json={"n8n_export": [{"name": "ok", "nodes": [AI]}, {"name": "bad", "nodes": None}]})
    assert r.status_code == 422 and "workflow 2" in r.json()["detail"]


def test_a_workflow_that_is_not_an_object_inside_a_list_is_refused_by_the_library():
    for bad in ([1], ["x"], [None], [[{"a": 1}]]):
        with pytest.raises(ScanInputError, match="workflow 1"):
            scan_n8n_export(bad, [])


def test_a_missing_nodes_key_is_still_an_empty_workflow(client):
    r = client.post("/discover", json={"n8n_export": {"name": "no-nodes"}})
    assert r.status_code == 200 and r.json()["candidates"] == []


def test_the_fixture_scan_is_unchanged(client):
    n8n = json.loads((FIXTURES / "n8n-export.json").read_text(encoding="utf-8"))
    r = client.post("/discover", json={"n8n_export": n8n})
    assert r.status_code == 200
    assert r.json()["scanned_workflows"] == 3
    assert len([c for c in r.json()["candidates"] if c["source"] == "n8n"]) == 2


def test_an_oversized_export_is_a_named_422(client):
    big = {"name": "big", "nodes": [{"name": "n", "type": "x", "parameters": "p" * 1000}] * (MAX_SCAN_BYTES // 1000 + 50)}
    r = client.post("/discover", json={"n8n_export": big})
    assert r.status_code == 422 and "n8n_export" in r.json()["detail"] and "1 MiB" in r.json()["detail"]


def test_an_export_just_under_the_cap_still_scans(client):
    wf = {"name": "ok", "nodes": [{"name": "n", "type": "x", "parameters": "p" * 1000}] * 900}
    assert len(json.dumps(wf)) < MAX_SCAN_BYTES
    assert client.post("/discover", json={"n8n_export": wf}).status_code == 200
