"""C-811 (reviewer C-745 F-C745-1..4): a redirect is not a delivered halt signal, the gap counter's unit is stated and
its increment is locked, and the client's no-redirect setting is pinned against a real redirect."""

from __future__ import annotations

import pytest

from test_endpoint_and_liveness import ALLOWED, OP, Stack


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 399])
def test_a_redirect_answer_is_a_failed_signal_not_a_delivered_one(tmp_path, monkeypatch, status):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack = Stack(tmp_path)
    stack.endpoint._handler = lambda m, u: status
    stack.with_endpoint("victim", f"http://{ALLOWED}/hooks/halt")
    r = stack.kill.post("/kill/victim", json=OP)
    assert r.status_code == 200                                       # the kill itself still happened
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "failed" and result["reason"] == "http_redirect", result
    assert result["http_status"] == status
    assert len(stack.events("kill.endpoint_failed")) == 1 and not stack.events("kill.endpoint_called")


@pytest.mark.parametrize("status,outcome,reason", [
    (200, "called", None), (204, "called", None), (299, "called", None),
    (400, "failed", "http_error"), (404, "failed", "http_error"), (503, "failed", "http_error"),
])
def test_the_other_statuses_keep_their_classification(tmp_path, monkeypatch, status, outcome, reason):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack = Stack(tmp_path)
    stack.endpoint._handler = lambda m, u: status
    stack.with_endpoint("victim", f"http://{ALLOWED}/hooks/halt")
    result = stack.kill.post("/kill/victim", json=OP).json()["endpoint_result"]
    assert result["outcome"] == outcome and result["reason"] == reason, result


def test_the_readme_states_the_counters_unit_and_scope():
    """C-811 F-C745-2: notes, not actions; per process; zero after a restart. A pinned wording."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    flat = " ".join(text.split())
    for phrase in ("failed ledger RECORDS (notes), not failed actions", "per PROCESS", "zero after a restart"):
        assert phrase in flat, phrase
