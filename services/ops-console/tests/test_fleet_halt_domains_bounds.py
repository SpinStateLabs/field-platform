"""POST /api/fleet/halt bounds its ``domains`` list (scout S3-19).

Each domain is one sequential kill-switch POST, so the list and each string are
capped (matching ``BulkAction.agent_ids``), and text that cannot be encoded as a
URL path segment is refused as a 422 rather than a 500 from ``_seg``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ops_console.api import ServiceClient, create_app


class Recorder:
    """Stands in for the kill-switch: records every POST, answers a clean halt."""

    def __init__(self):
        self.calls: list[str] = []

    def get(self, *a, **k):
        raise ConnectionError("down")

    def post(self, path, **kw):
        self.calls.append(path)
        import httpx

        return httpx.Response(200, json={"results": []})


class Dead:
    def get(self, *a, **k):
        raise ConnectionError("down")

    def post(self, *a, **k):
        raise ConnectionError("down")


def _console(tmp_path):
    kill = Recorder()
    dead = ServiceClient(client=Dead(), base_url="http://dead")
    app = create_app(
        registry=dead, ledger=dead, delegation=dead, governor=dead,
        killswitch=ServiceClient(client=kill, base_url="http://t"), sentinel=dead,
        lifecycle=dead, attest=dead, crosswalk=dead, federation=dead,
        replay=dead, gateway=dead, manifest_dir=tmp_path,
        stream_interval=0.01, stream_keepalive=0.0)
    return TestClient(app), kill


def _body(domains):
    return {"operator": "CISO", "reason": "incident", "confirm": "HALT", "domains": domains}


def test_a_normal_three_domain_halt_still_works(tmp_path):
    console, kill = _console(tmp_path)
    r = console.post("/api/fleet/halt", json=_body(["finance", "support", "ops"]))
    assert r.status_code == 200
    assert r.json()["domains"] == ["finance", "support", "ops"]
    assert kill.calls == [f"/kill/domain/{d}" for d in ("finance", "support", "ops")]


def test_exactly_the_cap_is_accepted(tmp_path):
    console, kill = _console(tmp_path)
    domains = [f"d{i}" for i in range(100)]
    assert console.post("/api/fleet/halt", json=_body(domains)).status_code == 200
    assert len(kill.calls) == 100


def test_101_domains_is_422_and_nothing_is_halted(tmp_path):
    console, kill = _console(tmp_path)
    r = console.post("/api/fleet/halt", json=_body([f"d{i}" for i in range(101)]))
    assert r.status_code == 422
    assert kill.calls == []


def test_a_128_char_domain_is_accepted_and_129_is_422(tmp_path):
    console, kill = _console(tmp_path)
    assert console.post("/api/fleet/halt", json=_body(["a" * 128])).status_code == 200
    assert len(kill.calls) == 1
    r = console.post("/api/fleet/halt", json=_body(["a" * 129]))
    assert r.status_code == 422
    assert len(kill.calls) == 1


@pytest.mark.parametrize("bad", ["\ud800", "ok\udfffok", "\udc00"])
def test_a_lone_surrogate_domain_is_422_not_500(tmp_path, bad):
    console, kill = _console(tmp_path)
    # a raw JSON body, so the lone surrogate travels as the \uXXXX escape json.loads accepts
    import json

    raw = json.dumps(_body([bad]), ensure_ascii=True)
    r = console.post("/api/fleet/halt", content=raw, headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert kill.calls == []
    assert bad not in r.text  # the no-echo handler does not repeat the input


def test_the_existing_empty_and_slash_refusals_still_hold(tmp_path):
    console, kill = _console(tmp_path)
    for bad in ([""], ["a/b"]):
        assert console.post("/api/fleet/halt", json=_body(bad)).status_code == 422
    assert kill.calls == []
