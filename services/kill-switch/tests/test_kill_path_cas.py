"""Compare-and-set at the registry: the reviewer's probes P1-P4 (don.reviewer, PR 1143 @210c43f) as real tests, plus the
cross-process and direct-PATCH variants. The drill's flip is conditional on the version it READ, its restore is
conditional on the version its flip RETURNED, and a real kill ALWAYS writes (even onto a killed row), so any kill
between the drill's read and its restore moves the version and the drill leaves the agent killed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from field_core.clients import AgentNotRegisteredError, LedgerClient, RegistryClient, RegistryUnreachableError
from kill_switch.api import create_app as create_kill_app
from test_kill_path_hardening import OP, _domain_stack, _stack


def _other_process(s):
    """A second kill-switch app over the same registry and ledger: its own counters, as another worker would have."""
    return TestClient(create_kill_app(registry=RegistryClient(client=s.registry, base_url="http://t"),
                                      ledger=LedgerClient(client=s.ledger, base_url="http://t")))


def test_P1_a_real_kill_between_the_restore_check_and_the_restore_write_is_not_undone(tmp_path):
    """The real kill arrives AFTER the drill's pre-restore checks passed and BEFORE its restore write."""
    s, w = _stack(tmp_path)
    s.register("a1")
    st = {"fired": False, "code": None}
    inner = w._inner

    def on_set(agent_id, status, **kw):
        if status == "active" and not st["fired"]:
            st["fired"] = True
            st["code"] = s.kill.post("/kill/a1", json=OP).status_code         # the REAL kill, mid-restore
        return inner.set_status(agent_id, status, **kw)      # the conditional token travels on, as through the client
    w.on_set = on_set
    r = s.kill.post("/drill/a1", json=OP)
    assert st["fired"] and st["code"] == 200
    assert s.status("a1") == "killed", "the real kill returned 200 but the drill's restore left the agent active"
    assert r.status_code == 409 and r.json()["detail"]["restore_skipped"] is True
    [ev] = s.events("kill.drill.restore_skipped")
    assert "row was written" in ev["payload"]["reason"]


def test_P2_a_real_kill_from_another_kill_switch_process_during_a_drill_is_not_undone(tmp_path):
    s, w = _stack(tmp_path)
    s.register("a1")
    other = _other_process(s)
    st = {"flipped": False, "fired": False, "code": None}
    w.after_set = lambda a, status: st.update(flipped=True) if status == "killed" else None

    def on_get(agent_id):
        if st["flipped"] and not st["fired"]:
            st["fired"] = True
            st["code"] = other.post("/kill/a1", json=OP).status_code
        return None
    w.on_get = on_get
    r = s.kill.post("/drill/a1", json=OP)
    assert st["code"] == 200 and s.status("a1") == "killed", "another instance's real kill was undone"
    assert r.status_code == 409


def test_a_direct_registry_patch_during_the_drill_is_not_undone_either(tmp_path):
    s, w = _stack(tmp_path)
    s.register("a1")
    st = {"flipped": False, "fired": False}
    w.after_set = lambda a, status: st.update(flipped=True) if status == "killed" else None

    def on_get(agent_id):
        if st["flipped"] and not st["fired"]:
            st["fired"] = True
            assert s.registry.patch("/agents/a1", json={"status": "killed"}).status_code == 200
        return None
    w.on_get = on_get
    assert s.kill.post("/drill/a1", json=OP).status_code == 409
    assert s.status("a1") == "killed"


def test_a_real_kill_from_another_process_between_the_drills_read_and_its_flip_refuses_the_drill(tmp_path):
    s, w = _stack(tmp_path)
    s.register("a1")
    other = _other_process(s)
    st = {"fired": False}

    def on_get(agent_id):
        if st["fired"]:
            return None
        st["fired"] = True
        stale = dict(s.inner.get_agent(agent_id))                  # what the drill reads: active, with its updated_at
        assert other.post("/kill/a1", json=OP).status_code == 200  # another process kills right after
        return stale
    w.on_get = on_get
    r = s.kill.post("/drill/a1", json=OP)
    assert r.status_code == 409 and s.status("a1") == "killed"
    assert [e for e in s.events("kill.drill.refused")]


def test_a_real_kill_of_an_already_killed_agent_still_writes_the_row(tmp_path):
    s, w = _stack(tmp_path)
    s.register("a1")
    assert s.kill.post("/kill/a1", json=OP).status_code == 200
    before = s.registry.get("/agents/a1").json()["updated_at"]
    assert s.kill.post("/kill/a1", json=OP).status_code == 200
    assert s.registry.get("/agents/a1").json()["updated_at"] != before, "a re-kill must move the row's version"


@pytest.mark.parametrize("body", [None, {}, {"status": "active"}, {"status": "KILLED"}, "killed", [],
                                  {"status": ["killed"]}])
def test_P3_a_patch_answer_that_does_not_say_killed_is_never_a_kill(tmp_path, body):
    s, w = _stack(tmp_path)
    s.register("a1")
    w.on_set = lambda a, st, **k: body
    assert s.kill.post("/kill/a1", json=OP).status_code != 200


def test_P3_a_patch_answer_with_status_killed_and_extra_keys_is_a_kill(tmp_path):
    s, w = _stack(tmp_path)
    s.register("a1")
    w.on_set = lambda a, st, **k: {"status": "killed", "x": 1}
    assert s.kill.post("/kill/a1", json=OP).status_code == 200


def test_P4_mixed_failures_in_a_domain_and_a_very_long_agent_id(tmp_path):
    s = _domain_stack(tmp_path, {"b1": AgentNotRegisteredError("b1"), "b2": RegistryUnreachableError("timeout"),
                                 "b3": ValueError("boom secret-ish"), "b4": None})
    r = s.kill.post("/kill/domain/finance", json=OP)
    assert r.status_code >= 400 and s.status("b4") == "killed"
    assert "secret-ish" not in r.text and s.events("kill.domain")
    assert s.kill.post("/kill/" + "a" * 300, json=OP).status_code < 500


def test_a_failed_registry_write_on_an_already_killed_agent_still_signals_it(tmp_path):
    s, w = _stack(tmp_path)
    s.register("a1")
    assert s.kill.post("/kill/a1", json=OP).status_code == 200
    n = len(s.events("kill.endpoint_skipped"))

    def boom(agent_id, status, **kw):
        raise RegistryUnreachableError("registry returned 500")
    w.on_set = boom
    assert s.kill.post("/kill/a1", json=OP).status_code == 502
    assert len(s.events("kill.endpoint_skipped")) == n + 1


def test_an_undisturbed_drill_still_restores_through_the_conditional_patch(tmp_path):
    s, w = _stack(tmp_path)
    s.register("a1")
    seen = []
    inner = w._inner

    def on_set(agent_id, status, **kw):
        seen.append((status, sorted(kw)))
        return inner.set_status(agent_id, status, **kw)
    w.on_set = on_set
    r = s.kill.post("/drill/a1", json=OP)
    assert r.status_code == 200 and s.status("a1") == "active"
    assert seen == [("killed", ["if_updated_at"]), ("active", ["if_updated_at"])]


# --- review round 4 (roley.reviewer F1/F2): the restore is ALWAYS conditional ---------------------------------------


def test_F1_a_flip_whose_answer_was_lost_leaves_the_agent_killed_and_writes_no_unconditional_restore(tmp_path):
    """The flip PATCH lands, then the call fails (a timeout after it may have landed): there is no version token, so the
    restore must not be written at all. A real kill from a second kill-switch instance in that window must survive."""
    s, w = _stack(tmp_path)
    s.register("a1")
    other = _other_process(s)
    inner = w._inner
    writes = []

    def on_set(agent_id, status, **kw):
        writes.append((status, sorted(kw)))
        if status == "killed":
            inner.set_status(agent_id, status, **kw)                       # the flip LANDS ...
            assert other.post("/kill/a1", json=OP).status_code == 200      # ... a real kill from another instance ...
            raise RegistryUnreachableError("timed out")                     # ... and the answer is lost
        return inner.set_status(agent_id, status, **kw)
    w.on_set = on_set
    r = s.kill.post("/drill/a1", json=OP)
    assert r.status_code >= 400
    assert s.status("a1") == "killed", "the drill restored the agent over a real kill after a lost flip answer"
    assert [x for x in writes if x[0] == "active"] == [], "an unconditional write of the previous status was attempted"
    [ev] = s.events("kill.drill.restore_skipped")
    assert "no version token" in ev["payload"]["reason"]


def test_F2_a_200_flip_answer_without_updated_at_gives_no_restore_write(tmp_path):
    s, w = _stack(tmp_path)
    s.register("a1")
    inner = w._inner
    writes = []

    def on_set(agent_id, status, **kw):
        writes.append((status, sorted(kw)))
        out = dict(inner.set_status(agent_id, status, **kw))
        out.pop("updated_at", None)                                          # a registry that returns no version
        return out
    w.on_set = on_set
    r = s.kill.post("/drill/a1", json=OP)
    assert r.status_code == 409 and r.json()["detail"]["restore_skipped"] is True
    assert s.status("a1") == "killed"
    assert [x for x in writes if x[0] == "active"] == []
    assert len(s.events("kill.drill.restore_skipped")) == 1


@pytest.mark.parametrize("token", [None, 0, "", ["x"]], ids=["null", "zero", "empty", "list"])
def test_F2_an_unusable_updated_at_in_the_flip_answer_is_treated_as_no_token(tmp_path, token):
    s, w = _stack(tmp_path)
    s.register("a1")
    inner = w._inner
    writes = []

    def on_set(agent_id, status, **kw):
        writes.append(status)
        out = dict(inner.set_status(agent_id, status, **kw))
        out["updated_at"] = token
        return out
    w.on_set = on_set
    r = s.kill.post("/drill/a1", json=OP)
    assert r.status_code == 409 and "active" not in writes and s.status("a1") == "killed"
