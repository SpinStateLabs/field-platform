"""RT-HARD-4 F2 (reviewer-9, MEDIUM): the 422 for an unresolvable ``manifest_ref`` is a fixed body. It does not repeat
the caller's text (unbounded, may be key-shaped) and does not name the server's manifest directory.

Every path, ref and key-shaped value here is made up."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_registry import api, cli
from agent_registry.api import create_app
from agent_registry.store import RegistryStore

BODY = {"agent_id": "invoicing-agent", "name": "Invoice Drafting Copilot",
        "owner": "Controller, Spin State Labs", "domain": "finance"}
MADE_UP_DIR = "madeup-manifest-dir-9f3"
KEY_SHAPED = "fok_" + "Q7w8E9r0" * 4


@pytest.fixture()
def registry(tmp_path, monkeypatch):
    d = tmp_path / MADE_UP_DIR
    d.mkdir()
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(d))
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    store = RegistryStore(tmp_path / "agents.sqlite3")
    client = TestClient(create_app(store=store, ledger=None))
    yield client, store
    store.close()


def _post(client, ref):
    return client.post("/agents", json={**BODY, "manifest_ref": ref})


def test_the_422_body_is_error_reason_and_a_fixed_hint_only(registry):
    client, _ = registry
    r = _post(client, "nope.yaml")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert set(detail) == {"error", "reason", "hint"}
    assert detail["error"] == "manifest_ref does not resolve" and detail["reason"] in ("missing", "invalid")


@pytest.mark.parametrize("ref", ["nope.yaml", KEY_SHAPED, "sub/absent.yaml", "x" * 100_000, "../" * 40 + "etc"])
def test_the_caller_text_is_never_echoed_and_the_body_is_bounded(registry, ref):
    client, _ = registry
    r = _post(client, ref)
    assert r.status_code == 422
    assert ref not in r.text and len(r.content) < 1024
    assert "manifest_ref" not in r.json()["detail"]


def test_a_key_shaped_ref_is_not_reflected_in_any_form(registry):
    client, _ = registry
    text = _post(client, KEY_SHAPED).text
    assert KEY_SHAPED not in text and "fok_" not in text and "Q7w8E9r0" not in text


def test_the_manifest_directory_is_not_disclosed(registry, tmp_path):
    client, _ = registry
    text = _post(client, "nope.yaml").text
    assert MADE_UP_DIR not in text and str(tmp_path) not in text and "manifest_dir" not in text


def test_the_body_is_identical_for_two_different_refs_with_the_same_reason(registry):
    client, _ = registry
    a, b = _post(client, "one.yaml").json(), _post(client, "two.yaml").json()
    assert a == b


def test_the_helper_returns_the_same_fixed_shape_for_post_and_patch():
    refusal = api.unresolvable_manifest_ref(KEY_SHAPED + ".yaml")
    assert refusal is not None and set(refusal) == {"error", "reason", "hint"}
    assert KEY_SHAPED not in json.dumps(refusal)
    assert api.unresolvable_manifest_ref(None) is None and api.unresolvable_manifest_ref("") is None


def test_nothing_is_written_for_a_refused_ref(registry):
    client, store = registry
    assert _post(client, KEY_SHAPED).status_code == 422
    assert store.list() == []


def test_the_operator_terminal_command_still_names_the_variable_to_check(tmp_path, monkeypatch):
    """The CLI prints to the person who ran it, on the host: ref, reason and the variable to check."""
    d = tmp_path / MADE_UP_DIR
    d.mkdir()
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(d))
    args = ["add", "invoicing-agent", "--name", "Inv", "--owner", "AP Lead", "--path", str(tmp_path / "c.sqlite3"),
            "--manifest-ref", "absent.yaml"]
    result = CliRunner().invoke(cli.app, args)
    assert result.exit_code == 2, result.output
    assert "does not resolve (missing)" in result.output and "FIELD_MANIFEST_DIR" in result.output
