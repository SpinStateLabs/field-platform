"""S6-1: a manifest kill_switch.endpoint that urlsplit rejects must not raise out of `_signal_endpoint`.

field-core only requires `endpoint` to be a non-empty string, so 'http://[::1/kill' validates; urlsplit then raises
ValueError('Invalid IPv6 URL'). The registry flip had already happened, so /kill/{id} was a 500 with no kill.agent
note, and a domain kill aborted mid-loop (later agents not halted, no kill.domain). The URL is never echoed."""

import pytest

from test_endpoint_and_liveness import OP, Stack

BAD = ["http://[::1/kill", "http://[::1]x/"]


@pytest.mark.parametrize("endpoint", BAD)
def test_a_malformed_endpoint_is_skipped_the_agent_is_killed_and_noted(tmp_path, endpoint):
    s = Stack(tmp_path)
    s.with_endpoint("bad-agent", endpoint)
    r = s.kill.post("/kill/bad-agent", json=OP)
    assert r.status_code == 200
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "skipped" and result["reason"] == "malformed_endpoint"
    assert result.get("endpoint_host") is None
    assert "[::1" not in r.text
    assert s.registry.get("/agents/bad-agent").json()["status"] == "killed"
    assert "kill.agent" in s.event_types()
    assert s.endpoint.calls == []


@pytest.mark.parametrize("endpoint", BAD)
def test_a_domain_kill_halts_every_agent_when_one_endpoint_is_malformed(tmp_path, endpoint):
    s = Stack(tmp_path)
    s.with_endpoint("a-bad-agent", endpoint)
    s.with_endpoint("b-normal-agent", "http://halt.invalid/kill")
    r = s.kill.post("/kill/domain/finance", json=OP)
    assert r.status_code == 200
    for agent in ("a-bad-agent", "b-normal-agent"):
        assert s.registry.get(f"/agents/{agent}").json()["status"] == "killed"
    assert "kill.domain" in s.event_types()
    assert "[::1" not in r.text


def test_a_drill_with_a_malformed_endpoint_still_restores(tmp_path):
    s = Stack(tmp_path)
    s.with_endpoint("bad-agent", BAD[0])
    r = s.kill.post("/drill/bad-agent", json=OP)
    assert r.status_code == 200
    assert s.registry.get("/agents/bad-agent").json()["status"] == "active"
