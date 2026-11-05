"""S8-3: the env key is stripped and validated like the key-file key, and a bad pair sends NO headers.

`operator_headers()` stripped FIELD_OPERATOR but returned FIELD_OPERATOR_KEY exactly as set, so a pasted key with a trailing
newline or space, or a whitespace-only value (truthy), went out as an illegal header (an h11 error every client wraps as
"unreachable") or a silent "operator credentials required". The key-file path, and the server's parse_headers, already
strip and apply _KEY_RE. Now the env path strips, applies _KEY_RE, sends nothing on failure and logs one line naming only
the variable and the problem class."""

import logging

import pytest

from field_core import operator_auth as oa

KEY = "fok_SECRETVALUE-0123456789abcdef"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in (oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(oa, "_logged_once", set())


def pair(monkeypatch, op, key):
    monkeypatch.setenv(oa.ENV_OPERATOR, op)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, key)


def test_a_clean_pair_is_sent_as_is(monkeypatch):
    pair(monkeypatch, "svc", KEY)
    assert oa.operator_headers() == {oa.HEADER_OPERATOR: "svc", oa.HEADER_KEY: KEY}


@pytest.mark.parametrize("padded", [KEY + "\n", KEY + "\r\n", "  " + KEY, KEY + " \t", "\n" + KEY + "\n"])
def test_a_padded_key_is_sent_stripped(monkeypatch, padded):
    pair(monkeypatch, "svc", padded)
    assert oa.operator_headers() == {oa.HEADER_OPERATOR: "svc", oa.HEADER_KEY: KEY}


@pytest.mark.parametrize("bad", ["   ", "\n", "\t \n", "two words", "inner\nnewline", "tab\tinside", "é-key", "a" * 257,
                                 "key;drop", "key,other", 'q"uote'])
def test_a_whitespace_only_or_malformed_key_sends_no_headers(monkeypatch, caplog, bad):
    pair(monkeypatch, "svc", bad)
    with caplog.at_level(logging.WARNING, logger=oa.log.name):
        assert oa.operator_headers() == {}
    assert oa.ENV_OPERATOR_KEY in caplog.text
    assert bad.strip() == "" or bad.strip() not in caplog.text


@pytest.mark.parametrize("op", ["bad id", "é", "a" * 65, "id;x", r"a/b\c"])
def test_an_invalid_id_sends_no_headers(monkeypatch, op):
    pair(monkeypatch, op, KEY)
    assert oa.operator_headers() == {}


def test_a_padded_id_is_stripped_as_before(monkeypatch):
    pair(monkeypatch, "  svc\n", KEY)
    assert oa.operator_headers()[oa.HEADER_OPERATOR] == "svc"


def test_no_value_ever_appears_in_the_log(monkeypatch, caplog):
    pair(monkeypatch, "bad id with SECRETID", "inner SECRETKEY space")
    with caplog.at_level(logging.DEBUG, logger=oa.log.name):
        assert oa.operator_headers() == {}
        assert oa.operator_headers() == {}
    assert "SECRETKEY" not in caplog.text and "SECRETID" not in caplog.text
    assert caplog.text.count(oa.ENV_OPERATOR_KEY) == 1          # logged once, not per call


def test_missing_values_stay_silent_and_empty(monkeypatch, caplog):
    with caplog.at_level(logging.DEBUG, logger=oa.log.name):
        assert oa.operator_headers() == {}
        monkeypatch.setenv(oa.ENV_OPERATOR, "svc")
        assert oa.operator_headers() == {}
        monkeypatch.setenv(oa.ENV_OPERATOR_KEY, "")
        assert oa.operator_headers() == {}
    assert caplog.text == ""


def test_a_malformed_key_with_no_operator_id_is_silent_and_empty(monkeypatch, caplog):
    """Pins the `if op` guard (reviewer C1): without FIELD_OPERATOR the key is neither validated nor logged."""
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, "two words")
    with caplog.at_level(logging.DEBUG, logger=oa.log.name):
        assert oa.operator_headers() == {}
    assert caplog.text == ""


def test_the_key_file_path_is_unchanged(monkeypatch, tmp_path):
    f = tmp_path / "key"
    f.write_text(KEY + "\n", encoding="utf-8")
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY_FILE, str(f))
    assert oa.operator_headers() == {oa.HEADER_OPERATOR: "svc", oa.HEADER_KEY: KEY}
    f.write_text("two words", encoding="utf-8")
    assert oa.operator_headers() == {}
