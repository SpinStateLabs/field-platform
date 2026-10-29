"""C-169 (reviewer C-157 F-C157-3, D-23): an unrecognised non-empty FIELD_SENTINEL_MODE.

`resolve_mode` returned log-only for any value it did not know (`enfroce`, `on`, `1`, `true`, `off`), and log-only
means every `/check` answers ALLOW. A non-empty value that is neither a log-only nor an enforce spelling now
raises at startup; unset or blank keeps the default."""

from __future__ import annotations

import pytest

from conformance_sentinel.mode import InvalidSentinelMode, SentinelMode, resolve_mode

ENV = "FIELD_SENTINEL_MODE"

LOG_ONLY = ["log_only", "log-only", "LOG_ONLY", "LogOnly", "logonly", " log_only ", "\tLog-Only\n"]
ENFORCE = ["enforce", "ENFORCE", "Enforce", "enforcing", "enforced", " Enforced ", "\tenforce\n"]
TYPOS = ["enfroce", "enforc", "enforces", "on", "off", "1", "0", "true", "false", "yes", "no", "production",
         "observe", "log", "logonly1", "log only", "log__only", "enforce!", "enforce enforce", "monitor",
         "disabled", "2", "enforce,log_only", "'enforce'", '"enforce"']


def test_unset_is_the_default(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    assert resolve_mode() is SentinelMode.LOG_ONLY
    assert resolve_mode(SentinelMode.ENFORCE) is SentinelMode.ENFORCE


@pytest.mark.parametrize("blank", ["", " ", "   ", "\t", "\n", " \t \n "])
def test_blank_is_the_default(monkeypatch, blank):
    monkeypatch.setenv(ENV, blank)
    assert resolve_mode() is SentinelMode.LOG_ONLY
    assert resolve_mode(SentinelMode.ENFORCE) is SentinelMode.ENFORCE


@pytest.mark.parametrize("raw", LOG_ONLY)
def test_every_log_only_spelling_is_log_only(monkeypatch, raw):
    monkeypatch.setenv(ENV, raw)
    assert resolve_mode() is SentinelMode.LOG_ONLY
    assert resolve_mode(SentinelMode.ENFORCE) is SentinelMode.LOG_ONLY       # explicit, not the default


@pytest.mark.parametrize("raw", ENFORCE)
def test_every_enforce_spelling_is_enforce(monkeypatch, raw):
    monkeypatch.setenv(ENV, raw)
    assert resolve_mode() is SentinelMode.ENFORCE


@pytest.mark.parametrize("raw", TYPOS)
def test_a_typo_or_foreign_value_raises(monkeypatch, raw):
    monkeypatch.setenv(ENV, raw)
    with pytest.raises(InvalidSentinelMode):
        resolve_mode()


@pytest.mark.parametrize("raw", TYPOS)
def test_a_typo_raises_whatever_the_default_is(monkeypatch, raw):
    monkeypatch.setenv(ENV, raw)
    for default in SentinelMode:
        with pytest.raises(InvalidSentinelMode):
            resolve_mode(default)


def test_the_message_names_the_variable_the_accepted_values_and_the_length_and_is_bounded(monkeypatch):
    monkeypatch.setenv(ENV, "enfroce")
    with pytest.raises(InvalidSentinelMode) as exc:
        resolve_mode()
    msg = str(exc.value)
    assert ENV in msg and "log_only" in msg and "enforce" in msg and "7 characters" in msg
    monkeypatch.setenv(ENV, "x" * 5000)
    with pytest.raises(InvalidSentinelMode) as exc:
        resolve_mode()
    assert len(str(exc.value)) < 300 and "5000 characters" in str(exc.value)


def test_the_error_is_a_value_error(monkeypatch):
    monkeypatch.setenv(ENV, "enfroce")
    with pytest.raises(ValueError):
        resolve_mode()


def test_the_served_app_refuses_to_start_on_a_typo(monkeypatch):
    """The point of the card: startup fails, so the estate cannot run as an observer by accident."""
    from conformance_sentinel.api import create_app

    monkeypatch.setenv(ENV, "enfroce")
    with pytest.raises(InvalidSentinelMode):
        create_app()


def test_the_served_app_starts_with_each_valid_spelling(monkeypatch):
    from conformance_sentinel.api import create_app

    for raw, want in (("enforce", SentinelMode.ENFORCE), ("log-only", SentinelMode.LOG_ONLY), ("", SentinelMode.LOG_ONLY)):
        monkeypatch.setenv(ENV, raw)
        assert create_app().state.engine.mode is want
