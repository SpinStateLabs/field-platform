"""estate_probe (C-105, reviewer R-06): --expect-mode on the status pairing, the canary restore after a
catalogue run that ends with it not verified active, the bounded response read, and the four test gaps
(the method compare in is_guarded, the gate-row bracket boundary, the ledger read error branch, the
'unknown' build_sha). Unit tests use fakes; two run the real estate of test_estate_probe."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import estate_probe as ep  # noqa: E402

from test_estate_probe import (CANARY, _catalogue, _change, _http, _kill, _open_estate, _run,  # noqa: E402,F401
                               estate)


@pytest.fixture(autouse=True)
def _results():
    ep.RESULTS.clear()
    yield
    ep.RESULTS.clear()


def _printed(fn, *a, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        value = fn(*a, **kw)
    return value, out.getvalue()


# --- the bounded read ---------------------------------------------------------------------------------


class _Resp:
    status = 200

    def __init__(self, raw: bytes, asked: list):
        self.raw, self.asked = raw, asked

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, size=-1):
        self.asked.append(size)
        return self.raw if size < 0 else self.raw[:size]


class _Opener:
    def __init__(self, raw: bytes, error: int | None = None):
        self.raw, self.error, self.asked = raw, error, []

    def open(self, req, timeout=None):
        if self.error is not None:
            fp = io.BytesIO(self.raw)
            asked = self.asked
            real_read = fp.read

            def read(size=-1):
                asked.append(size)
                return real_read(size)

            fp.read = read
            raise urllib.error.HTTPError(req.full_url, self.error, "err", {}, fp)
        return _Resp(self.raw, self.asked)


def _body(size: int) -> bytes:
    pad = size - len(json.dumps({"p": ""}))
    raw = json.dumps({"p": "x" * pad}).encode()
    assert len(raw) == size
    return raw


@pytest.fixture()
def estate_call(monkeypatch):
    def make(raw: bytes, error: int | None = None):
        opener = _Opener(raw, error)
        monkeypatch.setattr(ep, "_OPENER", opener)
        return ep.Estate("http://127.0.0.1:9", None), opener
    return make


def test_a_reply_of_exactly_the_cap_is_read_and_one_byte_more_is_refused(estate_call):
    e, opener = estate_call(_body(ep.MAX_RESPONSE_BYTES))
    status, body = e.call("GET", "/x")
    assert status == 200 and isinstance(body, dict) and len(body["p"]) > 0
    assert opener.asked == [ep.MAX_RESPONSE_BYTES + 1], "never ask for more than the cap plus one byte"
    e, opener = estate_call(_body(ep.MAX_RESPONSE_BYTES + 1))
    assert e.call("GET", "/x") == (200, {"response_too_large": ep.MAX_RESPONSE_BYTES})
    assert opener.asked == [ep.MAX_RESPONSE_BYTES + 1]


def test_an_oversized_reply_is_not_parsed_even_when_it_is_json(estate_call):
    e, _ = estate_call(b" " * (ep.MAX_RESPONSE_BYTES + 5) + b'{"ok": true}')
    status, body = e.call("GET", "/x")
    assert body == {"response_too_large": ep.MAX_RESPONSE_BYTES}


@pytest.mark.parametrize("size, too_large", [(ep.MAX_RESPONSE_BYTES, False), (ep.MAX_RESPONSE_BYTES + 1, True)])
def test_an_error_reply_is_bounded_the_same_way(estate_call, size, too_large):
    e, opener = estate_call(_body(size), error=500)
    status, body = e.call("GET", "/x")
    assert status == 500
    assert (body == {"response_too_large": ep.MAX_RESPONSE_BYTES}) is too_large
    assert opener.asked == [ep.MAX_RESPONSE_BYTES + 1]


def test_a_small_and_an_empty_reply_are_unchanged(estate_call):
    assert estate_call(b'{"a": 1}')[0].call("GET", "/x") == (200, {"a": 1})
    assert estate_call(b"")[0].call("GET", "/x") == (200, None)
    assert estate_call(b"not json")[0].call("GET", "/x") == (200, {"non_json_bytes": 8})


# --- the gap in is_guarded: the method is compared ------------------------------------------------------

SAMPLES = ["/killswitch/kill/a1", "/killswitch/revive/a1", "/killswitch/drill/a1", "/registry/agents/a1/attest",
           "/delegation/tokens/t1/revoke"]


@pytest.mark.parametrize("path", SAMPLES)
def test_only_a_post_to_a_guarded_route_is_guarded(path):
    assert ep.is_guarded("POST", path) and ep.is_guarded("post", path) and ep.is_guarded("POST", path + "?x=1")
    for method in ("GET", "PUT", "PATCH", "DELETE", "HEAD", ""):
        assert not ep.is_guarded(method, path), (method, path)


@pytest.mark.parametrize("path", ["/killswitch/kill/", "/killswitch/kill/a/b", "/killswitch/heartbeat/a1",
                                  "/killswitch/liveness", "/registry/agents/a1", "/delegation/tokens/t1",
                                  "/ledger/events", "/killswitch/kill"])
def test_an_unlisted_path_is_never_guarded_whatever_the_method(path):
    for method in ("POST", "GET"):
        assert not ep.is_guarded(method, path), (method, path)


# --- the gap in the gate-row bracket: the boundaries ----------------------------------------------------


@pytest.mark.parametrize("gate, before, after, want", [
    (1, 1, 1, True),          # equal counts, the smallest non-vacuous bracket
    (5, 5, 9, True),          # gate == before
    (9, 5, 9, True),          # gate == after
    (7, 5, 9, True),
    (4, 5, 9, False),         # stale: below before
    (10, 5, 9, False),        # inflated: above after
    (0, 0, 0, False),         # vacuous: before < 1 even though 0 == 0 == 0
    (0, 0, 3, False),
    (True, 1, 1, False),      # a bool is not a count
    ("5", 5, 9, False), (None, 5, 9, False), (5.0, 5, 9, False),
    (5, None, 9, False), (5, 5, None, False), (5, 9, 5, False),
])
def test_the_gate_row_bracket(gate, before, after, want):
    assert ep._gate_row_bracketed(gate, before, after) is want


# --- the gap in the ledger read: a failed read is a FAIL and None ---------------------------------------


class _Fake:
    """An Estate whose answers are canned per path."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def call(self, method, path, body=None, **kw):
        self.calls.append((method, path))
        return self.answers[path.split("?")[0]]


GOOD_HEALTH = {"event_count": 2, "head_hash": "h2"}


@pytest.mark.parametrize("name, answers, expect", [
    ("events 500", {"/ledger/health": (200, GOOD_HEALTH), "/ledger/events": (500, None),
                    "/ledger/verify": (200, {"ok": True, "length": 2})}, "GET /ledger/events failed (HTTP 500; /ledger/health HTTP 200)"),
    ("health 503", {"/ledger/health": (503, None), "/ledger/events": (200, [{"hash": "h1"}, {"hash": "h2"}]),
                    "/ledger/verify": (200, {"ok": True, "length": 2})}, "failed (HTTP 200; /ledger/health HTTP 503)"),
    ("events not a list", {"/ledger/health": (200, GOOD_HEALTH), "/ledger/events": (200, {"x": 1}),
                           "/ledger/verify": (200, {"ok": True, "length": 2})}, "GET /ledger/events failed"),
    ("health not an object", {"/ledger/health": (200, ["x"]), "/ledger/events": (200, []),
                              "/ledger/verify": (200, {"ok": True, "length": 0})}, "GET /ledger/events failed"),
])
def test_a_failed_ledger_read_is_a_fail_and_returns_none(name, answers, expect):
    events, out = _printed(ep._ledger, _Fake(answers))
    assert events is None
    assert [ok for ok, _ in ep.RESULTS] == [False], ep.RESULTS
    assert expect in ep.RESULTS[0][1], ep.RESULTS


def test_a_consistent_ledger_read_returns_the_events():
    answers = {"/ledger/health": (200, GOOD_HEALTH), "/ledger/events": (200, [{"hash": "h1"}, {"hash": "h2"}]),
               "/ledger/verify": (200, {"ok": True, "length": 2})}
    events, _ = _printed(ep._ledger, _Fake(answers))
    assert events == [{"hash": "h1"}, {"hash": "h2"}] and [ok for ok, _ in ep.RESULTS] == [True]


# --- the gap in the build_sha check: 'unknown' is shown as such and fails ------------------------------


WANT = "a" * 40


def test_an_unknown_build_sha_is_named_and_fails():
    _, out = _printed(ep._check_build_sha, "/ledger/health", {"build_sha": "unknown"}, WANT)
    assert [ok for ok, _ in ep.RESULTS] == [False]
    assert "build_sha 'unknown' == deploy SHA aaaaaaaaaaaa" in ep.RESULTS[0][1], ep.RESULTS


def test_a_matching_sha_passes_and_a_sha_shaped_mismatch_is_shown_but_other_values_are_not():
    _printed(ep._check_build_sha, "/h", {"build_sha": WANT}, WANT)
    _printed(ep._check_build_sha, "/h", {"build_sha": "b" * 40}, WANT)
    _printed(ep._check_build_sha, "/h", {"build_sha": "not a sha at all, long value"}, WANT)
    _printed(ep._check_build_sha, "/h", None, WANT)
    results = ep.RESULTS
    assert [ok for ok, _ in results] == [True, False, False, False]
    assert "build_sha " + "b" * 40 + " == deploy SHA" in results[1][1]
    assert "not a sha at all" not in results[2][1] and "not shown" in results[2][1]
    assert "not shown" in results[3][1]


# --- --expect-mode on the pairing -----------------------------------------------------------------------


def _pair(tail, expect=None):
    n, out = _printed(ep.check_status_pairing, tail, "in the test window", expect)
    results = list(ep.RESULTS)
    ep.RESULTS.clear()
    return n, results, out


ARMED = [_kill(CANARY, "kill.agent"), _change(CANARY, "killed"), _change(CANARY, "active"),
         _kill(CANARY, "kill.revive")]
def _strip(tail):
    out = []
    for ev in tail:
        ev = dict(ev, payload={k: v for k, v in ev["payload"].items() if k != ep.ATTRIBUTION_KEY})
        out.append(ev)
    return out


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_an_armed_estate_passes_an_armed_expectation_and_fails_off(mode):
    n, results, out = _pair(ARMED, mode)
    assert n == 2 and all(ok for ok, _ in results) and any(f"--expect-mode {mode}: all 2" in l for _, l in results)
    n, results, out = _pair(ARMED, "off")
    assert [ok for ok, label in results if "--expect-mode" in label] == [False]
    assert "none of the 2 status change(s) carries" in out and "(2 do)" in out


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_an_unarmed_ledger_fails_an_armed_expectation_that_the_payload_rule_alone_passes(mode):
    """The failure R-06 found: a ledger that strips the reserved keys pairs by agent and kind and passed."""
    tail = _strip(ARMED)
    n, results, _ = _pair(tail)                       # no expectation: every check passes (the old behaviour)
    assert n == 2 and all(ok for ok, _ in results)
    n, results, out = _pair(tail, mode)
    assert [ok for ok, label in results if "--expect-mode" in label] == [False]
    assert "(0 do)" in out or any("all 2" in l for _, l in results if "--expect-mode" in l)


def test_flags_off_passes_an_off_expectation():
    n, results, _ = _pair(_strip(ARMED), "off")
    assert n == 2 and all(ok for ok, _ in results)
    assert any("none of the 2 status change(s) carries" in l for _, l in results)


@pytest.mark.parametrize("mode", ["off", "log-only", "enforce"])
def test_a_mixed_window_fails_every_expectation(mode):
    # the first change carries the key, the second does not (a key present with a null value still counts as armed)
    mixed = [ARMED[0], ARMED[1], *_strip([ARMED[2], ARMED[3]])]
    n, results, _ = _pair(mixed, mode)
    assert n == 2 and [ok for ok, label in results if "--expect-mode" in label] == [False]


@pytest.mark.parametrize("mode", ["off", "log-only", "enforce"])
def test_an_expected_mode_with_no_status_change_cannot_be_verified(mode):
    n, results, _ = _pair([_kill(CANARY, "kill.agent")], mode)
    assert n == 0
    assert [ok for ok, label in results if "cannot be verified" in label] == [False]
    n, results, _ = _pair([_kill(CANARY, "kill.agent")])
    assert n == 0 and all(ok for ok, _ in results)    # without an expectation nothing changes


def test_expect_mode_is_a_catalogue_option_with_three_choices_and_no_other_subcommand_has_it():
    with pytest.raises(SystemExit) as e:
        ep.main(["--base", "http://127.0.0.1:9", "catalogue", "--agent", CANARY, "--token", "t",
                 "--expect-endpoint", "skipped", "--expect-mode", "sometimes"])
    assert e.value.code == 2
    with pytest.raises(SystemExit) as e:
        ep.main(["--base", "http://127.0.0.1:9", "canary", "--agent", CANARY, "--token", "t",
                 "--expect-mode", "off"])
    assert e.value.code == 2


def test_catalogue_with_expect_mode_off_passes_on_the_flags_off_estate_and_enforce_fails(estate):
    e = estate
    code, out = _run(e.argv("catalogue", "--agent", CANARY, "--token", e.token, "--expect-endpoint", "skipped",
                            "--expect-mode", "off"))
    assert code == 0 and "[PASS] RT1-3 --expect-mode off: none of the" in out, out
    code, out = _run(e.argv("catalogue", "--agent", CANARY, "--token", e.token, "--expect-endpoint", "skipped",
                            "--expect-mode", "enforce"))
    assert code == 1 and "[FAIL] RT1-3 --expect-mode enforce: all" in out, out


# --- the restore after a catalogue run that does not end with the canary verified active ---------------


class _Canary:
    """A fake estate: a heartbeat that says killed or not, and a revive that works or does not."""

    def __init__(self, killed, revive_flips=True, unreadable=False):
        self.killed, self.revive_flips, self.unreadable, self.calls = killed, revive_flips, unreadable, []

    def call(self, method, path, body=None, **kw):
        self.calls.append((method, path, body))
        if method == "GET" and path.startswith("/killswitch/heartbeat/"):
            return (500, None) if self.unreadable else (200, {"killed": self.killed})
        if method == "POST" and path.startswith("/killswitch/revive/"):
            if self.revive_flips:
                self.killed = False
            return 200, {}
        raise AssertionError((method, path))


OP = {"operator": "FIELD gate verification (canary)", "reason": "live catalogue check - canary only"}


def test_an_active_canary_is_left_alone_and_no_revive_is_sent():
    c = _Canary(killed=False)
    ok, _ = _printed(ep._restore_canary, c, CANARY, OP)
    assert ok is True and [m for m, _, _ in c.calls] == ["GET"] and ep.RESULTS == []


def test_a_killed_canary_is_revived_once_and_read_back():
    c = _Canary(killed=True)
    ok, out = _printed(ep._restore_canary, c, CANARY, OP)
    assert ok is True and c.killed is False
    assert [(m, p) for m, p, _ in c.calls] == [("GET", f"/killswitch/heartbeat/{CANARY}"),
                                              ("POST", f"/killswitch/revive/{CANARY}"),
                                              ("GET", f"/killswitch/heartbeat/{CANARY}")]
    assert c.calls[1][2] == OP and "RESTORE" in out
    assert [ok for ok, _ in ep.RESULTS] == [True] and "is active again" in ep.RESULTS[0][1]


def test_a_revive_that_does_not_flip_is_a_fail_and_says_the_canary_may_still_be_killed():
    c = _Canary(killed=True, revive_flips=False)
    ok, out = _printed(ep._restore_canary, c, CANARY, OP)
    assert ok is False and [ok for ok, _ in ep.RESULTS] == [False]
    assert "CANARY MAY STILL BE KILLED" in out and f"/killswitch/revive/{CANARY}" in out
    assert [m for m, _, _ in c.calls].count("POST") == 1, "one revive, not a retry loop"


def test_an_unreadable_heartbeat_is_not_taken_as_active():
    c = _Canary(killed=False, unreadable=True)
    ok, _ = _printed(ep._restore_canary, c, CANARY, OP)
    assert ok is False and [m for m, _, _ in c.calls].count("POST") == 1


def _stub_run(monkeypatch, kill_sent, active, code=0, raises=None):
    def run(estate, args, state):
        state["kill_sent"], state["active"] = kill_sent, active
        if raises:
            raise raises
        return code
    restores = []
    monkeypatch.setattr(ep, "_catalogue_run", run)
    monkeypatch.setattr(ep, "_restore_canary", lambda e, a, op: restores.append((a, op)) or True)
    return restores


class _Args:
    agent = CANARY


def test_a_run_that_ends_with_the_canary_verified_active_sends_no_restore(monkeypatch):
    restores = _stub_run(monkeypatch, True, True, code=0)
    assert ep.cmd_catalogue(object(), _Args()) == 0 and restores == []


def test_a_run_that_never_sent_the_kill_sends_no_restore(monkeypatch):
    restores = _stub_run(monkeypatch, False, False, code=1)
    assert ep.cmd_catalogue(object(), _Args()) == 1 and restores == []


def test_a_run_that_ends_with_the_canary_not_verified_active_restores_it_and_reports_through_the_exit_code(monkeypatch):
    restores = _stub_run(monkeypatch, True, False, code=0)
    ep.RESULTS.append((False, "a restore that failed would be recorded here"))
    code, _ = _printed(ep.cmd_catalogue, object(), _Args())
    assert code == 1, "the exit status is recomputed after the restore, so a failed restore is not lost"
    assert restores == [(CANARY, ep.CATALOGUE_OP)]


def test_an_exception_after_the_kill_restores_the_canary_and_propagates(monkeypatch):
    restores = _stub_run(monkeypatch, True, False, raises=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        ep.cmd_catalogue(object(), _Args())
    assert restores == [(CANARY, ep.CATALOGUE_OP)]
    restores = _stub_run(monkeypatch, True, False, raises=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        ep.cmd_catalogue(object(), _Args())
    assert restores == [(CANARY, ep.CATALOGUE_OP)]
    restores = _stub_run(monkeypatch, True, True, raises=RuntimeError("after the canary was verified active"))
    with pytest.raises(RuntimeError):
        ep.cmd_catalogue(object(), _Args())
    assert restores == []


def test_a_drill_that_leaves_the_canary_killed_is_restored_by_the_run_itself(estate):
    """The real estate: the fault re-kills the canary after the drill; the run still goes red on that check,
    and then revives the canary, so the probe does not leave the outage it just found."""
    estate.fault("drill_leaves_killed")
    code, out = _catalogue(estate)
    assert code == 1, out
    assert "[FAIL] B3 heartbeat 200 killed=false after the drill" in out, out
    assert "RESTORE" in out and f"[PASS] RESTORE {CANARY} is active again" in out, out
    status, hb = _http("GET", f"{estate.base}/killswitch/heartbeat/{CANARY}", None, estate.secret)
    assert status == 200 and hb["killed"] is False, hb


def test_a_healthy_run_sends_no_restore(estate):
    code, out = _catalogue(estate)
    assert code == 0 and "RESTORE" not in out, out
