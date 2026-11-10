"""`GET /presets` and `GET /presets/{name}` over HTTP (scout P-23, tests only, no source change).

Before: tests called `preset_block` directly and never the routes, so the route wiring, the 404 text and the perimeter
secret on these two read routes had no test. A finding is reported in the PR, not fixed here: the 404 detail repeats the
caller's name (as a repr), by design of `preset_block`'s KeyError text."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import create_app, mock_upstream
from force_gateway.presets import PRESETS, preset_block

SECRET = "synthetic-shared-secret-0000"


@pytest.fixture()
def client():
    return TestClient(create_app(upstream=mock_upstream))


def test_get_presets_is_the_preset_table(client):
    r = client.get("/presets")
    assert r.status_code == 200 and r.json() == PRESETS


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_get_a_preset_returns_its_block(client, name):
    r = client.get(f"/presets/{name}")
    assert r.status_code == 200
    assert r.json() == {"preset": name, "system_block": preset_block(name)}


def test_the_analysis_block_carries_the_protocol_header(client):
    block = client.get("/presets/analysis").json()["system_block"]
    assert block.startswith("# FORCE Runtime Protocol") and "preset: analysis" in block


def test_an_unknown_preset_is_404_naming_the_valid_ones(client):
    r = client.get("/presets/vibes")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "unknown FORCE preset" in detail
    assert all(p in detail for p in PRESETS)


@pytest.mark.parametrize("name", ["../etc/passwd", "..%2Fetc%2Fpasswd", "%2e%2e", "analysis%00", "a b", "ANALYSIS", "x" * 5000])
def test_an_odd_name_is_a_404_or_405_never_a_500_and_never_a_filesystem_path(client, name):
    r = client.get(f"/presets/{name}")
    assert r.status_code in (404, 405, 307, 308), (name[:20], r.status_code)
    assert r.status_code < 500
    text = r.text
    assert "/usr/" not in text and "\\Users\\" not in text and ".py" not in text and "Traceback" not in text


def test_a_trailing_slash_is_redirected_to_the_same_preset(client):
    r = client.get("/presets/analysis/")             # Starlette's redirect_slashes, followed by the test client
    assert r.status_code == 200 and r.json()["preset"] == "analysis"


def test_the_404_repeats_the_callers_name_as_a_repr_today(client):
    """REPORTED, not fixed: `preset_block` puts `{preset!r}` in its KeyError text and the route returns it as the detail.
    It is a JSON string, not HTML, and the name is the caller's own path segment; pinned so a change is a decision (the
    repo's 422 handlers elsewhere repeat no caller text)."""
    detail = client.get("/presets/MADE-UP-MARKER").json()["detail"]
    assert "'MADE-UP-MARKER'" in detail


def test_with_a_shared_secret_both_routes_need_x_field_auth(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    c = TestClient(create_app(upstream=mock_upstream))
    for path in ("/presets", "/presets/analysis"):
        assert c.get(path).status_code == 401, path
        assert c.get(path, headers={"x-field-auth": "wrong"}).status_code == 401, path
        assert c.get(path, headers={"x-field-auth": SECRET}).status_code == 200, path
    assert c.get("/health").status_code == 200                      # the one open path stays open


def test_without_a_shared_secret_the_routes_are_open(monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    c = TestClient(create_app(upstream=mock_upstream))
    assert c.get("/presets").status_code == 200 and c.get("/presets/audit").status_code == 200
