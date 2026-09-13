"""build_sha — the FIELD_BUILD_SHA every /health reports (v1.2 Phase C).

The per-service wiring (every create_app's /health carries the key) is pinned
by tools/tests/test_build_sha_health.py; this file pins the one helper.
"""

import pytest

from field_core.buildinfo import ENV_VAR, UNKNOWN, build_sha


def test_the_variable_is_reported_verbatim(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "db5ad33e0c1f")
    assert build_sha() == "db5ad33e0c1f"


@pytest.mark.parametrize("value", [None, "", "   ", "\n"])
def test_unset_or_blank_is_unknown_never_an_empty_value(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(ENV_VAR, value)
    assert build_sha() == UNKNOWN == "unknown"


def test_surrounding_whitespace_is_not_part_of_the_sha(monkeypatch):
    """A CRLF .env line must not put a carriage return into /health."""
    monkeypatch.setenv(ENV_VAR, " abc123\r")
    assert build_sha() == "abc123"


def test_read_per_call_not_at_import(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "one")
    assert build_sha() == "one"
    monkeypatch.setenv(ENV_VAR, "two")
    assert build_sha() == "two"
