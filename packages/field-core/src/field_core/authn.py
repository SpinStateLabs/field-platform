"""Optional shared-secret authentication for service APIs (STATE.md OQ-1).

Off by default: with ``FIELD_SHARED_SECRET`` unset, services run in the
documented localhost-trust demo mode. Set the same secret in every
service's and client's environment and every request must carry
``x-field-auth: <secret>`` — enforced by middleware on all paths except
``/health`` (liveness must stay probeable by infrastructure).

This is perimeter authn for a single trust domain, not identity: all
holders of the secret are equal. Per-caller identity, rotation, and TLS
belong to a real deployment's proxy layer and stay DECLARED.

Tiers (C-772): ``FIELD_SHARED_SECRET`` is the full (write) key. An optional
read key, ``FIELD_READ_KEY`` (or ``FIELD_READ_KEY_<SERVICE>`` when ``install``
is given a ``service``, which then replaces the generic one for that service),
is accepted only on a safe method (GET, HEAD, OPTIONS) of a path that is not
in ``write_only_paths``; it never authorises anything that changes state. A GET
that changes state must be listed in ``write_only_paths``: the method is the
only thing this layer can see. An entry may be a path template
(``/items/{id}``); a trailing slash and a ``root_path`` prefix are ignored on
both sides, and a request is write-only if ANY of its spellings matches (fail
closed). With a read key set and no full key, every
non-safe request is refused (never the open demo mode). A read key equal to the
full key is refused at install.
"""

from __future__ import annotations

import hmac
import os
import re

HEADER = "x-field-auth"
ENV_VAR = "FIELD_SHARED_SECRET"
READ_ENV_VAR = "FIELD_READ_KEY"
READ_ENV_PREFIX = READ_ENV_VAR + "_"
OPEN_PATHS = frozenset({"/health"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class TierKeyError(ValueError):
    """The tier keys are set up so a read key would carry write power."""


def _same(presented: str, key: str) -> bool:
    return hmac.compare_digest(presented.encode("utf-8", "surrogatepass"), key.encode("utf-8", "surrogatepass"))


def _norm(path: str) -> str:
    return path.rstrip("/") or "/"


def _write_only_matcher(paths):
    """A predicate on a request: does any spelling of its path match an entry (exact, or a ``{param}`` template)?"""
    exact: set[str] = set()
    patterns: list[re.Pattern[str]] = []
    for p in paths:
        n = _norm(p)
        if "{" not in n:
            exact.add(n)
            continue
        parts = re.split(r"(\{[^}/]*\})", n)
        patterns.append(re.compile("".join(
            (".+" if part.endswith(":path}") else "[^/]+") if i % 2 else re.escape(part)
            for i, part in enumerate(parts))))

    def matches(request) -> bool:
        root = request.scope.get("root_path") or ""
        for raw in (request.url.path, request.scope.get("path") or ""):
            spellings = {_norm(raw)}
            if root and (raw == root or raw.startswith(root + "/")):
                spellings.add(_norm(raw[len(root):] or "/"))
            if any(s in exact or any(pat.fullmatch(s) for pat in patterns) for s in spellings):
                return True
        return False

    return matches


def read_key(service: str | None = None) -> str | None:
    """The read key for ``service`` (its own variable when set, else the generic one), or None."""
    if service:
        own = os.environ.get(READ_ENV_PREFIX + service.upper().replace("-", "_"))
        if own:
            return own
    return os.environ.get(READ_ENV_VAR) or None


def tier_key_problem(service: str | None = None) -> str | None:
    """Fixed text naming the problem, or None. Never contains a key."""
    rkey, secret = read_key(service), shared_secret()
    if rkey and secret and _same(rkey, secret):
        return "the read key equals the full key: a read key must differ from FIELD_SHARED_SECRET"
    return None


def read_auth_headers(service: str | None = None) -> dict[str, str]:
    """Headers for a read-only caller: the read key only, never the full key or an operator pair."""
    rkey = read_key(service)
    return {HEADER: rkey} if rkey else {}


def shared_secret() -> str | None:
    """The configured secret, or None when authn is disabled."""
    return os.environ.get(ENV_VAR) or None


def auth_headers() -> dict[str, str]:
    """Headers a client should attach. Empty dict when authn is disabled."""
    from field_core.operator_auth import operator_headers

    secret = shared_secret()
    headers = {HEADER: secret} if secret else {}
    # Phase G: an internal caller's own operator identity (FIELD_OPERATOR /
    # FIELD_OPERATOR_KEY), when configured. Empty otherwise.
    headers.update(operator_headers())
    return headers


def install(app, open_paths: frozenset[str] | set[str] | None = None, *,
            service: str | None = None,
            write_only_paths: frozenset[str] | set[str] | None = None) -> None:
    """Install the authn middleware on a FastAPI app.

    The secret is read per-request (not captured at install time) so tests
    and long-lived processes see environment changes. ``open_paths``
    extends the default open set (e.g. a dashboard's HTML shell, which
    holds no data — its /api endpoints stay protected).
    """
    allowed = OPEN_PATHS | frozenset(open_paths or ())
    write_only = _write_only_matcher(write_only_paths or ())
    problem = tier_key_problem(service)
    if problem:
        raise TierKeyError(problem)

    @app.middleware("http")
    async def _field_authn(request, call_next):
        secret = shared_secret()
        rkey = read_key(service)
        if rkey and secret and _same(rkey, secret):
            rkey = None                       # equal adds no power (install refuses it; the env may change later)
        if (secret or rkey) and request.url.path not in allowed:
            presented = request.headers.get(HEADER, "")
            ok = bool(secret) and _same(presented, secret)
            if (not ok and rkey and request.method.upper() in SAFE_METHODS
                    and not write_only(request) and _same(presented, rkey)):
                ok = True
            if not ok:
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    {"detail": "missing or invalid x-field-auth header"},
                    status_code=401,
                )
        return await call_next(request)
