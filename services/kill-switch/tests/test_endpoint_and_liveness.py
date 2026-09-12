"""v1.2 kill-switch: resolvable agent-side endpoints + server-side liveness.

Every security property this service now claims has a test here that fails
if someone weakens the guard — the Phase A lesson (a security-critical guard
shipped with no test; a one-token regression would have gone green).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core.clients import LedgerClient, RegistryClient, RegistryUnreachableError
from field_core.templates_api import template_data
from kill_switch.api import (
    ENDPOINT_TIMEOUT_S,
    ORIGIN_HEADER,
    ORIGIN_VALUE,
    create_app as create_kill_app,
)
from kill_switch.store import HeartbeatStore
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

OP = {"operator": "CISO on-call", "reason": "anomalous behavior"}
ALLOWED = "halt.allowed.host"


# --- helpers -----------------------------------------------------------------


class FakeEndpoint:
    """Records every outbound halt signal. Zero calls is the assertion that
    matters for the SSRF cases."""

    def __init__(self, handler=None):
        self.calls: list[dict] = []
        self._handler = handler or (lambda method, url: 200)

    def request(self, method, url, headers=None, timeout=None):
        self.calls.append(
            {"method": method, "url": url, "headers": dict(headers or {}),
             "timeout": timeout}
        )
        outcome = self._handler(method, url)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(status_code=outcome)

    @property
    def hosts(self) -> list[str]:
        return [c["url"] for c in self.calls]


class FrozenClock:
    def __init__(self, start: datetime | None = None):
        self.now = start or datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


def write_manifest(tmp_path, agent_id: str, endpoint: str, method: str = "HTTP POST"):
    data = template_data("default")
    data["agent"]["name"] = agent_id
    data["enforcement"]["kill_switch"]["endpoint"] = endpoint
    data["enforcement"]["kill_switch"]["method"] = method
    path = tmp_path / f"{agent_id}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


class Stack:
    def __init__(self, tmp_path, *, endpoint=None, clock=None, heartbeats=None,
                 registry_wrapper=None):
        self.tmp_path = tmp_path
        self.registry = TestClient(
            create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3"))
        )
        self.ledger = TestClient(
            create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl"))
        )
        registry_client = RegistryClient(client=self.registry, base_url="http://t")
        if registry_wrapper is not None:
            registry_client = registry_wrapper(registry_client)
        self.endpoint = endpoint if endpoint is not None else FakeEndpoint()
        self.heartbeats = heartbeats
        self.kill = TestClient(
            create_kill_app(
                registry=registry_client,
                ledger=LedgerClient(client=self.ledger, base_url="http://t"),
                heartbeats=heartbeats,
                clock=clock,
                endpoint_client=self.endpoint,
            )
        )

    def register(self, agent_id, domain="finance", manifest_ref=None):
        body = {"agent_id": agent_id, "name": agent_id, "owner": "Owner",
                "domain": domain}
        if manifest_ref:
            body["manifest_ref"] = str(manifest_ref)
        r = self.registry.post("/agents", json=body)
        assert r.status_code == 201, r.text

    def with_endpoint(self, agent_id, endpoint, method="HTTP POST", domain="finance"):
        path = write_manifest(self.tmp_path, agent_id, endpoint, method)
        self.register(agent_id, domain=domain, manifest_ref=path)
        return path

    def events(self, event_type=None):
        params = {"event_type": event_type} if event_type else {}
        return self.ledger.get("/events", params=params).json()

    def event_types(self):
        return [e["event_type"] for e in self.events()]


@pytest.fixture()
def stack(tmp_path):
    return Stack(tmp_path)


# --- (a) SSRF allowlist ------------------------------------------------------


METADATA = "http://169.254.169.254/latest/meta-data"


def test_adversarial_metadata_endpoint_skipped_with_allowlist_unset(stack):
    """The link-local metadata service: allowlist unset ⇒ no call, ever."""
    stack.with_endpoint("invoicing-agent", METADATA)
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    assert r.status_code == 200
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "skipped" and result["reason"] == "allowlist_unset"
    assert stack.endpoint.calls == []
    assert "kill.endpoint_skipped" in stack.event_types()
    assert stack.registry.get("/agents/invoicing-agent").json()["status"] == "killed"


def test_adversarial_metadata_endpoint_skipped_when_allowlist_names_another_host(
    stack, monkeypatch
):
    """Allowlist SET but naming a different host ⇒ still zero calls."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", "example.com")
    stack.with_endpoint("invoicing-agent", METADATA)
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    assert r.status_code == 200
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "skipped"
    assert result["reason"] == "host_not_allowlisted"
    assert result["endpoint_host"] == "169.254.169.254"
    assert stack.endpoint.calls == []
    assert "kill.endpoint_skipped" in stack.event_types()


def test_adversarial_userinfo_host_trick_is_not_the_allowlisted_host(
    stack, monkeypatch
):
    """`http://halt.allowed.host@169.254.169.254/…` — the allowlisted name is
    only USERINFO; the real host is the metadata IP. A substring test over the
    URL passes this; exact `urlsplit(...).hostname` matching refuses it."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    endpoint = f"http://{ALLOWED}@169.254.169.254/latest/meta-data"
    assert ALLOWED in endpoint  # the substring test that MUST NOT be used
    stack.with_endpoint("invoicing-agent", endpoint)
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    assert r.status_code == 200
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "skipped"
    assert result["reason"] == "host_not_allowlisted"
    assert result["endpoint_host"] == "169.254.169.254"
    assert stack.endpoint.calls == []


def test_userinfo_before_an_allowlisted_host_is_parsed_as_userinfo(
    stack, monkeypatch
):
    """The mirror case from the plan text, `http://169.254.169.254@allowed/`:
    the IP is userinfo, the host really is the allowlisted one — so the call
    is made, and the recorded host is the HOST, never the credential half."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack.with_endpoint(
        "invoicing-agent", f"http://169.254.169.254@{ALLOWED}/halt"
    )
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "called"
    assert result["endpoint_host"] == ALLOWED
    assert len(stack.endpoint.calls) == 1


def test_adversarial_suffix_host_is_not_allowlisted(stack, monkeypatch):
    """`halt.allowed.host.evil.com` contains the allowlisted name as a
    prefix-substring. Exact match refuses it."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    endpoint = f"http://{ALLOWED}.evil.com/halt"
    assert ALLOWED in endpoint  # the substring test that MUST NOT be used
    stack.with_endpoint("invoicing-agent", endpoint)
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "skipped"
    assert result["reason"] == "host_not_allowlisted"
    assert result["endpoint_host"] == f"{ALLOWED}.evil.com"
    assert stack.endpoint.calls == []


def test_non_http_endpoint_skipped(stack, monkeypatch):
    """FIELD 1.1.0 allows `method: file` sentinel kill switches."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack.with_endpoint(
        "invoicing-agent", "file:///c:/state/KILL", method="file"
    )
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "skipped" and result["reason"] == "non_http_endpoint"
    assert stack.endpoint.calls == []


def test_unsupported_method_skipped(stack, monkeypatch):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack.with_endpoint(
        "invoicing-agent", f"http://{ALLOWED}/halt", method="carrier pigeon"
    )
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "skipped" and result["reason"] == "unsupported_method"
    assert stack.endpoint.calls == []


def test_no_manifest_ref_is_an_explicit_skip(stack):
    stack.register("invoicing-agent")
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "skipped" and result["reason"] == "no_manifest_ref"


def test_unresolvable_manifest_is_an_explicit_skip(stack, tmp_path):
    stack.register(
        "invoicing-agent", manifest_ref=str(tmp_path / "nope.yaml")
    )
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "skipped"
    assert result["reason"] == "manifest_unresolved"


# --- (a) self-call guard -----------------------------------------------------


def test_self_endpoint_path_shape_is_skipped(stack, monkeypatch):
    """The shape every shipped manifest uses today
    (`…/killswitch/kill/<agent>`): skipped even with the host allowlisted,
    or a kill would recurse into this service."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack.with_endpoint(
        "invoicing-agent", f"http://{ALLOWED}/killswitch/kill/invoicing-agent"
    )
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "skipped" and result["reason"] == "self_endpoint"
    assert stack.endpoint.calls == []


def test_self_domain_endpoint_path_shape_is_skipped(stack, monkeypatch):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack.with_endpoint(
        "invoicing-agent", f"http://{ALLOWED}/killswitch/kill/domain/finance"
    )
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "skipped" and result["reason"] == "self_endpoint"
    assert stack.endpoint.calls == []


def test_adversarial_incoming_origin_header_short_circuits(stack, monkeypatch):
    """A third-party hook path shape that the heuristic would NOT catch, but
    the header does: our own outbound signal coming back in must not recurse."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack.with_endpoint("invoicing-agent", f"http://{ALLOWED}/hooks/halt")
    r = stack.kill.post(
        "/kill/invoicing-agent", json=OP,
        headers={ORIGIN_HEADER: ORIGIN_VALUE},
    )
    assert r.status_code == 200
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "skipped" and result["reason"] == "self_endpoint"
    assert stack.endpoint.calls == []
    # and the kill itself still happened
    assert stack.registry.get("/agents/invoicing-agent").json()["status"] == "killed"


def test_outbound_signal_carries_the_origin_header(stack, monkeypatch):
    """The other half of the guard: what we send is marked, so the receiver
    can short-circuit."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack.with_endpoint("invoicing-agent", f"http://{ALLOWED}/hooks/halt")
    stack.kill.post("/kill/invoicing-agent", json=OP)
    assert stack.endpoint.calls[0]["headers"][ORIGIN_HEADER] == ORIGIN_VALUE
    assert stack.endpoint.calls[0]["timeout"] == 2.0


# --- (a) called / failed -----------------------------------------------------


def test_allowlisted_endpoint_200_is_called_and_ledgered(stack, monkeypatch):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", f"other.host, {ALLOWED}")
    stack.with_endpoint("invoicing-agent", f"http://{ALLOWED}/hooks/halt")
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    assert r.status_code == 200
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "called"
    assert result["method"] == "POST" and result["http_status"] == 200
    assert result["endpoint_host"] == ALLOWED
    assert result["elapsed_ms"] is not None
    called = stack.events("kill.endpoint_called")
    assert len(called) == 1
    assert called[0]["payload"]["endpoint_host"] == ALLOWED


def test_allowlisted_endpoint_that_raises_still_kills(stack, monkeypatch):
    """The halt is the registry flip. A dead agent endpoint degrades the
    SIGNAL, never the kill."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack.endpoint._handler = lambda m, u: ConnectionError("refused")
    stack.with_endpoint("invoicing-agent", f"http://{ALLOWED}/hooks/halt")
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    assert r.status_code == 200
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "failed" and result["reason"] == "transport_error"
    assert "ConnectionError" in result["error"]
    assert stack.registry.get("/agents/invoicing-agent").json()["status"] == "killed"
    assert len(stack.events("kill.endpoint_failed")) == 1


def test_allowlisted_endpoint_http_error_is_failed(stack, monkeypatch):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack.endpoint._handler = lambda m, u: 503
    stack.with_endpoint("invoicing-agent", f"http://{ALLOWED}/hooks/halt")
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    assert r.status_code == 200
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "failed" and result["http_status"] == 503
    assert len(stack.events("kill.endpoint_failed")) == 1


def test_adversarial_endpoint_credentials_never_leak(stack, monkeypatch):
    """A manifest endpoint can carry credentials. Neither the report nor the
    ledger may ever echo the URL — host only."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    endpoint = f"https://svc:sup3rsecret@{ALLOWED}/hooks/halt?key=t0ps3cret"
    stack.endpoint._handler = lambda m, u: ConnectionError(f"cannot connect to {u}")
    stack.with_endpoint("invoicing-agent", endpoint)
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    body = r.text
    ledger_text = str(stack.events())
    for secret in ("sup3rsecret", "t0ps3cret", "/hooks/halt"):
        assert secret not in body, f"{secret} leaked into the kill report"
        assert secret not in ledger_text, f"{secret} leaked into the ledger"
    assert r.json()["endpoint_result"]["endpoint_host"] == ALLOWED


def test_idempotent_rekill_still_sends_the_signal(stack, monkeypatch):
    """The flip is idempotent; the SIGNAL is the point of repeating it."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack.with_endpoint("invoicing-agent", f"http://{ALLOWED}/hooks/halt")
    stack.kill.post("/kill/invoicing-agent", json=OP)
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    assert r.json()["previous_status"] == "killed"
    assert r.json()["endpoint_result"]["outcome"] == "called"
    assert len(stack.endpoint.calls) == 2


# --- (b) domain kill ---------------------------------------------------------


def test_domain_kill_with_one_failing_endpoint_stays_200_with_mixed_results(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    endpoint = FakeEndpoint(
        handler=lambda m, u: ConnectionError("refused") if "beta" in u else 200
    )
    stack = Stack(tmp_path, endpoint=endpoint)
    stack.with_endpoint("alpha-agent", f"http://{ALLOWED}/hooks/alpha")
    stack.with_endpoint("beta-agent", f"http://{ALLOWED}/hooks/beta")
    r = stack.kill.post("/kill/domain/finance", json=OP)
    assert r.status_code == 200
    report = r.json()
    assert sorted(report["killed"]) == ["alpha-agent", "beta-agent"]
    outcomes = {
        row["agent_id"]: row["endpoint_result"]["outcome"] for row in report["results"]
    }
    assert outcomes == {"alpha-agent": "called", "beta-agent": "failed"}
    assert len(stack.events("kill.endpoint_called")) == 1
    assert len(stack.events("kill.endpoint_failed")) == 1
    for agent_id in ("alpha-agent", "beta-agent"):
        assert stack.registry.get(f"/agents/{agent_id}").json()["status"] == "killed"


def test_domain_kill_records_a_per_agent_registry_fault_without_500(tmp_path):
    """A registry fault on ONE agent is recorded, not raised mid-loop."""

    class OneAgentDown:
        def __init__(self, inner):
            self._inner = inner

        def get_agent(self, agent_id):
            if agent_id == "beta-agent":
                raise RegistryUnreachableError("simulated per-agent fault")
            return self._inner.get_agent(agent_id)

        def set_status(self, agent_id, status):
            return self._inner.set_status(agent_id, status)

        def list_agents(self, **kw):
            return self._inner.list_agents(**kw)

    stack = Stack(tmp_path, registry_wrapper=OneAgentDown)
    stack.register("alpha-agent")
    stack.register("beta-agent")
    r = stack.kill.post("/kill/domain/finance", json=OP)
    assert r.status_code == 200
    report = r.json()
    assert report["killed"] == ["alpha-agent"]
    rows = {row["agent_id"]: row for row in report["results"]}
    assert rows["beta-agent"]["outcome"] == "error"
    assert "502" in rows["beta-agent"]["error"]
    assert stack.registry.get("/agents/alpha-agent").json()["status"] == "killed"


# --- (c) drill ---------------------------------------------------------------


def test_adversarial_drill_failure_leaves_the_agent_active(tmp_path):
    """Today's bug: an HTTPException between the flip and the restore leaves
    the agent killed. try/finally must make that impossible."""

    class NeverConfirms:
        """set_status really flips; get_agent never admits it — the drill's
        propagation check raises 500 mid-flight."""

        def __init__(self, inner):
            self._inner = inner

        def get_agent(self, agent_id):
            record = self._inner.get_agent(agent_id)
            if record.get("status") == "killed":
                return {**record, "status": "active"}
            return record

        def set_status(self, agent_id, status):
            return self._inner.set_status(agent_id, status)

        def list_agents(self, **kw):
            return self._inner.list_agents(**kw)

    stack = Stack(tmp_path, registry_wrapper=NeverConfirms)
    stack.register("invoicing-agent")
    r = stack.kill.post("/drill/invoicing-agent", json=OP)
    assert r.status_code == 500
    assert "drill failed" in r.json()["detail"]
    # the whole point: the agent is NOT left killed
    assert stack.registry.get("/agents/invoicing-agent").json()["status"] == "active"


def test_drill_restore_failure_is_reported_not_masked(tmp_path):
    class RestoreFails:
        def __init__(self, inner):
            self._inner = inner

        def get_agent(self, agent_id):
            return self._inner.get_agent(agent_id)

        def set_status(self, agent_id, status):
            if status != "killed":
                raise RegistryUnreachableError("registry died before the restore")
            return self._inner.set_status(agent_id, status)

        def list_agents(self, **kw):
            return self._inner.list_agents(**kw)

    stack = Stack(tmp_path, registry_wrapper=RestoreFails)
    stack.register("invoicing-agent")
    r = stack.kill.post("/drill/invoicing-agent", json=OP)
    assert r.status_code == 200
    report = r.json()
    assert report["restored"] is False
    assert report["restored_status"] == "<restore failed>"
    assert len(stack.events("kill.drill.restore_failed")) == 1


def test_drill_reports_endpoint_result_and_confirmation(stack, monkeypatch):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack.with_endpoint("invoicing-agent", f"http://{ALLOWED}/hooks/halt")
    r = stack.kill.post("/drill/invoicing-agent", json=OP)
    assert r.status_code == 200
    report = r.json()
    assert report["endpoint_result"]["outcome"] == "called"
    assert report["endpoint_confirmed_ms"] is not None
    assert report["restored"] is True and report["restored_status"] == "active"
    assert len(stack.endpoint.calls) == 1


def test_drill_without_allowlist_sends_nothing(stack):
    stack.with_endpoint("invoicing-agent", "http://halt.example.com/hooks/halt")
    report = stack.kill.post("/drill/invoicing-agent", json=OP).json()
    assert report["endpoint_result"]["reason"] == "allowlist_unset"
    assert report["endpoint_confirmed_ms"] is None
    assert stack.endpoint.calls == []


# --- (d) heartbeat check-ins + liveness --------------------------------------


def test_checkin_records_last_seen_and_get_never_writes(tmp_path):
    clock = FrozenClock()
    store = HeartbeatStore(tmp_path / "hb.sqlite3")
    stack = Stack(tmp_path, clock=clock, heartbeats=store)
    stack.register("invoicing-agent")

    stack.kill.get("/heartbeat/invoicing-agent")
    assert store.get("invoicing-agent") is None, "GET must not write"

    r = stack.kill.post("/heartbeat/invoicing-agent")
    assert r.status_code == 200
    body = r.json()
    assert body["killed"] is False and body["status"] == "active"
    assert body["last_seen"] == clock.now.isoformat()
    assert store.get("invoicing-agent")["checkins"] == 1
    store.close()


def test_killed_agent_checkin_still_answers_killed(tmp_path):
    store = HeartbeatStore(tmp_path / "hb.sqlite3")
    stack = Stack(tmp_path, heartbeats=store)
    stack.register("invoicing-agent")
    stack.kill.post("/kill/invoicing-agent", json=OP)
    body = stack.kill.post("/heartbeat/invoicing-agent").json()
    assert body["killed"] is True and body["status"] == "killed"
    assert store.get("invoicing-agent")["status"] == "killed"
    store.close()


def test_unregistered_checkin_surfaces_a_shadow_agent(tmp_path):
    store = HeartbeatStore(tmp_path / "hb.sqlite3")
    stack = Stack(tmp_path, heartbeats=store)
    body = stack.kill.post("/heartbeat/ghost-agent").json()
    assert body["killed"] is True and body["status"] == "unregistered"
    assert store.get("ghost-agent")["status"] == "unregistered"
    store.close()


def test_liveness_stale_window_on_a_frozen_clock(tmp_path):
    clock = FrozenClock()
    store = HeartbeatStore(tmp_path / "hb.sqlite3")
    stack = Stack(tmp_path, clock=clock, heartbeats=store)
    stack.register("checks-in-agent")
    stack.register("never-checks-in-agent")

    stack.kill.post("/heartbeat/checks-in-agent")
    report = stack.kill.get("/liveness", params={"stale_after": 60}).json()
    assert [row["agent_id"] for row in report["live"]] == ["checks-in-agent"]
    assert [row["agent_id"] for row in report["stale"]] == ["never-checks-in-agent"]
    # last_seen null counts as stale
    assert report["stale"][0]["last_seen"] is None

    clock.advance(120)  # no real sleeps: the clock is the seam
    report = stack.kill.get("/liveness", params={"stale_after": 60}).json()
    assert report["live"] == []
    assert sorted(row["agent_id"] for row in report["stale"]) == [
        "checks-in-agent", "never-checks-in-agent",
    ]
    assert report["stale"][0]["age_seconds"] == 120.0
    store.close()


def test_liveness_only_lists_registry_active_agents(tmp_path):
    store = HeartbeatStore(tmp_path / "hb.sqlite3")
    stack = Stack(tmp_path, heartbeats=store)
    stack.register("invoicing-agent")
    stack.register("forecast-agent")
    stack.kill.post("/kill/forecast-agent", json=OP)
    report = stack.kill.get("/liveness", params={"stale_after": 60}).json()
    listed = [row["agent_id"] for row in report["stale"] + report["live"]]
    assert listed == ["invoicing-agent"]
    store.close()


def test_second_create_app_on_the_same_store_resumes_last_seen(tmp_path):
    clock = FrozenClock()
    path = tmp_path / "hb.sqlite3"
    first_store = HeartbeatStore(path)
    first = Stack(tmp_path, clock=clock, heartbeats=first_store)
    first.register("invoicing-agent")
    first.kill.post("/heartbeat/invoicing-agent")
    seen = first.kill.get("/liveness", params={"stale_after": 60}).json()
    assert seen["live"][0]["last_seen"] == clock.now.isoformat()
    first_store.close()

    # restart: a NEW app object over the SAME file
    second_store = HeartbeatStore(path)
    second = Stack(tmp_path, clock=clock, heartbeats=second_store)
    resumed = second.kill.get("/liveness", params={"stale_after": 60}).json()
    assert resumed["live"][0]["last_seen"] == seen["live"][0]["last_seen"]
    second_store.close()


def test_liveness_rejects_a_nonpositive_window(stack):
    assert stack.kill.get("/liveness", params={"stale_after": 0}).status_code == 422


# --- (d) the outbound client itself ------------------------------------------


def test_adversarial_the_halt_signal_client_does_not_follow_redirects():
    """The allowlist checks the URL in the manifest. If redirects were
    followed, an allowlisted host answering `302 Location:
    http://169.254.169.254/` would walk the signal to the exact place the
    allowlist exists to keep it away from — and the host check would never
    see the second URL.

    This drives REAL httpx redirect machinery (MockTransport, no network)
    with the flag read off the production client, so flipping that flag to
    True fails here instead of shipping."""
    import httpx

    from kill_switch.api import new_endpoint_client

    produced = new_endpoint_client()
    try:
        assert produced.follow_redirects is False
        assert produced.timeout.connect == ENDPOINT_TIMEOUT_S
    finally:
        produced.close()

    reached: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        reached.append(str(request.url))
        if request.url.host == ALLOWED:
            return httpx.Response(302, headers={"Location": METADATA})
        return httpx.Response(200, text="metadata leaked")

    probe = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=produced.follow_redirects,
        timeout=ENDPOINT_TIMEOUT_S,
    )
    try:
        response = probe.request("POST", f"http://{ALLOWED}/halt")
    finally:
        probe.close()
    assert response.status_code == 302
    assert reached == [f"http://{ALLOWED}/halt"]      # the IP was never reached
    assert not any("169.254.169.254" in url for url in reached)


def test_the_app_builds_its_endpoint_client_from_that_factory(
    tmp_path, monkeypatch
):
    """The test above is worth nothing if `create_app` builds its own client
    some other way. Drive a real kill with no injected client and assert the
    factory is what produced it."""
    from kill_switch import api as kill_api

    built: list[object] = []
    sentinel = FakeEndpoint()

    def fake_factory():
        built.append(sentinel)
        return sentinel

    monkeypatch.setattr(kill_api, "new_endpoint_client", fake_factory)
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack = Stack(tmp_path, endpoint=None)
    stack.kill.app.state.endpoint_client = None      # force the lazy path
    stack.with_endpoint("invoicing-agent", f"http://{ALLOWED}/halt")
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    assert r.status_code == 200
    assert r.json()["endpoint_result"]["outcome"] == "called"
    assert built == [sentinel]
    assert len(sentinel.calls) == 1


# --- (e) where the heartbeat database lands ----------------------------------


def test_the_heartbeat_store_lands_under_field_data_dir(tmp_path, monkeypatch):
    """The estates mount one data directory and back it up. A store that
    lands anywhere else is a database nobody knows exists — and on the demo
    stack it is also a file that does not survive a container restart."""
    from kill_switch.api import _default_store_path

    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    path = _default_store_path()
    assert path == tmp_path / "data" / "killswitch" / "heartbeats.sqlite3"


def test_the_heartbeat_store_defaults_under_var_when_unset(monkeypatch):
    from kill_switch.api import _default_store_path

    monkeypatch.delenv("FIELD_DATA_DIR", raising=False)
    assert _default_store_path().parts[-3:] == ("var", "killswitch",
                                                "heartbeats.sqlite3")


def test_a_kill_switch_that_is_never_checked_in_to_creates_no_file(
    tmp_path, monkeypatch
):
    """Lazy on purpose: importing or serving the app must not litter a
    database into whatever directory the process happens to start in."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("FIELD_DATA_DIR", str(data_dir))
    stack = Stack(tmp_path)
    stack.register("invoicing-agent")
    stack.kill.post("/kill/invoicing-agent", json=OP)
    assert not data_dir.exists()


def test_the_lazily_built_store_is_the_one_at_that_path(tmp_path, monkeypatch):
    """The path function is only half the guarantee — the app has to use it.
    A heartbeat with no injected store must create the file there and read
    back through it."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("FIELD_DATA_DIR", str(data_dir))
    stack = Stack(tmp_path, heartbeats=None)
    stack.register("invoicing-agent")
    assert stack.kill.post("/heartbeat/invoicing-agent").status_code == 200
    expected = data_dir / "killswitch" / "heartbeats.sqlite3"
    assert expected.exists()
    live = stack.kill.get("/liveness", params={"stale_after": 3600}).json()["live"]
    assert [row["agent_id"] for row in live] == ["invoicing-agent"]
    stack.kill.app.state.heartbeats.close()
