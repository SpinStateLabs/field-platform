"""S4-8: FieldClient only checked base_url's scheme when a shared secret was set, and its default opener still carries
urllib's FileHandler, FTPHandler and DataHandler, so a misconfigured FIELD_URL such as file:///srv/estate made check()
read a LOCAL FILE as the sentinel's answer, defeating the module's fail-closed rules. The scheme must be http or https
with a non-empty hostname at construction (ValueError), and _call refuses any non-http(s) request URL as unreachable
(so every rule fails closed) even if base_url is changed after construction."""

from __future__ import annotations

import urllib.parse

import pytest

from field_agent.field_client import FieldClient

TOKEN = "fake-token-id"


def build(base_url, **kw):
    return FieldClient(base_url, "agent-1", TOKEN, **kw)


@pytest.mark.parametrize("url", ["file:///x", "file:///srv/estate", "ftp://h", "ftp://h/x", "data:,x", "gopher://h",
                                 "estate.example", "estate.example:8080", "//estate.example", "/just/a/path",
                                 "http://", "https://", "http:///path", "HTTP:", "javascript:alert(1)"])
def test_a_base_url_that_is_not_http_or_https_with_a_host_is_refused_at_construction(url):
    with pytest.raises(ValueError):
        build(url)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8080", "https://h", "http://localhost", "https://estate.example/base",
                                 "HTTPS://Estate.Example", "http://[::1]:9", "http://10.0.2.10:18080/"])
def test_a_real_http_or_https_base_url_still_builds(url):
    assert build(url).base_url == url.rstrip("/")


def test_the_scheme_rule_holds_with_a_shared_secret_too():
    with pytest.raises(ValueError):
        build("file:///x", shared_secret="s")
    with pytest.raises(ValueError):
        build("ftp://10.0.0.1", shared_secret="s")
    build("https://h", shared_secret="s")                       # unchanged


def test_the_existing_missing_argument_check_still_comes_first():
    with pytest.raises(ValueError, match="required"):
        FieldClient("", "agent-1", TOKEN)


def test_a_file_url_never_reaches_the_opener_at_construction_or_use(tmp_path):
    secret_file = tmp_path / "answer.json"
    secret_file.write_text('{"decision": "ALLOW"}', encoding="utf-8")
    with pytest.raises(ValueError):
        build(secret_file.as_uri())                              # the harm: a local file read as the sentinel's answer


class Recorder:
    def __init__(self):
        self.urls: list[str] = []

    def __call__(self, req, timeout=None):
        self.urls.append(req.full_url)
        raise OSError("no network in this test")


def test_every_request_a_valid_client_makes_starts_with_its_base_url():
    rec = Recorder()
    c = build("http://127.0.0.1:8080", opener=rec, prefixes={"sentinel": "/custom-sentinel"})
    c.check("act")
    c.killed()
    assert rec.urls and all(u.startswith("http://127.0.0.1:8080/") for u in rec.urls), rec.urls
    assert rec.urls[0] == "http://127.0.0.1:8080/custom-sentinel/check"


@pytest.mark.parametrize("bad", ["file:///etc/hostname", "ftp://h", "data:,x", "gopher://h"])
def test_a_request_url_that_is_not_http_or_https_is_refused_before_the_opener_and_fails_closed(bad):
    rec = Recorder()
    c = build("http://127.0.0.1:8080", opener=rec)
    c.base_url = bad                                              # belt and braces: whatever got in after construction
    assert c.check("act").decision == "BLOCK"                     # rule 1: unreachable sentinel is a BLOCK
    assert c.killed() is True                                     # rules 2 and 4: unreachable is killed
    assert rec.urls == []                                         # the opener was never called


def test_a_prefixes_override_cannot_turn_the_request_into_another_host_or_scheme():
    """F-R656-1: "@evil.example" would send "http://127.0.0.1:8080@evil.example/check", host evil.example, secret and all."""
    rec = Recorder()
    c = build("http://127.0.0.1:8080", opener=rec, shared_secret="s", prefixes={"sentinel": "/s", "killswitch": "/k"})
    c.prefixes["sentinel"] = "@evil.example"
    assert c.check("act").decision != "ALLOW"            # unreachable: fail closed
    assert rec.urls == [], "the request never reached the opener"


@pytest.mark.parametrize("prefix", ["@evil.example", ".evil.example", ":9@evil.example", "#@evil.example", chr(92) + "@evil.example",
                                    "/ok@evil.example:80/x"], ids=["at", "dot", "port-at", "hash-at", "backslash-at", "path-at"])
def test_no_prefix_can_move_the_host_or_port_off_the_base_urls(prefix):
    rec = Recorder()
    c = build("https://estate.example:8443", opener=rec, shared_secret="s")
    c.prefixes["sentinel"] = prefix
    c.check("act")
    assert all(urllib.parse.urlsplit(u).hostname == "estate.example" for u in rec.urls)


def test_an_ordinary_prefix_is_still_sent_to_the_base_host_and_port():
    rec = Recorder()
    c = build("HTTPS://Estate.Example:8443/base", opener=rec, prefixes={"sentinel": "/sentinel"})
    c.check("act")                                                   # the opener raises: unreachable, but it was called
    assert rec.urls == ["HTTPS://Estate.Example:8443/base/sentinel/check"]


def test_a_base_url_changed_after_construction_to_another_host_is_not_followed_by_the_prefix_check():
    """The pin compares against the CURRENT base_url, so changing it later changes both sides together."""
    rec = Recorder()
    c = build("http://127.0.0.1:8080", opener=rec)
    c.base_url = "http://10.0.2.10:9000"
    c.check("act")
    assert rec.urls and rec.urls[0].startswith("http://10.0.2.10:9000/")

@pytest.mark.parametrize("base,prefix", [
    ("https://estate.example:8443", "@evil.example:8443"),      # another host on the SAME port
    ("https://estate.example", ":444"),                          # the same host on another port
    ("http://127.0.0.1:8080", "@127.0.0.2:8080"),                # another loopback host, same port
])
def test_the_host_and_the_port_are_each_pinned_on_their_own(base, prefix):
    rec = Recorder()
    c = build(base, opener=rec, shared_secret="s")
    c.prefixes["sentinel"] = prefix
    assert c.check("act").decision != "ALLOW"
    assert rec.urls == []
