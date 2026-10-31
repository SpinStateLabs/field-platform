"""Key rotation slice R2 (design v0.2 section 5.1 "independent witness", S8, S11): the
ledger's C-6 observer also records, from each service's open /health, generation
DECREASES and break-glass counter changes, and from the ledger's OWN parse of the
operators file the per-row 16-hex prefixes of each slot hash (the break-glass row
never), plus its own retired-hash counter. Test key values are throwaway constants."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from sealed_ledger import operator_observer as obs
from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore

KEY_DON = "tkv-r2obs-don-0123456789abcdef"
KEY_KS = "tkv-r2obs-ks-0123456789abcdef"
KEY_KS_NEXT = "tkv-r2obs-ksn-0123456789abcdef"
KEY_BG = "tkv-r2obs-bg-0123456789abcdef"


def H(k):
    return oa.key_sha256(k)


def _health(gen=None, auth=None, attempt=None, mode="log-only", sha="0123456789abcdef", rows=4):
    h = {"ok": True, "operator_mode": mode, "operator_registry_sha256_prefix": sha,
         "operator_registry_rows": rows}
    if gen is not None:
        h["operator_registry_generation"] = gen
    if auth is not None:
        h["breakglass_auth_count"], h["breakglass_attempt_count"] = auth, attempt
    return h


class Recorder:
    def __init__(self):
        self.events = []
        self.fail = set()

    def __call__(self, event_type, payload):
        if event_type in self.fail:
            raise RuntimeError("ledger busy (simulated)")
        self.events.append((event_type, payload))

    def of(self, t, service=None):
        return [p for et, p in self.events if et == t and (service is None or p["service"] == service)]


def _observer(rec, answers, self_state=None, slots=None, counters=None):
    state = {"h": self_state or _health(), "slots": slots, "counters": counters}
    o = obs.OperatorObserver(
        append=rec, self_health=lambda: state["h"],
        targets=[("kill-switch", "http://killswitch")],
        fetch=lambda url: answers.get(url.removesuffix("/health")),
        self_slots=(lambda: state["slots"]) if slots is not None else None,
        self_counters=(lambda: state["counters"]) if counters is not None else None)
    return o, state


# --- generation decreases ----------------------------------------------------------------


def test_a_generation_decrease_is_recorded_and_an_increase_is_not():
    rec = Recorder()
    answers = {"http://killswitch": _health(41)}
    o, _ = _observer(rec, answers)
    o.observe_once()
    assert rec.of(obs.GENERATION_EVENT) == []                 # the first observation is no decrease
    answers["http://killswitch"] = _health(43, sha="1111111111111111")
    o.observe_once()
    assert rec.of(obs.GENERATION_EVENT) == []
    answers["http://killswitch"] = _health(42, sha="2222222222222222")
    o.observe_once()
    assert rec.of(obs.GENERATION_EVENT) == [{
        "service": "kill-switch", "generation": 42, "previous_generation": 43,
        "registry_sha256_prefix": "2222222222222222", "observed_from": "health"}]
    o.observe_once()                                          # unchanged: nothing more
    assert len(rec.of(obs.GENERATION_EVENT)) == 1


def test_a_rollback_to_format1_generation_0_is_a_decrease():
    rec = Recorder()
    answers = {"http://killswitch": _health(5)}
    o, _ = _observer(rec, answers)
    o.observe_once()
    answers["http://killswitch"] = _health(0)
    o.observe_once()
    assert [p["generation"] for p in rec.of(obs.GENERATION_EVENT)] == [0]


def test_an_unreadable_generation_between_two_answers_does_not_hide_a_decrease():
    rec = Recorder()
    answers = {"http://killswitch": _health(9)}
    o, _ = _observer(rec, answers)
    o.observe_once()
    answers["http://killswitch"] = _health(None)              # invalid file: generation null
    o.observe_once()
    answers["http://killswitch"] = _health(3)
    o.observe_once()
    assert [(p["generation"], p["previous_generation"]) for p in rec.of(obs.GENERATION_EVENT)] == [(3, 9)]


def test_a_failed_decrease_append_is_retried_next_tick():
    rec = Recorder()
    answers = {"http://killswitch": _health(9)}
    o, _ = _observer(rec, answers)
    o.observe_once()
    answers["http://killswitch"] = _health(8)
    rec.fail.add(obs.GENERATION_EVENT)
    o.observe_once()
    rec.fail.clear()
    o.observe_once()
    assert [p["generation"] for p in rec.of(obs.GENERATION_EVENT)] == [8]


def test_the_ledgers_own_generation_is_watched_too():
    rec = Recorder()
    o, state = _observer(rec, {}, self_state=_health(7))
    o.observe_once()
    state["h"] = _health(6)
    o.observe_once()
    assert [p["service"] for p in rec.of(obs.GENERATION_EVENT)] == ["sealed-ledger"]


def test_generation_values_are_validated():
    for bad in (-1, True, "41", 41.0, 2 ** 60):
        assert obs.observed_rotation({"operator_registry_generation": bad})["generation"] is None


# --- break-glass counters ----------------------------------------------------------------


def test_breakglass_counters_zero_at_startup_are_not_an_event_any_change_is():
    rec = Recorder()
    answers = {"http://killswitch": _health(1, 0, 0)}
    o, _ = _observer(rec, answers)
    o.observe_once()
    assert rec.of(obs.BREAKGLASS_EVENT) == []
    answers["http://killswitch"] = _health(1, 0, 1)
    o.observe_once()
    answers["http://killswitch"] = _health(1, 1, 1)
    o.observe_once()
    answers["http://killswitch"] = _health(1, 0, 0)          # a restart resets them: recorded
    o.observe_once()
    got = [(p["breakglass_auth_count"], p["breakglass_attempt_count"],
            p["previous_breakglass_auth_count"], p["previous_breakglass_attempt_count"], p["startup"])
           for p in rec.of(obs.BREAKGLASS_EVENT)]
    assert got == [(0, 1, 0, 0, False), (1, 1, 0, 1, False), (0, 0, 1, 1, False)]


def test_breakglass_counters_above_zero_at_the_first_observation_are_recorded():
    rec = Recorder()
    o, _ = _observer(rec, {"http://killswitch": _health(1, 2, 3)})
    o.observe_once()
    [p] = rec.of(obs.BREAKGLASS_EVENT)
    assert (p["service"], p["breakglass_auth_count"], p["breakglass_attempt_count"], p["startup"],
            p["previous_breakglass_auth_count"]) == ("kill-switch", 2, 3, True, None)


def test_an_answer_without_the_counters_records_nothing():
    rec = Recorder()
    o, _ = _observer(rec, {"http://killswitch": _health(1)})
    o.observe_once()
    assert rec.of(obs.BREAKGLASS_EVENT) == [] and rec.of(obs.GENERATION_EVENT) == []
    assert obs.observed_rotation({"breakglass_auth_count": 1})["breakglass"] is None
    assert obs.observed_rotation({"breakglass_auth_count": -1,
                                  "breakglass_attempt_count": 0})["breakglass"] is None


# --- the ledger's own parse: slot fingerprints ------------------------------------------


def _witness(gen=41, ks_next="b" * 16, sealed="s1", rows_extra=()):
    return {"format": 2, "generation": gen, "registry_sha256_prefix": "abcdefabcdefabcd",
            "rows": [{"operator_id": "don", "status": "active", "current_fp": "a" * 16, "next_fp": None},
                     {"operator_id": "svc-killswitch", "status": "active", "current_fp": "c" * 16,
                      "next_fp": ks_next},
                     {"operator_id": "don-breakglass", "status": "active", "current_fp": "(sealed)",
                      "next_fp": None}, *rows_extra],
            "_sealed_state": sealed}


def test_the_first_valid_parse_is_recorded_with_every_rows_slot_fingerprints():
    rec = Recorder()
    o, _ = _observer(rec, {}, slots=_witness())
    o.observe_once()
    [p] = rec.of(obs.SLOTS_EVENT)
    assert p == {"service": "sealed-ledger", "format": 2, "generation": 41,
                 "registry_sha256_prefix": "abcdefabcdefabcd",
                 "previous_registry_sha256_prefix": None, "rows": _witness()["rows"],
                 "changed_operator_ids": [], "sealed_key_changed": False,
                 "previous_generation": None, "startup": True, "observed_from": "own_parse"}
    assert "_sealed_state" not in json.dumps(p) and "s1" not in json.dumps(p["rows"])
    o.observe_once()
    assert len(rec.of(obs.SLOTS_EVENT)) == 1                  # unchanged: nothing more


def test_a_slot_change_names_the_identity_whose_key_changed():
    rec = Recorder()
    o, state = _observer(rec, {}, slots=_witness())
    o.observe_once()
    state["slots"] = _witness(gen=42, ks_next=None)            # promote-like: NEXT gone
    o.observe_once()
    p = rec.of(obs.SLOTS_EVENT)[-1]
    assert (p["changed_operator_ids"], p["previous_generation"], p["generation"], p["startup"],
            p["sealed_key_changed"]) == (["svc-killswitch"], 41, 42, False, False)


def test_a_content_only_edit_is_witnessed_when_only_the_file_sha_changes():
    """C-34 part 2 finding 1 (proven by probe): same generation, same fingerprints, new
    bytes (scopes, auth or expiry edited by hand) was invisible to the witness."""
    rec = Recorder()
    o, state = _observer(rec, {}, slots=_witness())
    o.observe_once()
    edited = _witness()
    edited["registry_sha256_prefix"] = "1234567812345678"
    state["slots"] = edited
    o.observe_once()
    assert len(rec.of(obs.SLOTS_EVENT)) == 2
    p = rec.of(obs.SLOTS_EVENT)[-1]
    assert (p["registry_sha256_prefix"], p["previous_registry_sha256_prefix"], p["generation"],
            p["previous_generation"], p["changed_operator_ids"], p["sealed_key_changed"],
            p["startup"]) == ("1234567812345678", "abcdefabcdefabcd", 41, 41, [], False, False)
    o.observe_once()                                          # unchanged again: nothing more
    assert len(rec.of(obs.SLOTS_EVENT)) == 2


def test_a_missing_or_malformed_sha_is_a_change_to_none_and_is_never_ledgered_raw():
    rec = Recorder()
    o, state = _observer(rec, {}, slots=_witness())
    o.observe_once()
    bad = _witness()
    bad["registry_sha256_prefix"] = "not-a-sha-prefix"
    state["slots"] = bad
    o.observe_once()
    p = rec.of(obs.SLOTS_EVENT)[-1]
    assert p["registry_sha256_prefix"] is None and "not-a-sha" not in json.dumps(p)


def test_a_sealed_key_change_is_witnessed_without_any_of_its_bytes():
    rec = Recorder()
    o, state = _observer(rec, {}, slots=_witness())
    o.observe_once()
    state["slots"] = _witness(gen=42, sealed="s2")
    o.observe_once()
    p = rec.of(obs.SLOTS_EVENT)[-1]
    assert p["sealed_key_changed"] is True and p["changed_operator_ids"] == []
    assert "s2" not in json.dumps(p) and "s1" not in json.dumps(p)


def test_witness_values_are_validated_before_they_are_ledgered():
    rec = Recorder()
    w = _witness(rows_extra=({"operator_id": "x", "status": "active",
                              "current_fp": "f" * 64, "next_fp": "fok_abc"},
                             {"operator_id": "fok_" + "a" * 50, "status": "weird",
                              "current_fp": "A" * 16, "next_fp": None}))
    o, _ = _observer(rec, {}, slots=w)
    o.observe_once()
    rows = rec.of(obs.SLOTS_EVENT)[0]["rows"]
    assert rows[3] == {"operator_id": "x", "status": "active", "current_fp": "(not shown)",
                       "next_fp": "(not shown)"}
    assert rows[4] == {"operator_id": "(not shown)", "status": "(not shown)",
                       "current_fp": "(not shown)", "next_fp": None}


def test_no_valid_parse_records_nothing_and_a_failed_append_is_retried():
    rec = Recorder()
    o, state = _observer(rec, {}, slots=None)
    o.observe_once()
    assert rec.of(obs.SLOTS_EVENT) == []
    o2, state2 = _observer(rec, {}, slots=_witness())
    state2["slots"] = None                                    # invalid file right now
    o2.observe_once()
    assert rec.of(obs.SLOTS_EVENT) == []
    state2["slots"] = _witness()
    rec.fail.add(obs.SLOTS_EVENT)
    o2.observe_once()
    rec.fail.clear()
    o2.observe_once()
    assert [p["startup"] for p in rec.of(obs.SLOTS_EVENT)] == [True]


# --- the ledger's own retired-hash counter -----------------------------------------------


def test_the_retired_hash_counter_changes_are_recorded():
    rec = Recorder()
    o, state = _observer(rec, {}, counters={"retired_hash_seen": 0})
    o.observe_once()
    assert rec.of(obs.RETIRED_EVENT) == []
    state["counters"] = {"retired_hash_seen": 2}
    o.observe_once()
    assert [(p["retired_hash_seen"], p["previous_retired_hash_seen"]) for p in rec.of(obs.RETIRED_EVENT)] \
        == [(2, 0)]


def test_exactly_one_retired_hash_at_startup_is_witnessed_with_its_full_payload():
    """C-159 (reviewer R-22 F-R22-1): the first sighting of ONE retired hash is evidence of a reuse. `n > 0`
    to `n > 1` would drop it; the payload names the service, the count, startup and where it was observed."""
    rec = Recorder()
    o, _ = _observer(rec, {}, counters={"retired_hash_seen": 1})
    written = o.observe_once()
    assert rec.of(obs.RETIRED_EVENT) == [{
        "service": obs.SELF, "retired_hash_seen": 1, "previous_retired_hash_seen": None,
        "startup": True, "observed_from": "own_process"}]
    assert written == len(rec.events) and written >= 1          # the tick reports what it wrote


def test_a_later_change_is_not_a_startup_and_is_counted_in_the_tick_result():
    rec = Recorder()
    o, state = _observer(rec, {}, counters={"retired_hash_seen": 1})
    o.observe_once()
    state["counters"] = {"retired_hash_seen": 3}
    before = len(rec.events)
    written = o.observe_once()
    assert rec.of(obs.RETIRED_EVENT)[-1] == {
        "service": obs.SELF, "retired_hash_seen": 3, "previous_retired_hash_seen": 1,
        "startup": False, "observed_from": "own_process"}
    assert written == len(rec.events) - before == 1


def test_an_unchanged_retired_counter_writes_nothing_after_the_first_sighting():
    rec = Recorder()
    o, _ = _observer(rec, {}, counters={"retired_hash_seen": 2})
    o.observe_once()
    before = len(rec.events)
    assert o.observe_once() == 0 and len(rec.events) == before


def test_a_failed_write_of_the_retired_witness_is_retried_on_the_next_tick():
    """C-159: when the ledger cannot write the retired-hash record, the counter is NOT remembered, so the
    next tick still carries it (startup stays true): a transient ledger failure must not swallow the evidence."""
    rec = Recorder()
    rec.fail.add(obs.RETIRED_EVENT)
    o, _ = _observer(rec, {}, counters={"retired_hash_seen": 1})
    assert o.observe_once() == len(rec.events) and rec.of(obs.RETIRED_EVENT) == []
    rec.fail.clear()
    o.observe_once()
    assert [p["startup"] for p in rec.of(obs.RETIRED_EVENT)] == [True]


# --- end to end through the ledger app (its own parse, its own store) ---------------------


def test_the_ledger_app_witnesses_its_own_parse_and_never_stores_a_hash(tmp_path, monkeypatch):
    t = "2026-11-20T03:00:00Z"
    doc = {"format": 2, "generation": 41, "operators": [
        {"operator_id": "don", "status": "active", "rotation": "auto", "scopes": ["*"],
         "key_sha256": H(KEY_DON), "key_not_after": "2027-01-01T00:00:00Z"},
        {"operator_id": "svc-killswitch", "status": "active", "rotation": "auto", "scopes": ["kill"],
         "key_sha256": H(KEY_KS), "key_not_after": "2027-01-01T00:00:00Z",
         "next_key": {"key_sha256": H(KEY_KS_NEXT), "not_before": t, "not_after": "2027-02-01T00:00:00Z"}},
        {"operator_id": "don-breakglass", "status": "active", "rotation": "sealed", "scopes": ["kill"],
         "key_sha256": H(KEY_BG)}]}
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv("FIELD_LEDGER_OBSERVE_EVERY", "3600")
    monkeypatch.delenv("FIELD_LEDGER_OBSERVE_HEALTH", raising=False)
    app = create_app(store=LedgerStore(tmp_path / "events.jsonl"), observe_fetch=lambda u: None)
    app.state.operator_observer.observe_once()
    doc["generation"] = 40                                   # an older file is restored
    p.write_text(json.dumps(doc), encoding="utf-8")
    app.state.operator_observer.observe_once()
    c = TestClient(app)
    [s1, s2] = [e["payload"] for e in c.get("/events", params={"event_type": obs.SLOTS_EVENT}).json()]
    rows = {r["operator_id"]: r for r in s1["rows"]}
    assert rows["svc-killswitch"]["current_fp"] == H(KEY_KS)[:16]
    assert rows["svc-killswitch"]["next_fp"] == H(KEY_KS_NEXT)[:16]
    assert rows["don-breakglass"]["current_fp"] == "(sealed)"
    assert (s2["generation"], s2["previous_generation"]) == (40, 41)
    [g] = c.get("/events", params={"event_type": obs.GENERATION_EVENT}).json()
    assert g["payload"]["service"] == "sealed-ledger" and g["agent_id"] is None
    blob = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    for k in (KEY_DON, KEY_KS, KEY_KS_NEXT, KEY_BG):
        assert k not in blob and H(k) not in blob
    assert H(KEY_BG)[:16] not in blob and H(KEY_BG)[:8] not in blob
