"""S4-12: the governor CLI and provisioning.load_rate_limits put an agent id (or an escalation id) into a URL with a
plain f-string, so an id holding '/', '?', '#' or '..' reached a different governor route (the operator pair is attached
by path); lifecycle provision calls load_rate_limits with manifest.agent.name, a free-text field. Every id is now ONE
encoded path segment (quote(safe=''), and '%2E' / '%2E%2E' for the dot segments quote leaves alone). Ordinary ids give
byte-identical URLs. httpx is faked at module level; nothing leaves the process."""

from __future__ import annotations

import urllib.parse
from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

from field_core.templates_api import template_data
from spend_governor import cli
from spend_governor.provisioning import load_rate_limits, rate_limits_from_manifest

BASE = "http://gov.invalid"
runner = CliRunner()
HOSTILE = ["a/b", "a?x", "a#f", "../caps/x", "a b", "..", ".", "a%2Fb", "x/../../escalations", "é"]


def seg(value):
    out = urllib.parse.quote(value, safe="")
    return {".": "%2E", "..": "%2E%2E"}.get(out, out)


@pytest.fixture()
def calls(monkeypatch):
    monkeypatch.setenv("FIELD_GOVERNOR_URL", BASE)
    seen: list[tuple[str, str]] = []

    def fake(method):
        def call(url, **kw):
            seen.append((method, url))
            return SimpleNamespace(status_code=201 if (method, url.rsplit("/", 1)[-1]) == ("POST", "usage") else 200,
                                   text="{}", json=lambda: {})
        return call

    for m in ("get", "put", "post"):
        monkeypatch.setattr(cli.httpx, m, fake(m.upper()))
    return seen


def one_segment_after(url, prefix):
    assert url.startswith(prefix + "/"), url
    rest = url[len(prefix) + 1:]
    assert "/" not in rest.split("?", 1)[0] and "#" not in rest and "?" not in rest.split("?", 1)[0]
    return rest


@pytest.mark.parametrize("agent", HOSTILE)
@pytest.mark.parametrize("argv,method,prefix", [
    (["set-cap", "{a}", "--limit-cents", "100"], "PUT", "/caps"),
    (["rate-limits", "{a}"], "GET", "/rate-limits"),
    (["status", "{a}"], "GET", "/status"),
    (["usage", "{a}"], "GET", "/usage"),
    (["set-policy", "{a}", "--allowed-model", "m"], "PUT", "/policies"),
])
def test_every_agent_id_verb_puts_the_id_in_one_encoded_segment(calls, agent, argv, method, prefix):
    res = runner.invoke(cli.app, [a.replace("{a}", agent) if a == "{a}" else a for a in argv])
    assert res.exit_code == 0, res.output
    assert calls == [(method, f"{BASE}{prefix}/{seg(agent)}")]
    parts = urllib.parse.urlsplit(calls[0][1])
    assert parts.query == "" and parts.fragment == "" and parts.path.count("/") == 2


@pytest.mark.parametrize("escalation", HOSTILE)
def test_the_escalation_id_is_one_encoded_segment(calls, escalation):
    res = runner.invoke(cli.app, ["resolve", escalation, "--by", "Don"])
    assert res.exit_code == 0, res.output
    assert calls == [("POST", f"{BASE}/escalations/{seg(escalation)}/resolve")]
    assert urllib.parse.urlsplit(calls[0][1]).path.count("/") == 3


def test_a_usage_report_posts_to_the_fixed_route_with_the_id_in_the_body(calls):
    res = runner.invoke(cli.app, ["usage", "a/b", "--model", "m", "--in", "1", "--out", "1"])
    assert res.exit_code == 0, res.output
    assert calls == [("POST", f"{BASE}/usage")]


def test_ordinary_ids_give_byte_identical_urls(calls):
    runner.invoke(cli.app, ["set-cap", "invoicing-agent", "--limit-cents", "100"])
    runner.invoke(cli.app, ["status", "invoicing-agent"])
    runner.invoke(cli.app, ["resolve", "0b1c2d3e-4f50-6789-abcd-ef0123456789", "--by", "Don"])
    assert calls == [("PUT", f"{BASE}/caps/invoicing-agent"), ("GET", f"{BASE}/status/invoicing-agent"),
                     ("POST", f"{BASE}/escalations/0b1c2d3e-4f50-6789-abcd-ef0123456789/resolve")]


# ---- provisioning.load_rate_limits -------------------------------------------------------------------------------------


def limits_for(agent_id):
    data = template_data("default")
    data["enforcement"]["spend_cap"] = {"currency": "USD", "limit": 500, "period": "daily", "on_breach": "halt"}
    data["enforcement"]["rate_limits"] = [{"action": "send invoice", "max": 5, "period": "hourly"}]
    from field_core.manifest import FieldManifest
    return rate_limits_from_manifest(FieldManifest.from_dict(data), agent_id)


class Rec:
    def __init__(self):
        self.calls = []

    def get(self, path):
        self.calls.append(("GET", path))
        return SimpleNamespace(status_code=200, json=lambda: {"rate_limits": [{"x": 1}]}, text="{}")

    def put(self, path, json=None):
        self.calls.append(("PUT", path))
        return SimpleNamespace(status_code=200, json=lambda: {"rate_limits": []}, text="{}")


@pytest.mark.parametrize("agent", HOSTILE)
def test_load_rate_limits_puts_the_id_in_one_encoded_segment(agent):
    rec = Rec()
    out = load_rate_limits(rec.get, rec.put, limits_for(agent))
    assert out.outcome == "loaded"
    assert rec.calls == [("PUT", f"/rate-limits/{seg(agent)}")]


@pytest.mark.parametrize("agent", HOSTILE)
def test_load_rate_limits_clearing_path_gets_and_puts_the_same_encoded_segment(agent):
    from spend_governor.provisioning import RateLimitSet
    rec = Rec()                                                   # nothing declared, the governor holds a set: GET then PUT
    out = load_rate_limits(rec.get, rec.put, RateLimitSet(agent_id=agent, rate_limits=[]))
    assert out.outcome == "loaded"
    assert rec.calls == [("GET", f"/rate-limits/{seg(agent)}"), ("PUT", f"/rate-limits/{seg(agent)}")]


def test_load_rate_limits_ordinary_id_path_is_unchanged():
    rec = Rec()
    load_rate_limits(rec.get, rec.put, limits_for("invoicing-agent"))
    assert rec.calls == [("PUT", "/rate-limits/invoicing-agent")]


@pytest.mark.parametrize("agent", ["a/b", "../caps/x"])
def test_set_cap_from_manifest_loads_the_rate_limits_through_the_same_encoded_path(calls, tmp_path, agent):
    data = template_data("default")
    data["agent"]["name"] = "x"
    data["enforcement"]["spend_cap"] = {"currency": "USD", "limit": 500, "period": "daily", "on_breach": "halt"}
    data["enforcement"]["rate_limits"] = [{"action": "send invoice", "max": 5, "period": "hourly"}]
    m = tmp_path / "m.yaml"
    m.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    res = runner.invoke(cli.app, ["set-cap", agent, "--from-manifest", str(m)])
    assert res.exit_code == 0, res.output
    assert calls == [("PUT", f"{BASE}/caps/{seg(agent)}"), ("PUT", f"{BASE}/rate-limits/{seg(agent)}")]
