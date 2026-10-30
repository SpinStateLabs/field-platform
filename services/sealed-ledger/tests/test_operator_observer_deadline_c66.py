"""C-66 (reviewer C-64 finding 1, MEDIUM, proven by mutants on PR 45): unit tests that pin the deadline
primitives of the observer's own HTTP fetch, which the end-to-end tests exercise only coarsely:

* ``_DeadlineStream._left``: once the deadline has passed (left <= 0, including exactly 0) the next socket
  operation raises instead of waiting; otherwise the time left is capped by the caller's timeout;
* ``_resolve``: a lookup still running at the deadline is abandoned (ConnectTimeout), an empty answer and a
  lookup that raised are both a ConnectError that names the class only, and a good answer is returned.

No network: ``socket.getaddrinfo`` and ``time.monotonic`` are replaced."""

from __future__ import annotations

import socket
import time

import httpcore
import pytest

from sealed_ledger import operator_observer as ob


def _stream(deadline):
    return ob._DeadlineStream(None, deadline)


def test_left_is_the_time_to_the_deadline_capped_by_the_callers_timeout(monkeypatch):
    monkeypatch.setattr(ob.time, "monotonic", lambda: 100.0)
    assert _stream(105.0)._left(None) == 5.0
    assert _stream(105.0)._left(2.0) == 2.0          # the caller's smaller timeout wins
    assert _stream(105.0)._left(9.0) == 5.0          # the deadline wins over a larger timeout


@pytest.mark.parametrize("deadline", [100.0, 99.999, 50.0])
def test_a_deadline_at_or_before_now_raises_instead_of_waiting(monkeypatch, deadline):
    """Exactly equal (left == 0) must raise: a read given a zero timeout is not 'time left'."""
    monkeypatch.setattr(ob.time, "monotonic", lambda: 100.0)
    with pytest.raises(httpcore.ReadTimeout):
        _stream(deadline)._left(None)
    with pytest.raises(httpcore.ReadTimeout):
        _stream(deadline)._left(3.0)


def test_one_tick_before_the_deadline_still_has_time(monkeypatch):
    monkeypatch.setattr(ob.time, "monotonic", lambda: 100.0)
    assert _stream(100.001)._left(None) == pytest.approx(0.001)


def test_a_good_lookup_is_returned(monkeypatch):
    addrs = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 8002))]
    monkeypatch.setattr(ob.socket, "getaddrinfo", lambda *a, **k: addrs)
    assert ob._resolve("ledger", 8002, 1.0) == addrs


def test_an_empty_lookup_is_a_connect_error(monkeypatch):
    monkeypatch.setattr(ob.socket, "getaddrinfo", lambda *a, **k: [])
    with pytest.raises(httpcore.ConnectError) as e:
        ob._resolve("ledger", 8002, 1.0)
    assert "name resolution failed" in str(e.value)


def test_a_failed_lookup_is_a_connect_error_naming_the_class_only(monkeypatch):
    def boom(*a, **k):
        raise socket.gaierror("Name or service not known: secret-host.invalid")

    monkeypatch.setattr(ob.socket, "getaddrinfo", boom)
    with pytest.raises(httpcore.ConnectError) as e:
        ob._resolve("secret-host.invalid", 8002, 1.0)
    assert "gaierror" in str(e.value)
    assert "secret-host" not in str(e.value)


def test_a_lookup_still_running_at_the_deadline_is_abandoned(monkeypatch):
    def slow(*a, **k):
        time.sleep(1.5)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 8002))]

    monkeypatch.setattr(ob.socket, "getaddrinfo", slow)
    t0 = time.monotonic()
    with pytest.raises(httpcore.ConnectTimeout):
        ob._resolve("ledger", 8002, 0.2)
    assert time.monotonic() - t0 < 1.0               # returned at the deadline, not when the lookup ended
