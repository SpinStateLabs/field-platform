"""G18: the Stage 1 clean window is evaluated mechanically from two /health reads and fails closed.

The window rule is the stage controller's own (``_increases``); these tests pin what the new module adds: a whole-window
verdict from two snapshots, fail-closed handling, the optional minimum length, and the gate record a clean window leaves.
Every value is made up."""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[0]))

import stage1_window as sw  # noqa: E402

SHA = "ab12cd34" * 5


def healthy(service, **over):
    return {"service": service, "build_sha": SHA, **over}


class FakeEstate:
    """A stdlib HTTP server answering GET /<prefix>/health with the given bodies (a default body per service)."""

    def __init__(self, overrides=None):
        self.overrides = overrides or {}
        self.requests: list[tuple[str, str, bool]] = []
        est = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _serve(self):
                est.requests.append((self.command, self.path, "x-field-auth" in self.headers))
                for _label, path, service in sw.OPERATOR_BLOCK_SERVICES:
                    if self.path == path:
                        data = json.dumps(est.overrides.get(path, healthy(service))).encode()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                        return
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _serve

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


SERVICES = [label for label, _p, _s in sw.OPERATOR_BLOCK_SERVICES]
U, R = sw.sc.COUNTER_KEYS


def snap(t, **per):
    counters = {s: {U: 0, R: 0} for s in SERVICES}
    for s, over in per.items():
        counters[s] = {**counters[s], **over}
    return {"taken_at": t, "counters": counters}


def ev(before, after, min_hours=0.0):
    """The evaluation with the window length made explicit (the default of 24 hours has its own tests below)."""
    return sw.evaluate_window(before, after, min_hours=min_hours)


def test_equal_counters_over_a_forward_window_are_clean():
    assert ev(snap(100), snap(200)) == []


@pytest.mark.parametrize("key,word", [(U, "dropped_unauth_increase"), (R, "dropped_refused_increase")])
def test_an_increase_in_either_counter_on_any_service_fails_the_window(key, word):
    problems = ev(snap(100), snap(200, killswitch={key: 1}))
    assert word in problems


@pytest.mark.parametrize("key", [U, R])
def test_a_counter_that_goes_down_is_not_clean_because_it_is_a_restart(key):
    problems = ev(snap(0, ledger={key: 5}), snap(10 * 3600, ledger={key: 2}))
    assert f"ledger: {key} went down: the service restarted, the window cannot be judged" in problems


def test_before_5_3_after_0_0_ten_hours_apart_on_every_service_is_not_clean():
    before = snap(0, **{s: {U: 5, R: 3} for s in SERVICES})
    problems = ev(before, snap(10 * 3600), min_hours=1)
    assert len([p for p in problems if "went down" in p]) == 2 * len(SERVICES)


def test_equal_nonzero_counters_are_clean_and_only_a_decrease_is_refused():
    assert ev(snap(0, ledger={U: 5, R: 3}), snap(10, ledger={U: 5, R: 3})) == []
    assert ev(snap(0, ledger={U: 5}), snap(10, ledger={U: 6})) == ["dropped_unauth_increase"]


@pytest.mark.parametrize("bad", [None, "7", True, 1.5, [1]], ids=["null", "str", "bool", "float", "list"])
def test_a_counter_that_is_missing_or_not_an_integer_fails_closed(bad):
    after = snap(200)
    after["counters"]["registry"][U] = bad
    assert ev(snap(100), after) != []
    before = snap(100)
    before["counters"]["registry"][R] = bad
    assert ev(before, snap(200)) != []


def test_a_counter_key_absent_or_a_service_missing_from_after_fails_closed():
    after = snap(200)
    del after["counters"]["governor"][R]
    assert ev(snap(100), after) != []
    after = snap(200)
    del after["counters"]["lifecycle"]
    assert "health_failure" in ev(snap(100), after)


@pytest.mark.parametrize("before,after", [({}, snap(200)), (snap(100), {}), ("x", snap(200)), (snap(100), None),
                                          ({"taken_at": 1, "counters": {}}, snap(200))],
                         ids=["empty-before", "empty-after", "str", "none", "no-services"])
def test_an_empty_or_malformed_snapshot_is_not_clean(before, after):
    assert ev(before, after) != []


@pytest.mark.parametrize("t0,t1", [(200, 100), (100, 100), (None, 100), (100, "x"), (True, 100)])
def test_a_window_that_does_not_run_forward_is_not_clean(t0, t1):
    before, after = snap(0), snap(0)
    before["taken_at"], after["taken_at"] = t0, t1
    assert "the window does not run forward in time" in ev(before, after)


def test_the_default_minimum_window_is_24_hours_not_zero():
    assert sw.DEFAULT_MIN_HOURS == 24.0
    assert sw.evaluate_window(snap(0), snap(1)) != []                               # no flag, one second: not clean
    assert sw.evaluate_window(snap(0), snap(23 * 3600)) != []
    assert sw.evaluate_window(snap(0), snap(24 * 3600)) == []


def test_a_window_shorter_than_the_minimum_is_not_clean_and_a_long_one_is():
    assert ev(snap(0), snap(3600), min_hours=2) != []
    assert ev(snap(0), snap(2 * 3600), min_hours=2) == []


def write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_a_clean_window_records_gate_g18_bound_to_the_sha_and_a_dirty_one_writes_nothing(tmp_path, capsys):
    b, a = write(tmp_path, "b.json", snap(0)), write(tmp_path, "a.json", snap(30 * 3600))
    rec = tmp_path / "records.jsonl"
    sha = "ab12cd34" * 5
    assert sw.main(["evaluate", "--before", b, "--after", a, "--records", str(rec), "--build-sha", sha]) == 0
    rows = [json.loads(line) for line in rec.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and rows[0]["kind"] == "gate" and rows[0]["gate"] == "G18" and rows[0]["ok"] is True
    assert rows[0]["sha8"] == sw.sc.sha8_of(sha)
    assert rows[0]["window_hours"] == 30.0 and rows[0]["services"] == len(SERVICES)       # what was judged is in the row
    assert sw.sc.Records(rec).gate_ok("G18", sw.sc.sha8_of(sha))
    dirty = write(tmp_path, "d.json", snap(30 * 3600, ledger={R: 1}))
    rec2 = tmp_path / "records2.jsonl"
    assert sw.main(["evaluate", "--before", b, "--after", dirty, "--records", str(rec2)]) == 1
    assert not rec2.exists()
    assert "NOT clean" in capsys.readouterr().out


def test_a_one_second_window_with_no_min_hours_flag_is_not_clean_and_writes_no_row(tmp_path, capsys):
    b, a = write(tmp_path, "b.json", snap(0)), write(tmp_path, "a.json", snap(1))
    rec = tmp_path / "records.jsonl"
    assert sw.main(["evaluate", "--before", b, "--after", a, "--records", str(rec), "--build-sha", "abcdef1234"]) == 1
    assert not rec.exists()
    assert "shorter than 24 hour(s)" in capsys.readouterr().out


def test_a_restart_in_the_window_fails_the_cli_and_writes_no_row(tmp_path, capsys):
    b = write(tmp_path, "b.json", snap(0, **{s: {U: 5, R: 3} for s in SERVICES}))
    a = write(tmp_path, "a.json", snap(10 * 3600))
    rec = tmp_path / "records.jsonl"
    assert sw.main(["evaluate", "--before", b, "--after", a, "--records", str(rec), "--min-hours", "1"]) == 1
    assert not rec.exists() and "went down" in capsys.readouterr().out


def test_usage_errors_exit_2(tmp_path, capsys):
    b = write(tmp_path, "b.json", snap(0))
    assert sw.main(["evaluate", "--before", b, "--after", str(tmp_path / "missing.json")]) == 2
    assert sw.main(["evaluate", "--before", b, "--after", b, "--build-sha", "ab" * 20]) == 2     # sha without records
    assert sw.main(["evaluate", "--before", b, "--after", b, "--min-hours", "-1"]) == 2


def test_snapshot_reads_health_only_and_unreadable_counters_become_null(tmp_path, capsys):
    over = {
        "/registry/health": healthy("agent-registry", dropped_unauthenticated_records=3, dropped_refused_records=1),
        "/ledger/health": healthy("sealed-ledger", dropped_unauthenticated_records="7", dropped_refused_records=0),
    }
    e = FakeEstate(overrides=over)
    try:
        out = tmp_path / "s.json"
        assert sw.main(["snapshot", "--base", e.base, "--out", str(out)]) == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["counters"]["registry"] == {U: 3, R: 1}
        assert data["counters"]["ledger"] == {U: None, R: 0}              # a string is not a count
        assert data["counters"]["killswitch"] == {U: None, R: None}       # the fake carries no counters
        assert {m for m, _, _ in e.requests} == {"GET"} and not any(auth for _, _, auth in e.requests)
        assert ev(data, data) != []                         # null counters cannot be judged
    finally:
        e.close()
    assert "not readable" in capsys.readouterr().out


def test_a_service_answering_under_another_services_name_is_not_read_as_that_service(tmp_path):
    """W8: the answer's ``service`` must be the one the path belongs to; otherwise another service's counters count."""
    over = {"/registry/health": healthy("sealed-ledger", dropped_unauthenticated_records=0, dropped_refused_records=0)}
    e = FakeEstate(overrides=over)
    try:
        data = sw.read_snapshot(sw.ep.Estate(e.base, None))
    finally:
        e.close()
    assert data["counters"]["registry"] == {U: None, R: None}


def test_the_snapshot_sends_no_credential_even_when_the_estate_object_holds_one():
    """W12: /health is read without the shared secret. The estate object here HAS a secret, so only ``auth=False`` in
    the snapshot keeps it off the wire."""
    e = FakeEstate()
    try:
        sw.read_snapshot(sw.ep.Estate(e.base, "a-test-secret-not-a-real-one"))
        assert len(e.requests) == len(SERVICES) and not any(auth for _, _, auth in e.requests)
        assert sw.ep.Estate(e.base, "a-test-secret-not-a-real-one").authenticated     # the secret was in play
    finally:
        e.close()


# ---- R-PR837-3a435b7 conditions C1 and C2 -------------------------------------------------------------------------------

def _only(*labels, t):
    """A snapshot that holds only the given service labels."""
    full = snap(t)
    return {"taken_at": t, "counters": {k: v for k, v in full["counters"].items() if k in labels}}


def test_the_required_labels_are_the_eight_operator_block_services():
    assert len(sw.REQUIRED_LABELS) == 8 and list(sw.REQUIRED_LABELS) == SERVICES


def test_two_one_service_snapshots_are_not_a_clean_window_c1():
    """C1: a pair of snapshots that hold one service each used to produce a clean-window record."""
    problems = ev(_only("registry", t=0), _only("registry", t=30 * 3600))
    assert problems != []
    for label in SERVICES:
        if label != "registry":
            assert f"{label}: missing from the before snapshot" in problems
            assert f"{label}: missing from the after snapshot" in problems


@pytest.mark.parametrize("label", SERVICES)
@pytest.mark.parametrize("side", ["before", "after"])
def test_a_missing_label_on_either_side_names_the_label_and_the_side_c1(label, side):
    b, a = snap(0), snap(30 * 3600)
    del (b if side == "before" else a)["counters"][label]
    assert f"{label}: missing from the {side} snapshot" in ev(b, a)


def test_the_cli_writes_no_row_for_one_service_snapshots_c1(tmp_path, capsys):
    b, a = write(tmp_path, "b.json", _only("ledger", t=0)), write(tmp_path, "a.json", _only("ledger", t=30 * 3600))
    rec = tmp_path / "records.jsonl"
    assert sw.main(["evaluate", "--before", b, "--after", a, "--records", str(rec)]) == 1
    assert not rec.exists() and "NOT clean" in capsys.readouterr().out


def test_a_window_that_ends_in_the_future_is_not_clean_c2():
    now = 1_000_000.0
    assert sw.evaluate_window(snap(now - 40 * 3600), snap(now - 10), min_hours=24, now=now) == []
    assert "the window ends in the future" in sw.evaluate_window(snap(now - 10), snap(now + 40 * 3600), min_hours=24, now=now)
    # a little clock skew is tolerated, an hour is not
    assert sw.evaluate_window(snap(now - 40 * 3600), snap(now + 60), min_hours=24, now=now) == []
    assert sw.evaluate_window(snap(now - 40 * 3600), snap(now + 3600), min_hours=24, now=now) != []


def test_the_record_row_carries_the_window_end_c2(tmp_path):
    t1 = 30 * 3600 + 7
    b, a = write(tmp_path, "b.json", snap(0)), write(tmp_path, "a.json", snap(t1))
    rec = tmp_path / "records.jsonl"
    assert sw.main(["evaluate", "--before", b, "--after", a, "--records", str(rec)]) == 0
    row = json.loads(rec.read_text(encoding="utf-8").splitlines()[0])
    assert row["window_end"] == t1 and row["window_hours"] == round(t1 / 3600, 2)


# ---- R-PR837-c972adf C1 and reviewer-7 N1/N2: a non-finite number is never a clean window ---------------------------------

NAN, INF = float("nan"), float("inf")


@pytest.mark.parametrize("bad", [NAN, INF, -INF], ids=["nan", "inf", "-inf"])
@pytest.mark.parametrize("side", ["before", "after"])
def test_a_non_finite_taken_at_in_either_snapshot_is_not_clean(bad, side):
    b, a = snap(0), snap(100 * 3600)
    (b if side == "before" else a)["taken_at"] = bad
    problems = ev(b, a)
    assert problems and "a snapshot's taken_at is not a finite number" in problems


@pytest.mark.parametrize("bad", [NAN, INF, -INF], ids=["nan", "inf", "-inf"])
@pytest.mark.parametrize("min_hours", [0.0, 24.0])
def test_a_non_finite_min_hours_is_not_clean_even_over_a_long_window(bad, min_hours):
    problems = sw.evaluate_window(snap(0), snap(100 * 3600), min_hours=bad)
    assert "the minimum window length is not a finite number" in problems
    assert sw.evaluate_window(snap(0), snap(100 * 3600), min_hours=min_hours) == []     # the control: finite is clean


def test_the_cli_refuses_nan_and_inf_min_hours_with_exit_2_and_writes_no_row(tmp_path, capsys):
    b, a = write(tmp_path, "b.json", snap(0)), write(tmp_path, "a.json", snap(100 * 3600))
    rec = tmp_path / "records.jsonl"
    for bad in ("nan", "inf", "-inf", "NaN", "Infinity"):
        assert sw.main(["evaluate", "--before", b, "--after", a, "--records", str(rec), f"--min-hours={bad}"]) == 2
        assert "finite" in capsys.readouterr().out
    assert not rec.exists()


@pytest.mark.parametrize("which", ["before", "after"])
@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_a_snapshot_file_holding_a_non_finite_taken_at_fails_the_cli_and_writes_no_row(tmp_path, capsys, which, literal):
    b, a = write(tmp_path, "b.json", snap(0)), write(tmp_path, "a.json", snap(100 * 3600))
    target = Path(b if which == "before" else a)
    target.write_text(target.read_text(encoding="utf-8").replace(
        f'"taken_at": {json.loads(target.read_text(encoding="utf-8"))["taken_at"]}', f'"taken_at": {literal}'), encoding="utf-8")
    assert literal in target.read_text(encoding="utf-8")                  # the file really holds the literal
    rec = tmp_path / "records.jsonl"
    assert sw.main(["evaluate", "--before", b, "--after", a, "--records", str(rec), "--min-hours", "1"]) == 1
    assert not rec.exists()
    assert "not a finite number" in capsys.readouterr().out


def test_a_finite_window_is_unchanged_and_still_records(tmp_path, capsys):
    b, a = write(tmp_path, "b.json", snap(0)), write(tmp_path, "a.json", snap(100 * 3600))
    rec = tmp_path / "records.jsonl"
    assert sw.main(["evaluate", "--before", b, "--after", a, "--records", str(rec), "--min-hours", "24"]) == 0
    assert rec.exists()
