"""Whether a crossing request carries the named agent's own active delegation token (``x-field-token``).

The broker asks delegation-authority (``POST /introspect``). Anything but a clear yes is a no: an unreachable or
refusing authority, an unknown, revoked or expired token, or a token of another agent.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from field_core.authn import auth_headers
from field_core.http import pooled_limits

TOKEN_HEADER = "x-field-token"
#: a longer header value is not asked about
TOKEN_MAX = 200

log = logging.getLogger(__name__)


class OwnTokenCheck:
    def __init__(self, client: Any = None, base_url: str | None = None):
        self._base = (base_url or os.environ.get("FIELD_DELEGATION_URL", "http://127.0.0.1:8003")).rstrip("/")
        self._client = client

    def _http(self) -> Any:
        if self._client is None:
            import httpx

            # B16: idle connections expire before the server's keep-alive closes them
            self._client = httpx.Client(timeout=5.0, trust_env=False, limits=pooled_limits())
        return self._client

    def bound(self, token_id: str | None, agent_id: str | None) -> bool:
        """True only for an active token that delegation-authority says belongs to ``agent_id``."""
        if not token_id or not agent_id or len(token_id) > TOKEN_MAX or not token_id.isprintable():
            return False
        try:
            resp = self._http().post(f"{self._base}/introspect", json={"token_id": token_id}, headers=auth_headers())
            body = resp.json() if resp.status_code == 200 else None
        except Exception as exc:
            # the type only: the text can carry the address or the token
            log.warning("agent token not checked (%s)", type(exc).__name__)
            return False
        return isinstance(body, dict) and body.get("active") is True and body.get("agent_id") == agent_id
