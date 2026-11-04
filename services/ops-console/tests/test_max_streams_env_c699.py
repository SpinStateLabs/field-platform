"""FIELD_CONSOLE_MAX_STREAMS: a bad value refuses to start and is never echoed."""

import pytest

from ops_console import api
from ops_console.api import _max_streams_from_env

CANARY = "CANARY-9f3a"


def test_default_and_valid(monkeypatch):
    monkeypatch.delenv("FIELD_CONSOLE_MAX_STREAMS", raising=False)
    assert _max_streams_from_env() == 8
    monkeypatch.setenv("FIELD_CONSOLE_MAX_STREAMS", "0")
    assert _max_streams_from_env() == 0
    monkeypatch.setenv("FIELD_CONSOLE_MAX_STREAMS", " 3 ")
    assert _max_streams_from_env() == 3


@pytest.mark.parametrize("bad", [CANARY, "", "1.5", "-1", "nan"])
def test_bad_value_refused_without_echo(monkeypatch, bad):
    monkeypatch.setenv("FIELD_CONSOLE_MAX_STREAMS", bad)
    with pytest.raises(ValueError) as ei:
        _max_streams_from_env()
    text = str(ei.value)
    assert "FIELD_CONSOLE_MAX_STREAMS" in text
    assert CANARY not in text
    assert ei.value.__cause__ is None and ei.value.__suppress_context__


def test_create_app_uses_helper(monkeypatch):
    assert hasattr(api, "_max_streams_from_env")
    monkeypatch.setenv("FIELD_CONSOLE_MAX_STREAMS", CANARY)
    with pytest.raises(ValueError) as ei:
        api.create_app()
    assert CANARY not in str(ei.value)
