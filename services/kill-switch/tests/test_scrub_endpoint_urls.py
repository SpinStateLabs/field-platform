"""`kill_switch.api._scrub`: a URL (which may carry credentials) never reaches a kill report or the ledger (scout P-8,
tests only, no source change).

The substitution is `_URLISH.sub("<endpoint>", text)` THEN truncation to 200 characters; the order matters: truncating
first could cut a URL in half and leak its prefix past the pattern. The integration test makes a manifest endpoint raise a
transport error whose message contains the full URL, and checks the KillReport and the ledger events."""

from __future__ import annotations

import json

import pytest

from kill_switch.api import _scrub
from test_endpoint_and_liveness import ALLOWED, OP, Stack  # noqa: F401  (sibling import, as other suites do)

SECRET = "hunter2"
TOKEN = "tok-abc-123"


@pytest.mark.parametrize("text,expected", [
    (f"https://user:{SECRET}@host.example/x?token={TOKEN}", "<endpoint>"),
    ("POST http://h:80/kill", "POST <endpoint>"),
    ("a http://one.example/x b ftp://two.example:21/y c", "a <endpoint> b <endpoint> c"),
    ("ConnectionError: connection refused", "ConnectionError: connection refused"),   # no URL: unchanged
    ("", ""),
])
def test_scrub_replaces_every_url_run_and_leaves_other_text(text, expected):
    assert _scrub(text) == expected


def test_scrub_stringifies_a_non_string():
    assert _scrub(ValueError("bad http://h.example/p?k=v")) == "bad <endpoint>"
    assert _scrub(None) == "None"


def test_scrub_truncates_after_substitution_so_a_cut_url_is_still_replaced():
    """A URL cut by the limit would no longer match the pattern if truncation came first: here the cut falls inside
    `https://` (the first seven characters survive), and the bytes that survive would be a URL fragment in a report."""
    url = f"https://user:{SECRET}@host.example/" + "p" * 50
    text = "x" * 192 + " " + url               # the URL starts at 193: a cut at 200 keeps only "https:/"
    out = _scrub(text)
    assert out == ("x" * 192 + " <endpoint>")[:200]       # substituted first, then cut: 200 characters, "<endpoi" at the end
    assert "https" not in out and SECRET not in out


def test_scrub_output_is_never_longer_than_the_limit():
    assert len(_scrub("y" * 500)) == 200
    assert len(_scrub("y" * 500, limit=10)) == 10
    assert len(_scrub("z" * 195 + " https://h.example/" + "q" * 400)) <= 200


def test_a_scheme_less_credential_shape_is_not_matched_today():
    """Known limit, pinned so a change to the pattern is a decision: `_URLISH` needs `://`, so a bare `host:port/path?token=`
    is not replaced. A transport error message from httpx names the URL with its scheme, so this is not reachable from the
    signal path today; reported, not widened."""
    leaked = f"connect to host.example:8443/x?token={TOKEN} failed"
    assert _scrub(leaked) == leaked


def test_a_transport_error_with_the_full_url_reaches_neither_the_report_nor_the_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack = Stack(tmp_path)
    url = f"http://{ALLOWED}/hooks/halt"
    stack.endpoint._handler = lambda m, u: ConnectionError(f"HTTPSConnectionPool: could not reach https://op:{SECRET}@{ALLOWED}/hooks/halt?token={TOKEN}")
    stack.with_endpoint("invoicing-agent", url)
    r = stack.kill.post("/kill/invoicing-agent", json=OP)
    assert r.status_code == 200, r.text
    body = json.dumps(r.json())
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "failed" and result["reason"] == "transport_error"
    assert "<endpoint>" in result["error"] and "ConnectionError" in result["error"]
    ledger = json.dumps(stack.events())
    for blob in (body, ledger):
        assert SECRET not in blob and TOKEN not in blob and "op:" not in blob
    failed = stack.events("kill.endpoint_failed")
    assert len(failed) == 1 and "<endpoint>" in json.dumps(failed[0]["payload"])
