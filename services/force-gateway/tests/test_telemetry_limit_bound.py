"""GET /telemetry?limit= is bounded (S3-21): 0..500, an out-of-range value is a 422 (no echo), the default is 20."""

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import create_app, mock_upstream


@pytest.fixture
def client():
    c = TestClient(create_app(upstream=mock_upstream, sample_every=0, latency_budget_ms=10_000.0))
    for _ in range(25):
        assert c.post("/v1/messages", json={"model": "m", "messages": []},
                      headers={"x-force-preset": "analysis"}).status_code == 200
    return c


@pytest.mark.parametrize("limit", [501, 1_000_000, -1])
def test_an_out_of_range_limit_is_422_and_not_repeated(client, limit):
    r = client.get("/telemetry", params={"limit": limit})
    assert r.status_code == 422
    assert str(limit) not in r.text.replace('"loc"', "")  # the value is not echoed back


def test_the_bounds_and_the_default(client):
    assert client.get("/telemetry", params={"limit": 500}).status_code == 200
    assert client.get("/telemetry", params={"limit": 0}).json()["recent"] == []
    assert len(client.get("/telemetry").json()["recent"]) == 20
    assert len(client.get("/telemetry", params={"limit": 500}).json()["recent"]) == 25
