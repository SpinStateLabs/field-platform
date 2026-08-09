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
import os

HEADER = "x-field-auth"
ENV_VAR = "FIELD_SHARED_SECRET"
OPEN_PATHS = frozenset({"/health"})


def shared_secret() -> str | None:
    """The configured secret, or None when authn is disabled."""
    return os.environ.get(ENV_VAR) or None


def auth_headers() -> dict[str, str]:
    """Headers a client should attach. Empty dict when authn is disabled."""
    secret = shared_secret()
    return {HEADER: secret} if secret else {}


def install(app, open_paths: frozenset[str] | set[str] | None = None) -> None:
    """Install the authn middleware on a FastAPI app.

    The secret is read per-request (not captured at install time) so tests
    and long-lived processes see environment changes. ``open_paths``
    extends the default open set (e.g. a dashboard's HTML shell, which
    holds no data — its /api endpoints stay protected).
    """
    allowed = OPEN_PATHS | frozenset(open_paths or ())

    @app.middleware("http")
    async def _field_authn(request, call_next):
        secret = shared_secret()
        if secret and request.url.path not in allowed:
            presented = request.headers.get(HEADER, "")
            if not hmac.compare_digest(presented, secret):
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    {"detail": "missing or invalid x-field-auth header"},
                    status_code=401,
                )
        return await call_next(request)
