"""Push alerts to ntfy (alert channel K10; Don's decision P36 item 3).

Who calls this: the key rotator (``rotation_failed``), the dead-man check
(``rotation_overdue``), the break-glass observer (``breakglass_used``), the
Phase G stage controller (``stage_transition``) and ``field alert-test``
(``test``). Runbook: ``docs/runbooks/ntfy-alerts.md`` (configuration, the
one-time BOOTSTRAP, what is verified against ntfy's docs and what is not).

Configuration (read on every call, so a replaced file needs no restart):

* ``FIELD_NTFY_TOPIC_FILE``: a path whose stripped content is either a bare
  topic or a full topic URL (``https://ntfy.sh/<topic>`` or a self-hosted
  ``https://ntfy.example.org[/prefix]/<topic>``). When set (non-blank) it is
  the ONLY topic source: an unusable file never falls back to the env value
  (the same rule as ``FIELD_OPERATOR_KEY_FILE``).
* ``FIELD_NTFY_TOPIC``: the same content inline, used only when no file is set.
* ``FIELD_NTFY_BASE_URL``: the server for a BARE topic; default
  ``https://ntfy.sh``. Ignored when the topic content is a full URL.
* ``FIELD_NTFY_TOKEN_FILE`` / ``FIELD_NTFY_TOKEN`` (optional, same file-first
  rule): an ntfy access token, sent as ``Authorization: Bearer <token>``.

The topic is a credential (on ntfy.sh "the topic is essentially a password",
https://docs.ntfy.sh/publish/#picking-a-topic). It is therefore never taken
from a command line, never logged, never returned, never in ``/health`` and
never in a ledger row (this module writes no ledger rows at all). Without a
token a topic shorter than :data:`MIN_TOPIC_LEN_WITHOUT_TOKEN` is refused as
guessable. Only ``https`` is accepted, except plain ``http`` to a loopback
host (a local relay or the tests). Redirects are never followed (a redirect
would carry the token to another host).

Content: every alert is built from a fixed per-class template plus a few
caller fields (``estate``, ``subject``, ``detail``). Each field must match a
narrow charset and pass :func:`content_problem`: no key or token prefix
(``fok_``, ``tk_``), no run of 12+ hex digits (a hash or a 16-hex
fingerprint), no 32+ character opaque token run, no PEM block, and neither the
configured topic nor the token. A field that fails is replaced by
:data:`WITHHELD` and counted (``alerts_content_withheld``); the alert is still
sent, because a failure alert that never arrives is worse than one with a
field withheld. The rendered title, body and tags are checked again before
sending.

Delivery: ``POST`` to the topic URL with ``Title``, ``Priority`` and ``Tags``
headers (https://docs.ntfy.sh/publish/#message-title, #message-priority,
#tags-emojis). Bounded retry: at most :data:`MAX_ATTEMPTS_CAP` attempts, each
under a wall-clock deadline (name lookup, connect, TLS and the response status
line; the response body is never read), with fixed back-off between them;
retried on a timeout, a network error, 429 and 5xx; not retried on any other
status. Every failure is counted per process and shown by
:func:`health_fields` (merge it into the caller's ``GET /health``) and logged
as one line naming the alert class and a fixed reason (``not_configured``,
``topic_invalid``, ``url_invalid``, ``timeout``, ``network``,
``http_<status>``, ``error``, ...), never the URL, topic, token or response.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import http.client
import ipaddress
import logging
import os
import re
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

log = logging.getLogger("field_core.alerts")

ENV_TOPIC_FILE = "FIELD_NTFY_TOPIC_FILE"
ENV_TOPIC = "FIELD_NTFY_TOPIC"
ENV_BASE_URL = "FIELD_NTFY_BASE_URL"
ENV_TOKEN_FILE = "FIELD_NTFY_TOKEN_FILE"
ENV_TOKEN = "FIELD_NTFY_TOKEN"
DEFAULT_BASE_URL = "https://ntfy.sh"

#: ntfy topic names: letters, numbers, underscores and dashes, up to 64
#: characters (https://docs.ntfy.sh/publish/#picking-a-topic).
TOPIC_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
#: without an access token the topic is the only secret: refuse short ones.
MIN_TOPIC_LEN_WITHOUT_TOKEN = 20
_TOKEN_RE = re.compile(r"^[A-Za-z0-9._~+/=-]{8,256}$")
MAX_CONFIG_FILE_BYTES = 4096
_LOOPBACK_NAMES = {"localhost"}

DEFAULT_TIMEOUT_S = 5.0
MAX_TIMEOUT_S = 30.0
DEFAULT_MAX_ATTEMPTS = 3
MAX_ATTEMPTS_CAP = 5
#: sleep before attempt 2, 3, ... (the last value repeats)
DEFAULT_BACKOFF_S = (1.0, 2.0)
#: ntfy.sh message limit is 4,096 bytes (https://docs.ntfy.sh/publish/#limitations)
MAX_BODY_BYTES = 1024

WITHHELD = "(withheld: failed content check)"
_FIELD_RE = {
    "estate": re.compile(r"^[A-Za-z0-9._@:-]{1,64}$"),
    "subject": re.compile(r"^[A-Za-z0-9._@:-]{1,64}$"),
    "detail": re.compile(r"^[ -~]{1,200}$"),
}

# content_problem patterns
_SECRET_PREFIX_RE = re.compile(r"(?i)(fok_|tk_)")
_HEX_RUN_RE = re.compile(r"[0-9A-Fa-f]{12,}")
_OPAQUE_RUN_RE = re.compile(r"[A-Za-z0-9+/=_-]{32,}")
_PEM_RE = re.compile(r"-----BEGIN")


@dataclass(frozen=True)
class AlertClass:
    name: str
    #: ntfy priority 1-5 (5 = max/urgent: long vibration bursts, pop-over;
    #: 4 = high; 3 = default: short vibration and sound)
    priority: int
    tags: tuple[str, ...]
    title: str
    summary: str


#: Priority and tags per alert class. Tags that match an emoji short code are
#: shown as emoji (https://docs.ntfy.sh/publish/#tags-emojis); "field" and
#: "test" show as plain tags.
CLASSES: dict[str, AlertClass] = {
    "rotation_failed": AlertClass(
        "rotation_failed", 5, ("rotating_light", "key", "field"),
        "FIELD: key rotation FAILED",
        "A key rotation failed. The estate keeps its current keys; see the rotation runbook."),
    "rotation_overdue": AlertClass(
        "rotation_overdue", 4, ("warning", "hourglass", "field"),
        "FIELD: key rotation overdue",
        "No rotation completed in time, or a key is near its expiry (dead-man check)."),
    "breakglass_used": AlertClass(
        "breakglass_used", 5, ("sos", "rotating_light", "field"),
        "FIELD: break-glass key used",
        "The break-glass identity authenticated or was tried. Revoke it after the incident."),
    "stage_transition": AlertClass(
        "stage_transition", 4, ("arrow_right", "field"),
        "FIELD: Phase G stage transition",
        "The stage controller moved a Phase G stage."),
    "test": AlertClass(
        "test", 3, ("test_tube", "test", "field"),
        "FIELD TEST ALERT - no action needed",
        "This is a TEST alert sent by 'field alert-test'. No action needed. "
        "If you can read this, FIELD alerts reach this device."),
}


class AlertConfigError(Exception):
    """``reason`` is a fixed token; the message never carries file content."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Destination:
    url: str
    token: str | None
    topic: str

    def __repr__(self) -> str:  # never the url, topic or token
        return f"Destination(configured, token={'yes' if self.token else 'no'})"

    __str__ = __repr__


@dataclass(frozen=True)
class AlertResult:
    ok: bool
    alert_class: str
    attempts: int
    reason: str | None = None
    http_status: int | None = None
    withheld_fields: tuple[str, ...] = ()


# ---------------------------------------------------------------- counters

_lock = threading.Lock()


def _zero_stats() -> dict:
    return {"sent": 0, "failed": 0, "content_withheld": 0,
            "last_failure_reason": None, "last_failure_class": None,
            "last_failure_at": None, "last_success_at": None}


_stats = _zero_stats()


def reset_stats() -> None:
    """Tests only."""
    with _lock:
        _stats.clear()
        _stats.update(_zero_stats())


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _count_failure(alert_class: str, reason: str, attempts: int) -> None:
    with _lock:
        _stats["failed"] += 1
        _stats["last_failure_reason"] = reason
        _stats["last_failure_class"] = alert_class
        _stats["last_failure_at"] = _utcnow()
    log.error("field alerts: %s alert NOT delivered (%s after %d attempt(s)); "
              "counted in alerts_failed", alert_class, reason, attempts)


def _count_success() -> None:
    with _lock:
        _stats["sent"] += 1
        _stats["last_success_at"] = _utcnow()


def health_fields(env: Mapping[str, str] | None = None) -> dict:
    """Merge into the caller's ``GET /health``. Counters are per process.
    ``alerts_configured`` / ``alerts_config_error`` re-read the configuration
    now. Never the URL, the topic, the token or any part of them."""
    try:
        resolve_destination(env)
        configured, error = True, None
    except AlertConfigError as exc:
        configured, error = False, exc.reason
    with _lock:
        s = dict(_stats)
    return {
        "alerts_channel": "ntfy",
        "alerts_configured": configured,
        "alerts_config_error": error,
        "alerts_sent": s["sent"],
        "alerts_failed": s["failed"],
        "alerts_content_withheld": s["content_withheld"],
        "alerts_last_failure_reason": s["last_failure_reason"],
        "alerts_last_failure_class": s["last_failure_class"],
        "alerts_last_failure_at": s["last_failure_at"],
        "alerts_last_success_at": s["last_success_at"],
    }


# ----------------------------------------------------------- configuration

def _read_small_file(path: str, what: str) -> str:
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_CONFIG_FILE_BYTES + 1)
    except (OSError, ValueError):  # ValueError: a NUL in the path
        raise AlertConfigError(f"{what}_file_unreadable") from None
    if len(raw) > MAX_CONFIG_FILE_BYTES:
        raise AlertConfigError(f"{what}_file_invalid")
    try:
        text = raw.decode("utf-8-sig").strip()
    except UnicodeDecodeError:
        raise AlertConfigError(f"{what}_file_invalid") from None
    if not text or any(c.isspace() for c in text):
        raise AlertConfigError(f"{what}_file_invalid")
    return text


def _file_or_env(env: Mapping[str, str], file_var: str, var: str, what: str) -> str | None:
    path = (env.get(file_var) or "").strip()
    if path:
        return _read_small_file(path, what)
    value = (env.get(var) or "").strip()
    return value or None


def _is_loopback(host: str) -> bool:
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _host_encodes(host: str) -> bool:
    """The connect step encodes the host name with the ``idna`` codec; an
    empty label (``a..b``) or a label over 63 characters fails there with a
    ``UnicodeError``, which is not an ``OSError``. Refuse it here instead."""
    try:
        host.encode("idna")
    except UnicodeError:
        return False
    return True


def _check_server_url(url: str, reason: str) -> urllib.parse.SplitResult:
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or ""
        parts.port  # noqa: B018  (raises on a bad port)
    except ValueError:
        raise AlertConfigError(reason) from None
    if (not host or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment or "@" in parts.netloc
            or not _host_encodes(host)):
        raise AlertConfigError(reason)
    if parts.scheme == "https":
        return parts
    if parts.scheme == "http" and _is_loopback(host):
        return parts
    raise AlertConfigError(reason)


def resolve_destination(env: Mapping[str, str] | None = None) -> Destination:
    """The topic URL and optional token from the environment (file first).
    Raises :class:`AlertConfigError` with a fixed reason."""
    env = os.environ if env is None else env
    content = _file_or_env(env, ENV_TOPIC_FILE, ENV_TOPIC, "topic")
    if content is None:
        raise AlertConfigError("not_configured")
    token = _file_or_env(env, ENV_TOKEN_FILE, ENV_TOKEN, "token")
    if token is not None and not _TOKEN_RE.match(token):
        raise AlertConfigError("token_invalid")
    if content.lower().startswith(("http://", "https://")):
        parts = _check_server_url(content, "url_invalid")
        path = parts.path.rstrip("/")
        topic = path.rsplit("/", 1)[-1] if "/" in path else ""
        if not TOPIC_RE.match(topic):
            raise AlertConfigError("topic_invalid")
        url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    else:
        topic = content
        if not TOPIC_RE.match(topic):
            raise AlertConfigError("topic_invalid")
        base = (env.get(ENV_BASE_URL) or "").strip() or DEFAULT_BASE_URL
        parts = _check_server_url(base, "base_url_invalid")
        url = urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path.rstrip("/") + "/" + topic, "", ""))
    if token is None and len(topic) < MIN_TOPIC_LEN_WITHOUT_TOKEN:
        raise AlertConfigError("topic_guessable")
    return Destination(url=url, token=token, topic=topic)


# ----------------------------------------------------------------- content

def content_problem(text: str, *, secrets_: tuple[str, ...] = ()) -> str | None:
    """Why ``text`` must not go into an alert, or None. ``secrets_`` are the
    configured topic and token (compared case-insensitively)."""
    if _SECRET_PREFIX_RE.search(text):
        return "secret_prefix"
    if _HEX_RUN_RE.search(text):
        return "hex_run"
    if _OPAQUE_RUN_RE.search(text):
        return "opaque_run"
    if _PEM_RE.search(text):
        return "pem"
    low = text.lower()
    for s in secrets_:
        if s and s.lower() in low:
            return "configured_secret"
    return None


def _clean_field(name: str, value: str | None, secrets_: tuple[str, ...],
                 withheld: list[str]) -> str | None:
    if value is None:
        return None
    value = str(value)
    if not _FIELD_RE[name].match(value) or content_problem(value, secrets_=secrets_):
        withheld.append(name)
        log.warning("field alerts: %s field withheld (failed content check)", name)
        return WITHHELD
    return value


def render(alert_class: str, *, estate: str, subject: str | None = None,
           detail: str | None = None, secrets_: tuple[str, ...] = (),
           sent_at: str | None = None, test_id: str | None = None,
           ) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    """(title, body, tags, withheld field names). Raises ``ValueError`` on an
    unknown alert class (a programming error)."""
    cls = CLASSES.get(alert_class)
    if cls is None:
        raise ValueError(f"unknown alert class {alert_class!r}")
    withheld: list[str] = []
    estate_v = _clean_field("estate", estate, secrets_, withheld)
    subject_v = _clean_field("subject", subject, secrets_, withheld)
    detail_v = _clean_field("detail", detail, secrets_, withheld)
    lines = [cls.summary, f"estate: {estate_v}"]
    if subject_v is not None:
        lines.append(f"subject: {subject_v}")
    if detail_v is not None:
        lines.append(f"detail: {detail_v}")
    if test_id is not None:
        lines.append(f"test id: {test_id}")
    lines.append(f"sent: {sent_at or _utcnow()}")
    body = "\n".join(lines)
    title, tags = cls.title, cls.tags
    # Defence in depth: the whole payload once more. Template text passes, so
    # this only fires if a template or the field rules are ever broken.
    if content_problem(title, secrets_=secrets_):
        title = f"FIELD alert: {alert_class}"
        withheld.append("title")
    if content_problem(",".join(tags), secrets_=secrets_):
        tags = ("field",)
        withheld.append("tags")
    if content_problem(body, secrets_=secrets_):
        body = f"FIELD alert: {alert_class}\n(body withheld: failed content check)"
        withheld.append("body")
    if withheld:
        with _lock:
            _stats["content_withheld"] += len(withheld)
    return title, body, tags, tuple(withheld)


# ---------------------------------------------------------------- delivery

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None  # urllib then raises HTTPError(code)


_CONNS_ATTR = "_field_alert_conns"


def _tracking(http_class, req):
    """Wrap urllib's connection class so the attempt's connections are
    recorded on the request; an attempt past its deadline shuts them down."""
    conns = getattr(req, _CONNS_ATTR, None)
    if conns is None:
        return http_class

    def factory(*args, **kwargs):
        conn = http_class(*args, **kwargs)
        conns.append(conn)
        return conn

    return factory


class _TrackingHTTPHandler(urllib.request.HTTPHandler):
    def do_open(self, http_class, req, **kwargs):
        return super().do_open(_tracking(http_class, req), req, **kwargs)


class _TrackingHTTPSHandler(urllib.request.HTTPSHandler):
    def do_open(self, http_class, req, **kwargs):
        return super().do_open(_tracking(http_class, req), req, **kwargs)


_OPENER = urllib.request.build_opener(_NoRedirect, _TrackingHTTPHandler, _TrackingHTTPSHandler)
_RETRY_STATUSES = frozenset({429}) | frozenset(range(500, 600))


def _post_once(req: urllib.request.Request, timeout_s: float,
               opener) -> tuple[bool, str | None, int | None, bool]:
    """(ok, reason, status, retryable). The status line is all that is used:
    the response body is never read (ntfy's reply names the topic, and a
    trickled body would only stretch the attempt). Anything else it raises
    is caught by :func:`_attempt`."""
    try:
        with opener.open(req, timeout=timeout_s) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        return False, f"http_{status}", status, status in _RETRY_STATUSES
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            return False, "timeout", None, True
        return False, "network", None, True
    except (TimeoutError, socket.timeout):
        return False, "timeout", None, True
    except (OSError, http.client.HTTPException):
        return False, "network", None, True
    if 200 <= status < 300:
        return True, None, status, False
    return False, f"http_{status}", status, status in _RETRY_STATUSES


def _shut_down(conns: list) -> None:
    """Best effort: wake a worker blocked on a socket that is past its deadline."""
    for conn in list(conns):
        try:
            sock = getattr(conn, "sock", None)
            if sock is not None:
                sock.shutdown(socket.SHUT_RDWR)
        except Exception:  # noqa: BLE001
            pass
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _attempt(url: str, body: bytes, headers: dict, timeout_s: float,
             opener) -> tuple[bool, str | None, int | None, bool]:
    """One attempt under a wall-clock deadline of ``timeout_s``.

    urllib's ``timeout`` bounds each socket operation, not the request: a peer
    that trickles header bytes keeps every ``recv`` under it, and the name
    lookup is not covered at all. So the request runs in a daemon worker
    thread and the caller waits at most ``timeout_s`` for it. Past the
    deadline the attempt counts as ``timeout``, the worker's connection is
    shut down and its late result, if any, is discarded."""
    conns: list = []
    outcome: list = []

    def work() -> None:
        try:
            req = urllib.request.Request(url, data=body, method="POST", headers=headers)
            setattr(req, _CONNS_ATTR, conns)
            outcome.append(_post_once(req, timeout_s, opener))
        except Exception:  # noqa: BLE001  never past send()'s contract; fixed reason, not retried
            outcome.append((False, "error", None, False))

    worker = threading.Thread(target=work, name="field-alerts-post", daemon=True)
    worker.start()
    worker.join(timeout_s)
    if outcome:
        return outcome[0]
    _shut_down(conns)
    return False, "timeout", None, True


def send(alert_class: str, *, estate: str, subject: str | None = None,
         detail: str | None = None, env: Mapping[str, str] | None = None,
         timeout_s: float = DEFAULT_TIMEOUT_S, max_attempts: int = DEFAULT_MAX_ATTEMPTS,
         backoff_s: tuple[float, ...] | None = None,
         sleep: Callable[[float], None] = time.sleep, opener=None,
         test_id: str | None = None) -> AlertResult:
    """Send one alert. Never raises for a delivery or configuration problem:
    the result says what happened, the failure is counted and logged. Each
    attempt has a wall-clock deadline of ``timeout_s`` (name lookup, connect,
    TLS and the response status line together), so a send blocks for about
    ``max_attempts * timeout_s + sum(back-off)`` seconds at most, plus thread
    scheduling slack; use :func:`asend` from async code."""
    if alert_class not in CLASSES:
        raise ValueError(f"unknown alert class {alert_class!r}")
    backoff_s = DEFAULT_BACKOFF_S if backoff_s is None else backoff_s
    max_attempts = max(1, min(int(max_attempts), MAX_ATTEMPTS_CAP))
    timeout_s = max(0.05, min(float(timeout_s), MAX_TIMEOUT_S))
    try:
        dest = resolve_destination(env)
    except AlertConfigError as exc:
        _count_failure(alert_class, exc.reason, 0)
        return AlertResult(False, alert_class, 0, exc.reason)
    secrets_ = tuple(s for s in (dest.topic, dest.token) if s)
    title, body, tags, withheld = render(alert_class, estate=estate, subject=subject,
                                         detail=detail, secrets_=secrets_, test_id=test_id)
    data = body.encode("utf-8")[:MAX_BODY_BYTES]
    headers = {
        "Title": title,
        "Priority": str(CLASSES[alert_class].priority),
        "Tags": ",".join(tags),
        "Content-Type": "text/plain; charset=utf-8",
        "User-Agent": "field-core-alerts/1",
    }
    if dest.token:
        headers["Authorization"] = f"Bearer {dest.token}"
    opener = opener or _OPENER
    reason, status, attempts = None, None, 0
    for attempt in range(1, max_attempts + 1):
        if attempt > 1 and backoff_s:
            sleep(backoff_s[min(attempt - 2, len(backoff_s) - 1)])
        attempts = attempt
        ok, reason, status, retryable = _attempt(dest.url, data, headers, timeout_s, opener)
        if ok:
            _count_success()
            return AlertResult(True, alert_class, attempts, None, status, withheld)
        if not retryable:
            break
    _count_failure(alert_class, reason or "unknown", attempts)
    return AlertResult(False, alert_class, attempts, reason, status, withheld)


async def asend(alert_class: str, **kwargs) -> AlertResult:
    """:func:`send` in a worker thread, for async callers."""
    return await asyncio.to_thread(send, alert_class, **kwargs)


def send_test(*, estate: str, env: Mapping[str, str] | None = None, **kwargs) -> AlertResult:
    """The clearly marked test alert (``field alert-test``). Carries a short
    random test id so a receipt can be matched to one run."""
    return send("test", estate=estate, env=env, test_id=secrets.token_hex(3), **kwargs)


# ------------------------------------------------------------------- topic

def new_topic() -> str:
    """An unguessable topic: ``field-`` plus 192 random bits (url-safe)."""
    return "field-" + secrets.token_urlsafe(24)


def write_topic_file(path: str | os.PathLike, *, overwrite: bool = False) -> None:
    """Write a fresh :func:`new_topic` to ``path`` (owner-only where the OS
    supports it). Refuses an existing file unless ``overwrite``. Returns
    nothing, so no caller can print the topic by accident."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if overwrite else os.O_EXCL)
    fd = os.open(p, flags, 0o600)  # the mode applies only when the file is created
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        if overwrite and hasattr(os, "fchmod"):
            os.fchmod(fh.fileno(), 0o600)  # an existing file keeps its old mode otherwise
        fh.write(new_topic() + "\n")
