"""Phase G C-6: the sealed-ledger's own record of operator mode and registry changes.

``operator.mode_changed`` and ``operator.registry_changed`` are written by the
ledger ITSELF (its own store append, never accepted from an HTTP caller once
the ledger is armed: ``operator_auth.admit_ledger_event``), from the C-8
operator block it observes in each service's open ``GET /health``:

* ``operator_mode``                      -> ``operator.mode_changed``
* ``operator_registry_sha256_prefix`` and
  ``operator_registry_rows``             -> ``operator.registry_changed``

One of each per service at the first observation by this ledger process
(``startup: true``) and one each time the observed value differs from the last
one recorded for that service. A disarm (REQUIRE unset and the service
recreated), a downgrade to an older or placeholder operators file, and an image
without the operator block (``mode: absent``) therefore each leave a ledger
event (design 2.6, 5.4, 5.5, 5.6).

The ledger observes its own block in process (no HTTP hop to itself) and every
``name=url`` in FIELD_LEDGER_OBSERVE_HEALTH over HTTP. The observer is armed
only when FIELD_LEDGER_OBSERVE_EVERY is a positive whole number of seconds
(floored to MIN_EVERY_S); unset, blank, zero or anything else means no
observer and no event (byte-identical to before). The first tick runs at
start-up, then one every interval.

What reaches the ledger is validated first: the mode is one of
``off``/``log-only``/``enforce``, ``absent`` (the answer has no operator block)
or ``unrecognised``; the sha256 prefix is exactly 16 lower-case hex characters
or ``"(not shown)"``; the row count is a non-negative integer or null. A
service that does not answer (or answers non-JSON or non-200) is skipped for
that tick: nothing is written and the last recorded state is kept, so the
change is recorded when it answers again. An append that fails (ledger busy,
signing required and no key) is retried on the next tick. No request carries a
header but ``Host``: ``/health`` is open on every service, so the ledger sends
neither the perimeter secret nor any operator credential. One fetch is bounded
by one FETCH_TIMEOUT_S deadline for the whole exchange (``http_fetch``).

Key rotation, slice R2 (design 5.1 "independent witness", S8, S11). Also from
each service's open ``/health``:

* ``operator_registry_generation`` -> ``operator.registry_generation_decreased``
  when a service reports a LOWER generation than the last one observed for it
  (a restored or rolled-back operators file; verifiers never refuse it, design
  2.1, so the ledger records it);
* ``breakglass_auth_count`` / ``breakglass_attempt_count`` ->
  ``operator.breakglass_counters_changed`` on every change (a process restart
  resetting them included), and at the first observation only when one is
  above zero (a zero start is not an event, so the eight start-up rows CI
  counts stay exactly the mode and registry pairs).

And from the ledger process ITSELF (never over HTTP, never claimed by the
rotator):

* its OWN parse of the operators file (``operator_health.slot_witness``) ->
  ``operator.registry_slots_changed {format, generation, rows: [{operator_id,
  status, current_fp, next_fp}], changed_operator_ids, sealed_key_changed}``
  at the first valid parse and on every change, fingerprints being the first
  16 hex of each slot hash; the break-glass row shows ``(sealed)`` and only
  whether its key changed (no prefix of it is ever written);
* its own ``operator_retired_hash_seen`` -> ``operator.retired_hash_seen_changed``
  (on a change, and at the first observation when above zero). The other
  seven services' retired-hash counters are on their internal
  ``/operator/rotation-state``, which this observer does not read (it sends no
  perimeter secret).
"""

from __future__ import annotations

import json
import logging
import re
import socket
import threading
import time
from typing import Any, Callable

from field_core.operator_auth import printable_id

log = logging.getLogger("sealed_ledger.operator_observer")

EVERY_ENV = "FIELD_LEDGER_OBSERVE_EVERY"
HEALTH_ENV = "FIELD_LEDGER_OBSERVE_HEALTH"
SELF = "sealed-ledger"
MIN_EVERY_S = 5
MAX_TARGETS = 32
FETCH_TIMEOUT_S = 3.0
MAX_HEALTH_BYTES = 64 * 1024       # a /health answer is about 1 KiB
MODES = frozenset({"off", "log-only", "enforce"})
ABSENT = "absent"
UNRECOGNISED = "unrecognised"
NOT_SHOWN = "(not shown)"
MAX_ROWS = 100_000

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,47}$")
_SHA_PREFIX_RE = re.compile(r"^[0-9a-f]{16}$")

MODE_EVENT = "operator.mode_changed"
REGISTRY_EVENT = "operator.registry_changed"
# key rotation, slice R2
GENERATION_EVENT = "operator.registry_generation_decreased"
BREAKGLASS_EVENT = "operator.breakglass_counters_changed"
SLOTS_EVENT = "operator.registry_slots_changed"
RETIRED_EVENT = "operator.retired_hash_seen_changed"
ROTATION_WITNESS_EVENTS = frozenset({GENERATION_EVENT, BREAKGLASS_EVENT, SLOTS_EVENT,
                                     RETIRED_EVENT})
MAX_COUNT = 10 ** 12
MAX_GENERATION = 2 ** 53
MAX_WITNESS_ROWS = 256
SEALED_FP = "(sealed)"
_FP16_RE = re.compile(r"^[0-9a-f]{16}$")


def interval_from_env(raw: str | None) -> int | None:
    """The tick interval in seconds, or None (observer not armed)."""
    raw = (raw or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        return None
    return max(int(raw), MIN_EVERY_S)


def parse_targets(raw: str | None) -> list[tuple[str, str]]:
    """``name=url[,name=url...]``: lower-case service names, http(s) base URLs
    (trailing ``/`` dropped). Malformed entries, duplicates (first wins) and
    the ledger's own name are skipped with a warning; at most MAX_TARGETS."""
    out: list[tuple[str, str]] = []
    seen: set[str] = {SELF}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        name, sep, url = part.partition("=")
        name, url = name.strip(), url.strip().rstrip("/")
        if (not sep or not _NAME_RE.fullmatch(name) or name in seen
                or not (url.startswith("http://") or url.startswith("https://"))
                or len(url) > 512 or any(c.isspace() for c in url)):
            log.warning("%s: entry %d skipped (want a unique lower-case name=http(s)://url; "
                        "the ledger observes itself in process)", HEALTH_ENV, len(out) + 1)
            continue
        if len(out) >= MAX_TARGETS:
            log.warning("%s: more than %d entries, the rest are skipped", HEALTH_ENV, MAX_TARGETS)
            break
        seen.add(name)
        out.append((name, url))
    return out


def observed_state(health: Any) -> dict[str, Any]:
    """The three observed values, validated (see the module docstring)."""
    if not isinstance(health, dict):
        return {"mode": UNRECOGNISED, "sha": None, "rows": None}
    if "operator_mode" not in health:
        mode = ABSENT
    else:
        m = health.get("operator_mode")
        mode = m if isinstance(m, str) and m in MODES else UNRECOGNISED
    sha = health.get("operator_registry_sha256_prefix")
    if sha is not None:
        sha = sha if isinstance(sha, str) and _SHA_PREFIX_RE.fullmatch(sha) else NOT_SHOWN
    rows = health.get("operator_registry_rows")
    if isinstance(rows, bool) or not isinstance(rows, int) or not 0 <= rows <= MAX_ROWS:
        rows = None
    return {"mode": mode, "sha": sha, "rows": rows}


def _bounded_int(value: Any, top: int) -> int | None:
    return value if type(value) is int and 0 <= value <= top else None


def observed_rotation(health: Any) -> dict[str, Any]:
    """Slice R2: the generation and the two break-glass counters of a /health
    answer, validated (a non-negative int within bounds, else None)."""
    if not isinstance(health, dict):
        return {"generation": None, "breakglass": None}
    auth = _bounded_int(health.get("breakglass_auth_count"), MAX_COUNT)
    attempt = _bounded_int(health.get("breakglass_attempt_count"), MAX_COUNT)
    return {"generation": _bounded_int(health.get("operator_registry_generation"), MAX_GENERATION),
            "breakglass": None if auth is None or attempt is None else (auth, attempt)}


def _witness_fp(value: Any) -> str | None:
    if value is None or value == SEALED_FP:
        return value
    return value if isinstance(value, str) and _FP16_RE.fullmatch(value) else NOT_SHOWN


def _witness_rows(rows: Any) -> list[dict]:
    """The witness rows as they may be ledgered: id (already masked by
    operator_health.shown_id), status, and each fingerprint as 16 hex,
    ``(sealed)``, null or ``(not shown)``; at most MAX_WITNESS_ROWS."""
    out = []
    for r in (rows if isinstance(rows, list) else [])[:MAX_WITNESS_ROWS]:
        if not isinstance(r, dict):
            continue
        oid = r.get("operator_id")
        out.append({"operator_id": oid if oid == NOT_SHOWN or printable_id(oid) else NOT_SHOWN,
                    "status": r.get("status") if r.get("status") in ("active", "revoked") else NOT_SHOWN,
                    "current_fp": _witness_fp(r.get("current_fp")),
                    "next_fp": _witness_fp(r.get("next_fp"))})
    return out


class _DeadlineStream:
    """An httpcore network stream whose every read, write and TLS handshake is
    given at most the time left before ``deadline`` (time.monotonic()); once it
    has passed, the next operation raises instead of waiting."""

    def __init__(self, inner: Any, deadline: float):
        self._inner = inner
        self._deadline = deadline

    def _left(self, timeout: float | None) -> float:
        import httpcore

        left = self._deadline - time.monotonic()
        if left <= 0:
            raise httpcore.ReadTimeout("observer fetch deadline passed")
        return left if timeout is None else min(timeout, left)

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._inner.read(max_bytes, self._left(timeout))

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._inner.write(buffer, self._left(timeout))

    def close(self) -> None:
        self._inner.close()

    def start_tls(self, ssl_context: Any, server_hostname: str | None = None,
                  timeout: float | None = None) -> "_DeadlineStream":
        return _DeadlineStream(
            self._inner.start_tls(ssl_context, server_hostname, self._left(timeout)), self._deadline)

    def get_extra_info(self, info: str) -> Any:
        return self._inner.get_extra_info(info)


def _resolve(host: str, port: int, timeout: float) -> list[tuple]:
    """``getaddrinfo`` bounded by ``timeout``: it runs in a daemon thread, and a
    lookup still running at the deadline is abandoned (it holds no socket and
    ends on its own with the resolver's timeout)."""
    import httpcore

    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["addrs"] = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except Exception as exc:  # noqa: BLE001 - reported below as a connect failure
            box["error"] = exc

    t = threading.Thread(target=run, name="operator-observer-dns", daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise httpcore.ConnectTimeout("name resolution passed the observer fetch deadline")
    if "error" in box or not box.get("addrs"):
        raise httpcore.ConnectError(f"name resolution failed: {type(box.get('error')).__name__}")
    return box["addrs"]


class _DeadlineBackend:
    """httpcore's own sync backend with the name lookup, every connect attempt
    and every later socket operation bounded by one wall-clock deadline
    (``_DeadlineStream``). The host is resolved here and each address is
    connected in turn with only the time left, because ``socket.create_connection``
    gives EACH address the full timeout (a name with several addresses that
    all refuse took ~12 s on Windows)."""

    def __init__(self, deadline: float):
        import httpcore

        self._inner = httpcore.SyncBackend()
        self._deadline = deadline

    def _left(self, timeout: float | None) -> float:
        return _DeadlineStream(None, self._deadline)._left(timeout)

    def connect_tcp(self, host: str, port: int, timeout: float | None = None,
                    local_address: str | None = None, socket_options: Any = None) -> _DeadlineStream:
        import httpcore

        last: Exception = httpcore.ConnectError("no address")
        for _family, _type, _proto, _canon, sockaddr in _resolve(host, port, self._left(timeout)):
            try:
                inner = self._inner.connect_tcp(str(sockaddr[0]), int(sockaddr[1]), self._left(timeout),
                                                local_address, socket_options)
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last = exc
                continue
            return _DeadlineStream(inner, self._deadline)
        raise last

    def connect_unix_socket(self, path: str, timeout: float | None = None,
                            socket_options: Any = None) -> _DeadlineStream:
        return _DeadlineStream(self._inner.connect_unix_socket(path, self._left(timeout), socket_options),
                               self._deadline)

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)


def http_fetch(url: str) -> Any:
    """GET ``url`` with no headers but ``Host``; the decoded JSON of a 200, else None.

    ONE deadline, FETCH_TIMEOUT_S after the call starts, bounds the whole
    exchange: the connect, sending the request, reading the status line and
    headers, and the body (independent review of PR #42, R2-L1: with httpx the
    timeout applied to each read separately, so a target trickling its HEADERS
    held a fetch for ~48 s). Every socket operation is given at most the time
    left (``_DeadlineBackend``), and once the deadline has passed the next one
    raises. The body is streamed: more than MAX_HEALTH_BYTES is treated like no
    answer. A redirect is never followed (httpcore has no redirect logic: a
    302 is a non-200). No proxy variable is honoured (the targets are
    container or loopback addresses). One target therefore holds a tick for
    about FETCH_TIMEOUT_S at most, the name lookup included (a lookup still
    running at the deadline is abandoned in its daemon thread). Every
    connection is closed before this returns; it never raises."""
    deadline = time.monotonic() + FETCH_TIMEOUT_S
    body = bytearray()
    try:
        import httpcore

        timeouts = {"connect": FETCH_TIMEOUT_S, "read": FETCH_TIMEOUT_S,
                    "write": FETCH_TIMEOUT_S, "pool": FETCH_TIMEOUT_S}
        with httpcore.ConnectionPool(network_backend=_DeadlineBackend(deadline),
                                     max_connections=1, retries=0) as pool:
            with pool.stream("GET", url, extensions={"timeout": timeouts}) as resp:
                if resp.status != 200:
                    return None
                for chunk in resp.iter_stream():
                    body += chunk
                    if len(body) > MAX_HEALTH_BYTES or time.monotonic() > deadline:
                        return None
    except Exception:
        return None
    try:
        return json.loads(bytes(body))
    except (ValueError, RecursionError):
        # RecursionError: a body within the cap nested deeply enough (e.g. 65,000
        # "[") exhausts the decoder's recursion limit (hardening review F1)
        return None


class OperatorObserver:
    """``append(event_type, payload)`` is the ledger's own append;
    ``self_health()`` returns this app's C-8 block; ``targets`` are
    ``(name, base_url)``; ``fetch(url)`` returns a decoded /health or None."""

    def __init__(self, append: Callable[[str, dict], Any],
                 self_health: Callable[[], dict],
                 targets: list[tuple[str, str]],
                 fetch: Callable[[str], Any] | None = None,
                 self_slots: Callable[[], dict | None] | None = None,
                 self_counters: Callable[[], dict] | None = None):
        self.append = append
        self.self_health = self_health
        self.targets = list(targets)
        self.fetch = fetch or http_fetch
        # slice R2: the ledger's own parse (operator_health.slot_witness) and its
        # own process counters ({"retired_hash_seen": n}); None = not witnessed
        self.self_slots = self_slots
        self.self_counters = self_counters
        self._mode: dict[str, str] = {}
        self._registry: dict[str, tuple[Any, Any]] = {}
        self._generation: dict[str, int] = {}
        self._breakglass: dict[str, tuple[int, int]] = {}
        self._slots: tuple | None = None
        self._slot_rows: dict[str, tuple] = {}
        self._retired: int | None = None
        self._lock = threading.Lock()

    def _write(self, event_type: str, name: str, payload: dict) -> bool:
        try:
            self.append(event_type, payload)
        except Exception as exc:
            log.warning("operator observer: %s for %s not written (%s); retried next tick",
                        event_type, name, type(exc).__name__)
            return False
        return True

    def _observe_rotation(self, name: str, health: Any) -> int:
        """Slice R2: generation decreases and break-glass counter changes seen
        in one service's /health. A failed append keeps the last recorded
        state, so the event is written on the next tick."""
        st = observed_rotation(health)
        written = 0
        gen = st["generation"]
        if gen is not None:
            previous = self._generation.get(name)
            if previous is not None and gen < previous:
                payload = {"service": name, "generation": gen, "previous_generation": previous,
                           "registry_sha256_prefix": observed_state(health)["sha"],
                           "observed_from": "health"}
                if not self._write(GENERATION_EVENT, name, payload):
                    return written
                written += 1
            self._generation[name] = gen
        bg = st["breakglass"]
        if bg is not None:
            previous_bg = self._breakglass.get(name)
            if (previous_bg is None and any(bg)) or (previous_bg is not None and bg != previous_bg):
                payload = {"service": name, "breakglass_auth_count": bg[0],
                           "breakglass_attempt_count": bg[1],
                           "previous_breakglass_auth_count": previous_bg[0] if previous_bg else None,
                           "previous_breakglass_attempt_count": previous_bg[1] if previous_bg else None,
                           "startup": previous_bg is None, "observed_from": "health"}
                if not self._write(BREAKGLASS_EVENT, name, payload):
                    return written
                written += 1
            self._breakglass[name] = bg
        return written

    def _observe_self_witness(self) -> int:
        """Slice R2: the ledger's own parse of the operators file (per-row slot
        fingerprints) and its own retired-hash counter."""
        written = 0
        witness = None
        if self.self_slots is not None:
            try:
                witness = self.self_slots()
            except Exception:
                witness = None
        if isinstance(witness, dict):
            rows = _witness_rows(witness.get("rows"))
            gen = _bounded_int(witness.get("generation"), MAX_GENERATION)
            fmt = witness.get("format") if witness.get("format") in (1, 2) else None
            sealed_state = witness.get("_sealed_state")      # compared in memory, never written
            key = (fmt, gen, tuple((r["operator_id"], r["status"], r["current_fp"], r["next_fp"])
                                   for r in rows), sealed_state)
            if key != self._slots:
                previous = self._slots
                by_id = {r["operator_id"]: (r["status"], r["current_fp"], r["next_fp"]) for r in rows}
                changed = sorted(i for i in set(by_id) | set(self._slot_rows)
                                 if by_id.get(i) != self._slot_rows.get(i)) if previous else []
                sha = witness.get("registry_sha256_prefix")
                payload = {"service": SELF, "format": fmt, "generation": gen,
                           "registry_sha256_prefix": sha if isinstance(sha, str)
                           and _SHA_PREFIX_RE.fullmatch(sha) else None,
                           "rows": rows, "changed_operator_ids": changed,
                           "sealed_key_changed": previous is not None and previous[3] != sealed_state,
                           "previous_generation": previous[1] if previous else None,
                           "startup": previous is None, "observed_from": "own_parse"}
                if self._write(SLOTS_EVENT, SELF, payload):
                    written += 1
                    self._slots, self._slot_rows = key, by_id
        if self.self_counters is not None:
            try:
                n = _bounded_int((self.self_counters() or {}).get("retired_hash_seen"), MAX_COUNT)
            except Exception:
                n = None
            if n is not None:
                previous_n = self._retired
                if (previous_n is None and n > 0) or (previous_n is not None and n != previous_n):
                    payload = {"service": SELF, "retired_hash_seen": n,
                               "previous_retired_hash_seen": previous_n,
                               "startup": previous_n is None, "observed_from": "own_process"}
                    if not self._write(RETIRED_EVENT, SELF, payload):
                        return written
                    written += 1
                self._retired = n
        return written

    def _read(self, name: str, url: str | None) -> Any:
        try:
            return self.self_health() if url is None else self.fetch(f"{url}/health")
        except Exception:
            return None

    def _observe(self, name: str, health: Any) -> int:
        state = observed_state(health)
        written = 0
        startup = name not in self._mode
        if self._mode.get(name) != state["mode"]:
            payload = {"service": name, "mode": state["mode"],
                       "previous_mode": self._mode.get(name),
                       "startup": startup, "observed_from": "health"}
            try:
                self.append(MODE_EVENT, payload)
            except Exception as exc:
                log.warning("operator observer: %s for %s not written (%s); retried next tick",
                            MODE_EVENT, name, type(exc).__name__)
                return written
            self._mode[name] = state["mode"]
            written += 1
        reg = (state["sha"], state["rows"])
        previous = self._registry.get(name)
        if previous != reg:
            payload = {"service": name, "mode": state["mode"],
                       "registry_sha256_prefix": reg[0], "registry_rows": reg[1],
                       "previous_registry_sha256_prefix": previous[0] if previous else None,
                       "previous_registry_rows": previous[1] if previous else None,
                       "startup": previous is None, "observed_from": "health"}
            try:
                self.append(REGISTRY_EVENT, payload)
            except Exception as exc:
                log.warning("operator observer: %s for %s not written (%s); retried next tick",
                            REGISTRY_EVENT, name, type(exc).__name__)
                return written
            self._registry[name] = reg
            written += 1
        return written + self._observe_rotation(name, health)

    def observe_once(self) -> int:
        """One tick over itself and every target. Returns the number of
        events written. Never raises."""
        written = 0
        with self._lock:
            for name, url in [(SELF, None), *self.targets]:
                health = self._read(name, url)
                if health is None:
                    continue          # unreachable: nothing written, last state kept
                written += self._observe(name, health)
            written += self._observe_self_witness()
        return written

    def run_every(self, seconds: float, stop: threading.Event) -> None:
        """First tick now (start-up), then one every ``seconds`` until
        ``stop`` is set. A tick never raises."""
        while not stop.is_set():
            try:
                self.observe_once()
            except Exception:  # pragma: no cover - observe_once never raises
                log.exception("operator observer tick failed; continuing")
            stop.wait(seconds)


def from_env(environ: dict[str, str], append: Callable[[str, dict], Any],
             self_health: Callable[[], dict],
             fetch: Callable[[str], Any] | None = None,
             self_slots: Callable[[], dict | None] | None = None,
             self_counters: Callable[[], dict] | None = None,
             ) -> tuple[OperatorObserver | None, int | None]:
    """(observer, interval) when FIELD_LEDGER_OBSERVE_EVERY arms it, else (None, None)."""
    every = interval_from_env(environ.get(EVERY_ENV))
    if every is None:
        return None, None
    return OperatorObserver(append, self_health, parse_targets(environ.get(HEALTH_ENV)),
                            fetch=fetch, self_slots=self_slots,
                            self_counters=self_counters), every
