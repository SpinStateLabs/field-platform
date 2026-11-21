"""S12-22: a map entry with a secret_file must not send the estate secret in cleartext.

Estate.headers sends the contents of secret_file as x-field-auth on every sentinel, heartbeat and usage call, so an
http:// estate_base_url with a secret_file shipped the secret over plain HTTP. Rule (the repo's other secret senders,
witness.fetch_events and the witness Fly URL, refuse the same): with a secret_file the URL is https, or http to a
loopback host (127.0.0.0/8, ::1, localhost) or a reserved .test / .localhost name; otherwise the entry is unusable
with fixed text that does not echo the URL. http without a secret_file stays allowed."""
from __future__ import annotations

import json

import pytest

from approver_fakes import CONSOLE_AGENT, FIELD_AGENT
from claude_approver import config

FIXED = "estate_base_url must be https when secret_file is set (http only to a loopback or .test host)"


def parsed(url, secret_file="/run/secrets/estate"):
    raw = {"field_agent_id": FIELD_AGENT, "estate_base_url": url}
    if secret_file is not None:
        raw["secret_file"] = secret_file
    m = config.parse_agent_map(json.dumps({CONSOLE_AGENT: raw}))
    assert m.error is None
    return m.entries[CONSOLE_AGENT]


@pytest.mark.parametrize("url", [
    "https://fly.example.org",
    "https://203.0.113.5:8443/estate-a",
    "http://127.0.0.1:8000",
    "http://127.0.0.2",
    "http://127.255.255.254/x",
    "http://[::1]:8000/x",
    "http://localhost:9000",
    "http://LOCALHOST",
    "http://localhost.:9000",
    "http://estate.test",
    "http://a.b.test:8080/p",
    "http://svc.localhost",
], ids=repr)
def test_an_acceptable_url_with_a_secret_file_is_usable(url):
    e = parsed(url)
    assert e.problem is None and e.field_agent_id == FIELD_AGENT


@pytest.mark.parametrize("url", [
    "http://203.0.113.5",
    "http://fly.example.org",
    "http://fly.example.org:8080/estate-a",
    "http://128.0.0.1",
    "http://[2001:db8::1]:8000",
    "http://127.0.0.1.evil.example",
    "http://localhost.evil.example",
    "http://evil.test.example.org",
    "http://notlocalhost",
    "http://contest",
    "http://xtest",
], ids=repr)
def test_a_cleartext_remote_url_with_a_secret_file_is_unusable_with_fixed_text(url):
    e = parsed(url)
    assert e.problem == FIXED and e.field_agent_id is None
    assert "fly.example.org" not in e.problem and "203.0.113.5" not in e.problem


@pytest.mark.parametrize("url", ["http://203.0.113.5", "http://fly.example.org", "http://127.0.0.1"])
def test_http_without_a_secret_file_stays_allowed(url):
    e = parsed(url, secret_file=None)
    assert e.problem is None and e.field_agent_id == FIELD_AGENT


def test_a_blank_secret_file_counts_as_none():
    e = parsed("http://fly.example.org", secret_file="   ")
    assert e.problem is None


def test_the_readme_states_the_rule():
    from pathlib import Path
    text = " ".join((Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8").split())
    assert ("With a `secret_file` the URL must be https (http is accepted only to a loopback address, "
            "`localhost`, or a `.test` / `.localhost` name)") in text
