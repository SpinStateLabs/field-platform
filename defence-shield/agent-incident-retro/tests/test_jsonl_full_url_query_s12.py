"""S12-25: the jsonl parser reduces a uri to path+query only when it is an ABSOLUTE URL (a scheme and '://' before any
'/', '?' or '#'). Any uri holding '://' anywhere used to be cut at the first '://', so '/login?next=http://evil.example/x'
became '/x': the query, with the open-redirect / SSRF / RFI payload, was gone before classify() ran."""
from __future__ import annotations

import json

import pytest

from agent_incident_retro.parsers import resolve_parser
from agent_incident_retro.signatures import classify


def _target(uri, preset="generic", key="uri"):
    rec = {"ts": "2026-09-01T00:00:00Z", "ip": "203.0.113.5", key: uri, "status": 200}
    if preset == "cloudflare":
        rec = {"EdgeStartTimestamp": "2026-09-01T00:00:00Z", "ClientIP": "203.0.113.5", "ClientRequestURI": uri,
               "EdgeResponseStatus": 200}
    p = resolve_parser("jsonl", preset)(json.dumps(rec))
    assert p is not None
    return p.target


@pytest.mark.parametrize("uri", [
    "/login?next=http://evil.example/x",
    "/p?file=http://a/../../etc/passwd",
    "/a/b?u=https://h/x?y=1",
    "/x?redirect=ftp://h",
    "/?u=//evil.example",
    "/a#frag://x",
], ids=repr)
def test_a_relative_uri_with_a_url_in_its_query_is_unchanged(uri):
    assert _target(uri) == uri


@pytest.mark.parametrize("uri,expected", [
    ("https://h/x?y=1", "/x?y=1"),
    ("http://h:8080/a/b?c=d", "/a/b?c=d"),
    ("https://h", "/"),
    ("https://h/", "/"),
    ("HTTPS://H/x", "/x"),
    ("https://h?y=1", "/?y=1"),
    ("https://h#f", "/#f"),
    ("https://h/x?u=http://a/b", "/x?u=http://a/b"),
    ("ws+x.y-z://h/p", "/p"),
    ("https://h/x\ny=1", "/x\ny=1"),   # the rest is kept whole, a newline included
], ids=repr)
def test_an_absolute_url_is_still_reduced_to_path_and_query(uri, expected):
    assert _target(uri) == expected


def test_a_cloudflare_record_with_a_traversal_url_in_its_query_still_classifies_as_traversal():
    target = _target("/p?file=http://a/../../etc/passwd", preset="cloudflare")
    assert target == "/p?file=http://a/../../etc/passwd"
    path, _, query = target.partition("?")
    families, _fps = classify(path, query)
    assert "traversal" in families


def test_the_open_redirect_payload_survives_to_classification():
    target = _target("/login?next=http://evil.example/x")
    assert "next=http://evil.example/x" in target
