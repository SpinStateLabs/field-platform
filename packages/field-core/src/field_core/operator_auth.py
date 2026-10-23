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
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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
     "mint_for_others", "decommission"}
)


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def registry_path() -> str | None:
    return os.environ.get(ENV_REGISTRY, "").strip() or None


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
    failure: str | None = None       # log-only: why it was not authenticated

    @property
    def authenticated(self) -> bool:
        return self.operator_id is not None

    def has_scope(self, action: str) -> bool:
        # "*" covers every ordinary action but NOT mint_for_others: naming a
        # grantor other than yourself is an explicit, narrow grant.
        if action == "mint_for_others":
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


def ledger_fields() -> dict:
    """Fields merged into a ledger payload INSIDE the service's own append
    (so they are covered by its signature). {} when the mode is off."""
    return _current.get().ledger_fields()


def load_registry(path: str | None = None) -> list[dict]:
    """Parse the operators file. Any problem is RegistryUnavailable; the
    caller turns that into a 503 in ENFORCE mode (never an allow)."""
    path = path or registry_path()
    if not path:
        raise RegistryUnavailable("operator registry path is not set")
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
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
        scopes = r.get("scopes", [])
        if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
            raise RegistryUnavailable("operator registry malformed")
        out.append({"operator_id": r["operator_id"], "key_sha256": r["key_sha256"],
                    "status": r.get("status", "active"), "scopes": tuple(scopes)})
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


def _verify(operator: str, key: str, rows: list[dict]) -> tuple[bool, tuple[str, ...]]:
    """Hash and compare against EVERY row (no early exit), also for an unknown
    id, so timing reveals neither which ids exist nor which row matched."""
    presented = key_sha256(key)
    dummy = "0" * 64
    ok = False
    scopes: tuple[str, ...] = ()
    for r in rows or [{"operator_id": "", "key_sha256": dummy, "status": "revoked", "scopes": ()}]:
        hash_eq = hmac.compare_digest(presented, r["key_sha256"])
        id_eq = hmac.compare_digest(operator.encode(), r["operator_id"].encode())
        if hash_eq and id_eq and r["status"] == "active":
            ok = True
            scopes = r["scopes"]
    return ok, scopes


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
    ok, scopes = _verify(op, key, rows)
    if not ok:
        return fail(403, FORBIDDEN_DETAIL, "bad_credential")
    auth = OperatorAuth(m, operator_id=op, claimed=op, key_fp=key_fingerprint(key),
                        scopes=scopes)
    if not auth.has_scope(action):
        return fail(403, FORBIDDEN_DETAIL, "scope")
    return auth


def check_authorized(auth: OperatorAuth, authorized: list[str] | None) -> None:
    """manifest ``kill_switch.authorized_operators`` (non-empty list): the
    authenticated id must be on it. Same 403 as every other refusal."""
    if auth.mode != ENFORCE or not authorized:
        return
    if auth.operator_id not in set(authorized):
        raise OperatorRefused(403, FORBIDDEN_DETAIL)


def check_granted_by(auth: OperatorAuth, granted_by: str) -> None:
    """Mint: ``granted_by`` must equal the authenticated id, unless the
    identity holds the narrow ``mint_for_others`` scope (provisioning)."""
    if auth.mode != ENFORCE or not auth.authenticated:
        return
    if granted_by != auth.operator_id and not auth.has_scope("mint_for_others"):
        raise OperatorRefused(403, FORBIDDEN_DETAIL)


def guard(action: str, rows_loader: Callable[[], list[dict]] | None = None,
          ledger_getter: Callable[[object], object] | None = None):
    """FastAPI dependency factory for one guarded action. Async so the
    contextvar it binds is inherited by the threadpool the sync handler runs
    in; the (file-reading) check itself runs in the threadpool.

    ``ledger_getter(app)`` returns an object with ``append`` used to record
    ``operator.unauthenticated`` in LOG_ONLY mode (best effort: the write is
    allowed either way)."""
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
                        ledger.append, "operator.unauthenticated",
                        {"action": action, "path": request.url.path,
                         "reason": auth.failure, "operator_claimed": auth.claimed},
                        None)
            except Exception:
                pass
        return auth

    # `from __future__ import annotations` made the annotation a string FastAPI
    # cannot resolve (Request is imported locally): pin the real class.
    _guard.__annotations__ = {"request": Request, "return": OperatorAuth}
    return _guard
