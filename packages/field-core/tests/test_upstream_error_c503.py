"""C-503 (design note C-490): a reply from another service never becomes part of an exception message.

`field_core.errors.upstream_error` returns a fixed phrase and the status code; the body (first 200 characters, escaped,
one line) goes to a DEBUG record. Every client that used to copy `resp.text` into its error is exercised against an
upstream that answers 500 with a made-up marker plus a very long body.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from field_core.clients import (AgentNotRegisteredError, LedgerClient, LedgerUnreachableError, RegistryClient,
                                RegistryUnreachableError)
from field_core.errors import BODY_LOG_LIMIT, upstream_error

MARK = "CANARY-8f31-zq"          # made up; stands in for a value an upstream echoes back
BIG = MARK + "x" * 5000


class Resp:
    def __init__(self, status: int, text: str = BIG):
        self.status_code = status
        self.text = text

    def json(self):
        raise AssertionError("a failed reply must not be parsed")


class Upstream:
    """Answers every request with one fixed reply (the HttpLike the clients take)."""

    def __init__(self, status: int = 500, text: str = BIG):
        self.reply = Resp(status, text)

    def post(self, url, **kw):
        return self.reply

    get = patch = post


def chain(exc: BaseException):
    """The exception and everything it carries: __cause__ and __context__, recursively."""
    seen, todo = [], [exc]
    while todo:
        e = todo.pop()
        if e is None or any(e is x for x in seen):
            continue
        seen.append(e)
        todo += [e.__cause__, e.__context__]
    return seen


def assert_no_body(exc: BaseException) -> None:
    """The marker and the long body are on none of: str, repr, args, attributes, the cause or the context chain."""
    for e in chain(exc):
        surfaces = [str(e), repr(e), repr(e.args), repr(getattr(e, "__dict__", {}))]
        for text in surfaces:
            assert MARK not in text and "x" * 200 not in text, (type(e).__name__, text[:120])


def _clean(message: str, status: int, what: str, exc: BaseException | None = None) -> None:
    assert message == f"{what} returned {status}", message
    assert MARK not in message and len(message) < 80
    if exc is not None:
        assert_no_body(exc)


# ---- the helper ---------------------------------------------------------------------------------------------------

def test_the_message_is_the_phrase_and_the_status_only():
    assert upstream_error(Resp(502), "ledger append") == "ledger append returned 502"
    assert MARK not in upstream_error(Resp(500), "x")


def test_a_reply_without_a_status_or_a_readable_body_does_not_raise(caplog):
    class Broken:
        status_code = 500

        @property
        def text(self):
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")

    with caplog.at_level(logging.DEBUG, logger="field_core.upstream"):      # the body is only read when DEBUG is on
        assert upstream_error(Broken(), "x") == "x returned 500"
        assert upstream_error(SimpleNamespace(), "x") == "x returned None"


def test_the_body_goes_to_a_debug_record_truncated_and_on_one_line(caplog):
    with caplog.at_level(logging.DEBUG, logger="field_core.upstream"):
        upstream_error(Resp(500, MARK + "\nsecond line\x00" + "y" * 500), "ledger append")
    (rec,) = [r for r in caplog.records if r.name == "field_core.upstream"]
    assert rec.levelno == logging.DEBUG
    text = rec.getMessage()
    assert MARK in text and "\n" not in text and "\x00" not in text
    assert text.count("y") < BODY_LOG_LIMIT                       # at most 200 characters of the body, not 500
    assert len(text) < BODY_LOG_LIMIT + 120


def test_nothing_is_logged_above_debug(caplog):
    with caplog.at_level(logging.INFO, logger="field_core.upstream"):
        upstream_error(Resp(500), "ledger append")
    assert not [r for r in caplog.records if r.name == "field_core.upstream"]


# ---- every client that used to copy the body ----------------------------------------------------------------------

def _ledger():
    return LedgerClient(client=Upstream(), base_url="http://ledger.invalid", caller=None)


def _registry():
    return RegistryClient(client=Upstream(), base_url="http://registry.invalid")


@pytest.mark.parametrize("call,what", [
    (lambda: _ledger().append("e", {}, "a"), "ledger append"),
    (lambda: _ledger().retention_check(), "ledger retention check"),
    (lambda: _ledger().events(), "ledger events read"),
])
def test_a_ledger_client_error_carries_the_status_and_no_body(call, what):
    with pytest.raises(LedgerUnreachableError) as exc:
        call()
    _clean(str(exc.value), 500, what, exc.value)


@pytest.mark.parametrize("call", [
    lambda: _registry().get_agent("a"),
    lambda: _registry().require_active_agent("a"),
    lambda: _registry().list_agents(),
    lambda: _registry().set_status("a", "killed"),
])
def test_a_registry_client_error_carries_the_status_and_no_body(call):
    with pytest.raises(RegistryUnreachableError) as exc:
        call()
    _clean(str(exc.value), 500, "registry", exc.value)


def test_the_status_code_stays_on_the_ledger_exception():
    with pytest.raises(LedgerUnreachableError) as exc:
        _ledger().append("e", {}, "a")
    assert exc.value.status_code == 500


def test_a_404_is_still_not_registered_and_never_echoes():
    client = RegistryClient(client=Upstream(404), base_url="http://registry.invalid")
    with pytest.raises(AgentNotRegisteredError):
        client.get_agent("a")


# ---- properties of the helper that the stated behaviour depends on (C-584 F-C584-4/-5) ----------------------------

def test_the_debug_body_limit_is_200_characters():
    assert BODY_LOG_LIMIT == 200


def test_the_body_is_not_read_unless_debug_is_on(caplog):
    class Tripwire:
        status_code = 500
        touched = False

        @property
        def text(self):
            type(self).touched = True
            return BIG

    with caplog.at_level(logging.INFO, logger="field_core.upstream"):
        assert upstream_error(Tripwire(), "x") == "x returned 500"
    assert Tripwire.touched is False
    with caplog.at_level(logging.DEBUG, logger="field_core.upstream"):
        upstream_error(Tripwire(), "x")
    assert Tripwire.touched is True


def test_a_body_carried_on_the_exception_chain_is_caught_by_the_check():
    # the check itself: a body hidden in __cause__ or __context__ must fail assert_no_body
    try:
        try:
            raise ValueError(BIG)
        except ValueError as inner:
            raise LedgerUnreachableError("ledger append returned 500") from inner
    except LedgerUnreachableError as e:
        with pytest.raises(AssertionError):
            assert_no_body(e)
    try:
        try:
            raise ValueError(BIG)
        except ValueError:
            raise LedgerUnreachableError("ledger append returned 500")          # implicit __context__
    except LedgerUnreachableError as e:
        with pytest.raises(AssertionError):
            assert_no_body(e)


def test_a_status_that_is_not_an_integer_is_never_formatted():
    # C-685 F-C685-2(b): a reply object whose status_code is text (a stub, a different client) cannot smuggle a body in
    import http

    for odd in (f"500 {BIG}", BIG, b"500", 500.0, [500], True, object()):
        msg = upstream_error(SimpleNamespace(status_code=odd, text=BIG), "x")
        assert msg == "x returned None", (odd if len(str(odd)) < 40 else "long", msg)
    assert upstream_error(SimpleNamespace(status_code=http.HTTPStatus.BAD_GATEWAY, text=BIG), "x") == "x returned 502"
