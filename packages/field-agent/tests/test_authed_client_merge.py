"""S10-8: ``AuthedClient`` merges the per-call auth headers case-insensitively. A caller-supplied header of any case wins,
one header name is never sent twice (the old exact-key ``setdefault`` sent both ``X-Field-Auth`` and ``x-field-auth``),
the caller's dict is not mutated, and the secret is read per call (a secret set after construction is honoured). A
recording fake stands in for the inner client; every value is made up."""
from __future__ import annotations

import pytest

from field_agent._transport import AuthedClient

SECRET = "made-up-perimeter-secret"
OP, KEY = "made-up-operator", "fok_made-up-key-0123456789abcdef"


class Recorder:
    def __init__(self):
        self.calls = []

    def _rec(self, verb, url, **kw):
        self.calls.append((verb, url, kw))
        return object()

    def post(self, url, **kw):
        return self._rec("post", url, **kw)

    def get(self, url, **kw):
        return self._rec("get", url, **kw)

    def patch(self, url, **kw):
        return self._rec("patch", url, **kw)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in ("FIELD_SHARED_SECRET", "FIELD_OPERATOR", "FIELD_OPERATOR_KEY", "FIELD_OPERATOR_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)


def sent(client_call):
    rec = Recorder()
    client_call(AuthedClient(rec))
    return rec.calls[-1][2]["headers"]


def names(headers):
    return sorted(k.lower() for k in headers)


def test_nothing_configured_sends_no_auth_header():
    assert sent(lambda c: c.get("http://t/x")) == {}


@pytest.mark.parametrize("given", [None, {}], ids=repr)
def test_no_headers_given_gets_the_secret_header(monkeypatch, given):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    kwargs = {} if given is None else {"headers": given}
    assert sent(lambda c: c.post("http://t/x", **kwargs)) == {"x-field-auth": SECRET}


@pytest.mark.parametrize("name", ["X-Field-Auth", "x-field-auth", "X-FIELD-AUTH", "x-Field-AUTH"])
def test_a_caller_supplied_header_of_any_case_wins_and_is_sent_once(monkeypatch, name):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    headers = sent(lambda c: c.post("http://t/x", headers={name: "mine"}))
    assert names(headers) == ["x-field-auth"]
    assert list(headers.values()) == ["mine"] and SECRET not in headers.values()


def test_other_caller_headers_are_kept_beside_the_secret(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    headers = sent(lambda c: c.patch("http://t/x", headers={"Content-Type": "application/json"}))
    assert headers == {"Content-Type": "application/json", "x-field-auth": SECRET}


def test_the_operator_pair_is_merged_the_same_way(monkeypatch):
    monkeypatch.setenv("FIELD_OPERATOR", OP)
    monkeypatch.setenv("FIELD_OPERATOR_KEY", KEY)
    got = sent(lambda c: c.post("http://t/x"))
    assert got == {"x-field-operator": OP, "x-field-operator-key": KEY}
    mine = sent(lambda c: c.post("http://t/x", headers={"X-Field-Operator": "mine", "X-FIELD-OPERATOR-KEY": "k"}))
    assert names(mine) == ["x-field-operator", "x-field-operator-key"]
    assert sorted(mine.values()) == ["k", "mine"] and OP not in mine.values() and KEY not in mine.values()


def test_a_caller_header_that_is_bytes_named_still_wins(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    headers = sent(lambda c: c.get("http://t/x", headers={b"X-Field-Auth": "mine"}))
    assert len(headers) == 1 and list(headers.values()) == ["mine"]


def test_the_callers_dict_is_not_mutated(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    mine = {"X-Other": "1"}
    sent(lambda c: c.get("http://t/x", headers=mine))
    assert mine == {"X-Other": "1"}


def test_a_secret_set_after_construction_is_honoured_on_the_next_call(monkeypatch):
    rec = Recorder()
    client = AuthedClient(rec)
    client.get("http://t/x")
    assert rec.calls[-1][2]["headers"] == {}
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    client.get("http://t/x")
    assert rec.calls[-1][2]["headers"] == {"x-field-auth": SECRET}
    monkeypatch.delenv("FIELD_SHARED_SECRET")
    client.get("http://t/x")
    assert rec.calls[-1][2]["headers"] == {}


def test_the_url_and_other_keyword_arguments_pass_through(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    rec = Recorder()
    AuthedClient(rec).post("http://t/x", json={"a": 1}, timeout=3)
    verb, url, kw = rec.calls[-1]
    assert (verb, url, kw["json"], kw["timeout"]) == ("post", "http://t/x", {"a": 1}, 3)
