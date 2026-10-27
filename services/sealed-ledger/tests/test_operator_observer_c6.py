"""Phase G Stage 0, guards slice, C-6 (design 2.3, 2.6, 5.4, 5.5; RT1-2, RT3-6):
the sealed-ledger writes ``operator.mode_changed`` and
``operator.registry_changed`` ITSELF, from the operator block it observes in
each service's open ``/health`` (mode, registry sha256 prefix, row count): one
of each per service at start-up (the first observation by this ledger process)
and one each time the observed value changes. HTTP callers still cannot write
these types when the ledger is armed (tests/test_operator_health_g_sealed_ledger.py).

The observer is armed only by FIELD_LEDGER_OBSERVE_EVERY (unset = no observer,
no event, byte-identical to before). Test key values are throwaway constants;
nothing here reads a real key."""

from __future__ import annotations

import hashlib
import json
import time

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore

KEY_DON = "tkv-c6don-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE, "FIELD_LEDGER_OBSERVE_EVERY", "FIELD_LEDGER_OBSERVE_HEALTH"):
        monkeypatch.delenv(n, raising=False)


def _obs():
    from sealed_ledger import operator_observer
    return operator_observer


def _health(mode="off", sha=None, rows=None, **extra):
    return {"ok": True, "operator_mode": mode, "operator_registry_sha256_prefix": sha,
            "operator_registry_rows": rows, **extra}


class Recorder:
    def __init__(self, fail=0):
        self.events: list[tuple[str, dict]] = []
        self.fail = fail

    def __call__(self, event_type, payload):
        if self.fail:
            self.fail -= 1
            raise RuntimeError("ledger busy (simulated)")
        self.events.append((event_type, payload))

    def of(self, event_type, service=None):
        return [p for t, p in self.events
                if t == event_type and (service is None or p["service"] == service)]


class Fetch:
    """name/url -> health dict (None = unreachable)."""

    def __init__(self, answers):
        self.answers = answers
        self.urls: list[str] = []

    def __call__(self, url):
        self.urls.append(url)
        return self.answers.get(url.removesuffix("/health"))


def _observer(rec, fetch, self_state=None, targets=None):
    obs = _obs()
    state = {"h": self_state or _health()}
    o = obs.OperatorObserver(append=rec, self_health=lambda: state["h"],
                             targets=targets if targets is not None else [
                                 ("agent-registry", "http://registry"),
                                 ("kill-switch", "http://killswitch")],
                             fetch=fetch)
    return o, state


# --- start-up ------------------------------------------------------------------------------


def test_startup_writes_one_mode_and_one_registry_event_per_service_including_itself():
    rec = Recorder()
    fetch = Fetch({"http://registry": _health("log-only", "0123456789abcdef", 10),
                   "http://killswitch": _health("enforce", "0123456789abcdef", 10)})
    o, _ = _observer(rec, fetch)
    o.observe_once()
    modes = {p["service"]: p for p in rec.of("operator.mode_changed")}
    regs = {p["service"]: p for p in rec.of("operator.registry_changed")}
    assert set(modes) == set(regs) == {"sealed-ledger", "agent-registry", "kill-switch"}
    assert modes["kill-switch"] == {"service": "kill-switch", "mode": "enforce",
                                    "previous_mode": None, "startup": True,
                                    "observed_from": "health"}
    assert regs["agent-registry"] == {
        "service": "agent-registry", "mode": "log-only",
        "registry_sha256_prefix": "0123456789abcdef", "registry_rows": 10,
        "previous_registry_sha256_prefix": None, "previous_registry_rows": None,
        "startup": True, "observed_from": "health"}
    assert modes["sealed-ledger"]["mode"] == "off" and regs["sealed-ledger"]["registry_rows"] is None
    assert fetch.urls == ["http://registry/health", "http://killswitch/health"]


def test_an_unchanged_estate_writes_nothing_on_later_ticks():
    rec = Recorder()
    fetch = Fetch({"http://registry": _health("enforce", "aaaaaaaaaaaaaaaa", 9),
                   "http://killswitch": _health("enforce", "aaaaaaaaaaaaaaaa", 9)})
    o, _ = _observer(rec, fetch)
    o.observe_once()
    n = len(rec.events)
    o.observe_once()
    o.observe_once()
    assert len(rec.events) == n == 6


# --- changes -------------------------------------------------------------------------------


def test_a_disarm_is_a_mode_changed_event_with_the_previous_mode():
    rec = Recorder()
    answers = {"http://registry": _health("enforce", "aaaaaaaaaaaaaaaa", 9),
               "http://killswitch": _health("enforce", "aaaaaaaaaaaaaaaa", 9)}
    o, _ = _observer(rec, Fetch(answers))
    o.observe_once()
    rec.events.clear()
    answers["http://killswitch"] = _health("off", "aaaaaaaaaaaaaaaa", None)
    o.observe_once()
    [mode] = rec.of("operator.mode_changed")
    assert mode == {"service": "kill-switch", "mode": "off", "previous_mode": "enforce",
                    "startup": False, "observed_from": "health"}
    # the row count went 9 -> null (off does not validate as enforce): a registry change too
    [reg] = rec.of("operator.registry_changed")
    assert reg["service"] == "kill-switch" and reg["registry_rows"] is None
    assert reg["previous_registry_rows"] == 9 and reg["mode"] == "off"


def test_an_operators_file_edit_is_a_registry_changed_event_only():
    rec = Recorder()
    answers = {"http://registry": _health("log-only", "aaaaaaaaaaaaaaaa", 9),
               "http://killswitch": _health("log-only", "aaaaaaaaaaaaaaaa", 9)}
    o, _ = _observer(rec, Fetch(answers))
    o.observe_once()
    rec.events.clear()
    answers["http://registry"] = _health("log-only", "bbbbbbbbbbbbbbbb", 10)
    o.observe_once()
    assert rec.of("operator.mode_changed") == []
    [reg] = rec.of("operator.registry_changed")
    assert reg == {"service": "agent-registry", "mode": "log-only",
                   "registry_sha256_prefix": "bbbbbbbbbbbbbbbb", "registry_rows": 10,
                   "previous_registry_sha256_prefix": "aaaaaaaaaaaaaaaa",
                   "previous_registry_rows": 9, "startup": False, "observed_from": "health"}


def test_a_rollback_to_an_older_file_with_the_same_row_count_is_still_seen():
    """5.5: a restore of an older operators.json changes the bytes, not the count."""
    rec = Recorder()
    answers = {"http://registry": _health("enforce", "aaaaaaaaaaaaaaaa", 9),
               "http://killswitch": _health("enforce", "aaaaaaaaaaaaaaaa", 9)}
    o, _ = _observer(rec, Fetch(answers))
    o.observe_once()
    rec.events.clear()
    answers["http://killswitch"] = _health("enforce", "cccccccccccccccc", 9)
    o.observe_once()
    [reg] = rec.of("operator.registry_changed")
    assert reg["service"] == "kill-switch" and reg["registry_sha256_prefix"] == "cccccccccccccccc"


def test_an_unreachable_service_writes_nothing_and_its_change_is_seen_when_it_returns():
    rec = Recorder()
    answers = {"http://registry": _health("enforce", "aaaaaaaaaaaaaaaa", 9),
               "http://killswitch": None}
    o, _ = _observer(rec, Fetch(answers))
    o.observe_once()
    assert rec.of("operator.mode_changed", "kill-switch") == []
    answers["http://killswitch"] = _health("log-only", "aaaaaaaaaaaaaaaa", 9)
    o.observe_once()
    [mode] = rec.of("operator.mode_changed", "kill-switch")
    assert mode["startup"] is True and mode["mode"] == "log-only"
    answers["http://killswitch"] = None             # down again: nothing, state kept
    o.observe_once()
    answers["http://killswitch"] = _health("enforce", "aaaaaaaaaaaaaaaa", 9)
    o.observe_once()
    assert [m["mode"] for m in rec.of("operator.mode_changed", "kill-switch")] == ["log-only", "enforce"]


def test_a_health_without_an_operator_block_is_recorded_as_absent():
    """5.6: a pre-Phase-G image (image rollback) answers /health without the block."""
    rec = Recorder()
    answers = {"http://registry": _health("enforce", "aaaaaaaaaaaaaaaa", 9),
               "http://killswitch": _health("enforce", "aaaaaaaaaaaaaaaa", 9)}
    o, _ = _observer(rec, Fetch(answers))
    o.observe_once()
    rec.events.clear()
    answers["http://killswitch"] = {"ok": True, "service": "kill-switch"}
    o.observe_once()
    [mode] = rec.of("operator.mode_changed")
    assert mode["service"] == "kill-switch" and mode["mode"] == "absent"
    assert mode["previous_mode"] == "enforce"


def test_a_failed_append_is_retried_on_the_next_tick():
    rec = Recorder(fail=1)
    o, _ = _observer(rec, Fetch({}), targets=[])
    o.observe_once()                                # mode append fails
    assert rec.of("operator.mode_changed") == []
    o.observe_once()
    assert len(rec.of("operator.mode_changed", "sealed-ledger")) == 1
    assert len(rec.of("operator.registry_changed", "sealed-ledger")) == 1
    o.observe_once()
    assert len(rec.events) == 2


# --- what reaches the ledger ---------------------------------------------------------------


@pytest.mark.parametrize("bad_health,want_mode,want_sha,want_rows", [
    (_health("ENFORCE", "aaaaaaaaaaaaaaaa", 9), "unrecognised", "aaaaaaaaaaaaaaaa", 9),
    (_health("enforce", "fok_" + "a" * 40, 9), "enforce", "(not shown)", 9),
    (_health("enforce", "AAAAAAAAAAAAAAAA", "9"), "enforce", "(not shown)", None),
    (_health(["enforce"], None, True), "unrecognised", None, None),
    (_health("enforce", None, -1), "enforce", None, None),
    ("not a dict", "unrecognised", None, None),
])
def test_values_from_a_health_answer_are_validated_before_they_are_ledgered(
        bad_health, want_mode, want_sha, want_rows):
    rec = Recorder()
    o, _ = _observer(rec, Fetch({"http://x": bad_health}), targets=[("x", "http://x")])
    o.observe_once()
    [mode] = rec.of("operator.mode_changed", "x")
    [reg] = rec.of("operator.registry_changed", "x")
    assert mode["mode"] == want_mode
    assert reg["registry_sha256_prefix"] == want_sha and reg["registry_rows"] == want_rows
    assert "fok_" not in json.dumps(rec.events)


def test_the_ledgers_own_block_is_observed_in_process(tmp_path, monkeypatch):
    """Self is read from this app's operator block, never over HTTP to itself."""
    p = tmp_path / "operators.json"
    raw = json.dumps([{"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON),
                       "status": "active", "scopes": ["*"]}]).encode()
    p.write_bytes(raw)
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv("FIELD_LEDGER_OBSERVE_EVERY", "3600")
    app = create_app(store=LedgerStore(tmp_path / "events.jsonl"), observe_fetch=Fetch({}))
    app.state.operator_observer.observe_once()
    c = TestClient(app)
    [m] = c.get("/events", params={"event_type": "operator.mode_changed"}).json()
    [r] = c.get("/events", params={"event_type": "operator.registry_changed"}).json()
    assert m["payload"]["service"] == "sealed-ledger" and m["payload"]["mode"] == "log-only"
    assert r["payload"]["registry_sha256_prefix"] == hashlib.sha256(raw).hexdigest()[:16]
    assert r["payload"]["registry_rows"] == 1
    assert m["agent_id"] is None and "self_reported" not in m["payload"]
    assert KEY_DON not in json.dumps([m, r]) and oa.key_sha256(KEY_DON) not in json.dumps([m, r])


# --- arming --------------------------------------------------------------------------------


def test_unarmed_by_default_no_observer_and_no_event(tmp_path):
    app = create_app(store=LedgerStore(tmp_path / "events.jsonl"))
    assert app.state.operator_observer is None
    with TestClient(app) as c:
        time.sleep(0.3)
        assert c.get("/health").json()["event_count"] == 0


def test_armed_the_first_tick_runs_at_start_up_through_the_lifespan(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_LEDGER_OBSERVE_EVERY", "3600")
    monkeypatch.setenv("FIELD_LEDGER_OBSERVE_HEALTH", "agent-registry=http://registry")
    fetch = Fetch({"http://registry": _health("off")})
    app = create_app(store=LedgerStore(tmp_path / "events.jsonl"), observe_fetch=fetch)
    with TestClient(app) as c:
        deadline = time.monotonic() + 10
        evs = []
        while time.monotonic() < deadline:
            evs = c.get("/events", params={"event_type": "operator.mode_changed"}).json()
            if len(evs) == 2:
                break
            time.sleep(0.05)
        assert sorted(e["payload"]["service"] for e in evs) == ["agent-registry", "sealed-ledger"]
    assert app.state.operator_observer_thread is not None
    assert not app.state.operator_observer_thread.is_alive()   # stopped with the app


@pytest.mark.parametrize("raw,want", [
    ("agent-registry=http://registry:8001", [("agent-registry", "http://registry:8001")]),
    (" a=http://a , b=https://b/x/ ", [("a", "http://a"), ("b", "https://b/x")]),
    ("a=ftp://a,b=http://b", [("b", "http://b")]),               # http(s) only
    ("BAD NAME=http://a,c=http://c", [("c", "http://c")]),        # name charset
    ("a=http://a,a=http://other", [("a", "http://a")]),           # first wins, duplicate dropped
    ("sealed-ledger=http://l,d=http://d", [("d", "http://d")]),   # self is in-process only
    ("noequals,e=http://e", [("e", "http://e")]),
    ("", []),
])
def test_targets_are_parsed_strictly(raw, want):
    assert _obs().parse_targets(raw) == want


def test_the_target_list_is_capped():
    raw = ",".join(f"s{i}=http://h{i}" for i in range(100))
    assert len(_obs().parse_targets(raw)) == _obs().MAX_TARGETS


@pytest.mark.parametrize("raw,want", [("", None), ("0", None), ("-5", None), ("abc", None),
                                      ("1", 5), ("60", 60), (" 120 ", 120)])
def test_the_interval_is_parsed_and_floored(raw, want):
    assert _obs().interval_from_env(raw) == want


# --- R2-L3 Y2: a fetch that raises never stops a tick or the observer thread ----------------


class _Boom(Exception):
    """Not an OSError, not a ValueError: an except narrowed to the usual network errors
    would let it through."""


def test_a_fetch_that_raises_is_no_answer_and_the_rest_of_the_tick_still_runs():
    rec = Recorder()

    def fetch(url):
        if url.startswith("http://killswitch"):
            raise _Boom("fetch blew up (simulated)")
        return _health("enforce", "aaaaaaaaaaaaaaaa", 9)

    # the raising target FIRST, so a target after it proves the tick went on
    o, _ = _observer(rec, fetch, targets=[("kill-switch", "http://killswitch"),
                                          ("agent-registry", "http://registry")])
    assert o.observe_once() == 4                  # itself + agent-registry, two events each
    assert rec.of("operator.mode_changed", "kill-switch") == []
    assert [p["mode"] for p in rec.of("operator.mode_changed", "agent-registry")] == ["enforce"]


def test_a_self_health_that_raises_is_no_answer_and_the_targets_are_still_read():
    rec = Recorder()
    obs = _obs()

    def self_health():
        raise _Boom("own block blew up (simulated)")

    o = obs.OperatorObserver(append=rec, self_health=self_health,
                             targets=[("agent-registry", "http://registry")],
                             fetch=Fetch({"http://registry": _health("off")}))
    assert o.observe_once() == 2
    assert rec.of("operator.mode_changed", "sealed-ledger") == []


def test_the_observer_thread_survives_fetch_exceptions_and_keeps_ticking():
    import threading

    rec = Recorder()
    calls = {"n": 0}

    def fetch(url):
        calls["n"] += 1
        raise _Boom("fetch blew up (simulated)")

    o, state = _observer(rec, fetch, targets=[("kill-switch", "http://killswitch")])
    stop = threading.Event()
    t = threading.Thread(target=o.run_every, args=(0.02, stop), daemon=True)
    t.start()
    try:
        deadline = time.monotonic() + 10
        while calls["n"] < 5 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert calls["n"] >= 5 and t.is_alive()  # five ticks, each one raising, thread alive
        state["h"] = _health("log-only")          # and a later change is still recorded
        deadline = time.monotonic() + 10
        while len(rec.of("operator.mode_changed", "sealed-ledger")) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert [p["mode"] for p in rec.of("operator.mode_changed", "sealed-ledger")] == ["off", "log-only"]
    finally:
        stop.set()
        t.join(5)
    assert not t.is_alive()


def test_the_observer_thread_survives_a_tick_that_raises(monkeypatch):
    """The second layer: even a tick that raises (observe_once never should) does not end
    the thread."""
    import threading

    rec = Recorder()
    o, _ = _observer(rec, Fetch({}), targets=[])
    real = o.observe_once
    ticks = {"n": 0}

    def flaky():
        ticks["n"] += 1
        if ticks["n"] <= 2:
            raise _Boom("tick blew up (simulated)")
        return real()

    monkeypatch.setattr(o, "observe_once", flaky)
    stop = threading.Event()
    t = threading.Thread(target=o.run_every, args=(0.02, stop), daemon=True)
    t.start()
    try:
        deadline = time.monotonic() + 10
        while not rec.of("operator.mode_changed", "sealed-ledger") and time.monotonic() < deadline:
            time.sleep(0.01)
        assert t.is_alive() and ticks["n"] >= 3
        assert len(rec.of("operator.mode_changed", "sealed-ledger")) == 1
    finally:
        stop.set()
        t.join(5)
