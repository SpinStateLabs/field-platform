"""PG0-CLI-R2-03, the seventh reader: field-core's own FIELD_OPERATOR_KEY_FILE reader
(``operator_headers``, used by the four daemons and every field-core client in
own-client mode) accepts a key file written by Windows PowerShell 5.1
(``Set-Content -Encoding utf8``: a BOM) with a CRLF line end. The six CLI/tool
copies are pinned in tools/tests/test_operator_cli_c2.py.

The key value is a throwaway constant; nothing here reads a real key."""

from __future__ import annotations

import pytest

from field_core import operator_auth as oa

KEY = "tkv-bom-key-0123456789abcdef-NEVER-REAL"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr(oa, "_logged_once", set(), raising=False)


@pytest.mark.parametrize("content", [b"\xef\xbb\xbf" + KEY.encode() + b"\r\n", b"\xef\xbb\xbf" + KEY.encode()])
def test_a_key_file_with_a_bom_gives_the_key_without_it(tmp_path, monkeypatch, content):
    p = tmp_path / "svc.key"
    p.write_bytes(content)
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-test")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY_FILE, str(p))
    assert oa.operator_headers() == {oa.HEADER_OPERATOR: "svc-test", oa.HEADER_KEY: KEY}
