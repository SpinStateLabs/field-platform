"""Shared hygiene for the claude-approver suite: no network, no ``anthropic``.

Every test starts with the approver's environment cleared, ``FIELD_DATA_DIR``
in ``tmp_path`` and the FIELD service URLs pointing at names that only the
``httpx.MockTransport`` in ``approver_fakes.FieldServices`` answers.
"""

from __future__ import annotations

import sys

import pytest

from approver_fakes import FakeConsole, FieldServices, default_map, set_map

from claude_approver.core import Approver


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    import os

    for name in list(os.environ):
        if name.startswith("CLAUDE_APPROVER_") or name in (
            "FIELD_SHARED_SECRET", "FIELD_OPERATOR", "FIELD_OPERATOR_KEY", "FIELD_OPERATOR_KEY_FILE",
            "FIELD_BUILD_SHA",
        ):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIELD_SENTINEL_URL", "http://sentinel.test:8004")
    monkeypatch.setenv("FIELD_KILLSWITCH_URL", "http://killswitch.test:8005")
    monkeypatch.setenv("FIELD_GOVERNOR_URL", "http://governor.test:8006")
    # the key-file default is an absolute path that may not exist; point it into tmp
    monkeypatch.setenv("CLAUDE_APPROVER_API_KEY_FILE", str(tmp_path / "no-such-key"))
    yield
    # the suite must never have imported the SDK
    assert "anthropic" not in sys.modules


@pytest.fixture
def console() -> FakeConsole:
    return FakeConsole()


@pytest.fixture
def field() -> FieldServices:
    return FieldServices()


@pytest.fixture
def make_approver(console, field, tmp_path):
    def _make(**kw) -> Approver:
        kw.setdefault("client", console)
        kw.setdefault("http", field.client())
        kw.setdefault("cursor_path", tmp_path / "data" / "claude-approver" / "usage-cursor.json")
        kw.setdefault("sleep", lambda s: None)
        return Approver(**kw)

    return _make


@pytest.fixture
def mapped(monkeypatch):
    set_map(monkeypatch, default_map())
