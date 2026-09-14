"""v1.2 D3b — the registry refuses an unresolvable SET ``manifest_ref`` at
register: ``POST /agents`` 422 and ``registry add`` exit 2.

Resolution is field-core's shared resolver (B0) against ``FIELD_MANIFEST_DIR``
in the registry's own process — the same resolver and the same rule every
reader of ``manifest_ref`` uses (sentinel, delegation, kill-switch, ledger
retention). The refusal happens before any write: nothing persisted, no
``registry.registered`` event, and a duplicate id carrying a bad ref is a 422,
not a 409.

NOT covered, and stated in README LIMITS: ``PATCH /agents/{id}`` can still set
an unresolvable ref, and a ref that resolved at register can stop resolving
later (the file removed) — lifecycle's retention finding and the readers'
``missing``/``invalid`` handling are what see those.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import field_core.clients as fc
from agent_registry import api, cli
from agent_registry.api import create_app
from agent_registry.store import AgentNotFoundError, RegistryStore

FIXTURE_MANIFEST = Path(__file__).parent / "fixtures" / "manifests" / "invoicing-agent.yaml"
BODY = {"agent_id": "invoicing-agent", "name": "Invoice Drafting Copilot",
        "owner": "Controller, Spin State Labs", "domain": "finance"}


class _Ledger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, str | None]] = []

    def append(self, event_type, payload=None, agent_id=None):
        self.events.append((event_type, payload, agent_id))


@pytest.fixture()
def manifest_dir(tmp_path, monkeypatch):
    d = tmp_path / "manifest-dir"
    (d / "sub").mkdir(parents=True)
    (d / "sub" / "good.yaml").write_bytes(FIXTURE_MANIFEST.read_bytes())
    # Parses as YAML, fails field-core's schema validation.
    (d / "sub" / "invalid.yaml").write_text(
        "schema_version: field.spinstatelabs.ca/v1\nagent:\n  name: x\n", encoding="utf-8")
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(d))
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    return d


@pytest.fixture()
def registry(tmp_path, manifest_dir):
    store = RegistryStore(tmp_path / "agents.sqlite3")
    ledger = _Ledger()
    client = TestClient(create_app(store=store, ledger=ledger))
    yield client, store, ledger
    store.close()


def test_the_registry_uses_field_cores_shared_resolver():
    assert api.resolve_manifest_detail is fc.resolve_manifest_detail


@pytest.mark.parametrize("ref, reasons", [
    ("sub/absent.yaml", {"missing"}),
    ("sub/invalid.yaml", {"invalid"}),
    ("sub", {"invalid"}),               # a directory is not a manifest
    # whitespace is SET (not no_ref); Windows resolves it to the directory
    ("   ", {"missing", "invalid"}),
])
def test_an_unresolvable_set_ref_is_422_and_nothing_is_written(registry, ref, reasons):
    client, store, ledger = registry
    r = client.post("/agents", json={**BODY, "manifest_ref": ref})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["reason"] in reasons and detail["manifest_ref"] == ref
    with pytest.raises(AgentNotFoundError):
        store.get("invoicing-agent")
    assert ledger.events == []


def test_an_absolute_ref_to_a_missing_file_is_422(registry, tmp_path):
    client, _, _ = registry
    r = client.post("/agents", json={**BODY, "manifest_ref": str(tmp_path / "gone.yaml")})
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "missing"


def test_a_relative_ref_resolves_under_field_manifest_dir(registry, manifest_dir):
    client, store, ledger = registry
    r = client.post("/agents", json={**BODY, "manifest_ref": "sub/good.yaml"})
    assert r.status_code == 201, r.text
    assert store.get("invoicing-agent").manifest_ref == "sub/good.yaml"
    assert [e[0] for e in ledger.events] == ["registry.registered"]


def test_the_same_relative_ref_is_422_when_field_manifest_dir_does_not_hold_it(
        registry, manifest_dir, tmp_path, monkeypatch):
    client, _, _ = registry
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(tmp_path / "elsewhere"))
    r = client.post("/agents", json={**BODY, "manifest_ref": "sub/good.yaml"})
    assert r.status_code == 422
    assert r.json()["detail"]["manifest_dir"] == str(tmp_path / "elsewhere")
    r = client.post("/agents", json={**BODY, "manifest_ref": str(manifest_dir / "sub" / "good.yaml")})
    assert r.status_code == 201, r.text


@pytest.mark.parametrize("extra", [{}, {"manifest_ref": None}, {"manifest_ref": ""}])
def test_an_unset_ref_registers_as_before(registry, extra):
    client, _, _ = registry
    assert client.post("/agents", json={**BODY, **extra}).status_code == 201


def test_a_duplicate_id_with_an_unresolvable_ref_is_422_not_409(registry):
    """A 409 invites the caller (lifecycle provision) to PATCH the bad ref on."""
    client, _, _ = registry
    assert client.post("/agents", json={**BODY, "manifest_ref": "sub/good.yaml"}).status_code == 201
    r = client.post("/agents", json={**BODY, "manifest_ref": "sub/absent.yaml"})
    assert r.status_code == 422
    assert client.post("/agents", json={**BODY, "manifest_ref": "sub/good.yaml"}).status_code == 409


def test_limit_patch_is_not_checked(registry):
    """README LIMITS, pinned so the claim fails the day it stops being true."""
    client, store, _ = registry
    assert client.post("/agents", json=BODY).status_code == 201
    r = client.patch("/agents/invoicing-agent", json={"manifest_ref": "sub/absent.yaml"})
    assert r.status_code == 200
    assert store.get("invoicing-agent").manifest_ref == "sub/absent.yaml"


def test_cli_add_refuses_an_unresolvable_ref_with_exit_2_and_writes_nothing(
        tmp_path, manifest_dir):
    db = tmp_path / "cli.sqlite3"
    args = ["add", "invoicing-agent", "--name", "Inv", "--owner", "AP Lead", "--path", str(db)]
    result = CliRunner().invoke(cli.app, args + ["--manifest-ref", "sub/invalid.yaml"])
    assert result.exit_code == 2, result.output
    assert "does not resolve (invalid)" in result.output
    store = RegistryStore(db)
    try:
        assert store.list() == []
    finally:
        store.close()
    result = CliRunner().invoke(cli.app, args + ["--manifest-ref", "sub/good.yaml"])
    assert result.exit_code == 0, result.output
    result = CliRunner().invoke(cli.app, ["add", "other-agent", "--name", "O", "--owner", "AP Lead",
                                          "--path", str(db)])
    assert result.exit_code == 0, result.output
