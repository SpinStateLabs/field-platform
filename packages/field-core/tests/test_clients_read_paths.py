"""S7-7: LedgerClient.events and RegistryClient.get_agent / require_active_agent / list_agents, read paths pinned.

An injected fake client (no network). The 'unusable 200 body' cases of the registry reads belong to
test_clients_unusable_200.py (PR 676) and are left out here."""

import pytest

from field_core.clients import (AgentNotActiveError, AgentNotRegisteredError, LedgerClient, LedgerUnreachableError,
                                RegistryClient, RegistryUnreachableError)


class Resp:
    def __init__(self, status, body=None, bad_json=False):
        self.status_code = status
        self._body, self._bad = body, bad_json
        self.text = "UPSTREAM-BODY"

    def json(self):
        if self._bad:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._body


class Fake:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.calls = resp, exc, []

    def get(self, url, params=None, **kw):
        self.calls.append((url, params))
        if self.exc:
            raise self.exc
        return self.resp


def ledger(fake):
    return LedgerClient(client=fake, base_url="http://l")


def registry(fake):
    return RegistryClient(client=fake, base_url="http://r")


# -- LedgerClient.events -----------------------------------------------------------------------------------

def test_events_sends_event_type_only_when_given_and_returns_the_list():
    for given, params in (("kill.agent", {"event_type": "kill.agent"}), (None, {}), ("", {})):
        fake = Fake(Resp(200, [{"n": 1}]))
        assert ledger(fake).events(given) == [{"n": 1}]
        assert fake.calls == [("http://l/events", params)]


def test_events_no_argument_sends_no_params():
    fake = Fake(Resp(200, []))
    assert ledger(fake).events() == [] and fake.calls[0][1] == {}


@pytest.mark.parametrize("status", [201, 204, 301, 400, 403, 500, 503])
def test_events_a_non_200_is_unreachable_with_the_fixed_text_and_no_body(status):
    with pytest.raises(LedgerUnreachableError) as exc:
        ledger(Fake(Resp(status, []))).events()
    assert str(exc.value) == f"ledger events read returned {status}"
    assert "UPSTREAM-BODY" not in str(exc.value)
    # documented: unlike append, an events read does not carry the status on the exception
    assert exc.value.status_code is None


def test_events_a_200_that_is_not_json_is_unreachable_not_json():
    with pytest.raises(LedgerUnreachableError, match="ledger events read: not JSON"):
        ledger(Fake(Resp(200, bad_json=True))).events()


@pytest.mark.parametrize("body, kind", [({"events": []}, "dict"), ("x", "str"), (None, "NoneType"), (5, "int")])
def test_events_a_json_value_that_is_not_a_list_is_named(body, kind):
    with pytest.raises(LedgerUnreachableError) as exc:
        ledger(Fake(Resp(200, body))).events()
    assert str(exc.value) == f"ledger events read returned {kind}, not a list"


def test_events_a_transport_exception_is_unreachable_with_no_status_code():
    with pytest.raises(LedgerUnreachableError, match="connection refused") as exc:
        ledger(Fake(exc=ConnectionError("connection refused"))).events()
    assert exc.value.status_code is None and isinstance(exc.value.__cause__, ConnectionError)


# -- RegistryClient.get_agent ------------------------------------------------------------------------------

def test_get_agent_returns_the_record_on_200():
    fake = Fake(Resp(200, {"agent_id": "a1", "status": "active"}))
    assert registry(fake).get_agent("a1") == {"agent_id": "a1", "status": "active"}
    assert fake.calls[0][0] == "http://r/agents/a1"


def test_get_agent_404_is_not_registered_naming_the_agent():
    with pytest.raises(AgentNotRegisteredError) as exc:
        registry(Fake(Resp(404, {}))).get_agent("ghost")
    assert str(exc.value) == "ghost"


@pytest.mark.parametrize("status", [400, 401, 403, 500, 502, 503])
def test_get_agent_any_other_non_200_is_unreachable_with_the_fixed_text(status):
    with pytest.raises(RegistryUnreachableError) as exc:
        registry(Fake(Resp(status, {}))).get_agent("a1")
    assert str(exc.value) == f"registry returned {status}" and "UPSTREAM-BODY" not in str(exc.value)


def test_get_agent_a_transport_exception_is_unreachable():
    with pytest.raises(RegistryUnreachableError, match="boom"):
        registry(Fake(exc=TimeoutError("boom"))).get_agent("a1")


# -- RegistryClient.require_active_agent -------------------------------------------------------------------

def test_require_active_returns_the_record_when_active():
    rec = {"agent_id": "a1", "status": "active"}
    assert registry(Fake(Resp(200, rec))).require_active_agent("a1") == rec


@pytest.mark.parametrize("status", ["revoked", "killed", "suspended", "ACTIVE", ""])
def test_require_active_raises_with_the_status_for_anything_but_exactly_active(status):
    with pytest.raises(AgentNotActiveError) as exc:
        registry(Fake(Resp(200, {"agent_id": "a1", "status": status}))).require_active_agent("a1")
    assert exc.value.status == status
    assert str(exc.value) == f"agent 'a1' has status '{status}'"


def test_require_active_a_record_with_no_status_key_reports_unknown():
    with pytest.raises(AgentNotActiveError) as exc:
        registry(Fake(Resp(200, {"agent_id": "a1"}))).require_active_agent("a1")
    assert exc.value.status == "<unknown>" and str(exc.value) == "agent 'a1' has status '<unknown>'"


def test_require_active_a_record_with_status_none_reports_none_not_unknown():
    # documented: a present key holding None is not '<unknown>' (dict.get's default applies only to an absent key)
    with pytest.raises(AgentNotActiveError) as exc:
        registry(Fake(Resp(200, {"agent_id": "a1", "status": None}))).require_active_agent("a1")
    assert exc.value.status is None and str(exc.value) == "agent 'a1' has status 'None'"


def test_require_active_propagates_not_registered_and_unreachable():
    with pytest.raises(AgentNotRegisteredError):
        registry(Fake(Resp(404, {}))).require_active_agent("a1")
    with pytest.raises(RegistryUnreachableError):
        registry(Fake(Resp(500, {}))).require_active_agent("a1")


# -- RegistryClient.list_agents ----------------------------------------------------------------------------

@pytest.mark.parametrize("kw, params", [
    ({}, {}),
    ({"domain": "finance"}, {"domain": "finance"}),
    ({"status": "active"}, {"status": "active"}),
    ({"domain": "finance", "status": "killed"}, {"domain": "finance", "status": "killed"}),
    ({"domain": "", "status": ""}, {}),
    ({"domain": None, "status": None}, {}),
])
def test_list_agents_sends_domain_and_status_only_when_truthy(kw, params):
    fake = Fake(Resp(200, [{"agent_id": "a1"}]))
    assert registry(fake).list_agents(**kw) == [{"agent_id": "a1"}]
    assert fake.calls == [("http://r/agents", params)]


def test_list_agents_non_200_and_transport_failures_are_unreachable():
    with pytest.raises(RegistryUnreachableError) as exc:
        registry(Fake(Resp(503, []))).list_agents()
    assert str(exc.value) == "registry returned 503"
    with pytest.raises(RegistryUnreachableError, match="down"):
        registry(Fake(exc=OSError("down"))).list_agents()
