"""Phase G: `lifecycle decommission` needs an authenticated operator."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from field_core import operator_auth as oa
from lifecycle_manager import cli

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


@pytest.fixture()
def no_side_effects(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("decommission reached the engine without authenticating")

    monkeypatch.setattr(cli, "_provision_clients", boom)


ARGS = ["decommission", "a1", "--by", "Don", "--reason", "r"]


def run(env=None):
    return CliRunner().invoke(cli.app, ARGS, env=env or {})


def test_no_operator_credentials_is_refused_before_any_side_effect(enforce, no_side_effects):
    r = run()
    assert r.exit_code == 2 and "401" in r.output


def test_wrong_key_and_scope_are_refused(enforce, no_side_effects):
    r = run({oa.ENV_OPERATOR: "don", oa.ENV_OPERATOR_KEY: "fok_wrong"})
    assert r.exit_code == 2 and "403" in r.output
    r2 = run({oa.ENV_OPERATOR: "svc", oa.ENV_OPERATOR_KEY: KEY_SVC})  # kill-only
    assert r2.exit_code == 2 and "403" in r2.output
    assert "fok_wrong" not in r.output + r2.output and KEY_SVC not in r2.output


def test_good_key_reaches_the_engine(enforce, no_side_effects, monkeypatch):
    monkeypatch.setenv(oa.ENV_OPERATOR, "don")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY_DON)
    with pytest.raises(AssertionError, match="without authenticating"):
        CliRunner().invoke(cli.app, ARGS, catch_exceptions=False)


# --- review finding: /sweep kills through the service identity, unguarded ----------


def test_sweep_route_is_guarded(enforce):
    from fastapi.testclient import TestClient

    from lifecycle_manager.api import create_app

    class Dummy:
        def __getattr__(self, name):
            raise AssertionError("sweep ran past the guard")

    c = TestClient(create_app(registry=Dummy(), delegation=Dummy(), ledger=Dummy(),
                              killswitch=Dummy()))
    assert c.post("/sweep", json={}).status_code == 401
    assert c.post("/sweep", json={}, headers={oa.HEADER_OPERATOR: "don",
                                              oa.HEADER_KEY: "fok_wrong"}).status_code == 403
    assert c.post("/sweep", json={}, headers={oa.HEADER_OPERATOR: "svc",
                                              oa.HEADER_KEY: KEY_SVC}).status_code == 403
    # an authorised operator gets PAST the guard (then 503: no roster configured)
    r = c.post("/sweep", json={}, headers={oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: KEY_DON})
    assert r.status_code not in (401, 403)
