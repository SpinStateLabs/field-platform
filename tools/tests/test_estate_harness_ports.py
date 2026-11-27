"""Test estates choose their own ports. The harness binds port 0 and keeps that socket for its server, so two estates
started at once cannot share a port; a port that is meant to have no server stays bound while a test uses it."""
from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_estate_probe import Estate, _http, _nothing_listens


def test_two_estates_started_at_once_never_share_a_port(tmp_path):
    with ThreadPoolExecutor(max_workers=2) as pool:
        started = [pool.submit(Estate, tmp_path / name, False) for name in ("first", "second")]
    estates = [f.result() for f in started if f.exception() is None]
    try:
        failures = [f.exception() for f in started if f.exception() is not None]
        assert not failures, failures
        first, second = estates
        assert first.port != second.port and first.base != second.base
        # each number answers for its own estate: a switch set on one is not seen on the other
        first.fault("mock")
        assert _http("GET", f"{first.base}/__fault")[1] == {"on": ["mock"]}
        assert _http("GET", f"{second.base}/__fault")[1] == {"on": []}
    finally:
        for estate in estates:
            estate.close()


def test_a_port_with_no_server_cannot_be_taken_while_it_is_held():
    with _nothing_listens() as base:
        port = int(base.rsplit(":", 1)[1])
        with socket.socket() as other, pytest.raises(OSError):
            other.bind(("127.0.0.1", port))
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=5).close()
