"""C-1203: ``claude_approver.client`` is the one place the SDK is imported, and it is imported late.

The suite runs without the ``anthropic`` package (CI installs with ``--no-deps``), so these tests put a fake module in
``sys.modules`` for the length of one test and take it out again before the conftest teardown checks that the SDK was
never imported. Every key here is made up."""

from __future__ import annotations

import importlib
import sys
import types

import pytest

KEY = "made-up-api-key-0123456789"


class _Anthropic:
    """Records how it was built; ``boom`` makes the next construction raise."""

    calls: list = []
    boom: Exception | None = None

    def __init__(self, *args, **kwargs):
        if _Anthropic.boom is not None:
            raise _Anthropic.boom
        self.args, self.kwargs = args, kwargs
        _Anthropic.calls.append(self)


@pytest.fixture
def fake_sdk():
    _Anthropic.calls, _Anthropic.boom = [], None
    module = types.ModuleType("anthropic")
    module.Anthropic = _Anthropic
    sys.modules["anthropic"] = module
    try:
        yield _Anthropic
    finally:
        sys.modules.pop("anthropic", None)
        _Anthropic.calls, _Anthropic.boom = [], None


@pytest.fixture
def no_sdk():
    sys.modules["anthropic"] = None  # an import of it raises ImportError
    try:
        yield
    finally:
        sys.modules.pop("anthropic", None)


def test_importing_the_module_does_not_import_the_sdk(no_sdk):
    sys.modules.pop("claude_approver.client", None)
    module = importlib.import_module("claude_approver.client")
    assert callable(module.make_client)
    assert sys.modules["anthropic"] is None  # still the block: nothing replaced or loaded it


def test_make_client_passes_the_key_as_the_api_key_and_nothing_else(fake_sdk):
    from claude_approver.client import make_client
    client = make_client(KEY)
    assert fake_sdk.calls == [client]
    assert client.args == () and client.kwargs == {"api_key": KEY}


def test_make_client_returns_the_sdk_instance_unwrapped(fake_sdk):
    from claude_approver.client import make_client
    assert type(make_client(KEY)) is fake_sdk


def test_each_call_builds_a_new_client(fake_sdk):
    from claude_approver.client import make_client
    assert make_client(KEY) is not make_client(KEY)
    assert len(fake_sdk.calls) == 2


def test_an_sdk_error_reaches_the_caller_unchanged(fake_sdk):
    from claude_approver.client import make_client
    error = ValueError("made-up constructor failure")
    fake_sdk.boom = error
    with pytest.raises(ValueError) as caught:
        make_client(KEY)
    assert caught.value is error and KEY not in str(caught.value)


def test_without_the_sdk_the_failure_is_an_import_error_that_does_not_carry_the_key(no_sdk):
    from claude_approver.client import make_client
    with pytest.raises(ImportError) as caught:
        make_client(KEY)
    assert KEY not in str(caught.value)
