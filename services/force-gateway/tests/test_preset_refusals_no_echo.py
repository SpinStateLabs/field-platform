"""S4-24: an unknown preset is refused with a fixed text that lists only the known names: never the caller's header or path text.
Status codes stay 422 (POST /v1/messages) and 404 (GET /presets/{name}). Every value is a made-up marker."""
import pytest
from fastapi.testclient import TestClient

from force_gateway.api import create_app
from force_gateway.presets import PRESETS
from force_gateway.store import GatewayStore

MARK = "MADE-UP-MARKER-0123456789"
KNOWN = ", ".join(PRESETS)


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=GatewayStore(tmp_path / "g.sqlite3")))


@pytest.mark.parametrize("value", [MARK, MARK * 100, "vibes"])
def test_the_unknown_preset_header_is_not_repeated(client, value):
    r = client.post("/v1/messages", json={"model": "m", "messages": []}, headers={"x-force-preset": value})
    assert r.status_code == 422
    assert value not in r.text, r.text
    assert r.json() == {"detail": f"unknown preset; use {KNOWN}"}


@pytest.mark.parametrize("name", [MARK, MARK * 20, "vibes", "%27quoted%27"])
def test_the_unknown_preset_path_is_not_repeated(client, name):
    r = client.get(f"/presets/{name}")
    assert r.status_code == 404
    assert name not in r.text, r.text
    assert r.json() == {"detail": f"unknown FORCE preset; choose from {KNOWN}"}


def test_a_known_preset_still_works(client):
    name = next(iter(PRESETS))
    r = client.get(f"/presets/{name}")
    assert r.status_code == 200 and r.json()["preset"] == name and r.json()["system_block"]
    assert client.get("/presets").json() == PRESETS


def test_the_refusals_list_only_known_names(client):
    r = client.get(f"/presets/{MARK}")
    assert all(n in r.json()["detail"] for n in PRESETS)
