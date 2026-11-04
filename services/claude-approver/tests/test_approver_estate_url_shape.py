"""S4-22: an estate_base_url must be a plain http(s) base (optional path prefix): no query, fragment, whitespace or control
character, invalid port. estate_for appends /sentinel, /killswitch, /governor, so a query would mangle every URL."""
from __future__ import annotations

import json

import pytest

from approver_fakes import CONSOLE_AGENT, FIELD_AGENT
from claude_approver import config
from claude_approver.core import estate_for

QF = "estate_base_url must not carry a query or fragment"
WS = "estate_base_url must not contain whitespace or control characters"
PORT = "estate_base_url has an invalid port"
PATH = "estate_base_url path must be a plain prefix"


def entry(url):
    return {"field_agent_id": FIELD_AGENT, "estate_base_url": url}


def parsed(url):
    m = config.parse_agent_map(json.dumps({CONSOLE_AGENT: entry(url)}))
    assert m.error is None
    return m.entries[CONSOLE_AGENT]


@pytest.mark.parametrize("url,problem", [
    ("https://est.test?x=1", QF),
    ("https://est.test/?x=1", QF),
    ("https://est.test/#f", QF),
    ("https://est.test#f", QF),
    ("https://est.test?", QF),
    ("https://est.test#", QF),
    ("https://est.test/p?x=1", QF),
    ("https://est.test:99999", PORT),
    ("https://est.test:-1", PORT),
    ("https://est.test:abc", PORT),
    ("https://est.test:8000:9", PORT),
    ("https://est .test", WS),
    ("https://est.test/a b", WS),
    ("https://est.test/a\tb", WS),
    ("https://est.test/a\nb", WS),
    ("https://est.test/a\x00b", WS),
    ("https://est.test/a\x7fb", WS),
    ("https://est.test/a b", WS),
    ("https://est.test//a", PATH),
    ("https://est.test/a//b", PATH),
    ("https://est.test/./a", PATH),
    ("https://est.test/../a", PATH),
    ("https://est.test/a/..", PATH),
    ("https://est.test/%2e%2e/a", PATH),
    ("https://est.test/a;p=1", PATH),
    ("https://est.test/a%2Fb", PATH),
], ids=repr)
def test_a_malformed_estate_url_names_its_reason(url, problem):
    e = parsed(url)
    assert e.problem == problem and e.field_agent_id is None


@pytest.mark.parametrize("url,base", [
    ("https://est.test", "https://est.test"),
    ("https://est.test/", "https://est.test"),
    (" https://est.test/ ", "https://est.test"),
    ("https://est.test/estate-a/", "https://est.test/estate-a"),
    ("https://est.test:8443/api/v2", "https://est.test:8443/api/v2"),
    ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
    ("http://[::1]:8000/x", "http://[::1]:8000/x"),
    ("https://est.test/a.b_c~d", "https://est.test/a.b_c~d"),
])
def test_a_good_base_still_works_and_builds_the_service_urls(url, base):
    e = parsed(url)
    assert e.problem is None and e.estate_base_url == base
    est = estate_for(e)
    assert (est.sentinel, est.killswitch, est.governor) == (f"{base}/sentinel", f"{base}/killswitch", f"{base}/governor")


def test_existing_reasons_are_unchanged():
    assert parsed("ftp://est.test").problem == "estate_base_url is not an http(s) URL"
    assert parsed("http://u:p@est.test").problem == "estate_base_url must not carry credentials"
