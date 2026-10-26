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
  records dropped under flood (the guard's process-wide counter).
* ``refused_count`` / ``dropped_refused_records``: refusals this app's
  operator layer returned (any armed mode), and ``operator.refused`` records
  not written because of the caps below.
* ``manifests_unresolved`` (only when the caller passes ``manifest_refs``: the
  agent registry and the kill-switch): how many of the given manifest refs do
  not resolve (``missing`` / ``invalid``) in this process. Null when OFF or
  when the agent list cannot be read.

Never in the block: a key, a key hash, a row, or any registry content.

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
are counted in ``dropped_refused_records``. LOG-ONLY refusals (a malformed
header, a refused ``operator.*`` ledger append) are counted, not ledgered.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
import re
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


class OperatorHealthWithManifests(OperatorHealthFields):
    manifests_unresolved: int | None = None


def shown_id(value: str | None) -> str | None:
    """An operator id fit to print on an open endpoint or in a ledger row:
    None stays None; anything outside the operator id charset, or carrying the
    key prefix, is NOT_SHOWN (a key pasted where an id belongs is never
    echoed)."""
    if not value:
        return None
    if not oa._OPERATOR_RE.fullmatch(value) or value.startswith(KEY_PREFIX):
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


def registry_view(mode: str | None = None) -> dict[str, Any]:
    """sha256 prefix, row count and current error of the operators file, read
    once (the digest and the count describe the same bytes)."""
    m = mode or oa.mode()
    out: dict[str, Any] = {"operator_registry_sha256_prefix": None,
                           "operator_registry_rows": None, "last_registry_error": None}
    path = oa.registry_path()
    if not path:
        if m == oa.ENFORCE:
            out["last_registry_error"] = "operator registry path is not set"
        return out
    try:
        data = Path(path).read_bytes()
    except (OSError, ValueError) as exc:
        out["last_registry_error"] = f"operator registry unreadable: {type(exc).__name__}"
        return out
    out["operator_registry_sha256_prefix"] = hashlib.sha256(data).hexdigest()[
        :REGISTRY_SHA_PREFIX_LEN]
    try:
        raw = json.loads(data.decode("utf-8-sig"))      # as load_registry reads it
    except (UnicodeDecodeError, ValueError) as exc:
        out["last_registry_error"] = f"operator registry unreadable: {type(exc).__name__}"
        return out
    try:
        rows = oa.parse_registry(raw, require_active=m == oa.ENFORCE)
    except oa.RegistryUnavailable as exc:
        out["last_registry_error"] = _clip(str(exc))
        return out
    out["operator_registry_rows"] = len(rows)
    return out


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
            except Exception:
                pass
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


_install_lock = threading.Lock()


def install(app: Any, ledger_getter: Callable[[Any], Any] | None = None,
            **kw: Any) -> OperatorHealth:
    """Create this app's OperatorHealth and keep it on ``app.state``."""
    with _install_lock:
        h = OperatorHealth(app, ledger_getter, **kw)
        app.state.operator_health = h
        return h
