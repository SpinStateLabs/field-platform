"""S8-6 — direct pins for alerts.send_test and alerts.write_topic_file, which no test named. Tests only;
a fake opener stands in for the network, nothing is sent."""

from __future__ import annotations

import os
import re
import sys

import pytest

from field_core import alerts

TOPIC = "field-" + "a" * 24
ENV = {"FIELD_NTFY_TOPIC": TOPIC, "FIELD_NTFY_BASE_URL": "http://127.0.0.1:9"}
POSIX = sys.platform != "win32"


class _Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Opener:
    def __init__(self):
        self.requests: list = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        return _Resp()


@pytest.fixture(autouse=True)
def _fresh():
    alerts._reset_stats()
    yield
    alerts._reset_stats()


def _send_test(opener=None, **kw):
    opener = opener or _Opener()
    res = alerts.send_test(estate="acme-estate", env=ENV, opener=opener, sleep=lambda s: None,
                           backoff_s=(), **kw)
    return res, opener


def _body(req) -> str:
    return req.data.decode("utf-8")


# --- send_test ---------------------------------------------------------------------------------------

def test_one_post_of_the_test_class():
    res, op = _send_test()
    assert res.ok and res.attempts == 1 and len(op.requests) == 1
    req = op.requests[0]
    assert req.get_method() == "POST"
    h = {k.lower(): v for k, v in req.header_items()}
    assert h["title"] == "FIELD TEST ALERT - no action needed"
    assert h["priority"] == "3"
    assert h["tags"] == "test_tube,test,field"
    assert req.full_url.startswith("http://127.0.0.1:9/") and TOPIC in req.full_url


def test_the_body_carries_the_estate_and_a_six_hex_test_id_line():
    """The id is the line before the closing ``sent:`` stamp (the card said the body ENDS with it; it does not)."""
    _, op = _send_test()
    lines = _body(op.requests[0]).split("\n")
    assert lines[1] == "estate: acme-estate"
    assert re.fullmatch(r"test id: [0-9a-f]{6}", lines[-2]), lines
    assert re.fullmatch(r"sent: \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", lines[-1])


def test_the_id_comes_from_secrets_token_hex_and_differs_per_call(monkeypatch):
    seen = []

    def fake(n):
        assert n == 3
        seen.append(f"{len(seen):06x}")
        return seen[-1]

    monkeypatch.setattr(alerts.secrets, "token_hex", fake)
    _, a = _send_test()
    _, b = _send_test()
    assert "test id: 000000" in _body(a.requests[0]) and "test id: 000001" in _body(b.requests[0])
    assert seen == ["000000", "000001"]


def test_two_real_calls_give_different_ids():
    ids = {re.search(r"test id: ([0-9a-f]{6})", _body(_send_test()[1].requests[0])).group(1)
           for _ in range(8)}
    assert len(ids) > 1


def test_kwargs_are_forwarded_to_send(monkeypatch):
    got = {}

    def fake_send(alert_class, **kw):
        got.update(kw, alert_class=alert_class)
        return "sentinel-result"

    monkeypatch.setattr(alerts, "send", fake_send)
    op, sl = _Opener(), (lambda s: None)
    out = alerts.send_test(estate="e", env=ENV, max_attempts=2, opener=op, sleep=sl)
    assert out == "sentinel-result"
    assert got["alert_class"] == "test" and got["estate"] == "e" and got["env"] is ENV
    assert got["max_attempts"] == 2 and got["opener"] is op and got["sleep"] is sl
    assert re.fullmatch(r"[0-9a-f]{6}", got["test_id"])


def test_passing_test_id_is_a_duplicate_keyword():
    with pytest.raises(TypeError):
        alerts.send_test(estate="e", env=ENV, test_id="abcdef", opener=_Opener())


def test_an_unconfigured_env_is_not_configured_and_counted_once():
    res = alerts.send_test(estate="e", env={})
    assert res.ok is False and res.attempts == 0 and res.reason == "not_configured"
    h = alerts.health_fields({})
    assert h["alerts_failed"] == 1 and h["alerts_last_failure_class"] == "test"
    assert h["alerts_last_failure_reason"] == "not_configured" and h["alerts_sent"] == 0


# --- write_topic_file --------------------------------------------------------------------------------

def test_writes_one_url_safe_topic_line_and_returns_none(tmp_path):
    p = tmp_path / "topic"
    assert alerts.write_topic_file(p) is None
    raw = p.read_text(encoding="utf-8")
    assert raw.endswith("\n") and raw.count("\n") == 1
    topic = raw.strip()
    assert topic.startswith("field-") and alerts.TOPIC_RE.fullmatch(topic)
    assert len(topic) >= alerts.MIN_TOPIC_LEN_WITHOUT_TOKEN


def test_creates_missing_parent_directories(tmp_path):
    p = tmp_path / "a" / "b" / "topic"
    alerts.write_topic_file(p)
    assert p.is_file()


def test_refuses_an_existing_file_and_leaves_it_byte_identical(tmp_path):
    p = tmp_path / "topic"
    p.write_bytes(b"keep-me\n")
    with pytest.raises(FileExistsError):
        alerts.write_topic_file(p)
    assert p.read_bytes() == b"keep-me\n"


def test_overwrite_replaces_the_file(tmp_path):
    p = tmp_path / "topic"
    p.write_bytes(b"old\n" * 50)
    alerts.write_topic_file(p, overwrite=True)
    new = p.read_text(encoding="utf-8")
    assert new.startswith("field-") and "old" not in new and new.count("\n") == 1


def test_two_topics_differ(tmp_path):
    alerts.write_topic_file(tmp_path / "a")
    alerts.write_topic_file(tmp_path / "b")
    assert (tmp_path / "a").read_text() != (tmp_path / "b").read_text()


def test_a_directory_path_is_an_oserror(tmp_path):
    with pytest.raises(OSError):
        alerts.write_topic_file(tmp_path)
    with pytest.raises(OSError):
        alerts.write_topic_file(tmp_path, overwrite=True)


@pytest.mark.skipif(not POSIX, reason="POSIX file modes")
def test_the_mode_is_owner_only_created_and_overwritten(tmp_path):
    p = tmp_path / "topic"
    alerts.write_topic_file(p)
    assert (p.stat().st_mode & 0o777) == 0o600
    p.chmod(0o644)
    alerts.write_topic_file(p, overwrite=True)
    assert (p.stat().st_mode & 0o777) == 0o600
