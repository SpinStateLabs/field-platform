"""field_core.alerts: ntfy push alerts (K10, P36 item 3).

Every test runs against a local HTTP server on 127.0.0.1 standing in for
ntfy; no test reaches the network. Topics and tokens here are FAKE values.
"""

from __future__ import annotations

import ast
import asyncio
import http.server
import logging
import os
import re
import threading
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from field_core import alerts
from field_core.cli import app

FAKE_TOPIC = "faketopic_unit_test_only_xyz"          # 28 chars, not a real topic
FAKE_TOKEN = "tk_fakeTokenForUnitTestsOnly"           # not a real token
FAKE_KEY = "fok_" + "A" * 43                          # shape of an operator key, fake
FAKE_HASH = "ab" * 32                                 # a 64-hex "hash"
FAKE_FP = "0123456789abcdef"                          # a 16-hex fingerprint
ALL_ENV = (alerts.ENV_TOPIC_FILE, alerts.ENV_TOPIC, alerts.ENV_BASE_URL,
           alerts.ENV_TOKEN_FILE, alerts.ENV_TOKEN)


class _Ntfy:
    """A fake ntfy: records requests, answers from a script of (status, delay)."""

    def __init__(self):
        self.requests: list[dict] = []
        self.script: list[tuple[int, float]] = []
        self.default = (200, 0.0)
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n).decode("utf-8")
                outer.requests.append({"path": self.path, "headers": dict(self.headers),
                                       "body": body})
                status, delay = outer.script.pop(0) if outer.script else outer.default
                if delay:
                    time.sleep(delay)
                try:
                    self.send_response(status)
                    if 300 <= status < 400:
                        self.send_header("Location", f"http://127.0.0.1:{outer.port}/elsewhere")
                    reply = b'{"id":"x","topic":"%s"}' % self.path.strip("/").encode()
                    self.send_header("Content-Length", str(len(reply)))
                    self.end_headers()
                    self.wfile.write(reply)
                except OSError:
                    pass

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05},
                                       daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def ntfy():
    s = _Ntfy()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ALL_ENV:
        monkeypatch.delenv(k, raising=False)
    alerts.reset_stats()
    yield
    alerts.reset_stats()


def _env(ntfy, **extra):
    env = {alerts.ENV_TOPIC: FAKE_TOPIC, alerts.ENV_BASE_URL: ntfy.base}
    env.update(extra)
    return env


def _fast(**kw):
    kw.setdefault("sleep", lambda s: None)
    kw.setdefault("timeout_s", 2.0)
    return kw


# ------------------------------------------------------------ configuration

def test_bare_topic_goes_to_the_base_url(ntfy):
    r = alerts.send("test", estate="gb10", env=_env(ntfy), **_fast())
    assert r.ok and r.attempts == 1
    assert ntfy.requests[0]["path"] == f"/{FAKE_TOPIC}"


def test_default_base_url_is_ntfy_sh():
    d = alerts.resolve_destination({alerts.ENV_TOPIC: FAKE_TOPIC})
    assert d.url == f"https://ntfy.sh/{FAKE_TOPIC}"


def test_self_hosted_full_url_with_a_path_prefix_is_used_verbatim(tmp_path, ntfy):
    f = tmp_path / "topic.txt"
    f.write_text(f"\ufeff{ntfy.base}/ntfy/{FAKE_TOPIC}/\n", encoding="utf-8")
    r = alerts.send("test", estate="gb10", env={alerts.ENV_TOPIC_FILE: str(f),
                                                alerts.ENV_BASE_URL: "https://ignored.example"},
                    **_fast())
    assert r.ok
    assert ntfy.requests[0]["path"] == f"/ntfy/{FAKE_TOPIC}"
    d = alerts.resolve_destination({alerts.ENV_TOPIC: f"https://ntfy.example.org/{FAKE_TOPIC}"})
    assert d.url == f"https://ntfy.example.org/{FAKE_TOPIC}"


def test_the_file_is_the_only_source_when_set(tmp_path):
    good = {alerts.ENV_TOPIC: FAKE_TOPIC}
    missing = dict(good, **{alerts.ENV_TOPIC_FILE: str(tmp_path / "absent.txt")})
    with pytest.raises(alerts.AlertConfigError) as e:
        alerts.resolve_destination(missing)
    assert e.value.reason == "topic_file_unreadable"
    f = tmp_path / "t.txt"
    f.write_text("other_topic_from_the_file_xx\n", encoding="utf-8")
    d = alerts.resolve_destination(dict(good, **{alerts.ENV_TOPIC_FILE: str(f)}))
    assert d.topic == "other_topic_from_the_file_xx"


def test_blank_values_are_unset_and_nothing_configured_is_a_counted_failure(caplog):
    caplog.set_level(logging.ERROR, "field_core.alerts")
    env = {alerts.ENV_TOPIC_FILE: "  ", alerts.ENV_TOPIC: ""}
    r = alerts.send("rotation_failed", estate="gb10", env=env, **_fast())
    assert (r.ok, r.attempts, r.reason) == (False, 0, "not_configured")
    h = alerts.health_fields(env)
    assert h["alerts_failed"] == 1 and h["alerts_configured"] is False
    assert h["alerts_config_error"] == "not_configured"
    assert h["alerts_last_failure_class"] == "rotation_failed"
    assert "rotation_failed alert NOT delivered (not_configured" in caplog.text


@pytest.mark.parametrize("content,reason", [
    ("bad topic!", "topic_file_invalid"),            # whitespace inside
    ("bad/topic", "topic_invalid"),
    ("x" * 65, "topic_invalid"),
    ("http://ntfy.example.org/" + FAKE_TOPIC, "url_invalid"),      # plain http, not loopback
    ("https://user:pw@ntfy.example.org/" + FAKE_TOPIC, "url_invalid"),
    ("https://ntfy.example.org/" + FAKE_TOPIC + "?x=1", "url_invalid"),
    ("https://ntfy.example.org/" + FAKE_TOPIC + "#f", "url_invalid"),
    ("https://ntfy.example.org/", "topic_invalid"),
    ("short_topic", "topic_guessable"),
])
def test_invalid_configuration_is_refused_without_a_request(tmp_path, ntfy, content, reason):
    f = tmp_path / "t.txt"
    f.write_text(content, encoding="utf-8")
    r = alerts.send("test", estate="gb10", env={alerts.ENV_TOPIC_FILE: str(f)}, **_fast())
    assert (r.ok, r.reason, r.attempts) == (False, reason, 0)
    assert ntfy.requests == []


def test_base_url_must_be_https_or_loopback():
    with pytest.raises(alerts.AlertConfigError) as e:
        alerts.resolve_destination({alerts.ENV_TOPIC: FAKE_TOPIC,
                                    alerts.ENV_BASE_URL: "http://ntfy.example.org"})
    assert e.value.reason == "base_url_invalid"
    d = alerts.resolve_destination({alerts.ENV_TOPIC: FAKE_TOPIC,
                                    alerts.ENV_BASE_URL: "http://[::1]:8080/"})
    assert d.url == f"http://[::1]:8080/{FAKE_TOPIC}"


def test_a_short_topic_is_allowed_with_a_token(ntfy):
    r = alerts.send("test", estate="gb10",
                    env=_env(ntfy, **{alerts.ENV_TOPIC: "field-alerts", alerts.ENV_TOKEN: FAKE_TOKEN}),
                    **_fast())
    assert r.ok


# ------------------------------------------------------------------ headers

@pytest.mark.parametrize("cls,prio,tag", [
    ("rotation_failed", "5", "rotating_light"),
    ("rotation_overdue", "4", "hourglass"),
    ("breakglass_used", "5", "sos"),
    ("stage_transition", "4", "arrow_right"),
    ("test", "3", "test_tube"),
])
def test_priority_and_tags_per_alert_class(ntfy, cls, prio, tag):
    assert alerts.send(cls, estate="gb10", env=_env(ntfy), **_fast()).ok
    h = ntfy.requests[0]["headers"]
    assert h["Priority"] == prio
    assert tag in h["Tags"].split(",") and "field" in h["Tags"].split(",")
    assert h["Title"] == alerts.CLASSES[cls].title
    assert "Authorization" not in h


def test_token_is_sent_as_bearer_and_read_file_first(tmp_path, ntfy):
    tf = tmp_path / "token.txt"
    tf.write_text(FAKE_TOKEN + "\n", encoding="utf-8")
    env = _env(ntfy, **{alerts.ENV_TOKEN_FILE: str(tf), alerts.ENV_TOKEN: "tk_otherEnvTokenIgnored"})
    assert alerts.send("test", estate="gb10", env=env, **_fast()).ok
    assert ntfy.requests[0]["headers"]["Authorization"] == f"Bearer {FAKE_TOKEN}"


def test_an_invalid_token_is_refused():
    with pytest.raises(alerts.AlertConfigError) as e:
        alerts.resolve_destination({alerts.ENV_TOPIC: FAKE_TOPIC, alerts.ENV_TOKEN: "bad token"})
    assert e.value.reason == "token_invalid"


def test_unknown_alert_class_is_a_programming_error(ntfy):
    with pytest.raises(ValueError):
        alerts.send("nope", estate="gb10", env=_env(ntfy))
    assert ntfy.requests == []


# -------------------------------------------------------------------- retry

def test_5xx_and_429_are_retried_with_backoff_then_succeed(ntfy):
    ntfy.script = [(503, 0), (429, 0)]
    slept = []
    r = alerts.send("rotation_failed", estate="gb10", env=_env(ntfy),
                    sleep=slept.append, backoff_s=(0.5, 1.5), timeout_s=2.0)
    assert (r.ok, r.attempts) == (True, 3)
    assert slept == [0.5, 1.5]
    assert len(ntfy.requests) == 3
    assert alerts.health_fields()["alerts_sent"] == 1
    assert alerts.health_fields()["alerts_failed"] == 0


def test_a_4xx_is_not_retried(ntfy):
    ntfy.script = [(403, 0)]
    r = alerts.send("test", estate="gb10", env=_env(ntfy), **_fast())
    assert (r.ok, r.attempts, r.reason, r.http_status) == (False, 1, "http_403", 403)
    assert len(ntfy.requests) == 1


def test_retries_are_bounded_and_the_failure_is_counted(ntfy, caplog):
    caplog.set_level(logging.ERROR, "field_core.alerts")
    ntfy.default = (500, 0)
    r = alerts.send("breakglass_used", estate="gb10", env=_env(ntfy), max_attempts=99, **_fast())
    assert (r.ok, r.attempts, r.reason) == (False, alerts.MAX_ATTEMPTS_CAP, "http_500")
    assert len(ntfy.requests) == alerts.MAX_ATTEMPTS_CAP
    h = alerts.health_fields(_env(ntfy))
    assert h["alerts_failed"] == 1 and h["alerts_last_failure_reason"] == "http_500"
    assert h["alerts_last_failure_class"] == "breakglass_used"
    assert re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", h["alerts_last_failure_at"])
    assert "breakglass_used alert NOT delivered (http_500 after 5 attempt(s))" in caplog.text


def test_each_attempt_times_out_and_the_whole_send_is_bounded(ntfy):
    ntfy.default = (200, 1.5)
    t0 = time.monotonic()
    r = alerts.send("test", estate="gb10", env=_env(ntfy), timeout_s=0.2, max_attempts=2,
                    sleep=lambda s: None)
    elapsed = time.monotonic() - t0
    assert (r.ok, r.reason, r.attempts) == (False, "timeout", 2)
    assert elapsed < 1.4


def test_network_error_is_retried_and_counted():
    import urllib.error

    class Refusing:
        calls = 0

        def open(self, req, timeout):
            Refusing.calls += 1
            raise urllib.error.URLError(ConnectionRefusedError(10061, "refused"))

    r = alerts.send("test", estate="gb10", env={alerts.ENV_TOPIC: FAKE_TOPIC},
                    max_attempts=2, opener=Refusing(), **_fast())
    assert (r.ok, r.reason, r.attempts) == (False, "network", 2)
    assert Refusing.calls == 2
    assert alerts.health_fields()["alerts_failed"] == 1


def test_a_redirect_is_never_followed(ntfy):
    ntfy.script = [(302, 0)]
    r = alerts.send("test", estate="gb10", env=_env(ntfy, **{alerts.ENV_TOKEN: FAKE_TOKEN}),
                    **_fast())
    assert (r.ok, r.reason, r.attempts) == (False, "http_302", 1)
    assert len(ntfy.requests) == 1


# ------------------------------------------------------------------ content

def test_content_carries_no_secret_key_token_hash_or_topic(ntfy, capsys, caplog):
    """The proof the brief asks for: an alert whose caller fields carry a fake
    key, a 64-hex hash, a 16-hex fingerprint, the token and the topic sends
    none of them, and none reach a log, the result or /health."""
    caplog.set_level(logging.DEBUG, "field_core.alerts")
    env = _env(ntfy, **{alerts.ENV_TOKEN: FAKE_TOKEN})
    cases = [
        dict(subject=FAKE_KEY, detail=f"hash {FAKE_HASH}"),
        dict(subject="svc-rotator", detail=f"fp={FAKE_FP}"),
        dict(subject="svc-rotator", detail=f"token {FAKE_TOKEN}"),
        dict(subject=FAKE_TOPIC, detail=f"see {FAKE_TOPIC.upper()}"),
        dict(subject="svc-rotator", detail="-----BEGIN PRIVATE KEY-----"),
        dict(subject="svc-rotator", detail="Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFy"),
    ]
    for c in cases:
        r = alerts.send("rotation_failed", estate="gb10", env=env, **c, **_fast())
        assert r.ok and r.withheld_fields
        assert repr(r).find(FAKE_TOPIC) == -1
    forbidden = [FAKE_TOPIC, FAKE_TOPIC.upper(), FAKE_TOKEN, FAKE_KEY, FAKE_HASH, FAKE_FP,
                 "BEGIN PRIVATE", "Zm9vYmFyYmF6"]
    out = capsys.readouterr()
    sinks = [caplog.text, out.out, out.err, repr(alerts.health_fields(env)),
             repr(alerts.resolve_destination(env)), str(alerts.resolve_destination(env))]
    for req in ntfy.requests:
        sinks += [req["body"], req["headers"]["Title"], req["headers"]["Tags"]]
        assert alerts.WITHHELD in req["body"]
    for s in sinks:
        for f in forbidden:
            assert f not in s, (f, s)
    assert alerts.health_fields(env)["alerts_content_withheld"] == 8


def test_clean_fields_pass_through_unchanged(ntfy):
    r = alerts.send("stage_transition", estate="gb10", subject="stage-2",
                    detail="log-only -> enforce after 24 h soak; build 659f31b",
                    env=_env(ntfy), **_fast())
    assert r.ok and r.withheld_fields == ()
    body = ntfy.requests[0]["body"]
    assert "estate: gb10" in body and "subject: stage-2" in body
    assert "detail: log-only -> enforce after 24 h soak; build 659f31b" in body
    assert alerts.WITHHELD not in body


@pytest.mark.parametrize("text,problem", [
    ("fok_x", "secret_prefix"), ("TK_x", "secret_prefix"), ("a" * 11 + "1", "hex_run"),
    ("x" * 31 + "1", "opaque_run"), ("-----BEGIN X", "pem"), ("ok text 659f31b", None),
])
def test_content_problem_rules(text, problem):
    assert alerts.content_problem(text) == problem


def test_a_broken_template_is_caught_by_the_whole_payload_check(monkeypatch, ntfy):
    bad = alerts.AlertClass("test", 3, ("test",), "t", f"summary with {FAKE_HASH}")
    monkeypatch.setitem(alerts.CLASSES, "test", bad)
    r = alerts.send("test", estate="gb10", env=_env(ntfy), **_fast())
    assert r.ok and "body" in r.withheld_fields
    assert FAKE_HASH not in ntfy.requests[0]["body"]
    assert "(body withheld: failed content check)" in ntfy.requests[0]["body"]


def test_the_module_never_touches_the_ledger():
    src = Path(alerts.__file__).read_text(encoding="utf-8")
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
    assert not any(m.startswith("field_core") for m in mods), mods


# ------------------------------------------------------------ /health, async

def test_health_fields_merge_into_a_caller_health_route(ntfy):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    api = FastAPI()
    env = _env(ntfy)

    @api.get("/health")
    def health():
        return {"status": "ok", **alerts.health_fields(env)}

    ntfy.default = (500, 0)
    alerts.send("rotation_failed", estate="gb10", env=env, max_attempts=1, **_fast())
    body = TestClient(api).get("/health").json()
    assert body["alerts_failed"] == 1 and body["alerts_configured"] is True
    assert body["alerts_last_failure_reason"] == "http_500"
    assert FAKE_TOPIC not in repr(body)


def test_asend_runs_in_a_thread(ntfy):
    r = asyncio.run(alerts.asend("test", estate="gb10", env=_env(ntfy), **_fast()))
    assert r.ok and len(ntfy.requests) == 1


# ---------------------------------------------------------------------- CLI

def _cli_env(ntfy):
    return {alerts.ENV_TOPIC: FAKE_TOPIC, alerts.ENV_BASE_URL: ntfy.base}


def test_alert_test_cli_sends_a_clearly_marked_test_and_never_prints_the_topic(ntfy, monkeypatch):
    for k, v in _cli_env(ntfy).items():
        monkeypatch.setenv(k, v)
    res = CliRunner().invoke(app, ["alert-test", "--estate", "estate-under-test"])
    assert res.exit_code == 0, res.output
    assert "TEST alert delivered" in res.output
    assert FAKE_TOPIC not in res.output
    req = ntfy.requests[0]
    assert "TEST" in req["headers"]["Title"] and "no action needed" in req["headers"]["Title"]
    assert "test" in req["headers"]["Tags"].split(",")
    assert req["body"].startswith("This is a TEST alert")
    assert "estate: estate-under-test" in req["body"]
    assert re.search(r"^test id: [0-9a-f]{6}$", req["body"], re.M)


def test_alert_test_cli_exit_codes(ntfy, monkeypatch):
    res = CliRunner().invoke(app, ["alert-test"])
    assert res.exit_code == 2 and "reason=not_configured" in res.output
    for k, v in _cli_env(ntfy).items():
        monkeypatch.setenv(k, v)
    ntfy.default = (500, 0)
    monkeypatch.setattr(alerts, "DEFAULT_BACKOFF_S", (0.0,))
    res = CliRunner().invoke(app, ["alert-test"])
    assert res.exit_code == 1 and "NOT delivered (reason=http_500" in res.output
    assert FAKE_TOPIC not in res.output


def test_topic_init_writes_an_unguessable_topic_and_never_prints_it(tmp_path):
    out = tmp_path / ".field-local" / "ntfy-topic.txt"
    res = CliRunner().invoke(app, ["alert-topic-init", "--out", str(out)])
    assert res.exit_code == 0, res.output
    topic = out.read_text(encoding="utf-8").strip()
    assert alerts.TOPIC_RE.match(topic) and len(topic) >= 38
    assert topic not in res.output and "(not shown)" in res.output
    d = alerts.resolve_destination({alerts.ENV_TOPIC_FILE: str(out)})
    assert d.topic == topic
    again = CliRunner().invoke(app, ["alert-topic-init", "--out", str(out)])
    assert again.exit_code == 1 and out.read_text(encoding="utf-8").strip() == topic
    forced = CliRunner().invoke(app, ["alert-topic-init", "--out", str(out), "--force"])
    assert forced.exit_code == 0
    assert out.read_text(encoding="utf-8").strip() != topic
    if os.name == "posix":
        assert (out.stat().st_mode & 0o077) == 0


def test_new_topics_do_not_repeat():
    topics = {alerts.new_topic() for _ in range(200)}
    assert len(topics) == 200


# ------------------------------------------- review fixes (PR #56 round 1)

class _Trickle:
    """A peer that sends the status line, then one header byte every
    ``interval`` seconds for up to ``total`` seconds. Each byte arrives well
    inside a per-socket-operation timeout, so only a wall-clock deadline per
    attempt can bound the send. Records when it noticed each client leave."""

    def __init__(self, interval: float = 0.1, total: float = 4.0, body: bool = False):
        import socket

        self.interval, self.total, self.body = interval, total, body
        self.gone_at: list[float] = []
        self.accepted = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self._stop = threading.Event()
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            self.accepted += 1
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        conn.settimeout(2.0)
        try:
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                data += chunk
            if self.body:   # complete headers, then a trickled body
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n")
            else:           # the status line, then trickled header bytes
                conn.sendall(b"HTTP/1.1 200 OK\r\n")
            end = time.monotonic() + self.total
            while time.monotonic() < end and not self._stop.is_set():
                conn.sendall(b"X")
                time.sleep(self.interval)
        except OSError:
            self.gone_at.append(time.monotonic())
        finally:
            conn.close()

    def close(self):
        self._stop.set()
        self.sock.close()


def test_a_trickling_server_cannot_stretch_an_attempt_past_its_deadline():
    """F1: urllib's timeout bounds each socket operation, not the attempt. A
    peer trickling header bytes kept the old send running for seconds."""
    srv = _Trickle(interval=0.1, total=4.0)
    try:
        t0 = time.monotonic()
        r = alerts.send("rotation_failed", estate="gb10",
                        env={alerts.ENV_TOPIC: FAKE_TOPIC, alerts.ENV_BASE_URL: srv.base},
                        timeout_s=0.3, max_attempts=2, sleep=lambda s: None)
        returned = time.monotonic()
        assert (r.ok, r.reason, r.attempts) == (False, "timeout", 2)
        # stated bound: max_attempts * timeout_s + back-off (0 here) = 0.6 s, plus slack
        assert returned - t0 < 1.5, returned - t0
        h = alerts.health_fields()
        assert h["alerts_failed"] == 1 and h["alerts_last_failure_reason"] == "timeout"
        # the abandoned attempts' connections are shut down, not left trickling
        deadline = time.monotonic() + 3.0
        while len(srv.gone_at) < srv.accepted and time.monotonic() < deadline:
            time.sleep(0.05)
        assert srv.accepted == 2 and len(srv.gone_at) == 2, (srv.accepted, srv.gone_at)
    finally:
        srv.close()


def test_a_trickled_response_body_does_not_turn_a_delivery_into_a_timeout():
    """F1: the status line is enough; the body is never read. Reading it would
    let a slow body push a delivered alert past the deadline, and the retry
    would then deliver it twice."""
    srv = _Trickle(interval=0.1, total=4.0, body=True)
    try:
        t0 = time.monotonic()
        r = alerts.send("rotation_failed", estate="gb10",
                        env={alerts.ENV_TOPIC: FAKE_TOPIC, alerts.ENV_BASE_URL: srv.base},
                        timeout_s=0.5, max_attempts=2, sleep=lambda s: None)
        elapsed = time.monotonic() - t0
        assert (r.ok, r.attempts, r.http_status) == (True, 1, 200)
        assert elapsed < 0.5, elapsed
        assert srv.accepted == 1
    finally:
        srv.close()


def test_a_hung_name_lookup_cannot_stretch_an_attempt():
    """F1: no socket timeout covers getaddrinfo. An opener that hangs stands
    in for a resolver that does not answer."""
    import urllib.error

    release = threading.Event()

    class Hanging:
        calls = 0

        def open(self, req, timeout):
            Hanging.calls += 1
            release.wait(5.0)
            raise urllib.error.URLError(OSError("lookup failed"))

    try:
        t0 = time.monotonic()
        r = alerts.send("test", estate="gb10", env={alerts.ENV_TOPIC: FAKE_TOPIC},
                        timeout_s=0.2, max_attempts=2, opener=Hanging(), sleep=lambda s: None)
        elapsed = time.monotonic() - t0
    finally:
        release.set()
    assert (r.ok, r.reason, r.attempts) == (False, "timeout", 2)
    assert Hanging.calls == 2
    assert elapsed < 1.2, elapsed


@pytest.mark.parametrize("content", [
    "https://a..b/" + FAKE_TOPIC,                          # empty label
    "https://" + "x" * 70 + ".example/" + FAKE_TOPIC,      # label over 63 characters
])
def test_a_host_that_cannot_be_encoded_is_a_configuration_error(tmp_path, ntfy, content):
    """F2: such a host used to raise UnicodeEncodeError out of send(), uncounted."""
    f = tmp_path / "t.txt"
    f.write_text(content, encoding="utf-8")
    env = {alerts.ENV_TOPIC_FILE: str(f)}
    r = alerts.send("rotation_failed", estate="gb10", env=env, **_fast())
    assert (r.ok, r.reason, r.attempts) == (False, "url_invalid", 0)
    h = alerts.health_fields(env)
    assert h["alerts_failed"] == 1 and h["alerts_configured"] is False
    assert h["alerts_config_error"] == "url_invalid"
    assert FAKE_TOPIC not in repr(h)
    assert ntfy.requests == []


def test_a_base_url_host_that_cannot_be_encoded_is_refused():
    with pytest.raises(alerts.AlertConfigError) as e:
        alerts.resolve_destination({alerts.ENV_TOPIC: FAKE_TOPIC,
                                    alerts.ENV_BASE_URL: "https://a..b"})
    assert e.value.reason == "base_url_invalid"


def test_a_nul_in_the_topic_file_path_is_a_configuration_error():
    with pytest.raises(alerts.AlertConfigError) as e:
        alerts.resolve_destination({alerts.ENV_TOPIC_FILE: "topic\x00.txt"})
    assert e.value.reason == "topic_file_unreadable"


def test_an_unexpected_error_in_an_attempt_is_counted_and_never_raised(caplog):
    """F2: send() never raises past its contract, whatever the transport throws."""
    caplog.set_level(logging.ERROR, "field_core.alerts")

    class Exploding:
        calls = 0

        def open(self, req, timeout):
            Exploding.calls += 1
            raise UnicodeEncodeError("idna", "x", 0, 1, "label empty or too long")

    r = alerts.send("rotation_failed", estate="gb10", env={alerts.ENV_TOPIC: FAKE_TOPIC},
                    max_attempts=3, opener=Exploding(), **_fast())
    assert (r.ok, r.reason, r.attempts) == (False, "error", 1)   # deterministic: not retried
    assert Exploding.calls == 1
    h = alerts.health_fields()
    assert h["alerts_failed"] == 1 and h["alerts_last_failure_reason"] == "error"
    assert "rotation_failed alert NOT delivered (error after 1 attempt(s))" in caplog.text
    assert FAKE_TOPIC not in caplog.text


def test_a_configured_token_without_the_tk_prefix_is_withheld(ntfy):
    """F3: only the configured-secret rule can catch this token (no tk_ prefix,
    under 32 characters, no 12-hex run), so this test fails if the token is
    ever dropped from the content check."""
    token = "fakeSelfHosted123"                      # fake self-hosted token shape
    assert alerts.content_problem(f"auth {token} refused") is None
    env = _env(ntfy, **{alerts.ENV_TOKEN: token})
    r = alerts.send("rotation_failed", estate="gb10", subject="svc-rotator",
                    detail=f"auth {token.upper()} refused", env=env, **_fast())
    assert r.ok and r.withheld_fields == ("detail",)
    req = ntfy.requests[0]
    assert req["headers"]["Authorization"] == f"Bearer {token}"
    assert token.lower() not in req["body"].lower()
    assert alerts.WITHHELD in req["body"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
def test_topic_init_force_tightens_an_existing_files_mode(tmp_path):
    """F7: os.open applies 0o600 only when it creates the file."""
    out = tmp_path / "ntfy-topic.txt"
    out.write_text("old\n", encoding="utf-8")
    os.chmod(out, 0o644)
    res = CliRunner().invoke(app, ["alert-topic-init", "--out", str(out), "--force"])
    assert res.exit_code == 0, res.output
    assert (out.stat().st_mode & 0o777) == 0o600
    assert out.read_text(encoding="utf-8").strip() != "old"


def test_the_cli_never_renders_locals_in_a_traceback():
    """F8: alert-test's frames hold the Bearer header and the topic URL."""
    assert app.pretty_exceptions_show_locals is False
