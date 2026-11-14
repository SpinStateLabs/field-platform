"""B-S11-17: a secret or key file saved with a UTF-8 BOM (PowerShell 5.1 ``Out-File`` / ``>``) reads back as the bare
value, and a value with a non-printable or non-ASCII character is unusable (None) instead of a header httpx cannot
encode, which made every call fail as ``sentinel_error`` while /health still said ``key_file_present: true``."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from claude_approver import config
from claude_approver.api import create_app
from claude_approver.core import AUTH_HEADER, Estate


def _write(path, data: bytes):
    path.write_bytes(data)
    return path


def test_a_bom_prefixed_file_reads_back_as_the_bare_key(tmp_path):
    p = _write(tmp_path / "k", b"\xef\xbb\xbfabc123\r\n")
    assert config.read_secret_file(p) == "abc123"


def test_a_plain_file_is_unchanged(tmp_path):
    assert config.read_secret_file(_write(tmp_path / "k", b"  abc123\n")) == "abc123"


@pytest.mark.parametrize("data", [
    "ab\ufeffc".encode(), b"ab\ncd", b"ab\x00cd", b"ab\x1bcd", "ab\u200bcd".encode(), "caf\u00e9".encode(),
    b"\xef\xbb\xbf", b"\xef\xbb\xbf  \n", b"",
], ids=repr)
def test_an_unusable_value_is_none(tmp_path, data):
    assert config.read_secret_file(_write(tmp_path / "k", data)) is None


def test_estate_headers_for_a_bom_secret_file_is_a_usable_ascii_header(tmp_path):
    p = _write(tmp_path / "s", b"\xef\xbb\xbfperimeter-secret\n")
    e = Estate("http://s.test", "http://k.test", "http://g.test", True, str(p))
    headers = e.headers()
    assert headers == {AUTH_HEADER: "perimeter-secret"}
    headers[AUTH_HEADER].encode("ascii")


def test_estate_headers_for_an_unusable_secret_file_is_none(tmp_path):
    p = _write(tmp_path / "s", "ab\ufeffc".encode())
    assert Estate("http://s.test", "http://k.test", "http://g.test", True, str(p)).headers() is None


def test_health_says_key_file_present_false_for_an_unusable_file(tmp_path, monkeypatch, make_approver):
    p = _write(tmp_path / "key", "ab\ufeffc".encode())
    monkeypatch.setenv(config.ENV_KEY_FILE, str(p))
    body = TestClient(create_app(make_approver(client=None, client_factory=lambda k: None))).get("/health").json()
    assert body["key_file_present"] is False


def test_health_says_key_file_present_true_for_a_bom_file(tmp_path, monkeypatch, make_approver):
    p = _write(tmp_path / "key", b"\xef\xbb\xbfkey-value\n")
    monkeypatch.setenv(config.ENV_KEY_FILE, str(p))
    body = TestClient(create_app(make_approver(client=None, client_factory=lambda k: None))).get("/health").json()
    assert body["key_file_present"] is True
