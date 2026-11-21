"""S11-4: install() warns, once, when FIELD_SHARED_SECRET can never be sent by a caller.

A server strips leading and trailing whitespace from a header value and a client library refuses CR, LF and NUL in one,
so a secret imported with a trailing newline or CR (a PowerShell 5.1 pipe, a CRLF .env file) or a leading space makes
every guarded request answer 401 while /health stays open and looks fine. The MATCHING RULE is unchanged (no silent
strip: that would change what a configured secret means across services and clients); the warning names the variable
and the fact only, never the value or its length.
"""
from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI

from field_core import authn
from field_core.authn import ENV_VAR, install, secret_matches

LOGGER = "field_core.authn"
FACT = f"{ENV_VAR} holds leading/trailing whitespace or a control character; callers cannot send it"


def _install_log(monkeypatch, caplog, value):
    # the secret is injected at `shared_secret` because an OS environment variable cannot hold NUL ("embedded null
    # byte"): the NUL case is unreachable from a real environment and is exercised here only for the check itself
    monkeypatch.setattr(authn, "shared_secret", lambda: value or None)
    with caplog.at_level("DEBUG", logger=LOGGER):
        install(FastAPI())
    return [r.getMessage() for r in caplog.records if r.name == LOGGER]


@pytest.mark.parametrize("secret", ["abc\n", " abc", "ab\x00c", "abc\r", "abc ", "\tabc", "ab\x7fc", "a\x1bb", "abc\r\n"])
def test_a_secret_no_caller_can_send_warns_once_with_the_fixed_text(monkeypatch, caplog, secret):
    messages = _install_log(monkeypatch, caplog, secret)
    assert messages == [FACT]


@pytest.mark.parametrize("secret", ["abc-123", "s3cret demo", "a b c", "~!@#", "﻿abc-not-whitespace-stripped"[1:]])
def test_a_clean_secret_logs_nothing(monkeypatch, caplog, secret):
    assert _install_log(monkeypatch, caplog, secret) == []


@pytest.mark.parametrize("value", [None, ""])
def test_unset_or_empty_logs_nothing(monkeypatch, caplog, value):
    assert _install_log(monkeypatch, caplog, value) == []


@pytest.mark.parametrize("secret", ["XYZ-sec\n", " XYZ-sec", "XY\x00Z-sec", "XYZ-sec\r"])
def test_the_message_holds_neither_the_value_nor_its_length(monkeypatch, caplog, secret):
    text = " ".join(_install_log(monkeypatch, caplog, secret))
    assert "XYZ" not in text and "sec" not in text.replace("secret", "")
    assert str(len(secret)) not in text.split(ENV_VAR)[1]


def test_a_non_ascii_secret_keeps_its_own_line_and_a_clean_one_adds_none(monkeypatch, caplog):
    messages = _install_log(monkeypatch, caplog, "sécret-é")
    assert len(messages) == 1 and "non-ASCII" in messages[0]


def test_a_non_ascii_secret_with_a_trailing_newline_gets_both_lines(monkeypatch, caplog):
    messages = _install_log(monkeypatch, caplog, "sécret\n")
    assert len(messages) == 2 and any("non-ASCII" in m for m in messages) and FACT in messages


def test_the_matching_rule_is_unchanged():
    """No silent strip: the exact configured bytes match, a stripped form does not, and vice versa."""
    assert secret_matches("abc ", "abc ") is True
    assert secret_matches("abc", "abc ") is False
    assert secret_matches("abc ", "abc") is False
    assert secret_matches("abc", "abc") is True


def _serve(secret: str):
    app = FastAPI()
    install(app)

    @app.get("/data")
    def data():
        return {"v": 1}

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.02)
    assert server.started, "uvicorn did not start"
    return server, thread, port


def _status(port: int, header_value: bytes) -> int:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as c:
        c.sendall(b"GET /data HTTP/1.1\r\nHost: x\r\nx-field-auth: " + header_value + b"\r\nConnection: close\r\n\r\n")
        data = b""
        while chunk := c.recv(4096):
            data += chunk
    return int(data.split(b" ", 2)[1])


def test_the_server_stack_refuses_both_the_exact_and_the_stripped_form(monkeypatch):
    """The reason for the warning, observed on a real socket: the HTTP server strips trailing whitespace from the
    header value, so a secret that ends in a space is unreachable (the exact secret 'abc ' is refused, so is 'abc')."""
    monkeypatch.setenv(ENV_VAR, "abc ")
    server, thread, port = _serve("abc ")
    try:
        assert _status(port, b"abc ") == 401
        assert _status(port, b"abc") == 401
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_a_clean_secret_still_passes_on_the_same_stack(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "abc")
    server, thread, port = _serve("abc")
    try:
        assert _status(port, b"abc") == 200
        assert _status(port, b"abd") == 401
    finally:
        server.should_exit = True
        thread.join(timeout=5)
