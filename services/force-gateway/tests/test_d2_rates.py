"""v1.2 D2a — per-route hygiene rates over `all` and `last_N` windows.

A second injectable upstream (flattery, no tags, no CoT) makes the rates
non-trivial: the built-in mock alone scores 1.0 on every marker."""

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import create_app, mock_upstream, resolve_telemetry_window
from force_gateway.telemetry import METHOD_LABEL

RATE_KEYS = ("confidence_tag_rate", "flattery_free_rate", "cot_structure_rate")


def flattery_upstream(body, headers):
    return 200, {
        "id": "msg_flattery", "type": "message", "role": "assistant",
        "model": "flattery-mock (test upstream)",
        "content": [{"type": "text",
                     "text": "Great question! I'd be happy to help. It is $1,800."}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


class SwitchUpstream:
    """good = the built-in mock (every marker); bad = flattery_upstream."""

    def __init__(self):
        self.mode = "good"

    def __call__(self, body, headers):
        return (mock_upstream if self.mode == "good" else flattery_upstream)(body, headers)


def make(window=50, **kw):
    up = SwitchUpstream()
    client = TestClient(create_app(upstream=up, sample_every=0,
                                   latency_budget_ms=10_000.0,
                                   telemetry_window=window, **kw))
    return client, up


def send(client, up, mode, n=1, preset="analysis"):
    up.mode = mode
    for _ in range(n):
        r = client.post("/v1/messages", json={"model": "m", "messages": []},
                        headers={"x-force-preset": preset})
        assert r.status_code == 200, r.text


def rates_of(client, route="_all", window="all"):
    return client.get("/telemetry").json()["rates"][route][window]


def test_zero_requests_rates_are_none_not_zero():
    client, _ = make()
    rates = client.get("/telemetry").json()["rates"]
    assert set(rates) == {"_all"}
    for window in ("all", "last_N"):
        r = rates["_all"][window]
        assert r["requests"] == 0
        for key in RATE_KEYS:
            assert r[key] is None, (window, key)


def test_mixed_responses_rate_half():
    client, up = make()
    send(client, up, "good")
    send(client, up, "bad")
    for route in ("_all", "analysis"):
        for window in ("all", "last_N"):
            r = rates_of(client, route, window)
            assert r["requests"] == 2
            assert [r[k] for k in RATE_KEYS] == [0.5, 0.5, 0.5], (route, window)


def test_a_route_with_only_bad_responses_rates_zero_not_none():
    client, up = make()
    send(client, up, "good", preset="analysis")
    send(client, up, "bad", preset="audit")
    t = client.get("/telemetry").json()
    assert set(t["rates"]) == {"analysis", "audit", "_all"}
    assert [t["rates"]["analysis"]["all"][k] for k in RATE_KEYS] == [1.0, 1.0, 1.0]
    assert [t["rates"]["audit"]["all"][k] for k in RATE_KEYS] == [0.0, 0.0, 0.0]
    assert [t["rates"]["_all"]["all"][k] for k in RATE_KEYS] == [0.5, 0.5, 0.5]


def test_last_n_moves_all_does_not_forget():
    client, up = make(window=2)
    send(client, up, "good", 2)
    assert rates_of(client, window="last_N")["confidence_tag_rate"] == 1.0
    send(client, up, "bad", 2)
    last = rates_of(client, window="last_N")
    assert (last["requests"], last["window_size"]) == (2, 2)
    assert [last[k] for k in RATE_KEYS] == [0.0, 0.0, 0.0]
    every = rates_of(client, window="all")
    assert (every["requests"], every["window_size"]) == (4, None)
    assert [every[k] for k in RATE_KEYS] == [0.5, 0.5, 0.5]
    send(client, up, "good", 1)
    assert rates_of(client, window="last_N")["flattery_free_rate"] == 0.5
    assert rates_of(client, "analysis", "last_N")["flattery_free_rate"] == 0.5
    assert rates_of(client, window="all")["flattery_free_rate"] == 0.6


def test_every_count_is_kept_and_the_method_label_rides_every_rate():
    client, up = make()
    send(client, up, "good")
    send(client, up, "bad")
    t = client.get("/telemetry").json()
    assert t["total_requests"] == 2
    assert t["by_preset"] == {"analysis": 2}
    assert t["responses_with_confidence_tags"] == 1
    assert t["responses_clean_of_flattery"] == 1
    assert t["responses_with_cot_structure"] == 1
    assert t["total_corrections"] == 2  # the mock: "Correction:" + "the premise is flawed"
    assert (t["total_input_tokens"], t["total_output_tokens"]) == (250, 123)
    assert t["method"] == METHOD_LABEL
    for route in t["rates"].values():
        for window in route.values():
            assert window["method"] == METHOD_LABEL


def test_retention_prunes_rows_never_totals(monkeypatch):
    monkeypatch.setenv("FORCE_TELEMETRY_RETAIN", "3")
    client, up = make(window=2)
    send(client, up, "good", 3)
    send(client, up, "bad", 2)
    t = client.get("/telemetry").json()
    assert t["total_requests"] == 5
    assert len(t["recent"]) == 3  # only the retained rows
    assert t["rates"]["_all"]["all"]["confidence_tag_rate"] == 0.6
    assert t["rates"]["_all"]["last_N"]["confidence_tag_rate"] == 0.0


def test_retention_below_the_window_keeps_the_window_exact(monkeypatch):
    monkeypatch.setenv("FORCE_TELEMETRY_RETAIN", "1")
    client, up = make(window=3)
    send(client, up, "bad", 2)
    send(client, up, "good", 3)
    last = rates_of(client, window="last_N")
    assert last["requests"] == 3 and last["confidence_tag_rate"] == 1.0


def test_a_quiet_routes_last_n_survives_pruning_by_a_busy_route(monkeypatch):
    """Pruning is global by age, but each route also keeps its own newest N
    rows: a low-traffic route's `last_N` never empties while its `all` window
    still shows data."""
    monkeypatch.setenv("FORCE_TELEMETRY_RETAIN", "1")
    client, up = make(window=2)
    send(client, up, "bad", 1, preset="audit")
    send(client, up, "good", 2, preset="audit")
    send(client, up, "good", 5, preset="analysis")
    t = client.get("/telemetry").json()
    audit = t["rates"]["audit"]
    assert audit["all"]["requests"] == 3
    assert (audit["last_N"]["requests"], audit["last_N"]["window_size"]) == (2, 2)
    assert [audit["last_N"][k] for k in RATE_KEYS] == [1.0, 1.0, 1.0]  # the bad one aged out
    assert t["rates"]["analysis"]["last_N"]["requests"] == 2
    assert t["rates"]["_all"]["last_N"]["requests"] == 2
    assert len(t["recent"]) == 4  # rows held: the global newest 2 + audit's newest 2


@pytest.mark.parametrize("posts", [8, 9])
def test_retain_above_the_window_keeps_exactly_the_newest_retain_rows(monkeypatch, posts):
    """The per-route window floor never prunes INSIDE the global retain
    horizon: with RETAIN > N the newest RETAIN rows are all kept."""
    monkeypatch.setenv("FORCE_TELEMETRY_RETAIN", "4")
    client, up = make(window=2)
    send(client, up, "good", posts)
    t = client.get("/telemetry").json()
    assert len(t["recent"]) == 4
    assert t["total_requests"] == posts


def test_telemetry_window_env(monkeypatch):
    assert resolve_telemetry_window() == 50
    monkeypatch.setenv("FORCE_TELEMETRY_WINDOW", "7")
    assert resolve_telemetry_window() == 7
    monkeypatch.setenv("FORCE_TELEMETRY_WINDOW", "junk")
    assert resolve_telemetry_window() == 50
    monkeypatch.setenv("FORCE_TELEMETRY_WINDOW", "0")
    assert resolve_telemetry_window() == 1
    monkeypatch.setenv("FORCE_TELEMETRY_WINDOW", "4")
    client = TestClient(create_app(upstream=mock_upstream))
    assert client.get("/telemetry").json()["rates"]["_all"]["last_N"]["window_size"] == 4


@pytest.mark.parametrize("limit,expected", [(20, 3), (2, 2), (0, 0)])
def test_recent_limit_reads_the_newest_rows(limit, expected):
    client, up = make()
    send(client, up, "good", 3)
    recent = client.get("/telemetry", params={"limit": limit}).json()["recent"]
    assert len(recent) == expected
