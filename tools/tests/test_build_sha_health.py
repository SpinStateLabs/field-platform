"""FIELD_BUILD_SHA in every service's /health (v1.2 Phase C).

A deploy gate asserts every container REPORTS the SHA string its build was
given (`estate_probe.py health --expect-build-sha`); the value is the build
arg, not measured from the image's code. That gate is only as good as
the key it reads, so each of the thirteen served services is checked here
through its REAL create_app(): the key is present, equals the environment
verbatim, and reads `unknown` when the variable is unset. Delete the key from
any one /health and exactly that parameter fails.

The wiring that bakes the value into the images (Dockerfile ARG -> ENV,
compose build args, fly --build-arg) is exercised by CI's
compose-upgrade-smoke and fly-image-smoke jobs, not here.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

#: module -> (service name /health reports, create_app kwargs)
SERVICES: dict[str, tuple[str, dict]] = {
    "agent_registry.api": ("agent-registry", {}),
    "sealed_ledger.api": ("sealed-ledger", {}),
    "delegation_authority.api": ("delegation-authority", {}),
    "conformance_sentinel.api": ("conformance-sentinel", {}),
    "kill_switch.api": ("kill-switch", {}),
    "spend_governor.api": ("spend-governor", {}),
    "incident_replay.api": ("incident-replay", {}),
    "compliance_crosswalk.api": ("compliance-crosswalk", {}),
    "force_gateway.api": ("force-gateway", {}),
    "federation_broker.api": ("federation-broker", {}),
    "ops_console.api": ("ops-console", {}),
    "lifecycle_manager.api": ("lifecycle-manager", {}),
    "attestation_reporter.api": ("attestation-reporter", {}),
}


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """No test here may write into the repo or inherit an operator's env."""
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(tmp_path / "data" / "manifests"))
    monkeypatch.setenv("FIELD_LIFECYCLE_EVERY", "0")
    for var in ("FIELD_SHARED_SECRET", "FIELD_SENTINEL_JUDGE", "FORCE_HYGIENE_JUDGE",
                "FIELD_DOA_ROSTER", "FIELD_LIFECYCLE_ROSTER", "FIELD_BUILD_SHA"):
        monkeypatch.delenv(var, raising=False)


def _health(module: str) -> dict:
    service, kwargs = SERVICES[module]
    app = importlib.import_module(module).create_app(**kwargs)
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["service"] == service  # the right app, not a neighbour
    return body


def test_every_served_service_is_listed():
    """Thirteen served services (compose/fly): a new one must join this test."""
    assert len(SERVICES) == 13


@pytest.mark.parametrize("module", sorted(SERVICES))
def test_health_reports_the_build_sha_verbatim(module, monkeypatch):
    monkeypatch.setenv("FIELD_BUILD_SHA", "3f9c2b7e6a1d0c4b8e5f7a9d2c6b1e0f4a8d3c7b")
    assert _health(module)["build_sha"] == "3f9c2b7e6a1d0c4b8e5f7a9d2c6b1e0f4a8d3c7b"


@pytest.mark.parametrize("module", sorted(SERVICES))
def test_health_reports_unknown_when_no_sha_was_baked(module):
    assert _health(module)["build_sha"] == "unknown"


@pytest.mark.parametrize("module", sorted(SERVICES))
def test_health_is_read_per_request_not_at_app_creation(module, monkeypatch):
    """The images set the variable before any process starts; a test harness
    that builds the app first must still see the value at request time."""
    _, kwargs = SERVICES[module]
    app = importlib.import_module(module).create_app(**kwargs)
    client = TestClient(app)
    monkeypatch.setenv("FIELD_BUILD_SHA", "after-create")
    assert client.get("/health").json()["build_sha"] == "after-create"
