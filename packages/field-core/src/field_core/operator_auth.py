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

Every row needs ``status`` exactly ``active`` or ``revoked`` and a 64
lower-case hex ``key_sha256``; one bad row makes the whole file unavailable,
and under ENFORCE so does a file with no active row (parse_registry, C-18).
A ``ledger_attribute`` row lists ``event_prefixes`` (C-10).

Format 2 (key rotation, ``{"format": 2, "generation": N, "operators": [...]}``)
is a closed schema: each row holds a CURRENT key (``key_sha256`` with a
mandatory ``key_not_after``) and at most one NEXT key slot
(``next_key: {key_sha256, not_before, not_after}``), so a key can be replaced
without changing the identity. See _parse_format2 and _key_matches. A file
without ``format`` is format 1 and is read exactly as before.

Two env flags, both unset by default (the pre-Phase-G behaviour, reversible):

* ``FIELD_OPERATOR_REGISTRY=<path>`` -- LOG-ONLY. The credential is evaluated;
  a guarded write that is unauthenticated, or whose credential fails, is
  ledgered as ``operator.unauthenticated`` and STILL ALLOWED. Malformed
  credential headers are a 400 in any non-off mode (a request defect, not an
  identity decision).
* ``FIELD_OPERATOR_REQUIRE=1`` -- ENFORCE (so is any other non-empty value
  that is not 0/false/no/off, with a log error: C-17). No credential => 401. Wrong key,
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
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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
#: Client side (C-1): a path whose stripped content is the key, read on every
#: call. When set (non-blank) it is the ONLY key source; FIELD_OPERATOR_KEY
#: stays for tests and Fly secrets.
ENV_OPERATOR_KEY_FILE = "FIELD_OPERATOR_KEY_FILE"
#: A key file larger than this is not a key file.
MAX_KEY_FILE_BYTES = 4096

OFF, LOG_ONLY, ENFORCE = "off", "log-only", "enforce"

MAX_OPERATOR_LEN = 64
MAX_KEY_LEN = 256
_OPERATOR_RE = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")
_KEY_RE = re.compile(r"^[A-Za-z0-9._~+/=-]{1,256}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

#: The prefix ``operator_keygen.py`` gives every key it generates.
KEY_PREFIX = "fok_"
#: What an error message or a record says instead of a value that could be a key.
NOT_SHOWN = "(not shown)"


#: PG0-CORE-R2-03: an unbroken token this long (no dot, no @) is treated as a key
#: even without the key prefix: 32 random bytes are 43 base64url or 64 hex
#: characters, and operator ids are short names (``don``, ``svc-killswitch``).
_TOKEN_ID_RE = re.compile(r"[A-Za-z0-9_-]{40,}")


def printable_id(value) -> bool:
    """PG0-CORE-R1-10: True when ``value`` may be printed or stored where an
    operator id or alias belongs (an error message, an open /health, a log
    line, keygen output, a ledger row): inside the operator id charset, without
    the key prefix and (PG0-CORE-R2-03) not a 40+ character unbroken token. A
    key pasted into ``operator_id``, ``names`` or the id header is never
    echoed."""
    return (isinstance(value, str) and _OPERATOR_RE.fullmatch(value) is not None
            and not value.startswith(KEY_PREFIX)
            and _TOKEN_ID_RE.fullmatch(value) is None)


def shown_claim(value):
    """PG0-CORE-R2-01: a claimed operator id as it may be stored in a ledger
    row (``claimed_id`` / ``operator_claimed``): None stays None, a printable id
    is kept, anything else (a key in the id header after a swapped env pair, a
    non-string) is NOT_SHOWN."""
    if value is None:
        return None
    return value if printable_id(value) else NOT_SHOWN


def _shown_name(value) -> str:
    """An alias for an error message: display names (``Don Hagell, Spin State
    Labs``) are kept; a value carrying the key prefix, or a long unbroken
    token-shaped string, is NOT_SHOWN."""
    if (not isinstance(value, str) or value.startswith(KEY_PREFIX)
            or re.fullmatch(r"[A-Za-z0-9._~+/=-]{24,}", value)):
        return NOT_SHOWN
    return f"'{value}'"


def _shown_oid(value) -> str:
    return f"'{value}'" if printable_id(value) else NOT_SHOWN


#: PG0-CORE-R1-14: the request path in an ``operator.unauthenticated`` /
#: ``operator.refused`` record is attacker-chosen text. It is clipped to this
#: many characters and kept only when it is printable URL-path text without
#: the key prefix (else NOT_SHOWN).
MAX_RECORDED_PATH_LEN = 200
_RECORDED_PATH_RE = re.compile(r"[A-Za-z0-9._~:/@+%=,-]*")


def recorded_path(path) -> str:
    """The request path as it may be stored in an operator.* ledger record."""
    if not isinstance(path, str):
        return NOT_SHOWN if path is not None else ""
    if len(path) > MAX_RECORDED_PATH_LEN:
        path = path[: MAX_RECORDED_PATH_LEN - 3] + "..."
    if not _RECORDED_PATH_RE.fullmatch(path) or KEY_PREFIX in path:
        return NOT_SHOWN
    return path

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
     "escalation", "export", "ledger_attribute", "bypass_operator_list",
     "sweep_kill"}
)

#: Never implied by "*": each is an explicit, narrow grant.
#: C-10 split of the old ``assert_operator``: ``bypass_operator_list`` only
#: skips a manifest's ``authorized_operators`` check (grants no action by
#: itself); ``ledger_attribute`` only lets reserved operator keys through the
#: ledger, and only on event types that start with one of the row's
#: ``event_prefixes``. ``sweep_kill`` (C-11) lets a served lifecycle sweep
#: auto-kill orphans under ENFORCE; lifecycle reads it from the row itself, and
#: being here keeps every ``has_scope`` reader (health, probes) from counting a
#: ``*`` row as holding it.
EXPLICIT_ONLY = frozenset(
    {"mint_for_others", "assert_operator", "ledger_attribute", "bypass_operator_list",
     "sweep_kill"})

#: Scope names a registry row may no longer carry (C-10). ``assert_operator``
#: stays in ACTIONS only so the rejection can name it; a file that still
#: grants it is refused whole, so it can never silently grant both halves.
REJECTED_SCOPES = frozenset({"assert_operator"})

#: ``operator.*`` event types the ledger accepts from any HTTP caller (C-10,
#: C-15/C-16): the guards' own records of an unauthenticated or refused
#: attempt. Exact spelling only; every other ``operator.*`` type is refused.
SELF_REPORTABLE_EVENT_TYPES = frozenset({"operator.unauthenticated", "operator.refused"})

#: A row's ``event_prefixes`` entry: dotted lower-case segments ending in ".".
_EVENT_PREFIX_RE = re.compile(r"^[a-z0-9_-]+\.(?:[a-z0-9_-]+\.)*$")
MAX_EVENT_PREFIX_LEN = 64

#: The only accepted ``status`` values (C-18): exact, lower case, required.
STATUSES = frozenset({"active", "revoked"})

# --- operators file format 2 (key rotation design 2026-10-27, section 2.1, slice R1) ---
#: A top-level object with ``"format": 2`` is read under a CLOSED schema: every
#: field below is known, anything else makes the whole file unavailable. A file
#: without ``format`` (a list, or ``{"operators": [...]}``) or with
#: ``"format": 1`` is format 1 and is read exactly as before.
FORMAT_2 = 2
#: ``rotation``: who rotates the row's key (``sealed`` = break-glass, K7).
ROTATIONS = frozenset({"auto", "sealed", "remote"})
#: The only scopes a ``rotation: sealed`` row may hold (design 2.1).
SEALED_SCOPES = frozenset({"kill", "revive", "bypass_operator_list"})
#: ``auth``: how a row may authenticate. Only ``key`` is verified by this
#: module; ``session`` (passkey sessions) is slice H1. Absent = ``["key"]``.
AUTH_METHODS = frozenset({"key", "session"})
PASSKEY_ALGS = frozenset({"ES256", "EdDSA"})
_F2_TOP_REQUIRED = frozenset({"format", "generation", "operators"})
_F2_TOP_FIELDS = _F2_TOP_REQUIRED | {"issued_at", "issued_by"}
_F2_ROW_REQUIRED = frozenset({"operator_id", "status", "key_sha256", "rotation", "scopes"})
_F2_ROW_FIELDS = _F2_ROW_REQUIRED | {
    "names", "event_prefixes", "created_at", "key_created_at", "key_not_after",
    "next_key", "auth", "passkeys"}
_NEXT_KEY_FIELDS = frozenset({"key_sha256", "not_before", "not_after"})
_PASSKEY_FIELDS = frozenset(
    {"credential_id", "public_key_spki", "alg", "enrolled_at", "label", "hardware"})
#: Fields only format 2 defines. In a file that does not declare format 2 they
#: make the file unavailable: read leniently, an expiry or a NEXT slot would be
#: silently ignored (a dropped ``format`` line must fail closed, not open).
_F2_ONLY_TOP_FIELDS = frozenset({"generation", "issued_at", "issued_by"})
_F2_ONLY_ROW_FIELDS = frozenset(
    {"rotation", "key_created_at", "key_not_after", "next_key", "auth", "passkeys"})
#: Strict ISO 8601 UTC, whole seconds, ``Z`` (ASCII digits only).
_TIME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_FIELD_NAME_RE = re.compile(r"^[a-z_]{1,32}$")
_CREDENTIAL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,1366}$")
_SPKI_RE = re.compile(r"^[A-Za-z0-9_-]{40,2048}$")
_PASSKEY_LABEL_RE = re.compile(r"^[A-Za-z0-9 ._@()-]{1,64}$")
#: What the verifier compares a row's empty NEXT slot against, so every format 2
#: row costs the same number of comparisons whether or not it is mid-rotation.
_NO_SLOT = "0" * 64

#: Ledger payload keys only the authenticated path may set.
#: ``operator_on_behalf_of`` (C-12): the human a ``bypass_operator_list``
#: identity (the kill-switch) acts for; it enters a payload only through
#: ``bind_on_behalf_of`` -> ``ledger_fields``.
RESERVED_KEYS = frozenset(
    {"operator_id_authenticated", "operator_claimed", "operator_key_fp",
     "operator_body_claimed", "operator_on_behalf_of"}
)


_ON_SPELLINGS = frozenset({"1", "true", "yes", "on"})
_OFF_SPELLINGS = frozenset({"", "0", "false", "no", "off"})


def _require_flag() -> bool:
    """FIELD_OPERATOR_REQUIRE (C-17 / D-N). Unset, blank and the "off"
    spellings are OFF (no default change); 1/true/yes/on are ENFORCE; ANY
    other non-empty value (``enforce``, ``required``, ``2``) is ENFORCE too,
    with one log.error per process (it names the variable and the accepted
    spellings, never the value): a misspelt flag fails closed,
    never silently open."""
    raw = os.environ.get(ENV_REQUIRE, "").strip()
    v = raw.lower()
    if v in _OFF_SPELLINGS:
        return False
    if v not in _ON_SPELLINGS:
        # C-43 F-C43-2: the VALUE is never logged (it can be a pasted secret or key):
        # the variable and the accepted spellings only.
        _log_once(logging.ERROR, f"{ENV_REQUIRE} is not one of 1/true/yes/on or "
                  "0/false/no/off; treated as ENFORCE (fail closed)")
    return True


def registry_path() -> str | None:
    """The operators file path, or None. Blank, whitespace and the usual
    "off" spellings (0/false/no/off, any case) are OFF, exactly as for
    FIELD_OPERATOR_REQUIRE: an .env line ``FIELD_OPERATOR_REGISTRY=0`` must not
    arm LOG-ONLY against a file named "0"."""
    v = os.environ.get(ENV_REGISTRY, "").strip()
    return None if v.lower() in _OFF_SPELLINGS else v


def mode() -> str:
    """Read per call: a flag flip needs no restart and no test leaks."""
    if _require_flag():
        return ENFORCE
    if registry_path():
        return LOG_ONLY
    return OFF


def key_sha256(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_fingerprint(key: str) -> str:
    return key_sha256(key)[:8]


_logged_once: set[str] = set()
_logged_once_lock = threading.Lock()
_MAX_LOGGED_ONCE = 256


def _log_once(level: int, message: str) -> None:
    """Log ``message`` the first time it is seen (bounded). Callers pass fixed
    text, ids and exception type names only: never a key, a hash or file
    content."""
    with _logged_once_lock:
        if message in _logged_once or len(_logged_once) >= _MAX_LOGGED_ONCE:
            return
        _logged_once.add(message)
    log.log(level, message)


def _key_from_file(path: str) -> str:
    """The stripped content of the key file, or "" (with one log line per
    distinct problem) when it is unreadable, oversize, not UTF-8, empty or not
    a single key token. The content is never logged."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_KEY_FILE_BYTES + 1)
    except OSError as exc:
        _log_once(logging.ERROR, f"{ENV_OPERATOR_KEY_FILE} unreadable ({type(exc).__name__}); "
                  "no operator headers are sent")
        return ""
    problem = None
    key = ""
    if len(raw) > MAX_KEY_FILE_BYTES:
        problem = "larger than a key"
    else:
        try:
            key = raw.decode("utf-8-sig").strip()
        except UnicodeDecodeError:
            problem = "not UTF-8"
        else:
            if not key:
                problem = "empty"
            elif not _KEY_RE.match(key):
                problem = "not a single key token"
    if problem:
        _log_once(logging.ERROR, f"{ENV_OPERATOR_KEY_FILE} content rejected ({problem}); "
                  "no operator headers are sent")
        return ""
    return key


def operator_headers() -> dict[str, str]:
    """Client side: the two headers from FIELD_OPERATOR plus the key, or {}.
    The key comes from FIELD_OPERATOR_KEY_FILE when that is set (read on every
    call, so a rotated file needs no restart; an unusable file sends NO
    headers and never falls back to FIELD_OPERATOR_KEY), else from
    FIELD_OPERATOR_KEY. Both the id and the key must be non-empty.
    ``field_core.authn.auth_headers`` merges these so every internal client
    carries its service identity once the env is set."""
    op = os.environ.get(ENV_OPERATOR, "").strip()
    key_file = os.environ.get(ENV_OPERATOR_KEY_FILE, "").strip()
    if key_file:
        if os.environ.get(ENV_OPERATOR_KEY, ""):
            _log_once(logging.WARNING, f"both {ENV_OPERATOR_KEY_FILE} and {ENV_OPERATOR_KEY} "
                      f"are set; the file is used and {ENV_OPERATOR_KEY} is ignored")
        key = _key_from_file(key_file) if op else ""
    else:
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
    event_prefixes: tuple[str, ...] = ()   # ledger_attribute reach (C-10)

    @property
    def authenticated(self) -> bool:
        return self.operator_id is not None

    def has_scope(self, action: str) -> bool:
        # "*" covers every ordinary action but NOT mint_for_others: naming a
        # grantor other than yourself is an explicit, narrow grant.
        if action in EXPLICIT_ONLY:
            return action in self.scopes
        return "*" in self.scopes or action in self.scopes

    def may_attribute(self, event_type: str) -> bool:
        """C-10: reserved operator keys survive the ledger only for an
        authenticated identity holding ``ledger_attribute`` and only on an
        event type that starts with one of its ``event_prefixes``. Never on an
        ``operator.*`` type (any case, any surrounding whitespace)."""
        if not self.authenticated or not self.has_scope("ledger_attribute"):
            return False
        if event_type.strip().lower().startswith("operator."):
            return False
        return any(event_type.startswith(p) for p in self.event_prefixes)

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

_on_behalf: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "field_operator_on_behalf_of", default=None
)


def _acts_for_others(auth: OperatorAuth) -> bool:
    return auth.mode != OFF and auth.authenticated and auth.has_scope("bypass_operator_list")


def bind_on_behalf_of(value) -> str | None:
    """C-12: record ``value`` as ``operator_on_behalf_of`` on this request's
    ledger appends (``ledger_fields``). The ONLY way that reserved key enters a
    payload: bound only when the request authenticated an identity holding
    ``bypass_operator_list`` (``*`` does not imply it) and ``value`` is one
    printable operator id; otherwise nothing is bound and None is returned.
    Per request, like the bound identity (a contextvar)."""
    if not _acts_for_others(_current.get()) or not isinstance(value, str) or not printable_id(value):
        return None
    _on_behalf.set(value)
    return value


def ledger_fields() -> dict:
    """Fields merged into a ledger payload INSIDE the service's own append
    (so they are covered by its signature). {} when the mode is off."""
    auth = _current.get()
    f = auth.ledger_fields()
    if f and _body_claim.get() is not None:
        f = {**f, "operator_body_claimed": _body_claim.get()}
    if f and _on_behalf.get() is not None and _acts_for_others(auth):
        f = {**f, "operator_on_behalf_of": _on_behalf.get()}
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
    """DEPRECATED (C-10): use admit_ledger_event. No row can hold
    ``assert_operator`` any more, and without the event type no
    ``ledger_attribute`` reach can apply, so when armed every reserved key is
    stripped (fail closed). Flags OFF: the payload object itself."""
    if mode() == OFF or not _has_reserved(payload):
        return payload            # flags OFF: nothing is rewritten
    _warn_attribution_loss_once()
    return _strip_reserved(payload)


_warned = False


def _warn_attribution_loss_once() -> None:
    """A service that adds authenticated-operator fields but may not attribute
    them has them stripped by the ledger: say so, once, so the loss of
    attribution is never silent."""
    global _warned
    if not _warned:
        _warned = True
        log.warning(
            "operator attribution LOST: a ledger append carried authenticated-operator "
            "fields from a caller that may not attribute them; the fields were dropped. "
            "Give the appending service a FIELD_OPERATOR identity holding ledger_attribute "
            "with event_prefixes covering the event type, and have the ledger call "
            "admit_ledger_event.")


def reject_reserved_event_type(event_type: str, headers) -> None:
    """DEPRECATED (C-10): use admit_ledger_event. The ``operator.*`` half of
    that policy: every ``operator.*`` type is refused from every caller except
    the exact SELF_REPORTABLE_EVENT_TYPES. Armed only."""
    if mode() == OFF or not event_type.strip().lower().startswith("operator."):
        return
    if event_type not in SELF_REPORTABLE_EVENT_TYPES:
        raise OperatorRefused(403, FORBIDDEN_DETAIL)


def _attributing_caller(headers) -> OperatorAuth | None:
    """The caller's identity if it authenticates with ``ledger_attribute``,
    else None. Never raises: a missing, wrong or malformed credential, or an
    unusable registry, only means "not attributed"."""
    try:
        a = authenticate(headers, "ledger_attribute")
    except OperatorRefused:
        return None
    return a if a.authenticated else None


def admit_ledger_event(event_type: str, payload: dict, headers) -> dict:
    """C-10: the sealed-ledger's ``POST /events`` policy, as one call. Returns
    the payload to store or raises OperatorRefused(403). Flags OFF: the
    payload object itself, nothing refused (byte-identical to pre-Phase-G).

    * ``operator.*`` types are refused from every HTTP caller, whatever it
      holds, except the exact types in SELF_REPORTABLE_EVENT_TYPES. Those are
      accepted from any caller, reserved keys stripped, and stamped
      ``self_reported: true`` unless the caller authenticates with
      ``ledger_attribute`` (then ``false``). A registry fault never refuses
      them: they are the evidence of the fault.
    * Any other type: reserved operator keys survive only when the caller is
      an authenticated identity whose ``ledger_attribute`` reach
      (``event_prefixes``) covers the type; otherwise they are stripped at
      every depth (the loss is logged once).
    * The registry is read only when the decision needs it (a reserved key is
      present, or a self-reportable record must be stamped)."""
    if mode() == OFF:
        return payload
    if event_type.strip().lower().startswith("operator."):
        if event_type not in SELF_REPORTABLE_EVENT_TYPES:
            raise OperatorRefused(403, FORBIDDEN_DETAIL)
        caller = _attributing_caller(headers)
        clean = _strip_reserved(payload)
        if "claimed_id" in clean:
            # PG0-CORE-R2-01, defence in depth: a caller that did not mask
            # cannot store a key-shaped claimed id either.
            clean["claimed_id"] = shown_claim(clean["claimed_id"])
        clean["self_reported"] = caller is None
        return clean
    if not _has_reserved(payload):
        return payload
    caller = _attributing_caller(headers)
    if caller is not None and caller.may_attribute(event_type):
        return payload
    _warn_attribution_loss_once()
    return _strip_reserved(payload)


#: P35 (machine verifier, proposed 2026-10-28): an operator id with this prefix
#: (``svc-verifier-gb10``, ``svc-verifier-fly``) is LIST-BOUND. Unless it holds
#: ``bypass_operator_list`` (it must not; the row ships without it), every
#: authorized_operators check (check_record_authorized: kill, revive, drill, the
#: registry status PATCH and, under ENFORCE, attest) refuses it unless the agent's
#: manifest NAMES it (id or alias): an empty list or a record without a
#: manifest_ref, which let any authenticated identity through, refuse it (403).
#: Only narrows. The shipped canary manifests name its alias
#: ``FIELD canary (gate verification)``; no other manifest in the repository does.
LIST_BOUND_PREFIX = "svc-verifier-"


def list_bound(auth: OperatorAuth) -> bool:
    """True for an authenticated machine-verifier identity (LIST_BOUND_PREFIX)."""
    return (auth.authenticated and isinstance(auth.operator_id, str)
            and auth.operator_id.startswith(LIST_BOUND_PREFIX))


def list_bound_applies(auth: OperatorAuth) -> bool:
    """True when the list-bound rule binds this request: ENFORCE, an
    authenticated LIST_BOUND_PREFIX identity, and no ``bypass_operator_list``
    (the same exemption check_record_authorized honours)."""
    return (auth.mode == ENFORCE and list_bound(auth)
            and not auth.has_scope("bypass_operator_list"))


def check_list_bound_reach(auth: OperatorAuth, manifest_ref: str | None) -> None:
    """P35 (review F1/F2), ENFORCE only: a list-bound identity acts on a
    delegation token only for an agent whose manifest NAMES it. Delegation
    calls this for every mint (whatever ``granted_by`` is: its own id, its
    alias, or another name under a scope it must not hold) and for every revoke
    (the token's agent). The bound never depends on configuration such as
    ``FIELD_DOA_ROSTER``. A no-op for every other identity and outside ENFORCE."""
    if not list_bound_applies(auth):
        return
    check_explicitly_listed(auth, manifest_ref)


def check_record_authorized(auth: OperatorAuth, manifest_ref: str | None) -> None:
    """The kill-switch and the registry share this: resolve the record's
    manifest and enforce its ``kill_switch.authorized_operators``. A manifest
    that is referenced but unreadable is a 503 (deny); no manifest_ref at all
    declares no list, so authentication + scope are all that apply."""
    if auth.mode != ENFORCE:
        return
    if auth.authenticated and auth.has_scope("bypass_operator_list"):
        # A service identity (kill-switch, break-glass) acts for a human it
        # has ALREADY checked, or for itself. C-10: ``bypass_operator_list``
        # is the list half of the old ``assert_operator``; ``ledger_attribute``
        # never bypasses. Every authorized_operators check shares this.
        return
    if list_bound(auth):
        # P35: a machine verifier is never let through by an empty list or a
        # record without a manifest; the manifest must name it.
        check_explicitly_listed(auth, manifest_ref)
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
    * the alias "*" is rejected (it would match a list that says "*");
    * the alias BREAKGLASS_ID is rejected on any row but the break-glass row itself,
      with or without that row in the file (an ordinary row would satisfy a list
      naming the break-glass identity; reviewer C-76/C-86, format 1 and 2 alike)."""
    seen: set[str] = set()
    for r in rows:
        oid = str(r["operator_id"])
        if oid in seen:
            return f"duplicate operator_id {_shown_oid(oid)}"
        seen.add(oid)
    owner_of: dict[str, str] = {}
    for r in rows:
        for n in r.get("names", ()):
            if n == "*":
                return f"alias '*' on operator {_shown_oid(r['operator_id'])}"
            if n == BREAKGLASS_ID and r["operator_id"] != BREAKGLASS_ID:
                return (f"alias {_shown_name(n)} of operator {_shown_oid(r['operator_id'])} "
                        "is the break-glass identity")
            if n in seen:
                return (f"alias {_shown_name(n)} of operator {_shown_oid(r['operator_id'])} "
                        "equals an operator id")
            if n in owner_of and owner_of[n] != r["operator_id"]:
                return (f"alias {_shown_name(n)} is shared by {_shown_oid(owner_of[n])} "
                        f"and {_shown_oid(r['operator_id'])}")
            owner_of[n] = r["operator_id"]
    return None


def _malformed(i: int, row, what: str) -> RegistryUnavailable:
    """A RegistryUnavailable naming the row (1-based) and, when it is a
    well-formed id, its operator_id. Never key or hash material: an id that
    could be a key (PG0-CORE-R1-10: the key prefix) is "(id not shown)", since
    this text reaches the open /health, every service log and keygen."""
    oid = row.get("operator_id") if isinstance(row, dict) else None
    if printable_id(oid):
        who = f" ('{oid}')"
    elif isinstance(oid, str) and oid:
        who = " (id not shown)"
    else:
        who = ""
    return RegistryUnavailable(f"operator registry malformed: row {i}{who}: {what}")


def valid_event_prefix(prefix) -> bool:
    """An ``event_prefixes`` entry: dotted lower-case segments ending in ".",
    at most MAX_EVENT_PREFIX_LEN characters, never in the ``operator.``
    namespace (C-10)."""
    return (isinstance(prefix, str) and len(prefix) <= MAX_EVENT_PREFIX_LEN
            and _EVENT_PREFIX_RE.fullmatch(prefix) is not None
            and not prefix.startswith("operator."))


def _status_problem(status) -> str:
    if status is None:
        return "status is missing (must be 'active' or 'revoked')"
    # PG0-CORE-R1-03: never echo the value (a field swap could put a key in
    # it); the row id (named by _malformed) and the problem class only.
    return f"status must be 'active' or 'revoked' (got a {type(status).__name__})"


@dataclass(frozen=True)
class RegistryDoc:
    """A parsed operators document. ``generation`` is 0 for format 1 (which
    has none). Times are epoch seconds."""
    format: int
    generation: int
    rows: list
    issued_at: int | None = None
    issued_by: str | None = None


def parse_time(value) -> int | None:
    """Epoch seconds of a strict ``YYYY-MM-DDTHH:MM:SSZ`` string, else None."""
    if not isinstance(value, str) or not _TIME_RE.fullmatch(value):
        return None
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def format_time(epoch: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _shown_fields(names) -> str:
    """Field names for an error message: a name outside ``[a-z_]{1,32}`` (a
    pasted key used as a field name) is not shown."""
    return ", ".join(sorted(f"'{n}'" if isinstance(n, str) and _FIELD_NAME_RE.fullmatch(n)
                            else NOT_SHOWN for n in names))


def _registry_format(raw) -> int:
    """1 for a list, or an object without ``format`` or with ``"format": 1``;
    2 for ``"format": 2``. Any other ``format`` value (``"2"``, ``2.0``,
    ``true``, ``3``) makes the file unavailable: read as format 1 it would
    silently drop every expiry."""
    if not isinstance(raw, dict) or "format" not in raw:
        return 1
    value = raw["format"]
    if type(value) is int and value in (1, FORMAT_2):
        return value
    raise RegistryUnavailable("operator registry malformed: format must be the integer 1 or 2")


def _refuse_format2_fields(raw) -> None:
    """A file that is not format 2 must not carry format 2 fields."""
    if isinstance(raw, dict):
        extra = set(raw) & _F2_ONLY_TOP_FIELDS
        if extra:
            raise RegistryUnavailable(
                f"operator registry malformed: field(s) {_shown_fields(extra)} need "
                '"format": 2')
    rows = raw.get("operators") if isinstance(raw, dict) else raw
    if isinstance(rows, list):
        for i, r in enumerate(rows, 1):
            if isinstance(r, dict):
                extra = set(r) & _F2_ONLY_ROW_FIELDS
                if extra:
                    raise _malformed(i, r, f"field(s) {_shown_fields(extra)} need "
                                     'a "format": 2 file')


def parse_registry_doc(raw, *, require_active: bool = False) -> RegistryDoc:
    """parse_registry, returning the document (format, generation, rows)."""
    if _registry_format(raw) == FORMAT_2:
        return _parse_format2(raw, require_active=require_active)
    _refuse_format2_fields(raw)
    return RegistryDoc(1, 0, _parse_format1(raw, require_active=require_active))


def parse_registry(raw, *, require_active: bool = False) -> list[dict]:
    """Validate a decoded operators document and return the normalised rows.
    Format 1 (a list, or {"operators": [...]}): see _parse_format1. Format 2
    (``"format": 2``): see _parse_format2. Any problem is RegistryUnavailable;
    nothing is partly honoured (C-18)."""
    return parse_registry_doc(raw, require_active=require_active).rows


def _check_common_lists(i: int, r: dict) -> tuple[tuple, tuple, tuple]:
    """scopes / names / event_prefixes, checked exactly as format 1 does."""
    scopes = r.get("scopes", [])
    if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
        raise _malformed(i, r, "scopes must be a list of strings")
    rejected = sorted(set(scopes) & REJECTED_SCOPES)
    if rejected:
        raise _malformed(i, r, f"scope '{rejected[0]}' is no longer accepted: grant "
                         "bypass_operator_list and/or ledger_attribute (with "
                         "event_prefixes) instead")
    names = r.get("names", [])
    if (not isinstance(names, list)
            or not all(isinstance(n, str) and 0 < len(n) <= 128 for n in names)):
        raise _malformed(i, r, "names must be a list of 1-128 character strings")
    prefixes = r.get("event_prefixes", [])
    if not isinstance(prefixes, list) or not all(valid_event_prefix(p) for p in prefixes):
        raise _malformed(i, r, "event_prefixes must be a list of dotted lower-case "
                         "prefixes ending in '.', never 'operator.'")
    return tuple(scopes), tuple(names), tuple(prefixes)


def _parse_passkeys(i: int, r: dict) -> tuple[dict, ...]:
    """``passkeys`` (design 3.1): public keys only, a closed object each. This
    slice checks their shape and the credential rules; it never authenticates
    with them (slice H1)."""
    value = r["passkeys"]
    if not isinstance(value, list):
        raise _malformed(i, r, "passkeys must be a list")
    out = []
    for pk in value:
        if not isinstance(pk, dict) or set(pk) != _PASSKEY_FIELDS:
            raise _malformed(i, r, "a passkey must have exactly the fields "
                             f"{_shown_fields(_PASSKEY_FIELDS)}")
        if (not isinstance(pk["credential_id"], str)
                or not _CREDENTIAL_ID_RE.fullmatch(pk["credential_id"])):
            raise _malformed(i, r, "passkey credential_id must be 16-1366 base64url characters")
        if not isinstance(pk["public_key_spki"], str) or not _SPKI_RE.fullmatch(pk["public_key_spki"]):
            raise _malformed(i, r, "passkey public_key_spki must be 40-2048 base64url characters")
        if pk["alg"] not in PASSKEY_ALGS:
            raise _malformed(i, r, "passkey alg must be ES256 or EdDSA")
        if parse_time(pk["enrolled_at"]) is None:
            raise _malformed(i, r, "passkey enrolled_at must be YYYY-MM-DDTHH:MM:SSZ")
        if (not isinstance(pk["label"], str) or not _PASSKEY_LABEL_RE.fullmatch(pk["label"])
                or pk["label"].startswith(KEY_PREFIX)):
            raise _malformed(i, r, "passkey label must be 1-64 plain characters")
        if type(pk["hardware"]) is not bool:
            raise _malformed(i, r, "passkey hardware must be true or false")
        out.append(dict(pk))
    return tuple(out)


def _parse_format2(raw: dict, *, require_active: bool) -> RegistryDoc:
    """Format 2 (design 2.1), a CLOSED schema; every rule fails the whole file:

    * top level: exactly ``format`` (2), ``generation`` (integer >= 1) and
      ``operators``, plus optional ``issued_at`` (time) and ``issued_by`` (id);
    * a row: required ``operator_id`` (a printable id), ``status``,
      ``key_sha256`` (the CURRENT key), ``rotation`` (auto | sealed | remote)
      and ``scopes`` (``*`` or known actions); optional ``names``,
      ``event_prefixes``, ``created_at``, ``key_created_at``,
      ``key_not_after``, ``next_key``, ``auth``, ``passkeys``. Nothing else;
    * every time is ``YYYY-MM-DDTHH:MM:SSZ``;
    * ``key_not_after`` is required on every row except the sealed one, which
      has no expiry and must not carry one (invariant 3);
    * ``next_key`` is exactly {key_sha256, not_before, not_after} with
      ``not_before < not_after``, never on a revoked or a sealed row;
    * at most ONE ``rotation: sealed`` row; its scopes are a subset of
      SEALED_SCOPES, its ``auth`` is key-only, it has no ``next_key`` and no
      ``passkeys``;
    * no key hash appears twice anywhere in the file (any row, any slot, also
      revoked rows), and no passkey ``credential_id`` appears twice;
    * the format 1 rules (status, hex, lists, ids and aliases, and with
      ``require_active`` at least one active row) still apply."""
    unknown = set(raw) - _F2_TOP_FIELDS
    if unknown:
        raise RegistryUnavailable("operator registry malformed: unknown top-level field(s) "
                                  f"{_shown_fields(unknown)} in a format 2 file")
    missing = _F2_TOP_REQUIRED - set(raw)
    if missing:
        raise RegistryUnavailable("operator registry malformed: format 2 needs "
                                  f"{_shown_fields(missing)}")
    generation = raw["generation"]
    if type(generation) is not int or generation < 1:
        raise RegistryUnavailable("operator registry malformed: generation must be an "
                                  "integer >= 1")
    issued_at = None
    if "issued_at" in raw:
        issued_at = parse_time(raw["issued_at"])
        if issued_at is None:
            raise RegistryUnavailable("operator registry malformed: issued_at must be "
                                      "YYYY-MM-DDTHH:MM:SSZ")
    issued_by = raw.get("issued_by")
    if "issued_by" in raw and not printable_id(issued_by):
        raise RegistryUnavailable("operator registry malformed: issued_by must be an "
                                  "operator id")
    rows = raw["operators"]
    if not isinstance(rows, list):
        raise RegistryUnavailable("operator registry malformed: not a list of operators")
    out: list[dict] = []
    hash_row: dict[str, int] = {}
    credential_row: dict[str, int] = {}
    sealed_rows: list[int] = []
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            raise _malformed(i, r, "not an object")
        unknown = set(r) - _F2_ROW_FIELDS
        if unknown:
            raise _malformed(i, r, f"unknown field(s) {_shown_fields(unknown)} in a "
                             "format 2 file")
        missing = _F2_ROW_REQUIRED - set(r)
        if missing:
            raise _malformed(i, r, f"format 2 needs {_shown_fields(missing)}")
        if not printable_id(r["operator_id"]):
            raise _malformed(i, r, "operator_id must be an operator id ([A-Za-z0-9._@-], "
                             "at most 64 characters, not key-shaped)")
        if not isinstance(r["key_sha256"], str) or not _HEX64.fullmatch(r["key_sha256"]):
            raise _malformed(i, r, "key_sha256 must be 64 lower-case hex characters")
        status = r["status"]
        if not isinstance(status, str) or status not in STATUSES:
            raise _malformed(i, r, _status_problem(status))
        rotation = r["rotation"]
        if not isinstance(rotation, str) or rotation not in ROTATIONS:
            raise _malformed(i, r, "rotation must be 'auto', 'sealed' or 'remote'")
        scopes, names, prefixes = _check_common_lists(i, r)
        unknown_scopes = [s for s in scopes if s != "*" and s not in ACTIONS]
        if unknown_scopes:
            raise _malformed(i, r, "scopes must be '*' or known actions")
        for name in ("created_at", "key_created_at"):
            if name in r and parse_time(r[name]) is None:
                raise _malformed(i, r, f"{name} must be YYYY-MM-DDTHH:MM:SSZ")
        auth = ("key",)
        if "auth" in r:
            value = r["auth"]
            if (not isinstance(value, list) or not value
                    or not all(isinstance(a, str) and a in AUTH_METHODS for a in value)
                    or len(set(value)) != len(value)):
                raise _malformed(i, r, "auth must be a non-empty list of distinct "
                                 "'key' / 'session'")
            auth = tuple(value)
        passkeys = _parse_passkeys(i, r) if "passkeys" in r else ()
        sealed = rotation == "sealed"
        if r["operator_id"] == BREAKGLASS_ID and not sealed:
            # is_breakglass() treats this id as break-glass whatever the row says;
            # the sealed rules below (key-only, no expiry, no next_key, no
            # passkeys, narrow scopes) are what make it one (design 3.4).
            raise _malformed(i, r, f"the break-glass identity {BREAKGLASS_ID!r} must be a "
                             "'rotation: sealed' row")
        if BREAKGLASS_ID in names and r["operator_id"] != BREAKGLASS_ID:
            # An alias equal to the break-glass id would let an ordinary row satisfy a list
            # that names the break-glass identity (reviewer C-76, alias squat). validate_rows
            # refuses an alias equal to a row's id only when that row exists.
            raise _malformed(i, r, f"the alias {BREAKGLASS_ID!r} belongs to the break-glass "
                             "identity alone")
        key_not_after = None
        if sealed:
            if "key_not_after" in r:
                raise _malformed(i, r, "a sealed row has no expiry (key_not_after not allowed)")
        else:
            if "key_not_after" not in r:
                raise _malformed(i, r, "key_not_after is required")
            key_not_after = parse_time(r["key_not_after"])
            if key_not_after is None:
                raise _malformed(i, r, "key_not_after must be YYYY-MM-DDTHH:MM:SSZ")
        next_key = None
        if "next_key" in r:
            nk = r["next_key"]
            if not isinstance(nk, dict) or set(nk) != _NEXT_KEY_FIELDS:
                raise _malformed(i, r, "next_key must have exactly the fields "
                                 f"{_shown_fields(_NEXT_KEY_FIELDS)}")
            if not isinstance(nk["key_sha256"], str) or not _HEX64.fullmatch(nk["key_sha256"]):
                raise _malformed(i, r, "next_key.key_sha256 must be 64 lower-case hex characters")
            not_before = parse_time(nk["not_before"])
            not_after = parse_time(nk["not_after"])
            if not_before is None or not_after is None:
                raise _malformed(i, r, "next_key not_before / not_after must be "
                                 "YYYY-MM-DDTHH:MM:SSZ")
            if not not_before < not_after:
                raise _malformed(i, r, "next_key.not_before must be before not_after")
            if status == "revoked":
                raise _malformed(i, r, "a revoked row has no next_key")
            next_key = {"key_sha256": nk["key_sha256"], "not_before": not_before,
                        "not_after": not_after}
        if sealed:
            sealed_rows.append(i)
            if not set(scopes) <= SEALED_SCOPES:
                raise _malformed(i, r, "a sealed row's scopes must be a subset of "
                                 "kill, revive, bypass_operator_list")
            if auth != ("key",):
                raise _malformed(i, r, "a sealed row authenticates by key only")
            if next_key is not None:
                raise _malformed(i, r, "a sealed row has no next_key")
            if "passkeys" in r:
                raise _malformed(i, r, "a sealed row has no passkeys")
        slot_hashes = [r["key_sha256"]] + ([next_key["key_sha256"]] if next_key else [])
        for h in slot_hashes:
            if h in hash_row:
                first = hash_row[h]
                raise RegistryUnavailable(
                    "operator registry ambiguous: one key hash appears twice "
                    f"(rows {first} and {i})" if first != i else
                    f"operator registry ambiguous: row {i} has the same hash in both slots")
            hash_row[h] = i
        for pk in passkeys:
            cid = pk["credential_id"]
            if cid in credential_row:
                raise RegistryUnavailable(
                    "operator registry ambiguous: one passkey credential_id appears twice "
                    f"(rows {credential_row[cid]} and {i})")
            credential_row[cid] = i
        out.append({"operator_id": r["operator_id"], "key_sha256": r["key_sha256"],
                    "status": status, "scopes": scopes, "names": names,
                    "event_prefixes": prefixes, "format": FORMAT_2, "rotation": rotation,
                    "key_not_after": key_not_after, "next_key": next_key, "auth": auth,
                    "passkeys": passkeys})
    if len(sealed_rows) > 1:
        raise RegistryUnavailable("operator registry ambiguous: more than one sealed row "
                                  f"(rows {sealed_rows[0]} and {sealed_rows[1]})")
    problem = validate_rows(out)
    if problem:
        raise RegistryUnavailable(f"operator registry ambiguous: {problem}")
    if require_active and not any(r["status"] == "active" for r in out):
        raise RegistryUnavailable("operator registry has no active rows")
    return RegistryDoc(FORMAT_2, generation, out, issued_at, issued_by)


def _parse_format1(raw, *, require_active: bool = False) -> list[dict]:
    """Validate a decoded format 1 operators document (a list, or
    {"operators": [...]}) and return the normalised rows. Any problem is
    RegistryUnavailable naming the first bad row; nothing is partly honoured
    (C-18):

    * ``status`` is required and exactly ``active`` or ``revoked`` (a missing
      status is no longer read as active; ``Active`` is not ``active``);
    * ``key_sha256`` is exactly 64 lower-case hex characters;
    * ``scopes`` / ``names`` / ``event_prefixes`` (C-10) are well-formed;
    * the identity-collision rules of validate_rows;
    * with ``require_active`` (ENFORCE) at least one row is active, so an empty
      or all-revoked file is a 503, never a silent 403 for every key."""
    rows = raw.get("operators") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise RegistryUnavailable("operator registry malformed: not a list of operators")
    out = []
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            raise _malformed(i, r, "not an object")
        if not isinstance(r.get("operator_id"), str):
            raise _malformed(i, r, "operator_id is missing or not a string")
        if not isinstance(r.get("key_sha256"), str) or not _HEX64.fullmatch(r["key_sha256"]):
            raise _malformed(i, r, "key_sha256 must be 64 lower-case hex characters")
        status = r.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            raise _malformed(i, r, _status_problem(status))
        try:
            r["operator_id"].encode("utf-8")
        except UnicodeEncodeError:
            continue  # a lone surrogate can never authenticate: drop the row
        scopes = r.get("scopes", [])
        if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
            raise _malformed(i, r, "scopes must be a list of strings")
        rejected = sorted(set(scopes) & REJECTED_SCOPES)
        if rejected:
            raise _malformed(i, r, f"scope '{rejected[0]}' is no longer accepted: grant "
                             "bypass_operator_list and/or ledger_attribute (with "
                             "event_prefixes) instead")
        names = r.get("names", [])
        if (not isinstance(names, list)
                or not all(isinstance(n, str) and 0 < len(n) <= 128 for n in names)):
            raise _malformed(i, r, "names must be a list of 1-128 character strings")
        prefixes = r.get("event_prefixes", [])
        if not isinstance(prefixes, list) or not all(valid_event_prefix(p) for p in prefixes):
            raise _malformed(i, r, "event_prefixes must be a list of dotted lower-case "
                             "prefixes ending in '.', never 'operator.'")
        out.append({"operator_id": r["operator_id"], "key_sha256": r["key_sha256"],
                    "status": status, "scopes": tuple(scopes),
                    "names": tuple(names), "event_prefixes": tuple(prefixes)})
    problem = validate_rows(out)
    if problem:
        raise RegistryUnavailable(f"operator registry ambiguous: {problem}")
    if require_active and not any(r["status"] == "active" for r in out):
        raise RegistryUnavailable("operator registry has no active rows")
    return out


_registry_failures_logged: set[tuple[str | None, str]] = set()
_registry_failures_lock = threading.Lock()


def _note_registry_failure(path: str | None, reason: str) -> None:
    """C-15: log.error once per distinct failure of a given file (until the
    next good load), so a broken or downgraded file is visible in the service
    log without flooding it on every guarded request."""
    key = (path, reason)
    with _registry_failures_lock:
        if key in _registry_failures_logged or len(_registry_failures_logged) >= _MAX_LOGGED_ONCE:
            return
        _registry_failures_logged.add(key)
    log.error("operator registry unavailable (fail closed): %s [%s]", reason, path or "path unset")


def _note_registry_ok() -> None:
    if _registry_failures_logged:
        with _registry_failures_lock:
            _registry_failures_logged.clear()


@dataclass(frozen=True)
class RegistrySnapshot:
    """One read of the operators file (slice R2): the parsed document, the rows
    a verifier matches against (retired-hash memory applied, exactly what
    load_registry returns), the decoded JSON and the sha256 of the BYTES read.
    Never logged or exposed whole: callers show prefixes and counts only."""
    doc: RegistryDoc
    rows: list
    raw: object
    sha256: str


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    """json object_pairs_hook: a repeated key is refused, not last-wins (reviewer C-172
    F-C172-2: ``\"operator_id\": \"don\", \"operator_id\": \"mallory\"`` loaded as mallory while a
    reader of the file saw don first)."""
    out: dict = {}
    for k, v in pairs:
        if k in out:
            raise RegistryUnavailable("operator registry malformed: duplicate JSON key "
                                      f"{_shown_fields({k})}")
        out[k] = v
    return out


def decode_registry_document(data: bytes) -> object:
    """Decode the operators file bytes the way the services read them: BOM tolerated, a repeated
    JSON key refused, undecodable or too deeply nested input is RegistryUnavailable. ONE function
    for every reader of the file (the loader, ``operator_keygen --check`` and ``slot_witness``), so a
    check tool never says OK for a file the service refuses (reviewer C-181 F-C181-1/-2)."""
    try:
        # utf-8-sig: Windows PowerShell 5.1 writes a BOM.
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_no_duplicate_keys)
    except (OSError, ValueError, RecursionError) as exc:  # C-172 F-C172-3: deep nesting
        raise RegistryUnavailable(f"operator registry unreadable: {type(exc).__name__}")


def load_registry_snapshot(path: str | None = None, *,
                           require_active: bool | None = None) -> RegistrySnapshot:
    """load_registry, returning the document, the raw JSON and the file digest
    of the same bytes too (slice R2: ``/operator/verify-hash`` answers from the
    verifier's own parse, with the generation it parsed). Same failures, same
    C-15 log, same retired-hash memory as load_registry."""
    if require_active is None:
        require_active = mode() == ENFORCE
    path = path or registry_path()
    try:
        if not path:
            raise RegistryUnavailable("operator registry path is not set")
        try:
            data = Path(path).read_bytes()
        except (OSError, ValueError) as exc:
            raise RegistryUnavailable(f"operator registry unreadable: {type(exc).__name__}")
        raw = decode_registry_document(data)
        doc = parse_registry_doc(raw, require_active=require_active)
    except RegistryUnavailable as exc:
        _note_registry_failure(path, str(exc))
        raise
    _note_registry_ok()
    return RegistrySnapshot(doc, _apply_retired_memory(path, doc), raw,
                            hashlib.sha256(data).hexdigest())


def load_registry(path: str | None = None, *, require_active: bool | None = None) -> list[dict]:
    """Parse the operators file. Any problem is RegistryUnavailable; the
    caller turns that into a 503 in ENFORCE mode (never an allow).
    ``require_active`` defaults to "the mode is ENFORCE" (C-18)."""
    return load_registry_snapshot(path, require_active=require_active).rows


# --- retired-hash memory (design 2.4 item 3) ---
#: Per process and per registry path: the generation and slot hashes of the last
#: good load AND of the highest-generation load seen, and every hash seen
#: REMOVED by a load at a higher generation than either (hash -> the highest
#: generation that removed it). A retired hash that comes back in a file whose
#: generation is not above the one that removed it (a restored backup, a stale
#: ``.prev``) is refused alone: that slot never matches (403), the rest of the
#: file still works (never 503). A file BELOW the highest generation seen also
#: has every hash that the highest-generation file lacks refused the same way
#: (that higher file removed it; stricter than retiring against the last load
#: only, review F3(a)). Memory resets on a process restart (Declared, design
#: section 11 row 10), and it learns only from loads this process makes (each
#: authentication loads the file; a generation that is live only between two
#: loads is never seen: Declared, review F3(b)). Format 1 counts as generation
#: 0, so a format 1 file never retires a hash from another format 1 file.
#: Hashes are kept in memory only, never logged or exposed.
MAX_RETIRED_HASHES = 4096
_retired_lock = threading.Lock()
_retired_state: dict[str, dict] = {}
_retired_seen: set[tuple[str, str, int]] = set()
#: ``operator_retired_hash_seen``: distinct (path, hash, generation) sightings
#: of a retired hash coming back. For the observer and alerting (slice R2).
retired_hash_seen = 0


def _row_slot_hashes(r: dict) -> list[str]:
    nk = r.get("next_key")
    return [r["key_sha256"]] + ([nk["key_sha256"]] if nk else [])


def reset_retired_memory() -> None:
    """Forget every retired hash (tests; a process restart does the same)."""
    global retired_hash_seen
    with _retired_lock:
        _retired_state.clear()
        _retired_seen.clear()
        retired_hash_seen = 0


def _apply_retired_memory(path: str, doc: RegistryDoc) -> list[dict]:
    global retired_hash_seen
    key = os.path.abspath(path)
    present = {h for r in doc.rows for h in _row_slot_hashes(r)}
    generation = doc.generation
    with _retired_lock:
        st = _retired_state.setdefault(key, {"generation": None, "hashes": frozenset(),
                                             "high_generation": None,
                                             "high_hashes": frozenset(), "retired": {}})
        retired = st["retired"]
        removed: set[str] = set()
        if st["generation"] is not None and generation > st["generation"]:
            removed |= st["hashes"] - present
        if st["high_generation"] is not None and generation > st["high_generation"]:
            removed |= st["high_hashes"] - present
        for h in removed:
            retired[h] = max(generation, retired.get(h, 0))
        if len(retired) > MAX_RETIRED_HASHES:
            keep = sorted(retired.items(), key=lambda kv: kv[1])[-MAX_RETIRED_HASHES:]
            retired.clear()
            retired.update(keep)
        if st["high_generation"] is None or generation > st["high_generation"]:
            st["high_generation"] = generation
            st["high_hashes"] = frozenset(present)
        st["generation"] = generation
        st["hashes"] = frozenset(present)
        returned = {h for h in present if h in retired and generation <= retired[h]}
        if generation < st["high_generation"]:
            returned |= present - st["high_hashes"]
        fresh = []
        for h in returned:
            sighting = (key, h, generation)
            if sighting not in _retired_seen and len(_retired_seen) < MAX_RETIRED_HASHES:
                _retired_seen.add(sighting)
                retired_hash_seen += 1
                fresh.append(h)
    if not returned:
        return doc.rows
    out = []
    for r in doc.rows:
        refused = frozenset(h for h in _row_slot_hashes(r) if h in returned)
        if refused:
            if fresh and refused & set(fresh):
                _log_once(logging.ERROR,
                          f"operator registry: a retired key of {_shown_oid(r['operator_id'])} "
                          f"came back in a file at generation {generation}; that key alone "
                          "is refused (operator_retired_hash_seen)")
            r = {**r, "refused_hashes": refused}
        out.append(r)
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


#: The verifier's clock (epoch seconds); tests replace it.
clock: Callable[[], float] = time.time


def _key_matches(presented: str, r: dict, now: float) -> bool:
    """Format 1: the one key. Format 2 (design 2.1): the CURRENT key while
    ``now < key_not_after`` (the sealed row has no expiry), or the NEXT key
    while ``not_before <= now < not_after``; never outside its window, never a
    refused (retired) hash, never when the row's ``auth`` excludes ``key``.
    Every slot is compared whatever the outcome (no early exit)."""
    refused = r.get("refused_hashes", ())
    if r.get("format") != FORMAT_2:
        return hmac.compare_digest(presented, r["key_sha256"]) and r["key_sha256"] not in refused
    current_eq = hmac.compare_digest(presented, r["key_sha256"])
    nk = r.get("next_key")
    next_eq = hmac.compare_digest(presented, nk["key_sha256"] if nk else _NO_SLOT)
    expiry = r.get("key_not_after")
    current_ok = (current_eq and r["key_sha256"] not in refused
                  and (r.get("rotation") == "sealed" if expiry is None else now < expiry))
    next_ok = (nk is not None and next_eq and nk["key_sha256"] not in refused
               and nk["not_before"] <= now < nk["not_after"])
    return (current_ok or next_ok) and "key" in r.get("auth", ("key",))


def _verify(operator: str, key: str, rows: list[dict], now: float | None = None) -> tuple[
        bool, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Hash and compare against EVERY row and every slot (no early exit), also
    for an unknown id, so timing reveals neither which ids exist nor which row
    matched. Returns (ok, scopes, names, event_prefixes)."""
    presented = key_sha256(key)
    dummy = "0" * 64
    now = clock() if now is None else now
    ok = False
    scopes: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()
    for r in rows or [{"operator_id": "", "key_sha256": dummy, "status": "revoked", "scopes": ()}]:
        hash_eq = _key_matches(presented, r, now)
        id_eq = hmac.compare_digest(
            operator.encode("utf-8", "replace"), str(r["operator_id"]).encode("utf-8", "replace"))
        if hash_eq and id_eq and r["status"] == "active":
            ok = True
            scopes = r["scopes"]
            names = tuple(r.get("names", ()))
            prefixes = tuple(r.get("event_prefixes", ()))
    return ok, scopes, names, prefixes


#: The break-glass identity (P22, design 3.4). Also any ``rotation: sealed`` row.
BREAKGLASS_ID = "don-breakglass"
#: Design 3.4 / slice R2: per process, exposed on the open ``/health`` and
#: witnessed by the ledger's C-6 observer. ``breakglass_auth_count``: a
#: break-glass key verified (the identity authenticated). ``breakglass_attempt_count``:
#: a request claiming the break-glass identity that the operator layer refused
#: or left unauthenticated (any armed mode), and every ``/operator/verify-hash``
#: question about it (never answered).
breakglass_auth_count = 0
breakglass_attempt_count = 0
_breakglass_lock = threading.Lock()


def is_breakglass(operator_id, rows: list[dict] | None = None) -> bool:
    """The literal BREAKGLASS_ID, or the id of a ``rotation: sealed`` row in
    ``rows`` (when given)."""
    if not isinstance(operator_id, str):
        return False
    if operator_id == BREAKGLASS_ID:
        return True
    return any(r.get("rotation") == "sealed" and r.get("operator_id") == operator_id
               for r in rows or ())


def note_breakglass(*, used: bool) -> None:
    """Count one break-glass use (``used``) or attempt."""
    global breakglass_auth_count, breakglass_attempt_count
    with _breakglass_lock:
        if used:
            breakglass_auth_count += 1
        else:
            breakglass_attempt_count += 1


def authenticate(
    headers, action: str, rows_loader: Callable[[], list[dict]] | None = None
) -> OperatorAuth:
    """Evaluate a guarded write. Returns the OperatorAuth (in LOG_ONLY a failed
    credential comes back with ``failure`` set and is NOT raised). Raises
    OperatorRefused in ENFORCE (401/403/503) and for malformed headers (400).
    A claimed break-glass identity is counted (note_breakglass)."""
    m = mode()
    if m == OFF:
        return NO_AUTH
    op, key = parse_headers(headers)
    enforce = m == ENFORCE
    # PG0-CORE-R2-01: ``claimed`` reaches ledger rows (operator.unauthenticated,
    # every attributed service row); a key-shaped header value never does.
    claimed = shown_claim(op)
    rows: list[dict] | None = None

    def fail(status: int, detail: str, why: str) -> OperatorAuth:
        if is_breakglass(op, rows):
            note_breakglass(used=False)
        if enforce:
            raise OperatorRefused(status, detail)
        return OperatorAuth(m, claimed=claimed, failure=why)

    if op is None or key is None:
        return fail(401, UNAUTH_DETAIL, "no_credential" if op is None and key is None
                    else "incomplete_credential")
    try:
        rows = (rows_loader or load_registry)()
    except RegistryUnavailable:
        return fail(503, "operator registry unavailable", "registry_unavailable")
    ok, scopes, names, prefixes = _verify(op, key, rows)
    if not ok:
        return fail(403, FORBIDDEN_DETAIL, "bad_credential")
    if is_breakglass(op, rows):
        note_breakglass(used=True)
    auth = OperatorAuth(m, operator_id=op, claimed=claimed, key_fp=key_fingerprint(key),
                        scopes=scopes, names=names, event_prefixes=prefixes)
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


def check_granted_by(auth: OperatorAuth, granted_by: str) -> bool:
    """Mint: ``granted_by`` must equal the authenticated id, unless the
    identity holds the narrow ``mint_for_others`` scope (provisioning), or
    ``granted_by`` is one of the identity's OWN registered aliases (P35, the
    machine verifier: ``svc-verifier-<estate>`` mints canary tokens as
    ``FIELD canary (gate verification)``, the DOA grantor of the canaries).

    Returns True for the alias case and False otherwise. An alias grant is
    bounded by the agent, not only by the grantor: the caller MUST then call
    :func:`check_explicitly_listed` with the agent's manifest_ref, which refuses
    unless that manifest's ``kill_switch.authorized_operators`` lists this
    identity. Aliases are Don-assigned, unique across the file and never equal
    to another row's id (validate_rows), so an alias names the same identity
    as its id; ``*`` implies nothing here."""
    if auth.mode != ENFORCE or not auth.authenticated:
        return False
    if granted_by == auth.operator_id or auth.has_scope("mint_for_others"):
        return False
    if granted_by in auth.names:
        return True
    raise OperatorRefused(403, FORBIDDEN_DETAIL)


def check_explicitly_listed(auth: OperatorAuth, manifest_ref: str | None) -> None:
    """P35, ENFORCE only: the agent's manifest must NAME this identity (id or
    alias) in ``kill_switch.authorized_operators``. Used (1) for a mint whose
    ``granted_by`` is the caller's own alias (:func:`check_granted_by`
    returned True) and (2) by :func:`check_record_authorized` for a list-bound
    identity (:func:`list_bound`). Stricter than the ordinary list check: no
    manifest_ref, or an empty list, is a 403 here, and this function never
    looks at ``bypass_operator_list`` (callers decide that first). An
    unresolvable manifest is a 503 (deny), as everywhere else."""
    if auth.mode != ENFORCE:
        return
    if not auth.authenticated:
        raise OperatorRefused(401, UNAUTH_DETAIL)
    from field_core.clients import resolve_manifest_detail

    manifest, why = resolve_manifest_detail(manifest_ref)
    if manifest is None:
        if why == "no_ref":
            raise OperatorRefused(403, FORBIDDEN_DETAIL)
        raise OperatorRefused(503, "manifest unresolvable - cannot check authorized_operators")
    try:
        listed = manifest.enforcement.kill_switch.authorized_operators or []
    except AttributeError:  # pragma: no cover
        listed = []
    if not listed:
        raise OperatorRefused(403, FORBIDDEN_DETAIL)
    check_authorized(auth, listed)


LEDGER_APPEND_TIMEOUT_S = 1.5
MAX_CONCURRENT_UNAUTH_RECORDS = 8
_unauth_slots = threading.BoundedSemaphore(MAX_CONCURRENT_UNAUTH_RECORDS)
#: LOG-ONLY ``operator.unauthenticated`` records NOT written: dropped under
#: flood, or whose append failed (refused, 5xx, unreachable, timed out).
dropped_unauthenticated_records = 0
_dropped_lock = threading.Lock()


def append_failure_status(exc: BaseException) -> str:
    """What a failed operator-record append is logged with: the HTTP status
    when the ledger answered, else the failure class. Never the message (it
    can carry a response body)."""
    status = getattr(exc, "status_code", None)
    return str(status) if isinstance(status, int) else type(exc).__name__


def _count_dropped_unauthenticated() -> None:
    global dropped_unauthenticated_records
    with _dropped_lock:
        dropped_unauthenticated_records += 1


def _record_unauthenticated(ledger, action: str, path: str, auth: OperatorAuth) -> None:
    """Best effort and BOUNDED: the append runs in a daemon thread and we wait
    at most LEDGER_APPEND_TIMEOUT_S, so a slow ledger cannot delay a kill.

    C-15: the header's claimed id travels as ``claimed_id``, a NON-reserved
    key, so it survives merge_payload and the ledger's reserved-key strip
    (``operator_claimed`` is reserved and is dropped for a caller that may not
    attribute). The thread runs in a copy of the caller's context, so the
    bound OperatorAuth is the one any merge inside ``append`` sees."""
    if not _unauth_slots.acquire(blocking=False):
        _count_dropped_unauthenticated()          # drop-and-count under flood
        return

    def _go() -> None:
        try:
            ledger.append(
                "operator.unauthenticated",
                {"action": action, "path": recorded_path(path), "reason": auth.failure,
                 "claimed_id": auth.claimed, "operator_claimed": auth.claimed}, None)
        except Exception as exc:
            # Never silent (GB10 2026-10-27: every record was refused 403 and
            # nothing said so): counted, one line with the type and status only.
            _count_dropped_unauthenticated()
            log.warning("operator.unauthenticated ledger append failed (status=%s); "
                        "counted in dropped_unauthenticated_records", append_failure_status(exc))
        finally:
            _unauth_slots.release()

    ctx = contextvars.copy_context()
    t = threading.Thread(target=ctx.run, args=(_go,), daemon=True)
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
