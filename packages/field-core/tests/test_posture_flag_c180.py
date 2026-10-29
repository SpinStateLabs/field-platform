"""C-180: the shared reading of a 0/1 posture switch, and the field-core reader of the same
FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM variable the gateway refuses to start on."""

from __future__ import annotations

import pytest

from field_core import llm, posture_flag

KEY = "sk-test-key-never-printed"
TRUE = ["1", "true", "yes", "on", "TRUE", "Yes", " ON ", "\t1\n"]
FALSE = ["0", "false", "no", "off", "FALSE", "No", " OFF ", "\t0\n"]
BLANK = [None, "", " ", "\t", "\n"]
BAD = ["2", "enforce", "enable", "y", "t", "tru", "1.0", "true!", "on off", "-1", "01", "none"]


@pytest.mark.parametrize("raw", TRUE)
def test_true_spellings(raw):
    assert posture_flag.parse(raw) is True


@pytest.mark.parametrize("raw", FALSE + BLANK)
def test_false_and_blank(raw):
    assert posture_flag.parse(raw) is False


@pytest.mark.parametrize("raw", BAD)
def test_unrecognised_is_none_not_false(raw):
    assert posture_flag.parse(raw) is None


def test_the_spellings_do_not_overlap():
    assert not set(posture_flag.TRUE_SPELLINGS) & set(posture_flag.FALSE_SPELLINGS)
    assert posture_flag.TRUE_SPELLINGS == ("1", "true", "yes", "on")
    assert posture_flag.FALSE_SPELLINGS == ("0", "false", "no", "off")


def _plain_http(monkeypatch, value):
    monkeypatch.setenv(llm.BASE_URL_ENV, "http://plain.example.test:9000")
    llm._warned.clear()
    if value is None:
        monkeypatch.delenv(llm.REQUIRE_TLS_ENV, raising=False)
    else:
        monkeypatch.setenv(llm.REQUIRE_TLS_ENV, value)


@pytest.mark.parametrize("raw", TRUE)
def test_every_true_spelling_refuses_a_plain_http_public_base_url(monkeypatch, raw):
    _plain_http(monkeypatch, raw)
    with pytest.raises(llm.InsecureBaseURLError):
        llm.make_http_client(KEY)


@pytest.mark.parametrize("raw", FALSE + BLANK)
def test_a_false_or_blank_value_only_warns(monkeypatch, raw):
    _plain_http(monkeypatch, raw)
    assert llm.make_http_client(KEY)


@pytest.mark.parametrize("raw", BAD)
def test_an_unrecognised_value_fails_closed_here(monkeypatch, raw):
    """field-core cannot refuse to start (it is a library): an unrecognised value is read as armed, never as off."""
    _plain_http(monkeypatch, raw)
    with pytest.raises(llm.InsecureBaseURLError):
        llm.make_http_client(KEY)


def test_https_is_unaffected_by_any_value(monkeypatch):
    monkeypatch.delenv(llm.BASE_URL_ENV, raising=False)
    for raw in TRUE + FALSE + BAD:
        monkeypatch.setenv(llm.REQUIRE_TLS_ENV, raw)
        assert llm.make_http_client(KEY)
