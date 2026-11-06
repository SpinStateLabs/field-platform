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


def test_equal_counters_over_a_forward_window_are_clean():
    assert sw.evaluate_window(snap(100), snap(200)) == []


@pytest.mark.parametrize("key,word", [(U, "dropped_unauth_increase"), (R, "dropped_refused_increase")])
def test_an_increase_in_either_counter_on_any_service_fails_the_window(key, word):
    problems = sw.evaluate_window(snap(100), snap(200, killswitch={key: 1}))
    assert word in problems


def test_a_decrease_is_not_an_increase():
    assert sw.evaluate_window(snap(100, ledger={U: 5}), snap(200, ledger={U: 2})) == []


@pytest.mark.parametrize("bad", [None, "7", True, 1.5, [1]], ids=["null", "str", "bool", "float", "list"])
def test_a_counter_that_is_missing_or_not_an_integer_fails_closed(bad):
    after = snap(200)
    after["counters"]["registry"][U] = bad
    assert sw.evaluate_window(snap(100), after) != []
    before = snap(100)
    before["counters"]["registry"][R] = bad
    assert sw.evaluate_window(before, snap(200)) != []


def test_a_counter_key_absent_or_a_service_missing_from_after_fails_closed():
    after = snap(200)
    del after["counters"]["governor"][R]
    assert sw.evaluate_window(snap(100), after) != []
    after = snap(200)
    del after["counters"]["lifecycle"]
    assert "health_failure" in sw.evaluate_window(snap(100), after)


@pytest.mark.parametrize("before,after", [({}, snap(200)), (snap(100), {}), ("x", snap(200)), (snap(100), None),
                                          ({"taken_at": 1, "counters": {}}, snap(200))],
                         ids=["empty-before", "empty-after", "str", "none", "no-services"])
def test_an_empty_or_malformed_snapshot_is_not_clean(before, after):
    assert sw.evaluate_window(before, after) != []


@pytest.mark.parametrize("t0,t1", [(200, 100), (100, 100), (None, 100), (100, "x"), (True, 100)])
def test_a_window_that_does_not_run_forward_is_not_clean(t0, t1):
    before, after = snap(0), snap(0)
    before["taken_at"], after["taken_at"] = t0, t1
    assert "the window does not run forward in time" in sw.evaluate_window(before, after)


def test_a_window_shorter_than_the_minimum_is_not_clean_and_a_long_one_is():
    assert sw.evaluate_window(snap(0), snap(3600), min_hours=2) != []
    assert sw.evaluate_window(snap(0), snap(2 * 3600), min_hours=2) == []


def write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_a_clean_window_records_gate_g18_bound_to_the_sha_and_a_dirty_one_writes_nothing(tmp_path, capsys):
    b, a = write(tmp_path, "b.json", snap(0)), write(tmp_path, "a.json", snap(10))
    rec = tmp_path / "records.jsonl"
    sha = "ab12cd34" * 5
    assert sw.main(["evaluate", "--before", b, "--after", a, "--records", str(rec), "--build-sha", sha]) == 0
    rows = [json.loads(line) for line in rec.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and rows[0]["kind"] == "gate" and rows[0]["gate"] == "G18" and rows[0]["ok"] is True
    assert rows[0]["sha8"] == sw.sc.sha8_of(sha)
    assert sw.sc.Records(rec).gate_ok("G18", sw.sc.sha8_of(sha))
    dirty = write(tmp_path, "d.json", snap(10, ledger={R: 1}))
    rec2 = tmp_path / "records2.jsonl"
    assert sw.main(["evaluate", "--before", b, "--after", dirty, "--records", str(rec2)]) == 1
    assert not rec2.exists()
    assert "NOT clean" in capsys.readouterr().out


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
        assert sw.evaluate_window(data, data) != []                         # null counters cannot be judged
    finally:
        e.close()
    assert "not readable" in capsys.readouterr().out
