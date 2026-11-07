"""S9-3 card (B-S9-11): the `kill.domain` ledger event says what happened to EVERY agent of the domain.

It carried `killed` and `skipped_retired` only. An agent that was already killed, or one whose registry write failed, was in the HTTP
report (with the error text) but not in the ledger, so a post-mortem from the ledger alone could not tell which agents a domain halt
failed to stop. The payload now also has `already_killed` (ids), `errored` (`{agent_id, status_code}` only: the error text can quote
registry text or a URL, so it never goes to the ledger) and `attempted` (int), additive to the existing keys."""

import pytest

from field_core.clients import RegistryUnreachableError

from test_endpoint_and_liveness import OP, Stack


class FailFor:
    """A registry wrapper whose status writes fail for the named agents (and, optionally, every agent)."""

    def __init__(self, agents=(), everyone=False):
        self.agents, self.everyone = set(agents), everyone

    def __call__(self, inner):
        agents, everyone = self.agents, self.everyone

        class W:
            def get_agent(self, agent_id):
                return inner.get_agent(agent_id)

            def list_agents(self, **kw):
                return inner.list_agents(**kw)

            def set_status(self, agent_id, status):
                if everyone or agent_id in agents:
                    raise RegistryUnreachableError("registry returned 401: operator credentials required http://10.9.8.7/secret")
                return inner.set_status(agent_id, status)
        return W()


def payload(s):
    [ev] = s.events("kill.domain")
    return ev["payload"]


def test_a_mixed_domain_names_each_agent_in_the_right_list(tmp_path):
    s = Stack(tmp_path, registry_wrapper=FailFor(agents=("bad",)))
    for a in ("good", "was-killed", "bad"):
        s.register(a)
    assert s.registry.patch("/agents/was-killed", json={"status": "killed"}).status_code == 200
    r = s.kill.post("/kill/domain/finance", json=OP)
    assert r.status_code == 200
    p = payload(s)
    assert p["killed"] == ["good"]
    assert p["already_killed"] == ["was-killed"]
    assert p["errored"] == [{"agent_id": "bad", "status_code": 502}]
    assert p["attempted"] == 3
    assert p["skipped_retired"] == []


def test_the_all_error_502_case_ledgers_every_agent_as_errored_and_none_killed(tmp_path):
    s = Stack(tmp_path, registry_wrapper=FailFor(everyone=True))
    for a in ("a1", "a2"):
        s.register(a)
    assert s.kill.post("/kill/domain/finance", json=OP).status_code == 502
    p = payload(s)
    assert p["killed"] == [] and p["already_killed"] == []
    assert sorted(e["agent_id"] for e in p["errored"]) == ["a1", "a2"]
    assert all(e["status_code"] == 502 for e in p["errored"]) and p["attempted"] == 2


def test_skipped_retired_is_unchanged_and_not_counted_as_attempted(tmp_path):
    s = Stack(tmp_path)
    for a in ("live", "gone"):
        s.register(a)
    assert s.registry.patch("/agents/gone", json={"status": "retired"}).status_code == 200
    s.kill.post("/kill/domain/finance", json=OP)
    p = payload(s)
    assert p["skipped_retired"] == ["gone"] and p["killed"] == ["live"] and p["errored"] == [] and p["attempted"] == 1


def test_no_error_text_or_url_reaches_the_ledger_payload(tmp_path):
    s = Stack(tmp_path, registry_wrapper=FailFor(agents=("bad",)))
    for a in ("good", "bad"):
        s.register(a)
    s.kill.post("/kill/domain/finance", json=OP)
    text = str(payload(s))
    for leaked in ("credentials", "10.9.8.7", "secret", "registry returned", "unreachable"):
        assert leaked not in text
    assert set(payload(s)) >= {"operator", "reason", "domain", "killed", "skipped_retired", "elapsed_ms",
                               "already_killed", "errored", "attempted"}


def test_a_clean_domain_has_empty_new_lists_and_the_http_report_is_unchanged(tmp_path):
    s = Stack(tmp_path)
    for a in ("a1", "a2"):
        s.register(a)
    r = s.kill.post("/kill/domain/finance", json=OP)
    body = r.json()
    assert body["killed"] == ["a1", "a2"] and body["already_killed"] == []
    p = payload(s)
    assert p["killed"] == ["a1", "a2"] and p["already_killed"] == [] and p["errored"] == [] and p["attempted"] == 2
