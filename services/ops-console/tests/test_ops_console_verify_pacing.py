"""The console's whole-chain check is paced: one check per interval however many overviews are built, a "busy" answer
is waited out as the ledger asks and shown as "busy, retrying", and a hidden page asks for nothing.

The page half needs node + npm (jsdom is cached by test_setup_behaviour's fixture): skipped when unavailable, a
failure when CI=true.
"""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from ops_console.api import ServiceClient, create_app
from ops_console.verify_pacer import BUSY, VerifyPacer

from test_setup_behaviour import HTML_PATH, jsdom_dir  # noqa: F401  (fixture)

HARNESS = Path(__file__).parent / "verify_pacing_harness.mjs"
INTACT = {"ok": True, "length": 3}
BROKEN = {"ok": False, "length": 3, "reason": "hash mismatch"}


def ok(body=INTACT):
    return httpx.Response(200, json=body)


def busy(retry_after):
    return httpx.Response(503, headers={"Retry-After": retry_after}, json={"detail": "ledger busy"})


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now


class Estate:
    """A console whose ledger answers ``/verify`` with ``answers`` in order (the last one repeats)."""

    def __init__(self, *answers):
        self.answers, self.checks = list(answers), 0

        def handle(request):
            if request.url.path != "/verify":
                return httpx.Response(200, json=[])
            self.checks += 1
            return self.answers[min(self.checks, len(self.answers)) - 1]

        upstream = ServiceClient(client=httpx.Client(transport=httpx.MockTransport(handle), base_url="http://t"),
                                 base_url="http://t")
        app = create_app(registry=upstream, ledger=upstream, delegation=upstream, governor=upstream,
                         stream_interval=0.01, stream_keepalive=0.0)
        self.clock = Clock()
        app.state.verify_pacer.clock = self.clock
        self.client = TestClient(app)

    def at(self, seconds):
        """The ``ledger_verify`` section of an overview built ``seconds`` after the start."""
        self.clock.now = 1000.0 + seconds
        return self.client.get("/api/overview").json()["ledger_verify"]


def test_overviews_and_streams_share_one_check_per_interval():
    estate = Estate(ok())
    for _ in range(5):
        assert estate.at(0) == {"available": True, "source": "GET /verify", "data": INTACT, "error": None}
    with estate.client.stream("GET", "/api/stream", params={"frames": 3}) as r:
        "".join(r.iter_text())
    estate.at(29.9)
    assert estate.checks == 1
    estate.at(30)
    assert estate.checks == 2


def test_a_busy_answer_is_shown_as_busy_and_not_as_an_error():
    estate = Estate(busy("5"))
    assert estate.at(0) == {"available": False, "source": "GET /verify", "data": None, "error": "busy, retrying"}
    assert estate.checks == 1                      # no second request for the same overview


def test_a_busy_answer_is_not_asked_again_before_its_retry_after():
    estate = Estate(busy("120"), ok())
    for seconds in (0, 1, 30, 60, 119.9):
        assert estate.at(seconds)["error"] == BUSY
    assert estate.checks == 1
    assert estate.at(120)["data"] == INTACT
    assert estate.checks == 2


def test_a_short_retry_after_does_not_shorten_the_interval():
    estate = Estate(busy("5"), ok())
    for seconds in (0, 5, 29.9):
        estate.at(seconds)
    assert estate.checks == 1
    assert estate.at(30)["available"] is True and estate.checks == 2


@pytest.mark.parametrize("value,wait", [("soon", 30), ("-5", 30), ("nan", 30), ("1000000000", 300), ("inf", 300)])
def test_an_odd_retry_after_waits_a_bounded_time(value, wait):
    estate = Estate(busy(value), ok())
    estate.at(0)
    assert estate.at(wait - 0.1)["error"] == BUSY and estate.checks == 1
    estate.at(wait)
    assert estate.checks == 2


@pytest.mark.parametrize("last", [INTACT, BROKEN])
def test_busy_keeps_the_last_result_beside_it(last):
    estate = Estate(ok(last), busy("5"))
    estate.at(0)
    assert estate.at(30) == {"available": False, "source": "GET /verify", "data": last, "error": BUSY}


def test_a_503_without_retry_after_is_an_error_and_is_paced_too():
    estate = Estate(httpx.Response(503, json={"detail": "x"}), ok())
    assert estate.at(0)["error"] == "status 503: upstream error"
    estate.at(29.9)
    assert estate.checks == 1
    assert estate.at(30)["available"] is True


def test_callers_arriving_during_a_check_do_not_start_another():
    pacer, reading, release, calls = VerifyPacer(), threading.Event(), threading.Event(), []

    def read():
        calls.append(1)
        reading.set()
        assert release.wait(10)
        return 200, INTACT, None

    answers = []
    threads = [threading.Thread(target=lambda: answers.append(pacer.answer(read, str))) for _ in range(4)]
    threads[0].start()
    assert reading.wait(10)
    for t in threads[1:]:
        t.start()
    release.set()
    for t in threads:
        t.join(10)
    assert len(calls) == 1 and [a["data"] for a in answers] == [INTACT] * 4


def test_a_caller_during_a_later_check_gets_the_last_answer_without_waiting():
    clock = Clock()
    pacer, reading, release = VerifyPacer(clock=clock), threading.Event(), threading.Event()
    pacer.answer(lambda: (200, INTACT, None), str)
    clock.now += 30                                    # the next check is due

    def slow():
        reading.set()
        assert release.wait(10)
        return 200, BROKEN, None

    def never():
        raise AssertionError("a second check was started")

    first, second = [], []
    checker = threading.Thread(target=lambda: first.append(pacer.answer(slow, str)))
    checker.start()
    assert reading.wait(10)
    other = threading.Thread(target=lambda: second.append(pacer.answer(never, str)))
    other.start()
    other.join(5)
    returned_while_checking = not other.is_alive()
    release.set()
    checker.join(10)
    other.join(10)
    assert returned_while_checking, "the caller waited for the running check"
    assert second == [{"available": True, "data": INTACT, "error": None}]
    assert first[0]["data"] == BROKEN
    assert pacer.answer(never, str)["data"] == BROKEN  # the finished check's answer from then on


@pytest.fixture(scope="module")
def seen(jsdom_dir) -> dict:
    p = subprocess.run(["node", str(HARNESS), str(jsdom_dir), str(HTML_PATH)], capture_output=True, text=True,
                       encoding="utf-8", timeout=120)
    assert p.returncode == 0, p.stderr[-800:]
    return json.loads(p.stdout.strip().splitlines()[-1])


def test_a_hidden_page_asks_for_nothing(seen):
    nothing = {"overview": 0, "platform": 0, "streams": 0, "open": 0}
    assert seen["hiddenAtLoad"] == nothing and seen["hiddenAfterPoll"] == nothing
    assert seen["hiddenRequests"] == 0 and seen["askedWhileHiddenAgain"] == 0


def test_the_page_asks_while_visible_and_stops_when_hidden(seen):
    assert seen["visibleAtLoad"] == {"overview": 1, "platform": 1, "streams": 1, "open": 1}
    assert seen["visibleAfterPoll"]["platform"] == 2             # the strip is polled while visible
    assert seen["shown"] == {"overview": 1, "platform": 1, "streams": 1, "open": 1}
    assert seen["hiddenAgain"] == {"overview": 1, "platform": 1, "streams": 1, "open": 0}
    assert seen["shownAgain"] == {"overview": 2, "platform": 2, "streams": 2, "open": 1}


def test_the_integrity_tile_says_busy_retrying(seen):
    tiles = seen["tiles"]
    assert tiles["busy"] == {"text": "LEDGER: busy, retrying", "cls": "UNKNOWN"}
    assert tiles["busyAfterIntact"] == {"text": "LEDGER: busy, retrying (last: INTACT 7)", "cls": "UNKNOWN"}
    assert tiles["busyAfterBroken"]["cls"] == "BROKEN"
    assert tiles["busyAfterBroken"]["text"].endswith("hash mismatch (busy, retrying)")
    assert tiles["error"]["text"] == "LEDGER: UNREACHABLE"
    assert tiles["intact"] == {"text": "LEDGER: INTACT (9)", "cls": "INTACT"}
