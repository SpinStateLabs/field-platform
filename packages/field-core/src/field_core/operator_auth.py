"""Authenticated operators (v1.2 Phase G).

Guarded writes (kill, revive, drill, attest, rotate, hold place/release, mint,
decommission) can require an operator identity proven by a key:

    x-field-operator:      the operator id
    x-field-operator-key:  that operator's key

The verifier reads a LOCAL operators file (like the DOA and lifecycle
rosters), so a kill works with the agent registry down. The file stores only
the sha256 of each key::

    [{"operator_id": "don", "key_sha256": "<hex>", "status": "active",
      "created_at": "2026-..", "scopes": ["*"]}, ...]

Two env flags, both unset by default (the pre-Phase-G behaviour, reversible):

* ``FIELD_OPERATOR_REGISTRY=<path>`` -- LOG-ONLY. The credential is evaluated;
  a guarded write that is unauthenticated, or whose credential fails, is
  ledgered as ``operator.unauthenticated`` and STILL ALLOWED. Malformed
  credential headers are a 400 in any non-off mode (a request defect, not an
  identity decision).
* ``FIELD_OPERATOR_REQUIRE=1`` -- ENFORCE. No credential => 401. Wrong key,
  id/key mismatch, unknown or revoked id, missing scope, id not in the
  manifest's ``kill_switch.authorized_operators`` => 403 with one identical
  body (no oracle). An unreadable or unset registry file => 503, never
  fail-open. NOT armed anywhere; arming it is not undone by an image rollback
  (todo.md reversibility row G).

Declared limitation: the key is a bearer secret sent in a header. On plain HTTP
anyone who can read the wire can replay it. TLS and replay protection are the
deployment's job (Caddy / Fly edge), not this module.

Neither header is ever logged, echoed, or put in an exception message.
"""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

log = logging.getLogger("field_core.operator_auth")

HEADER_OPERATOR = "x-field-operator"
HEADER_KEY = "x-field-operator-key"
ENV_REGISTRY = "FIELD_OPERATOR_REGISTRY"
ENV_REQUIRE = "FIELD_OPERATOR_REQUIRE"
# Client side: the identity an internal caller or CLI presents.
ENV_OPERATOR = "FIELD_OPERATOR"
ENV_OPERATOR_KEY = "FIELD_OPERATOR_KEY"

OFF, LOG_ONLY, ENFORCE = "off", "log-only", "enforce"

MAX_OPERATOR_LEN = 64
MAX_KEY_LEN = 256
_OPERATOR_RE = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")
_KEY_RE = re.compile(r"^[A-Za-z0-9._~+/=-]{1,256}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

#: The one refusal body for every 403, so a caller cannot tell a wrong key from
#: a wrong id, a missing scope or a manifest that does not list them.
FORBIDDEN_DETAIL = "operator not authorised"
UNAUTH_DETAIL = "operator credentials required"

#: Scopes. "*" grants all. Internal callers get narrow scopes (e.g. the
#: lifecycle service identity holds only "kill"); "mint_for_others" lets a
#: provisioning identity mint with a granted_by that is not itself.
ACTIONS = frozenset(
    {"kill", "revive", "drill", "attest", "rotate", "hold", "mint",
     "mint_for_others", "decommission", "revoke", "retention", "sweep",
     "assert_operator", "registry_edit", "register", "caps", "federation",
     "escalation", "export"}
)

#: Never implied by "*": each is an explicit, narrow grant.
#: ``assert_operator`` lets a SERVICE identity put authenticated-operator
#: fields into a ledger event it appends on a human's behalf.
EXPLICIT_ONLY = frozenset({"mint_for_others", "assert_operator"})

#: Ledger payload keys only the authenticated path may set.
RESERVED_KEYS = frozenset(
    {"operator_id_authenticated", "operator_claimed", "operator_key_fp",
     "operator_body_claimed"}
)


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


_OFF_SPELLINGS = frozenset({"", "0", "false", "no", "off"})


def registry_path() -> str | None:
    """The operators file path, or None. Blank, whitespace and the usual
    "off" spellings (0/false/no/off, any case) are OFF, exactly as for
    FIELD_OPERATOR_REQUIRE: an .env line ``FIELD_OPERATOR_REGISTRY=0`` must not
    arm LOG-ONLY against a file named "0"."""
    v = os.environ.get(ENV_REGISTRY, "").strip()
    return None if v.lower() in _OFF_SPELLINGS else v


def mode() -> str:
    """Read per call: a flag flip needs no restart and no test leaks."""
    if _flag(ENV_REQUIRE):
        return ENFORCE
    if registry_path():
        return LOG_ONLY
    return OFF


def key_sha256(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_fingerprint(key: str) -> str:
    return key_sha256(key)[:8]


def operator_headers() -> dict[str, str]:
    """Client side: the two headers from FIELD_OPERATOR / FIELD_OPERATOR_KEY,
    or {}. ``field_core.authn.auth_headers`` merges these so every internal
    client carries its service identity once the env is set."""
    op = os.environ.get(ENV_OPERATOR, "").strip()
    key = os.environ.get(ENV_OPERATOR_KEY, "")
    if op and key:
        return {HEADER_OPERATOR: op, HEADER_KEY: key}
    return {}


class OperatorRefused(Exception):
    """Carries the HTTP status. ``detail`` is a fixed string, never a header."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class RegistryUnavailable(Exception):
    pass


@dataclass(frozen=True)
class OperatorAuth:
    mode: str
    operator_id: str | None = None   # authenticated id (None = not proven)
    claimed: str | None = None       # what the header said, proven or not
    key_fp: str | None = None
    scopes: tuple[str, ...] = ()
    names: tuple[str, ...] = ()      # aliases (display names) from operators.json
    failure: str | None = None       # log-only: why it was not authenticated

    @property
    def authenticated(self) -> bool:
        return self.operator_id is not None

    def has_scope(self, action: str) -> bool:
        # "*" covers every ordinary action but NOT mint_for_others: naming a
        # grantor other than yourself is an explicit, narrow grant.
        if action in EXPLICIT_ONLY:
            return action in self.scopes
        return "*" in self.scopes or action in self.scopes

    def ledger_fields(self) -> dict:
        if self.mode == OFF:
            return {}
        return {
            "operator_id_authenticated": self.operator_id,
            "operator_claimed": self.claimed,
            "operator_key_fp": self.key_fp if self.authenticated else None,
        }


NO_AUTH = OperatorAuth(OFF)

_current: contextvars.ContextVar[OperatorAuth] = contextvars.ContextVar(
    "field_operator_auth", default=NO_AUTH
)


def current() -> OperatorAuth:
    return _current.get()


def bind(auth: OperatorAuth) -> contextvars.Token:
    return _current.set(auth)


_body_claim: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "field_operator_body_claim", default=None
)


def ledger_fields() -> dict:
    """Fields merged into a ledger payload INSIDE the service's own append
    (so they are covered by its signature). {} when the mode is off."""
    f = _current.get().ledger_fields()
    if f and _body_claim.get() is not None:
        f = {**f, "operator_body_claimed": _body_claim.get()}
    return f


def merge_payload(payload: dict) -> dict:
    """The only way operator fields enter a payload: any caller-supplied
    reserved key is dropped, then the authenticated context (if any) is set."""
    if mode() == OFF:
        return payload            # flags OFF: byte-identical to pre-Phase-G
    clean = _strip_reserved(payload)
    clean.update(ledger_fields())
    return clean


def _has_reserved(obj) -> bool:
    if isinstance(obj, dict):
        return any(k in RESERVED_KEYS or _has_reserved(v) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return any(_has_reserved(v) for v in obj)
    return False


def _strip_reserved(obj):
    """Reserved keys removed at EVERY depth (a nested copy is still a forgery
    to anyone reading the event)."""
    if isinstance(obj, dict):
        return {k: _strip_reserved(v) for k, v in obj.items() if k not in RESERVED_KEYS}
    if isinstance(obj, list):
        return [_strip_reserved(v) for v in obj]
    return obj


def bind_body_operator(value: str) -> str:
    """The request body's free-text operator name must not stand in for the
    proven identity. When the request is authenticated the authenticated id
    replaces it (the discrepancy is ledgered as ``operator_body_claimed``);
    otherwise the value is returned unchanged."""
    auth = _current.get()
    if auth.authenticated:
        if value != auth.operator_id:
            _body_claim.set(value)
        return auth.operator_id
    return value


def strip_reserved_unless_asserted(payload: dict, headers) -> dict:
    """Ledger POST /events: reserved operator keys survive only when the
    caller is an authenticated service identity holding ``assert_operator``.
    Anyone else's reserved keys are forged and are dropped."""
    if mode() == OFF or not _has_reserved(payload):
        return payload            # flags OFF: nothing is rewritten
    try:
        a = authenticate(headers, "assert_operator")
        if a.authenticated:
            return payload
    except OperatorRefused:
        pass
    _warn_attribution_loss_once()
    return _strip_reserved(payload)


_warned = False


def _warn_attribution_loss_once() -> None:
    """A service that adds authenticated-operator fields but lacks the
    assert_operator scope has them stripped by the ledger: say so, once, so
    the loss of attribution is never silent."""
    global _warned
    if not _warned:
        _warned = True
        log.warning(
            "operator attribution LOST: a ledger append carried authenticated-operator "
            "fields from a caller without the assert_operator scope; the fields were "
            "dropped. Give the appending service a FIELD_OPERATOR identity with assert_operator.")


def reject_reserved_event_type(event_type: str, headers) -> None:
    """Event types in the ``operator.`` namespace are written by the guard
    itself; a caller without assert_operator may not forge them. Armed only."""
    if mode() == OFF or not event_type.strip().lower().startswith("operator."):
        return
    try:
        if authenticate(headers, "assert_operator").authenticated:
            return
    except OperatorRefused:
        pass
    raise OperatorRefused(403, FORBIDDEN_DETAIL)


def check_record_authorized(auth: OperatorAuth, manifest_ref: str | None) -> None:
    """The kill-switch and the registry share this: resolve the record's
    manifest and enforce its ``kill_switch.authorized_operators``. A manifest
    that is referenced but unreadable is a 503 (deny); no manifest_ref at all
    declares no list, so authentication + scope are all that apply."""
    if auth.mode != ENFORCE:
        return
    if auth.authenticated and auth.has_scope("assert_operator"):
        # A service identity (kill-switch, lifecycle, sentinel, canary tooling)
        # acts for a human it has ALREADY checked, or for itself; a human key
        # never holds this scope. Every authorized_operators check shares this.
        return
    from field_core.clients import resolve_manifest_detail

    manifest, why = resolve_manifest_detail(manifest_ref)
    listed = None
    if manifest is None and why != "no_ref":
        raise OperatorRefused(503, "manifest unresolvable - cannot check authorized_operators")
    if manifest is not None:
        try:
            listed = manifest.enforcement.kill_switch.authorized_operators
        except AttributeError:  # pragma: no cover
            listed = None
    check_authorized(auth, listed)


def validate_rows(rows: list[dict]) -> str | None:
    """Identity-collision rules (fail closed). Returns a description of the
    first problem (ids and aliases only - never key or hash material) or None.

    * a duplicate operator_id is rejected outright (no later row can silently
      supersede, or fail to supersede, an earlier one);
    * an alias equal to ANY row's id is rejected (it would let one human satisfy
      a list naming another);
    * an alias shared by two rows is rejected;
    * the alias "*" is rejected (it would match a list that says "*")."""
    seen: set[str] = set()
    for r in rows:
        oid = str(r["operator_id"])
        if oid in seen:
            return f"duplicate operator_id '{oid}'"
        seen.add(oid)
    owner_of: dict[str, str] = {}
    for r in rows:
        for n in r.get("names", ()):
            if n == "*":
                return f"alias '*' on operator '{r['operator_id']}'"
            if n in seen:
                return f"alias '{n}' of operator '{r['operator_id']}' equals an operator id"
            if n in owner_of and owner_of[n] != r["operator_id"]:
                return f"alias '{n}' is shared by '{owner_of[n]}' and '{r['operator_id']}'"
            owner_of[n] = r["operator_id"]
    return None


def load_registry(path: str | None = None) -> list[dict]:
    """Parse the operators file. Any problem is RegistryUnavailable; the
    caller turns that into a 503 in ENFORCE mode (never an allow)."""
    path = path or registry_path()
    if not path:
        raise RegistryUnavailable("operator registry path is not set")
    try:
        # utf-8-sig: Windows PowerShell 5.1 writes a BOM.
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RegistryUnavailable(f"operator registry unreadable: {type(exc).__name__}")
    rows = raw.get("operators") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise RegistryUnavailable("operator registry malformed")
    out = []
    for r in rows:
        if (not isinstance(r, dict) or not isinstance(r.get("operator_id"), str)
                or not _HEX64.match(str(r.get("key_sha256", "")))):
            raise RegistryUnavailable("operator registry malformed")
        try:
            r["operator_id"].encode("utf-8")
        except UnicodeEncodeError:
            continue  # a lone surrogate can never authenticate: drop the row
        scopes = r.get("scopes", [])
        if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
            raise RegistryUnavailable("operator registry malformed")
        names = r.get("names", [])
        if (not isinstance(names, list)
                or not all(isinstance(n, str) and 0 < len(n) <= 128 for n in names)):
            raise RegistryUnavailable("operator registry malformed")
        out.append({"operator_id": r["operator_id"], "key_sha256": r["key_sha256"],
                    "status": r.get("status", "active"), "scopes": tuple(scopes),
                    "names": tuple(names)})
    problem = validate_rows(out)
    if problem:
        log.error("operator registry rejected (fail closed): %s", problem)
        raise RegistryUnavailable("operator registry ambiguous")
    return out


def parse_headers(request_headers) -> tuple[str | None, str | None]:
    """Exactly one of each, ASCII, charset- and length-capped. Duplicates,
    comma-joined multi-values, non-ASCII or oversize => 400. Accepts a
    Starlette Headers (``getlist``) or a plain dict."""
    def one(name: str) -> str | None:
        if hasattr(request_headers, "getlist"):
            vals = request_headers.getlist(name)
        else:
            lowered = {k.lower(): v for k, v in dict(request_headers).items()}
            vals = [lowered[name]] if name in lowered else []
        if not vals:
            return None
        if len(vals) != 1:
            raise OperatorRefused(400, "malformed operator credential headers")
        v = vals[0]
        # Comma-joined multi-values, non-ASCII, whitespace and oversize are all
        # outside the anchored charset regexes below; only emptiness needs
        # its own check.
        if not v:
            raise OperatorRefused(400, "malformed operator credential headers")
        return v

    op = one(HEADER_OPERATOR)
    key = one(HEADER_KEY)
    if op is not None and not _OPERATOR_RE.match(op):
        raise OperatorRefused(400, "malformed operator credential headers")
    if key is not None and not _KEY_RE.match(key):
        raise OperatorRefused(400, "malformed operator credential headers")
    return op, key


def _verify(operator: str, key: str, rows: list[dict]) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    """Hash and compare against EVERY row (no early exit), also for an unknown
    id, so timing reveals neither which ids exist nor which row matched."""
    presented = key_sha256(key)
    dummy = "0" * 64
    ok = False
    scopes: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    for r in rows or [{"operator_id": "", "key_sha256": dummy, "status": "revoked", "scopes": ()}]:
        hash_eq = hmac.compare_digest(presented, r["key_sha256"])
        id_eq = hmac.compare_digest(
            operator.encode("utf-8", "replace"), str(r["operator_id"]).encode("utf-8", "replace"))
        if hash_eq and id_eq and r["status"] == "active":
            ok = True
            scopes = r["scopes"]
            names = tuple(r.get("names", ()))
    return ok, scopes, names


def authenticate(
    headers, action: str, rows_loader: Callable[[], list[dict]] | None = None
) -> OperatorAuth:
    """Evaluate a guarded write. Returns the OperatorAuth (in LOG_ONLY a failed
    credential comes back with ``failure`` set and is NOT raised). Raises
    OperatorRefused in ENFORCE (401/403/503) and for malformed headers (400)."""
    m = mode()
    if m == OFF:
        return NO_AUTH
    op, key = parse_headers(headers)
    enforce = m == ENFORCE

    def fail(status: int, detail: str, why: str) -> OperatorAuth:
        if enforce:
            raise OperatorRefused(status, detail)
        return OperatorAuth(m, claimed=op, failure=why)

    if op is None or key is None:
        return fail(401, UNAUTH_DETAIL, "no_credential" if op is None and key is None
                    else "incomplete_credential")
    try:
        rows = (rows_loader or load_registry)()
    except RegistryUnavailable:
        if enforce:
            raise OperatorRefused(503, "operator registry unavailable")
        return OperatorAuth(m, claimed=op, failure="registry_unavailable")
    ok, scopes, names = _verify(op, key, rows)
    if not ok:
        return fail(403, FORBIDDEN_DETAIL, "bad_credential")
    auth = OperatorAuth(m, operator_id=op, claimed=op, key_fp=key_fingerprint(key),
                        scopes=scopes, names=names)
    if not auth.has_scope(action):
        return fail(403, FORBIDDEN_DETAIL, "scope")
    return auth


def check_authorized(auth: OperatorAuth, authorized: list[str] | None) -> None:
    """manifest ``kill_switch.authorized_operators`` (non-empty list): the
    authenticated id must be on it. Same 403 as every other refusal."""
    if auth.mode != ENFORCE:
        return
    # Under ENFORCE the caller must be authenticated whatever the list says:
    # an empty list means "no restriction beyond authentication + scope",
    # never "anyone".
    if not auth.authenticated:
        raise OperatorRefused(401, UNAUTH_DETAIL)
    if not authorized:
        return
    # The id, or any alias Don registered for this operator (manifests list
    # DISPLAY names such as "Don Hagell, Spin State Labs"). Exact, case-sensitive.
    listed = set(authorized)
    if auth.operator_id not in listed and not (set(auth.names) & listed):
        raise OperatorRefused(403, FORBIDDEN_DETAIL)


def check_granted_by(auth: OperatorAuth, granted_by: str) -> None:
    """Mint: ``granted_by`` must equal the authenticated id, unless the
    identity holds the narrow ``mint_for_others`` scope (provisioning)."""
    if auth.mode != ENFORCE or not auth.authenticated:
        return
    if granted_by != auth.operator_id and not auth.has_scope("mint_for_others"):
        raise OperatorRefused(403, FORBIDDEN_DETAIL)


LEDGER_APPEND_TIMEOUT_S = 1.5
MAX_CONCURRENT_UNAUTH_RECORDS = 8
_unauth_slots = threading.BoundedSemaphore(MAX_CONCURRENT_UNAUTH_RECORDS)
dropped_unauthenticated_records = 0


def _record_unauthenticated(ledger, action: str, path: str, auth: OperatorAuth) -> None:
    """Best effort and BOUNDED: the append runs in a daemon thread and we wait
    at most LEDGER_APPEND_TIMEOUT_S, so a slow ledger cannot delay a kill."""
    if not _unauth_slots.acquire(blocking=False):
        global dropped_unauthenticated_records
        dropped_unauthenticated_records += 1      # drop-and-count under flood
        return

    def _go() -> None:
        try:
            ledger.append(
                "operator.unauthenticated",
                {"action": action, "path": path, "reason": auth.failure,
                 "operator_claimed": auth.claimed}, None)
        except Exception:
            pass
        finally:
            _unauth_slots.release()

    t = threading.Thread(target=_go, daemon=True)
    t.start()
    t.join(LEDGER_APPEND_TIMEOUT_S)


def authorize_sync(headers, action: str, path: str = "", ledger=None,
                   rows_loader: Callable[[], list[dict]] | None = None) -> OperatorAuth:
    """Authenticate + bind for code that already runs in a worker thread (a
    handler whose action depends on the body). Raises OperatorRefused."""
    auth = authenticate(headers, action, rows_loader)
    bind(auth)
    if auth.mode == LOG_ONLY and not auth.authenticated and ledger is not None:
        _record_unauthenticated(ledger, action, path, auth)
    return auth


def guard(action: str, rows_loader: Callable[[], list[dict]] | None = None,
          ledger_getter: Callable[[object], object] | None = None):
    """FastAPI dependency factory for one guarded action. Async so the
    contextvar it binds is inherited by the threadpool the sync handler runs
    in; the (file-reading) check itself runs in the threadpool.

    ``ledger_getter(app)`` returns an object with ``append`` used to record
    ``operator.unauthenticated`` in LOG_ONLY mode (best effort, bounded)."""
    from fastapi import HTTPException, Request
    from starlette.concurrency import run_in_threadpool

    async def _guard(request: Request) -> OperatorAuth:
        try:
            auth = await run_in_threadpool(
                authenticate, request.headers, action, rows_loader)
        except OperatorRefused as exc:
            raise HTTPException(exc.status, exc.detail)
        bind(auth)
        if auth.mode == LOG_ONLY and not auth.authenticated and ledger_getter:
            try:
                ledger = ledger_getter(request.app)
                if ledger is not None:
                    await run_in_threadpool(
                        _record_unauthenticated, ledger, action,
                        request.url.path, auth)
            except Exception:
                pass
        return auth

    # `from __future__ import annotations` made the annotation a string FastAPI
    # cannot resolve (Request is imported locally): pin the real class.
    _guard.__annotations__ = {"request": Request, "return": OperatorAuth}
    return _guard
