"""The outbound headers of the sentinel's own clients (C-1180, Lane 7 C-1150 F2 slice B).

``field_core.authn.auth_headers()`` merges this service's operator pair (``x-field-operator`` and
``x-field-operator-key``) into EVERY request a client sends, reads included. The sentinel's own routes, the
governor's status reads and the delegation introspection carry no operator guard, so those clients send the
perimeter secret and nothing else. The measurement CLI provisions an agent and a token through the registry and the
delegation service: those two clients carry the pair on the receiver's guarded writes only
(``POST /agents``, ``POST /tokens`` and the routes in field-core's tables), and never to another origin."""

from __future__ import annotations

import httpx

from field_core.guarded_operator import (
    DELEGATION_GUARDED,
    REGISTRY_GUARDED,
    GuardedOperatorAuth,
    perimeter_headers,
)
from field_core import authn

_OPERATOR, _KEY = "x-field-operator", "x-field-operator-key"   # the two headers of the pair (not imported: this service does not apply operator auth)
REGISTRY_TABLE = REGISTRY_GUARDED
DELEGATION_TABLE = DELEGATION_GUARDED


def _pair() -> tuple[str, str] | None:
    """This service's own operator pair from the environment, or None when none is configured."""
    h = authn.auth_headers()
    return (h[_OPERATOR], h[_KEY]) if _OPERATOR in h and _KEY in h else None


def sentinel_client(base: str, *, timeout: float = 15.0, transport=None) -> httpx.Client:
    """A client of the sentinel: no operator guard on its routes, so the secret alone."""
    return httpx.Client(base_url=base, timeout=timeout, headers=perimeter_headers(), transport=transport)


def registry_client(base: str, *, timeout: float = 10.0, transport=None) -> httpx.Client:
    return httpx.Client(base_url=base, timeout=timeout, headers=perimeter_headers(),
                        auth=GuardedOperatorAuth(base, _pair(), REGISTRY_GUARDED), transport=transport)


def delegation_client(base: str, *, timeout: float = 10.0, transport=None) -> httpx.Client:
    return httpx.Client(base_url=base, timeout=timeout, headers=perimeter_headers(),
                        auth=GuardedOperatorAuth(base, _pair(), DELEGATION_GUARDED), transport=transport)
