"""n8n export shapes: a malformed export is refused BY NAME (422 / exit 2), never a 500 or a traceback (scout P-2 (a)).

Before: `scan_n8n_export` called `wf.get(...)` and `node.get(...)` unguarded, so `"nodes": null`, a non-object node or a
non-object workflow raised TypeError / AttributeError out of POST /discover (a 500) and out of `registry scan --n8n`; and
`load_n8n_file` let a missing file, bad JSON or non-UTF-8 bytes escape as a traceback. The messages name a position
(workflow index, node index), never a value. Scout P-2 (b), the substring registered-match, is NOT changed here: it is a
rule for Don (see the PR)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_registry import cli
from agent_registry.api import create_app
from agent_registry.discover import load_n8n_file, scan_n8n_export
from agent_registry.models import AgentCreate
from agent_registry.redaction import ScanInputError
from agent_registry.store import RegistryStore

MARK = "MADE-UP-MARKER-0123456789"
AI_NODE = {"name": "Agent", "type": "@n8n/n8n-nodes-langchain.agent"}


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "agents.sqlite3"
    store = RegistryStore(path)
    store.add(AgentCreate(agent_id="invoicing-agent", name="Invoice Drafting Copilot", owner="Controller", domain="finance"))
    store.close()
    return path


@pytest.fixture()
def client(tmp_path):
    store = RegistryStore(tmp_path / "api.sqlite3")
    yield TestClient(create_app(store=store), raise_server_exceptions=False)
    store.close()


BAD_EXPORTS = [
    {"name": "wf", "nodes": None},
    {"name": "wf", "nodes": "not a list"},
    {"name": "wf", "nodes": {"a": 1}},
    {"name": "wf", "nodes": [None]},
    {"name": "wf", "nodes": [5]},
    {"name": "wf", "nodes": ["x"]},
    {"name": "wf", "nodes": [[AI_NODE]]},
    [{"name": "wf", "nodes": [AI_NODE]}, {"name": "wf2", "nodes": None}],
]


@pytest.mark.parametrize("export", BAD_EXPORTS, ids=range(len(BAD_EXPORTS)))
def test_scan_refuses_a_malformed_export_by_name(export):
    with pytest.raises(ScanInputError):
        scan_n8n_export(export, [])


@pytest.mark.parametrize("export", [5, "x", None, [5], ["x"], [None], [[{"nodes": []}]]], ids=range(7))
def test_scan_refuses_a_non_object_workflow_by_name(export):
    with pytest.raises(ScanInputError):
        scan_n8n_export(export, [])


@pytest.mark.parametrize("export", BAD_EXPORTS[:7], ids=range(7))
def test_the_api_answers_422_not_500(client, export):
    r = client.post("/discover", json={"n8n_export": export})
    assert r.status_code == 422, (r.status_code, r.text)


def test_a_422_names_a_position_and_repeats_no_value(client):
    r = client.post("/discover", json={"n8n_export": {"name": "wf", "nodes": [MARK]}})
    assert r.status_code == 422 and MARK not in r.text, r.text


def test_a_well_formed_export_still_finds_the_unregistered_workflow():
    found = scan_n8n_export({"id": "wf-1", "name": "Billing helper", "nodes": [AI_NODE]}, [])
    assert [c.identifier for c in found] == ["wf-1"]


def test_a_workflow_with_no_nodes_key_is_still_just_not_a_candidate():
    assert scan_n8n_export({"id": "wf-1", "name": "Empty"}, []) == []
    assert scan_n8n_export({"id": "wf-1", "name": "Empty", "nodes": []}, []) == []


# --- the file loader and the CLI ----------------------------------------------------------------


def test_load_n8n_file_refuses_a_missing_file_by_name(tmp_path):
    with pytest.raises(ScanInputError) as e:
        load_n8n_file(str(tmp_path / "nope.json"))
    assert "nope.json" in str(e.value)


def test_load_n8n_file_refuses_invalid_json_and_quotes_none_of_it(tmp_path):
    f = tmp_path / "wf.json"
    f.write_text("{" + MARK, encoding="utf-8")
    with pytest.raises(ScanInputError) as e:
        load_n8n_file(str(f))
    assert "wf.json" in str(e.value) and MARK not in str(e.value)


def test_load_n8n_file_refuses_non_utf8_by_name(tmp_path):
    f = tmp_path / "wf.json"
    f.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ScanInputError) as e:
        load_n8n_file(str(f))
    assert "wf.json" in str(e.value)


@pytest.mark.parametrize("content", [
    None,                                    # file missing
    "{" + MARK,                              # invalid JSON
    json.dumps({"name": "wf", "nodes": None}),
    json.dumps({"name": "wf", "nodes": [MARK]}),
    json.dumps(5),
])
def test_the_cli_exits_2_with_a_one_line_error_not_a_traceback(tmp_path, db, content):
    f = tmp_path / "wf.json"
    if content is not None:
        f.write_text(content, encoding="utf-8")
    r = CliRunner().invoke(cli.app, ["scan", "--n8n", str(f), "--path", str(db)])
    assert r.exit_code == 2, (r.exit_code, r.output, repr(r.exception))
    assert isinstance(r.exception, SystemExit), repr(r.exception)
    assert MARK not in r.output and "Traceback" not in r.output


def test_the_cli_still_scans_a_good_export(tmp_path, db):
    f = tmp_path / "wf.json"
    f.write_text(json.dumps({"id": "wf-1", "name": "Billing helper", "nodes": [AI_NODE]}), encoding="utf-8")
    r = CliRunner().invoke(cli.app, ["scan", "--n8n", str(f), "--path", str(db)])
    assert r.exit_code == 0 or r.exit_code == 3, (r.exit_code, r.output)
    assert "wf-1" in r.output
