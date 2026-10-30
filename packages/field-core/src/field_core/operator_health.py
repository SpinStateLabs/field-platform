"""Operator-auth health block (C-8) and refusal evidence (C-16), Phase G.

One object per service app, created with :func:`install`::

    oh = operator_health.install(app, ledger_getter=lambda a: a.state.ledger)
    guard_kill = oh.guard("kill")                 # replaces operator_auth.guard
    ...
    except operator_auth.OperatorRefused as exc:  # a refusal inside a handler
        raise oh.http_refusal(exc, action="kill", path=request.url.path,
                              headers=request.headers)
    ...
    return {..., **oh.health_fields()}            # GET /health

``health_fields()`` (C-8) returns, on every call:

* ``operator_mode``: ``off`` / ``log-only`` / ``enforce`` as the guards see it now.
* ``operator_registry_sha256_prefix``: the first 16 hex of the sha256 of the
  operators file BYTES (the same digest ``operator_keygen.py --check`` prints),
  or null when no file is configured or it cannot be read.
* ``operator_registry_rows``: the row count of that file when it passes the
  validation the guards apply (under ENFORCE that includes "at least one active
  row"), else null.
* ``last_registry_error``: why the file does not pass right now (re-read on
  every call), null when it does or when no file is configured outside
  ENFORCE. Fixed text, row numbers, operator ids and exception type names only.
* ``operator_identity_id`` / ``identity_present``: this service's own outgoing
  identity (``FIELD_OPERATOR``) and whether a usable key goes with it. A value
  that could be a key (``fok_`` prefix, outside the operator id charset, or
  equal to the service's own key) is shown as ``"(not shown)"``.
* ``dropped_unauthenticated_records``: LOG-ONLY ``operator.unauthenticated``
  records not written: dropped under flood, or whose ledger append failed
  (refused, 5xx, unreachable, timed out; the guard's process-wide counter).
* ``refused_count`` / ``dropped_refused_records``: refusals this app's
  operator layer returned (any armed mode), and ``operator.refused`` records
  not written because of the caps below or because their append failed.
* ``manifests_unresolved`` (only when the caller passes ``manifest_refs``: the
  agent registry and the kill-switch): how many of the given manifest refs do
  not resolve (``missing`` / ``invalid``) in this process. Null when OFF or
  when the agent list cannot be read.
* Key rotation, slice R2 (design 5.1, O3, S12): ``operator_registry_format``
  (1 or 2) and ``operator_registry_generation`` (0 for format 1) of that file
  when it passes validation, else null; ``operator_roster_sha16``, the first
  16 hex of :func:`roster_sha256` (every row with its KEY fields removed, so a
  rotation leaves it unchanged and any roster change moves it), null when the
  file does not pass; ``breakglass_auth_count`` / ``breakglass_attempt_count``
  (``operator_auth.note_breakglass``, per process).

Never in the block: a key, a key hash (or a prefix of one), a row, or any
registry content. Everything that carries a hash prefix is on the INTERNAL
``GET /operator/rotation-state`` (perimeter secret, refused at the edge except
from loopback), never on the open ``/health``.

Slice R2 also adds two internal routes to every app :func:`install` is given
(the eight operator-block services), both answering 404 when the operator
layer is OFF or no perimeter secret is configured:

* ``POST /operator/verify-hash`` ``{"operator_id", "key_sha256"}``: takes a key
  HASH, never a key, and answers from this process's own parse of the
  operators file whether that hash is the named row's CURRENT or NEXT key and
  whether it would authenticate now. Refuses (403, counted as a break-glass
  attempt) any question about the break-glass identity. Never ledgered, never
  counted as a refusal (design 4.3 steps 5, 9b, 10; S3).
* ``GET /operator/rotation-state``: this service's own identity key
  fingerprint (16 hex), every row's slot fingerprints (16 hex; the
  break-glass row's never) and windows, expiry and age summaries, the
  break-glass and retired-hash counters, ``clock_synced`` and the K4 grace
  flag (design 5.3, R6).

C-16: under ENFORCE every refusal (400/401/403/503 from the operator layer)
is ledgered as ``operator.refused {action, path, reason, status, claimed_id,
operator_claimed}``, with the agent the refused route names (if any) as the
event's agent id. ``reason`` is fixed text per status; the claimed id is the
header's id (masked like the identity above, null when the headers were
malformed); the key and its hash never appear; the request path is clipped to
``operator_auth.MAX_RECORDED_PATH_LEN`` characters and stored as "(not shown)"
unless it is printable URL-path text without the key prefix (PG0-CORE-R1-14,
the same rule as ``operator.unauthenticated``). Bounded so a flood cannot fill
the ledger: at most MAX_REFUSED_RECORDS_PER_WINDOW records per
REFUSED_WINDOW_S seconds per app, at most MAX_CONCURRENT_REFUSED_RECORDS
appends in flight, each waited for at most LEDGER_APPEND_TIMEOUT_S (the same
budget as ``operator.unauthenticated``). Every refusal is counted in
``refused_count`` whether or not its record was written; records not written
(capped, or the append failed: one log line with the event type and status,
never a header value) are counted in ``dropped_refused_records``. LOG-ONLY refusals (a malformed
header, a refused ``operator.*`` ledger append) are counted, not ledgered.
"""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from pydantic import BaseModel

from field_core import operator_auth as oa

REGISTRY_SHA_PREFIX_LEN = 16
MAX_ERROR_LEN = 200
NOT_SHOWN = oa.NOT_SHOWN
#: the prefix ``operator_keygen.py`` gives every key it generates
KEY_PREFIX = oa.KEY_PREFIX

REFUSED_WINDOW_S = 60.0
MAX_REFUSED_RECORDS_PER_WINDOW = 30
MAX_CONCURRENT_REFUSED_RECORDS = 4

_FROM_HEADERS = object()

_REASONS = {400: "malformed_credential", 401: "no_credential", 403: "forbidden",
            503: "unavailable"}


class OperatorHealthFields(BaseModel):
    """The C-8 block, for services whose /health has a response model."""
    operator_mode: str = oa.OFF
    operator_registry_sha256_prefix: str | None = None
    operator_registry_rows: int | None = None
    operator_identity_id: str | None = None
    identity_present: bool = False
    last_registry_error: str | None = None
    dropped_unauthenticated_records: int = 0
    refused_count: int = 0
    dropped_refused_records: int = 0
    operator_registry_format: int | None = None
    operator_registry_generation: int | None = None
    operator_roster_sha16: str | None = None
    breakglass_auth_count: int = 0
    breakglass_attempt_count: int = 0


class OperatorHealthWithManifests(OperatorHealthFields):
    manifests_unresolved: int | None = None


def shown_id(value: str | None) -> str | None:
    """An operator id fit to print on an open endpoint or in a ledger row:
    None stays None; anything outside the operator id charset, or carrying the
    key prefix, is NOT_SHOWN (a key pasted where an id belongs is never
    echoed)."""
    if not value:
        return None
    # PG0-CORE-R2-03: one rule with the registry errors and ledger rows (the key
    # prefix, the id charset and a 40+ character unbroken token).
    if not oa.printable_id(value):
        return NOT_SHOWN
    return value


_LABEL_RE = re.compile(r"[A-Za-z0-9._:/-]{1,64}")


def shown_label(value: Any) -> str | None:
    """A short caller-supplied label (an event type) fit for a ledger row:
    printable id-like text up to 64 chars and without the key prefix, else
    NOT_SHOWN."""
    if value is None:
        return None
    if (not isinstance(value, str) or not _LABEL_RE.fullmatch(value)
            or value.startswith(KEY_PREFIX)):
        return NOT_SHOWN
    return value


def _clip(text: str) -> str:
    return text if len(text) <= MAX_ERROR_LEN else text[: MAX_ERROR_LEN - 3] + "..."


#: Design 4.3 ``diff_guard``: the fields a rotation may change. Everything else in
#: the file is the ROSTER (row order, ids, status, scopes, names, prefixes, auth,
#: rotation, passkeys, created_at, ...), which a rotation never touches (O3).
KEY_TOP_FIELDS = frozenset({"format", "generation", "issued_at", "issued_by"})
KEY_ROW_FIELDS = frozenset({"key_sha256", "key_created_at", "key_not_after", "next_key"})


def roster_sha256(raw: Any) -> str:
    """sha256 (hex) of the roster of a decoded operators document: the row list
    (a format 1 list, or the ``operators`` of an object), each row with
    KEY_ROW_FIELDS removed, as canonical JSON (sorted keys, no spaces, ASCII).
    Top-level fields are not part of the roster (format 2 allows only the
    KEY_TOP_FIELDS besides ``operators``). Call it on a document that passed
    ``parse_registry``; the open /health shows the first 16 hex."""
    rows = raw.get("operators") if isinstance(raw, dict) else raw
    roster = [{k: v for k, v in r.items() if k not in KEY_ROW_FIELDS} if isinstance(r, dict) else r
              for r in (rows if isinstance(rows, list) else [])]
    blob = json.dumps({"operators": roster}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)
    return hashlib.sha256(blob.encode("ascii")).hexdigest()


def _read_registry(m: str) -> tuple[dict[str, Any], Any, Any]:
    """(view, raw, doc): the C-8 view of the operators file plus, when it passes
    validation (pure parse, no retired-hash memory), the decoded JSON and the
    parsed RegistryDoc (else None, None)."""
    out: dict[str, Any] = {"operator_registry_sha256_prefix": None,
                           "operator_registry_rows": None, "last_registry_error": None,
                           "operator_registry_format": None,
                           "operator_registry_generation": None,
                           "operator_roster_sha16": None}
    path = oa.registry_path()
    if not path:
        if m == oa.ENFORCE:
            out["last_registry_error"] = "operator registry path is not set"
        return out, None, None
    try:
        data = Path(path).read_bytes()
    except (OSError, ValueError) as exc:
        out["last_registry_error"] = f"operator registry unreadable: {type(exc).__name__}"
        return out, None, None
    out["operator_registry_sha256_prefix"] = hashlib.sha256(data).hexdigest()[
        :REGISTRY_SHA_PREFIX_LEN]
    try:
        raw = oa.decode_registry_document(data)      # the one decoder every reader shares
    except oa.RegistryUnavailable as exc:
        out["last_registry_error"] = _clip(str(exc))
        return out, None, None
    try:
        doc = oa.parse_registry_doc(raw, require_active=m == oa.ENFORCE)
    except oa.RegistryUnavailable as exc:
        out["last_registry_error"] = _clip(str(exc))
        return out, None, None
    out["operator_registry_rows"] = len(doc.rows)
    out["operator_registry_format"] = doc.format
    out["operator_registry_generation"] = doc.generation
    out["operator_roster_sha16"] = roster_sha256(raw)[:REGISTRY_SHA_PREFIX_LEN]
    return out, raw, doc


def registry_view(mode: str | None = None) -> dict[str, Any]:
    """sha256 prefix, row count, format, generation, roster digest and current
    error of the operators file, read once (all describe the same bytes)."""
    return _read_registry(mode or oa.mode())[0]


def _unresolved(manifest_refs: Callable[[], Iterable[str | None]]) -> int | None:
    from field_core.clients import resolve_manifest_detail

    try:
        refs = list(manifest_refs())
    except Exception:
        return None
    return sum(1 for ref in refs
               if resolve_manifest_detail(ref)[1] not in ("ok", "no_ref"))


class OperatorHealth:
    """Per-app counters, the refusal recorder and the /health block."""

    def __init__(self, app: Any = None,
                 ledger_getter: Callable[[Any], Any] | None = None, *,
                 window_s: float = REFUSED_WINDOW_S,
                 max_records_per_window: int = MAX_REFUSED_RECORDS_PER_WINDOW,
                 max_concurrent: int = MAX_CONCURRENT_REFUSED_RECORDS,
                 append_timeout_s: float = oa.LEDGER_APPEND_TIMEOUT_S,
                 clock: Callable[[], float] = time.monotonic):
        self.app = app
        self.ledger_getter = ledger_getter
        self.window_s = window_s
        self.max_records_per_window = max_records_per_window
        self.append_timeout_s = append_timeout_s
        self.clock = clock
        self.refused_count = 0
        self.dropped_records = 0
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._window_start: float | None = None
        self._window_written = 0

    # -- C-8 ----------------------------------------------------------------

    def health_fields(self, manifest_refs: Callable[[], Iterable[str | None]] | None = None
                      ) -> dict[str, Any]:
        m = oa.mode()
        out: dict[str, Any] = {"operator_mode": m, **registry_view(m)}
        own = oa.operator_headers()
        op = os.environ.get(oa.ENV_OPERATOR, "").strip()
        own_key = own.get(oa.HEADER_KEY) or os.environ.get(oa.ENV_OPERATOR_KEY, "")
        # an id that IS this service's key (a swapped env pair) is never shown
        out["operator_identity_id"] = NOT_SHOWN if op and op == own_key else shown_id(op)
        out["identity_present"] = bool(own)
        out["dropped_unauthenticated_records"] = oa.dropped_unauthenticated_records
        out["breakglass_auth_count"] = oa.breakglass_auth_count
        out["breakglass_attempt_count"] = oa.breakglass_attempt_count
        with self._lock:
            out["refused_count"] = self.refused_count
            out["dropped_refused_records"] = self.dropped_records
        if manifest_refs is not None:
            out["manifests_unresolved"] = None if m == oa.OFF else _unresolved(manifest_refs)
        return out

    # -- C-16 ---------------------------------------------------------------

    def _admit_record(self) -> bool:
        """Count one refusal; True when its record may be written (window
        cap not reached), else count the drop."""
        with self._lock:
            self.refused_count += 1
            now = self.clock()
            if self._window_start is None or now - self._window_start >= self.window_s:
                self._window_start, self._window_written = now, 0
            if self._window_written >= self.max_records_per_window:
                self.dropped_records += 1
                return False
            self._window_written += 1
            return True

    def note_refused(self, exc: oa.OperatorRefused, *, action: str, path: str,
                     headers: Any, extra: dict[str, str] | None = None,
                     claimed: Any = _FROM_HEADERS, agent_id: str | None = None) -> None:
        """Count the refusal; under ENFORCE ledger ``operator.refused`` (best
        effort, bounded, never raises). The claimed id is the request's
        ``x-field-operator`` unless ``claimed`` is given (a handler that only
        holds the bound OperatorAuth passes ``.claimed``). ``agent_id`` (the
        agent the refused route names, when it names one) becomes the event's
        agent id. ``extra`` adds short labels (each value passed through
        :func:`shown_label`)."""
        m = oa.mode()
        if m == oa.OFF:
            return
        if m != oa.ENFORCE:
            with self._lock:              # LOG-ONLY: counted, never ledgered
                self.refused_count += 1
            return
        if not self._admit_record():
            return
        ledger = None
        if self.ledger_getter is not None:
            try:
                ledger = self.ledger_getter(self.app)
            except Exception:
                ledger = None
        if ledger is None:
            # No ledger wired, or the getter raised: nothing can be written, so the drop is
            # counted (reviewer C-40 finding 1: refused_count must never exceed written + dropped).
            with self._lock:
                self.dropped_records += 1
            return
        if claimed is _FROM_HEADERS:
            try:
                claimed, _ = oa.parse_headers(headers)
            except oa.OperatorRefused:
                claimed = None
        claimed = shown_id(claimed)
        status = int(getattr(exc, "status", 0) or 0)
        # PG0-CORE-R1-14: the path is caller-chosen text; clipped and printable only
        payload = {"action": action, "path": oa.recorded_path(path),
                   "reason": _REASONS.get(status, "refused"),
                   "status": status, "claimed_id": claimed, "operator_claimed": claimed}
        for k, v in (extra or {}).items():
            payload[k] = shown_label(v)
        agent = shown_label(agent_id)
        agent = None if agent == NOT_SHOWN else agent
        if not self._slots.acquire(blocking=False):
            with self._lock:
                self.dropped_records += 1
            return

        def _go() -> None:
            try:
                ledger.append("operator.refused", payload, agent)
            except Exception as exc:
                # Never silent: counted, one line with the type and status only.
                with self._lock:
                    self.dropped_records += 1
                oa.log.warning("operator.refused ledger append failed (status=%s); "
                               "counted in dropped_refused_records", oa.append_failure_status(exc))
            finally:
                self._slots.release()

        ctx = contextvars.copy_context()
        t = threading.Thread(target=ctx.run, args=(_go,), daemon=True)
        t.start()
        t.join(self.append_timeout_s)

    def http_refusal(self, exc: oa.OperatorRefused, *, action: str, path: str,
                     headers: Any, claimed: Any = _FROM_HEADERS,
                     agent_id: str | None = None):
        """note_refused, then the HTTPException to raise (same status and
        detail as before)."""
        from fastapi import HTTPException

        self.note_refused(exc, action=action, path=path, headers=headers, claimed=claimed,
                          agent_id=agent_id)
        return HTTPException(exc.status, exc.detail)

    def guard(self, action: str, rows_loader: Callable[[], list[dict]] | None = None):
        """operator_auth.guard for ``action`` (same checks, same LOG-ONLY
        ``operator.unauthenticated`` record through this app's ledger), plus:
        every refusal it returns is counted and, under ENFORCE, ledgered."""
        from fastapi import HTTPException, Request
        from starlette.concurrency import run_in_threadpool

        inner = oa.guard(action, rows_loader, ledger_getter=self.ledger_getter)

        async def _guard(request: Request) -> oa.OperatorAuth:
            try:
                return await inner(request)
            except HTTPException as exc:      # the inner guard raises only refusals
                await run_in_threadpool(
                    self.note_refused, oa.OperatorRefused(exc.status_code, str(exc.detail)),
                    action=action, path=request.url.path, headers=request.headers,
                    agent_id=request.path_params.get("agent_id"))
                raise

        _guard.__annotations__ = {"request": Request, "return": oa.OperatorAuth}
        return _guard


    # -- key rotation, slice R2 ---------------------------------------------

    def rotation_state(self, now: float | None = None) -> dict[str, Any]:
        """The internal ``GET /operator/rotation-state`` answer (module
        :func:`rotation_state`) plus this app's refusal counters."""
        out = rotation_state(now)
        with self._lock:
            out["counters"]["refused_count"] = self.refused_count
            out["counters"]["dropped_refused_records"] = self.dropped_records
        return out


# --- key rotation, slice R2: internal routes (design 4.3, 5.1, 5.3; S3, S8, S12) ---

VERIFY_HASH_PATH = "/operator/verify-hash"
ROTATION_STATE_PATH = "/operator/rotation-state"
INTERNAL_PATHS = (VERIFY_HASH_PATH, ROTATION_STATE_PATH)
MAX_VERIFY_BODY = 1024
FP_LEN = 16
#: shown instead of any fingerprint of the break-glass row's key: a hash prefix
#: would let whoever holds a candidate break-glass key test it offline, without
#: the attempt counter seeing it (design 3.4, S8)
SEALED_FP = "(sealed)"
NOT_FOUND_DETAIL = "Not Found"
BAD_BODY_DETAIL = ('body must be exactly {"operator_id": <operator id>, '
                   '"key_sha256": <64 lower-case hex>}; a hash, never a key')
SEALED_DETAIL = "not answered for the break-glass identity"
UNAVAILABLE_DETAIL = "operator registry unavailable"
#: adjtimex(2) clock state: the kernel clock is not synchronised
_TIME_ERROR = 5
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_VERIFY_FIELDS = frozenset({"operator_id", "key_sha256"})
_NO_SLOT = "0" * 64


def internal_routes_enabled() -> bool:
    """The internal routes answer only when the operator layer is armed
    (LOG-ONLY or ENFORCE) AND a perimeter secret is configured (so the authn
    middleware demands ``x-field-auth`` on them); otherwise they are 404 as if
    absent (fail closed: no question about the operators file is answered on
    an estate without a perimeter)."""
    from field_core.authn import shared_secret

    return oa.mode() != oa.OFF and shared_secret() is not None


#: An internal-only secret for the two internal routes (C-801, D-12). ``FIELD_INTERNAL_SECRET_SHA256`` holds the
#: sha256 (64 lower-case hex) of the secret, so a service holds a hash, not a credential; ``FIELD_INTERNAL_SECRET``
#: holds the value. Either set means the routes also need ``x-field-internal``; both set means both must match;
#: neither set is today's behaviour (perimeter secret only). A malformed hash matches nothing (fail closed).
_PRINTABLE_ASCII_RE = re.compile(r"[\x21-\x7e]+")
INTERNAL_HEADER = "x-field-internal"
ENV_INTERNAL_SECRET = "FIELD_INTERNAL_SECRET"
ENV_INTERNAL_SECRET_SHA256 = "FIELD_INTERNAL_SECRET_SHA256"


def internal_secret_problem() -> str | None:
    """Fixed text (never a secret) when the internal-secret setup cannot work or adds nothing: a hash that is not
    64 lower-case hex, or an internal secret equal to the perimeter secret (C-859 C2, C3). Checked at install."""
    from field_core.authn import shared_secret

    want_hash = os.environ.get(ENV_INTERNAL_SECRET_SHA256, "")
    want_value = os.environ.get(ENV_INTERNAL_SECRET, "")
    if want_hash and not _HEX64_RE.fullmatch(want_hash):
        return f"{ENV_INTERNAL_SECRET_SHA256} must be 64 lower-case hex characters"
    if want_hash == hashlib.sha256(b"").hexdigest():
        return f"{ENV_INTERNAL_SECRET_SHA256} is the hash of the empty string"
    if want_value and not _PRINTABLE_ASCII_RE.fullmatch(want_value):
        return f"{ENV_INTERNAL_SECRET} must be printable ASCII with no whitespace (it travels in a header)"
    perimeter = shared_secret()
    if perimeter:
        p = perimeter.encode("utf-8", "surrogatepass")
        if want_value and hmac.compare_digest(p, want_value.encode("utf-8", "surrogatepass")):
            return "the internal secret equals the perimeter secret"
        if want_hash and hmac.compare_digest(hashlib.sha256(p).hexdigest().encode("ascii"),
                                              want_hash.encode("ascii", "replace")):
            return "the internal secret equals the perimeter secret"
    return None


def internal_request_allowed(presented: str | None) -> bool:
    """True when no internal secret is configured, or the presented header satisfies every configured form."""
    want_hash = os.environ.get(ENV_INTERNAL_SECRET_SHA256, "")
    want_value = os.environ.get(ENV_INTERNAL_SECRET, "")
    if not want_hash and not want_value:
        return True
    if not presented:
        return False                   # an absent or empty header is never a secret (sha256 of "" must not open it)
    got = presented.encode("utf-8", "surrogatepass")
    ok = True
    if want_hash:
        digest = hashlib.sha256(got).hexdigest()
        ok = _HEX64_RE.fullmatch(want_hash) is not None and hmac.compare_digest(
            digest.encode("ascii"), want_hash.encode("ascii", "replace"))
    if want_value:
        ok = hmac.compare_digest(got, want_value.encode("utf-8", "surrogatepass")) and ok
    return ok


def _iso(epoch: int | None) -> str | None:
    return None if epoch is None else oa.format_time(epoch)


def verify_hash_answer(body: bytes, now: float | None = None) -> tuple[int, dict[str, Any]]:
    """(status, JSON) for ``POST /operator/verify-hash``. The body is exactly
    ``{"operator_id": <id>, "key_sha256": <64 lower-case hex>}``; anything
    else is 422 with fixed text (the input is never echoed, so a key pasted in
    by mistake is not reflected). The answer comes from this process's own
    parse (``load_registry_snapshot``: the verifier's rows, retired-hash
    memory included) and says, for the NAMED row only:

    * ``matched``: ``current`` / ``next`` / ``none``, which slot holds the hash;
    * ``matchable_now``: whether that hash would authenticate that id now (row
      active, slot inside its window, not retired, ``auth`` includes ``key``):
      exactly the verifier's rule (``operator_auth._key_matches``);
    * ``retired``: the slot holds it but the retired-hash memory refuses it;
    * the registry format, generation and file sha256 prefix it answered from.

    The break-glass identity (BREAKGLASS_ID or a sealed row) is never answered:
    403, counted as a break-glass attempt. Every row and slot is compared (no
    early exit). Never ledgered, never counted as a refusal."""
    try:
        req = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return 422, {"detail": BAD_BODY_DETAIL}
    if (not isinstance(req, dict) or set(req) != _VERIFY_FIELDS
            or not oa.printable_id(req["operator_id"])
            or not isinstance(req["key_sha256"], str)
            or not _HEX64_RE.fullmatch(req["key_sha256"])):
        return 422, {"detail": BAD_BODY_DETAIL}
    op, presented = req["operator_id"], req["key_sha256"]
    if oa.is_breakglass(op):
        oa.note_breakglass(used=False)
        return 403, {"detail": SEALED_DETAIL}
    try:
        snap = oa.load_registry_snapshot()
    except oa.RegistryUnavailable:
        return 503, {"detail": UNAVAILABLE_DETAIL}
    if oa.is_breakglass(op, snap.rows):
        oa.note_breakglass(used=False)
        return 403, {"detail": SEALED_DETAIL}
    now = oa.clock() if now is None else now
    matched, matchable, retired = "none", False, False
    op_b = op.encode("utf-8")
    for r in snap.rows:
        nk = r.get("next_key")
        id_eq = hmac.compare_digest(op_b, str(r["operator_id"]).encode("utf-8", "replace"))
        cur_eq = hmac.compare_digest(presented, r["key_sha256"])
        next_eq = hmac.compare_digest(
            presented, nk["key_sha256"] if nk else _NO_SLOT) and nk is not None
        ok_now = r["status"] == "active" and oa._key_matches(presented, r, now)
        held = cur_eq or next_eq
        refused = held and presented in r.get("refused_hashes", ())
        if id_eq and held:
            matched = "current" if cur_eq else "next"
            matchable = ok_now
            retired = refused
    return 200, {"operator_id": op, "matched": matched, "matchable_now": matchable,
                 "retired": retired, "registry_format": snap.doc.format,
                 "registry_generation": snap.doc.generation,
                 "registry_sha256_prefix": snap.sha256[:REGISTRY_SHA_PREFIX_LEN]}


def clock_synced() -> bool | None:
    """Whether the kernel reports its clock synchronised (adjtimex(2) in read
    mode: anything but TIME_ERROR), or None when that cannot be read (not
    Linux, no libc, an error). None is never "synced" (design 4.3 step 0)."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        buf = ctypes.create_string_buffer(512)   # struct timex, modes = 0 (read only)
        rc = int(libc.adjtimex(buf))
    except Exception:
        return None
    if rc < 0:
        return None
    return rc != _TIME_ERROR


def _own_identity() -> tuple[str | None, str | None]:
    """(shown identity id, sha256 hex of this service's own key) or Nones."""
    own = oa.operator_headers()
    op = os.environ.get(oa.ENV_OPERATOR, "").strip()
    key = own.get(oa.HEADER_KEY)
    shown = NOT_SHOWN if op and key and op == key else shown_id(op)
    return shown, (oa.key_sha256(key) if key else None)


def rotation_state(now: float | None = None) -> dict[str, Any]:
    """The internal rotation state of this process (design 5.2, 5.3; R6 and the
    dead-man check read it): the registry view (format, generation, file and
    roster digests, error), this service's own identity key fingerprint
    (16 hex) and which slot of its row holds it, every row's slot
    fingerprints (16 hex; ``(sealed)`` for the break-glass row) and windows
    and whether each slot would authenticate now, the earliest current-key
    expiry, the oldest current key, the number of NEXT keys, the break-glass
    and retired-hash counters, ``clock_synced`` and ``key_grace_active``.

    ``key_grace_active`` is the K4 flag (an expired kill-switch key accepted
    for kills only): K4 is not implemented by any merged slice, every expired
    key is refused (R1), so it is always false here."""
    m = oa.mode()
    now = oa.clock() if now is None else now
    ident, own_hash = _own_identity()
    out: dict[str, Any] = {
        "operator_mode": m, "now": _iso(int(now)), "registry_format": None,
        "registry_generation": None, "registry_sha256_prefix": None,
        "operator_roster_sha16": None, "operator_registry_rows": None,
        "last_registry_error": None, "identity_id": ident,
        "identity_key_fp": own_hash[:FP_LEN] if own_hash else None,
        "identity_key_slot": None, "rows": [], "keys_next": 0, "expiry_min": None,
        "expiry_min_operator_id": None, "oldest_current_key_created_at": None,
        "oldest_current_key_age_s": None, "key_created_at_missing": 0,
        "counters": {"breakglass_auth_count": oa.breakglass_auth_count,
                     "breakglass_attempt_count": oa.breakglass_attempt_count,
                     "retired_hash_seen": oa.retired_hash_seen,
                     "dropped_unauthenticated_records": oa.dropped_unauthenticated_records},
        "clock_synced": clock_synced(), "key_grace_active": False,
    }
    try:
        snap = oa.load_registry_snapshot()
    except oa.RegistryUnavailable as exc:
        view = registry_view(m)
        out["registry_sha256_prefix"] = view["operator_registry_sha256_prefix"]
        out["last_registry_error"] = view["last_registry_error"] or _clip(str(exc))
        return out
    doc, rows = snap.doc, snap.rows
    out.update({"registry_format": doc.format, "registry_generation": doc.generation,
                "registry_sha256_prefix": snap.sha256[:REGISTRY_SHA_PREFIX_LEN],
                "operator_roster_sha16": roster_sha256(snap.raw)[:REGISTRY_SHA_PREFIX_LEN],
                "operator_registry_rows": len(rows)})
    raw_rows = snap.raw.get("operators") if isinstance(snap.raw, dict) else None
    expiry: tuple[int, str] | None = None
    oldest: int | None = None
    for i, r in enumerate(rows):
        sealed = oa.is_breakglass(r["operator_id"], rows)
        active = r["status"] == "active"
        nk = r.get("next_key")
        created = None
        if doc.format == oa.FORMAT_2 and isinstance(raw_rows, list):
            created = oa.parse_time(raw_rows[i].get("key_created_at"))
        refused = r.get("refused_hashes", ())
        row = {
            "operator_id": shown_id(r["operator_id"]), "status": r["status"],
            "rotation": r.get("rotation"),
            "current_fp": SEALED_FP if sealed else r["key_sha256"][:FP_LEN],
            "current_not_after": _iso(r.get("key_not_after")),
            "current_matchable_now": active and oa._key_matches(r["key_sha256"], r, now),
            "next_fp": None, "next_not_before": None, "next_not_after": None,
            "next_matchable_now": False,
            "key_created_at": _iso(created),
            "retired_slots": sum(1 for h in oa._row_slot_hashes(r) if h in refused),
        }
        if nk is not None:
            row.update({"next_fp": SEALED_FP if sealed else nk["key_sha256"][:FP_LEN],
                        "next_not_before": _iso(nk["not_before"]),
                        "next_not_after": _iso(nk["not_after"]),
                        "next_matchable_now": active and oa._key_matches(nk["key_sha256"], r, now)})
            if active:
                out["keys_next"] += 1
        out["rows"].append(row)
        if own_hash is not None and r["operator_id"] == os.environ.get(oa.ENV_OPERATOR, "").strip():
            out["identity_key_slot"] = ("current" if hmac.compare_digest(own_hash, r["key_sha256"])
                                        else "next" if nk and hmac.compare_digest(
                                            own_hash, nk["key_sha256"]) else "none")
        if not active or sealed:
            continue
        exp = r.get("key_not_after")
        if exp is not None and (expiry is None or exp < expiry[0]):
            expiry = (exp, r["operator_id"])
        if created is None:
            out["key_created_at_missing"] += 1
        elif oldest is None or created < oldest:
            oldest = created
    if own_hash is not None and out["identity_key_slot"] is None:
        out["identity_key_slot"] = "none"
    if expiry is not None:
        out["expiry_min"] = _iso(expiry[0])
        out["expiry_min_operator_id"] = shown_id(expiry[1])
    # unknown is never reported as fresh: one active row without key_created_at
    # (every format 1 row) makes the oldest age unknown
    if oldest is not None and out["key_created_at_missing"] == 0:
        out["oldest_current_key_created_at"] = _iso(oldest)
        out["oldest_current_key_age_s"] = max(0, int(now) - oldest)
    return out


def slot_witness() -> dict[str, Any] | None:
    """For the ledger's C-6 observer (design 5.1, S11): this process's OWN parse
    (pure, no retired-hash memory) of the operators file, as per-row 16-hex
    prefixes of each slot hash, or None when no file is configured or it does
    not pass. The break-glass row shows SEALED_FP; its hashes only feed
    ``_sealed_state``, an in-memory comparison value the observer must never
    write anywhere (it records only whether it changed)."""
    view, _raw, doc = _read_registry(oa.mode())
    if doc is None:
        return None
    rows, sealed = [], []
    for r in doc.rows:
        nk = r.get("next_key")
        if oa.is_breakglass(r["operator_id"], doc.rows):
            sealed.append(r["operator_id"] + ":" + r["key_sha256"])
            rows.append({"operator_id": shown_id(r["operator_id"]), "status": r["status"],
                         "current_fp": SEALED_FP, "next_fp": SEALED_FP if nk else None})
            continue
        rows.append({"operator_id": shown_id(r["operator_id"]), "status": r["status"],
                     "current_fp": r["key_sha256"][:FP_LEN],
                     "next_fp": nk["key_sha256"][:FP_LEN] if nk else None})
    return {"format": doc.format, "generation": doc.generation,
            "registry_sha256_prefix": view["operator_registry_sha256_prefix"], "rows": rows,
            "_sealed_state": hashlib.sha256("\n".join(sorted(sealed)).encode("utf-8")).hexdigest()}


def install_routes(app: Any, h: OperatorHealth) -> None:
    """Add the two internal routes to a FastAPI app (no-op for anything else)."""
    if not hasattr(app, "add_api_route"):
        return
    from fastapi import Request
    from fastapi.responses import JSONResponse
    from starlette.concurrency import run_in_threadpool

    problem = internal_secret_problem()
    if problem:
        raise ValueError(problem)
    headers = {"cache-control": "no-store"}

    def _absent():
        return JSONResponse({"detail": NOT_FOUND_DETAIL}, status_code=404, headers=headers)

    async def verify_hash(request: Request):
        if not internal_routes_enabled() or not internal_request_allowed(request.headers.get(INTERNAL_HEADER)):
            return _absent()
        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > MAX_VERIFY_BODY:
                return JSONResponse({"detail": BAD_BODY_DETAIL}, status_code=413, headers=headers)
        status, payload = await run_in_threadpool(verify_hash_answer, bytes(body))
        return JSONResponse(payload, status_code=status, headers=headers)

    def rotation_state_route(request: Request):
        if not internal_routes_enabled() or not internal_request_allowed(request.headers.get(INTERNAL_HEADER)):
            return _absent()
        return JSONResponse(h.rotation_state(), headers=headers)

    verify_hash.__annotations__ = {"request": Request}
    rotation_state_route.__annotations__ = {"request": Request}
    app.add_api_route(VERIFY_HASH_PATH, verify_hash, methods=["POST"], include_in_schema=False)
    app.add_api_route(ROTATION_STATE_PATH, rotation_state_route, methods=["GET"],
                      include_in_schema=False)


_install_lock = threading.Lock()


def install(app: Any, ledger_getter: Callable[[Any], Any] | None = None,
            **kw: Any) -> OperatorHealth:
    """Create this app's OperatorHealth and keep it on ``app.state``; on a
    FastAPI app also add the internal routes (install_routes)."""
    with _install_lock:
        h = OperatorHealth(app, ledger_getter, **kw)
        app.state.operator_health = h
        install_routes(app, h)
        return h
