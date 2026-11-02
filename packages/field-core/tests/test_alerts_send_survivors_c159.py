"""C-159 (reviewer R-22 F-R22-2, PR 59): survivors in the alert send path.

* ``_post_once`` decides which failures are retried: a timeout or a network error is retryable, an HTTP
  400 is not, a 429 and 5xx are (``_RETRY_STATUSES``); the status line is all that is used.
* ``_shut_down`` closes a connection past its deadline (best effort, one failure does not stop the next).
* ``render`` carries the ``sent:`` line, and the defence-in-depth content check on the title, tags and body
  withholds each with its own label; the tags are checked joined with a comma.

A fake opener stands in for the network; nothing is sent."""

from __future__ import annotations

import http.client
import socket
import urllib.error

import pytest

from field_core import alerts


class _Opener:
    def __init__(self, *, status=None, exc=None):
        self.status, self.exc = status, exc

    def open(self, req, timeout=None):
        if self.exc is not None:
            raise self.exc
        return _Resp(self.status)


class _Resp:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _post(opener):
    return alerts._post_once(object(), 1.0, opener)


class _Body:
    def close(self):
        pass


def _http_error(code):
    return urllib.error.HTTPError("http://x/", code, "m", {}, _Body())


@pytest.mark.parametrize("exc,want", [
    (urllib.error.URLError(socket.timeout()), (False, "timeout", None, True)),
    (urllib.error.URLError(TimeoutError()), (False, "timeout", None, True)),
    (urllib.error.URLError(ConnectionRefusedError()), (False, "network", None, True)),
    (urllib.error.URLError("no route"), (False, "network", None, True)),
    (TimeoutError(), (False, "timeout", None, True)),
    (socket.timeout(), (False, "timeout", None, True)),
    (ConnectionResetError(), (False, "network", None, True)),
    (http.client.RemoteDisconnected("x"), (False, "network", None, True)),
])
def test_a_timeout_or_network_failure_is_retryable(exc, want):
    assert _post(_Opener(exc=exc)) == want


@pytest.mark.parametrize("code,retry", [
    (400, False), (401, False), (403, False), (404, False), (408, False), (413, False), (499, False),
    (429, True), (500, True), (502, True), (503, True), (599, True),
    (600, False),
])
def test_an_http_error_is_retryable_only_for_429_and_5xx(code, retry):
    assert _post(_Opener(exc=_http_error(code))) == (False, f"http_{code}", code, retry)


@pytest.mark.parametrize("status", [199, 300, 302, 400, 429, 500])
def test_a_non_2xx_status_line_is_a_failure_with_the_same_retry_rule(status):
    ok, reason, st, retry = _post(_Opener(status=status))
    assert (ok, reason, st) == (False, f"http_{status}", status)
    assert retry is (status in alerts._RETRY_STATUSES)


@pytest.mark.parametrize("status", [200, 201, 204, 299])
def test_a_2xx_status_line_is_delivery(status):
    assert _post(_Opener(status=status)) == (True, None, status, False)


def test_an_http_error_is_closed():
    closed = []

    class _B:
        def close(self):
            closed.append(1)

    _post(_Opener(exc=urllib.error.HTTPError("http://x/", 500, "m", {}, _B())))
    assert closed == [1]


class _Sock:
    def __init__(self, boom=False):
        self.shut, self.boom = [], boom

    def shutdown(self, how):
        self.shut.append(how)
        if self.boom:
            raise OSError("already closed")


class _Conn:
    def __init__(self, sock=None, boom=False):
        self.sock, self.closed, self.boom = sock, 0, boom

    def close(self):
        self.closed += 1
        if self.boom:
            raise OSError("boom")


def test_shut_down_closes_every_connection_and_shuts_its_socket():
    s1, s2 = _Sock(), _Sock()
    c1, c2, c3 = _Conn(s1), _Conn(s2), _Conn(None)
    alerts._shut_down([c1, c2, c3])
    assert (c1.closed, c2.closed, c3.closed) == (1, 1, 1)
    assert s1.shut == [socket.SHUT_RDWR] and s2.shut == [socket.SHUT_RDWR]


def test_shut_down_is_best_effort_one_failure_does_not_stop_the_rest():
    bad = _Conn(_Sock(boom=True), boom=True)
    good = _Conn(_Sock())
    alerts._shut_down([bad, good])
    assert bad.closed == 1 and good.closed == 1 and good.sock.shut == [socket.SHUT_RDWR]


def test_the_body_carries_a_sent_line_with_the_given_time():
    _, body, _, _ = alerts.render("test", estate="gb10", sent_at="2026-10-30T12:00:00Z")
    assert body.splitlines()[-1] == "sent: 2026-10-30T12:00:00Z"


def test_the_body_without_a_time_still_carries_a_sent_line():
    _, body, _, _ = alerts.render("test", estate="gb10")
    assert body.splitlines()[-1].startswith("sent: ") and len(body.splitlines()[-1]) > len("sent: ")


def _custom(monkeypatch, *, title="T", tags=("field",), summary="S"):
    monkeypatch.setitem(alerts.CLASSES, "c159", alerts.AlertClass("c159", 3, tags, title, summary))


def test_a_secret_in_the_tags_is_withheld_and_labelled(monkeypatch):
    _custom(monkeypatch, tags=("topicsecret",))
    title, body, tags, withheld = alerts.render("c159", estate="gb10", secrets_=("topicsecret",))
    assert tags == ("field",) and "tags" in withheld


def test_the_tags_are_checked_joined_with_a_comma(monkeypatch):
    """A secret that only exists across the comma join of two tags is still caught: the check is on
    the comma join of the tags, not on each tag alone or on a different separator."""
    _custom(monkeypatch, tags=("abcsecret", "defsecret"))
    _, _, tags, withheld = alerts.render("c159", estate="gb10", secrets_=("abcsecret,defsecret",))
    assert tags == ("field",) and "tags" in withheld


def test_a_secret_in_the_title_is_withheld_and_labelled(monkeypatch):
    _custom(monkeypatch, title="titlesecret")
    title, _, _, withheld = alerts.render("c159", estate="gb10", secrets_=("titlesecret",))
    assert title == "FIELD alert: c159" and "title" in withheld


def test_a_secret_in_the_body_template_is_withheld_and_labelled(monkeypatch):
    _custom(monkeypatch, summary="bodysecret")
    _, body, _, withheld = alerts.render("c159", estate="gb10", secrets_=("bodysecret",))
    assert body.startswith("FIELD alert: c159\n(body withheld") and "body" in withheld


def test_clean_tags_are_left_alone(monkeypatch):
    _custom(monkeypatch, tags=("rotating_light", "key"))
    _, _, tags, withheld = alerts.render("c159", estate="gb10", secrets_=("zzz",))
    assert tags == ("rotating_light", "key") and "tags" not in withheld
