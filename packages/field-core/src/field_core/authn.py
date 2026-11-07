"""Optional shared-secret authentication for service APIs (STATE.md OQ-1).

Off by default: with ``FIELD_SHARED_SECRET`` unset, services run in the
documented localhost-trust demo mode. Set the same secret in every
service's and client's environment and every request must carry
``x-field-auth: <secret>`` — enforced by middleware on all paths except
``/health`` (liveness must stay probeable by infrastructure).

This is perimeter authn for a single trust domain, not identity: all
holders of the secret are equal. Per-caller identity, rotation, and TLS
belong to a real deployment's proxy layer and stay DECLARED.
"""

from __future__ import annotations

import hmac
import logging
import os

HEADER = "x-field-auth"
ENV_VAR = "FIELD_SHARED_SECRET"
OPEN_PATHS = frozenset({"/health"})
log = logging.getLogger("field_core.authn")


def secret_matches(presented: str, secret: str) -> bool:
    """Constant-time comparison of the presented header with the secret, on BYTES. ``hmac.compare_digest`` raises
    ``TypeError`` for a ``str`` that is not ASCII, which turned a header with a raw byte such as 0xE9 (decoded as
    latin-1 by the server) or a non-ASCII configured secret into a 500 instead of a 401 (red team F-H1-1, F-H1-2). The
    header goes back to its raw bytes (latin-1 is how the server read them); the secret is compared as UTF-8."""
    try:
        got = presented.encode("latin-1")
    except UnicodeEncodeError:
        return False
    return hmac.compare_digest(got, secret.encode("utf-8", "surrogatepass"))


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


def install(app, open_paths: frozenset[str] | set[str] | None = None) -> None:
    """Install the authn middleware on a FastAPI app.

    The secret is read per-request (not captured at install time) so tests
    and long-lived processes see environment changes. ``open_paths``
    extends the default open set (e.g. a dashboard's HTML shell, which
    holds no data — its /api endpoints stay protected).
    """
    allowed = OPEN_PATHS | frozenset(open_paths or ())
    configured = shared_secret()
    if configured and not configured.isascii():
        # one line, the variable name only: a non-ASCII secret cannot be sent by an HTTP client library that encodes
        # header values as ASCII, so every such caller would be refused (F-H1-2)
        log.warning("%s holds a non-ASCII character; callers must send its UTF-8 bytes in %s", ENV_VAR, HEADER)

    @app.middleware("http")
    async def _field_authn(request, call_next):
        secret = shared_secret()
        if secret and request.url.path not in allowed:
            presented = request.headers.get(HEADER, "")
            if not secret_matches(presented, secret):
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    {"detail": "missing or invalid x-field-auth header"},
                    status_code=401,
                )
        return await call_next(request)
