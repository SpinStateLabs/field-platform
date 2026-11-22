"""Backlog B17 (roley.reviewer C3 on #1272): a query or fragment in the sentinel base URL put ``/check`` inside the
query or the fragment, so the check was POSTed to the wrong path. ``/check`` now goes on the path; the query is kept
after it; the fragment (never sent) is dropped. Hosts are made up; no request leaves the process."""
from __future__ import annotations

import pytest

from force_gateway.api import SentinelClient, sentinel_check_url


@pytest.mark.parametrize("base,want", [
    ("http://sentinel:8004", "http://sentinel:8004/check"),
    ("http://sentinel:8004/", "http://sentinel:8004/check"),
    ("http://sentinel:8004/base", "http://sentinel:8004/base/check"),
    ("http://sentinel:8004/base/", "http://sentinel:8004/base/check"),
    ("http://sentinel:8004?x=1", "http://sentinel:8004/check?x=1"),
    ("http://sentinel:8004/base?x=1&y=2", "http://sentinel:8004/base/check?x=1&y=2"),
    ("http://sentinel:8004/base#frag", "http://sentinel:8004/base/check"),
    ("http://sentinel:8004/base?x=1#frag", "http://sentinel:8004/base/check?x=1"),
    ("https://[::1]:8443/s", "https://[::1]:8443/s/check"),
    ("http://u:pw@sentinel:8004/b?x=1", "http://u:pw@sentinel:8004/b/check?x=1"),   # the call keeps the full URL
])
def test_check_goes_on_the_path_whatever_the_base_carries(base, want):
    assert sentinel_check_url(base) == want


class _Recorder:
    """An injected transport that records the URL it is asked to POST and answers ALLOW."""

    def __init__(self):
        self.urls: list[str] = []

    def post(self, url, json=None):
        self.urls.append(url)

        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"decision": "ALLOW", "clause_id": None}

        return _Resp()


@pytest.mark.parametrize("base,want", [
    ("http://sentinel:8004/base?x=1#frag", "http://sentinel:8004/base/check?x=1"),
    ("http://sentinel:8004#frag", "http://sentinel:8004/check"),
    ("http://sentinel:8004", "http://sentinel:8004/check"),
])
def test_the_client_posts_to_the_built_url(base, want):
    rec = _Recorder()
    verdict = SentinelClient(client=rec, base_url=base, timeout=1.0).check("a-1", "t-1", "egress")
    assert verdict["decision"] == "ALLOW" and rec.urls == [want]


def test_the_environment_base_is_built_the_same_way(monkeypatch):
    monkeypatch.setenv("FIELD_SENTINEL_URL", " http://sentinel:8004/base/?x=1 ")
    rec = _Recorder()
    SentinelClient(client=rec, timeout=1.0).check("a-1", "t-1", "egress")
    assert rec.urls == ["http://sentinel:8004/base/check?x=1"]
