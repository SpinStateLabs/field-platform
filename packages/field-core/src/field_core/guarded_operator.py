"""The operator pair goes only on a guarded write (C-511, Lane 10 design note C-491).

``field_core.authn.auth_headers()`` merges the service's own operator pair (``x-field-operator`` and
``x-field-operator-key``) into EVERY request, reads included, to receivers that check the pair only on
guarded writes: a bearer key that rides every hop for nothing. This module is the one mechanism that attaches
it only where a receiver looks for it:

* ``is_guarded`` / ``GuardedOperatorAuth`` (moved here from the kill-switch CLI): an allowlist of
  ``(method, path)`` pairs under a base URL;
* the route tables of the services whose outbound clients hold an identity: ``LEDGER_GUARDED``,
  ``REGISTRY_GUARDED``, ``DELEGATION_GUARDED``, ``KILLSWITCH_GUARDED``. A table lists the routes its receiver
  guards: each receiver's own tests compare its table with the routes that carry ``op_health.guard`` and with
  the routes that read the pair another way (``DECLARED_EXTRAS``), in both directions, so a table cannot drift;
* ``perimeter_headers`` (``x-field-auth`` only) and ``request_headers`` (the secret, plus the pair on a guarded
  route).

A route in a table that needs no pair only adds a header to a request that has no use for it; a guarded route
missing from a table is the failure (the write loses its identity and is refused under ENFORCE). So when a
route is in doubt it is listed.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Iterable

import httpx

from field_core import authn

Routes = tuple[tuple[str, re.Pattern[str]], ...]
Template = tuple[str, str]          # ("POST", "/agents/{agent_id}/attest")


def compile_routes(templates: Iterable[Template]) -> Routes:
    """``{name}`` is one path segment."""
    return tuple((m.upper(), re.compile(re.sub(r"\{[^/}]+\}", "[^/]+", t))) for m, t in templates)


#: sealed-ledger. POST /events is listed because ``admit_ledger_event`` reads the pair there (the
#: ``ledger_attribute`` identity); the rest carry ``op_health.guard``.
LEDGER_TEMPLATES: tuple[Template, ...] = (
    ("POST", "/events"), ("POST", "/export"), ("POST", "/rotate"), ("POST", "/hold"),
    ("POST", "/hold/release"), ("POST", "/retention/apply"),
)
#: agent-registry. PATCH /agents/{agent_id} is listed because it authenticates the caller (the status guards and
#: ``x-field-operator-on-behalf-of``) inside the handler; the others carry ``op_health.guard``.
REGISTRY_TEMPLATES: tuple[Template, ...] = (
    ("POST", "/agents"), ("POST", "/agents/{agent_id}/attest"), ("PATCH", "/agents/{agent_id}"),
)
DELEGATION_TEMPLATES: tuple[Template, ...] = (("POST", "/tokens"), ("POST", "/tokens/{token_id}/revoke"))
KILLSWITCH_TEMPLATES: tuple[Template, ...] = (
    ("POST", "/kill/{agent_id}"), ("POST", "/kill/domain/{domain}"), ("POST", "/revive/{agent_id}"),
    ("POST", "/drill/{agent_id}"),
)
#: Routes a receiver guards WITHOUT ``op_health.guard`` (the receiver's drift test names them).
DECLARED_EXTRAS: dict[str, frozenset[Template]] = {
    "ledger": frozenset({("POST", "/events")}),
    "registry": frozenset({("PATCH", "/agents/{agent_id}")}),
    "delegation": frozenset(),
    "killswitch": frozenset(),
}

LEDGER_GUARDED = compile_routes(LEDGER_TEMPLATES)
REGISTRY_GUARDED = compile_routes(REGISTRY_TEMPLATES)
DELEGATION_GUARDED = compile_routes(DELEGATION_TEMPLATES)
KILLSWITCH_GUARDED = compile_routes(KILLSWITCH_TEMPLATES)


def is_guarded_path(method: str, path: str, routes: Routes) -> bool:
    """``path`` relative to the receiver's base URL."""
    return any(m == method.upper() and rx.fullmatch(path) for m, rx in routes)


def is_guarded(method: str, path: str, base: str, routes: Routes) -> bool:
    """True only for an allowlisted (method, path) under ``base`` (the base's own path prefix is stripped)."""
    prefix = urllib.parse.urlsplit(base).path.rstrip("/")
    if prefix:
        if not path.startswith(prefix + "/"):
            return False
        path = path[len(prefix):]
    return is_guarded_path(method, path, routes)


class GuardedOperatorAuth(httpx.Auth):
    """Adds the operator pair to a request only when it is an allowlisted guarded route; every other request
    leaves without it."""

    def __init__(self, base: str, pair: tuple[str, str] | None, routes: Routes):
        self._base, self._pair, self._routes = base, pair, routes

    def auth_flow(self, request):
        if self._pair and is_guarded(request.method, request.url.path, self._base, self._routes):
            request.headers["x-field-operator"], request.headers["x-field-operator-key"] = self._pair
        yield request


def perimeter_headers() -> dict[str, str]:
    """``x-field-auth`` only. Never ``authn.auth_headers()`` for a read: that adds the env operator pair."""
    secret = authn.shared_secret()
    return {authn.HEADER: secret} if secret else {}


def request_headers(method: str, path: str, routes: Routes) -> dict[str, Any]:
    """The headers for ONE request, read now: the perimeter secret, plus this service's own operator pair when
    (method, path) is a guarded route of the target. ``path`` is relative to the target's base URL."""
    if is_guarded_path(method, path, routes):
        return authn.auth_headers()
    return perimeter_headers()


def guard_dependent_routes(app: Any) -> set[Template]:
    """The (method, path template) of every route of a FastAPI ``app`` that carries an ``op_health.guard``
    dependency. A receiver's drift test compares this with its table (plus ``DECLARED_EXTRAS``)."""
    out: set[Template] = set()
    for route in getattr(app, "routes", []):
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        if any(getattr(d.call, "__name__", "") == "_guard" for d in dependant.dependencies):
            out |= {(m.upper(), route.path) for m in route.methods or ()}
    return out


def all_routes(app: Any) -> set[Template]:
    """Every (method, path template) route of the app (HEAD and OPTIONS left out)."""
    return {(m.upper(), r.path) for r in getattr(app, "routes", []) for m in (getattr(r, "methods", None) or ())
            if m.upper() not in ("HEAD", "OPTIONS")}


def drift_problems(app: Any, templates: Iterable[Template], extras: Iterable[Template]) -> list[str]:
    """Both directions: every guarded route of the receiver (plus the declared extras) is in the table, and
    every table entry is a real route of the receiver that is guarded or declared."""
    table, extras = set(templates), set(extras)
    guarded, real = guard_dependent_routes(app), all_routes(app)
    out = [f"guarded route missing from the table: {m} {p}" for m, p in sorted((guarded | extras) - table)]
    out += [f"table entry that is not a route of the receiver: {m} {p}" for m, p in sorted(table - real)]
    out += [f"table entry that the receiver neither guards nor declares: {m} {p}"
            for m, p in sorted(table - guarded - extras)]
    out += [f"declared extra that is not a route of the receiver: {m} {p}" for m, p in sorted(extras - real)]
    return out
