"""Operator-side helpers: register an agent, mint a delegation token.

Deliberately NOT re-exported from ``field_agent`` — granting authority is
a human act (``granted_by`` is a person, never an agent), and an agent must
not find self-authorization one autocomplete away. Demos, operator scripts,
and the CLI import this module by name: ``from field_agent import bootstrap``.
"""

from __future__ import annotations

from field_agent._transport import AuthedClient
from field_agent.errors import BootstrapError
from field_core.delegation import DelegationToken
from field_core.errors import upstream_error

import os
from datetime import datetime
from typing import Any


def _client(client: Any | None) -> AuthedClient:
    if client is None:
        import httpx

        client = httpx.Client(timeout=5.0)
    return AuthedClient(client)


def register(
    agent_id: str,
    name: str,
    owner: str,
    domain: str = "general",
    manifest_ref: str | None = None,
    *,
    client: Any | None = None,
    registry_url: str | None = None,
) -> dict[str, Any]:
    """POST /agents on the registry. Not idempotent: a duplicate 409s and
    raises — deciding to reuse an existing registration is the operator's
    call, not the helper's."""
    base = (registry_url or os.environ.get(
        "FIELD_REGISTRY_URL", "http://127.0.0.1:8001"
    )).rstrip("/")
    try:
        resp = _client(client).post(
            f"{base}/agents",
            json={
                "agent_id": agent_id,
                "name": name,
                "owner": owner,
                "domain": domain,
                "manifest_ref": manifest_ref,
            },
        )
    except Exception as exc:
        raise BootstrapError(f"agent-registry unreachable: {exc}") from exc
    if resp.status_code != 201:
        raise BootstrapError(upstream_error(resp, "register"))
    # The 201 reply must be a JSON object (the agent record). Before C-785 it was returned unvalidated, so a list or a
    # string came back as a "registration". Only the type name of a failure is kept; the raise is outside the block.
    bad = None
    try:
        record = resp.json()
    except Exception as exc:
        bad = type(exc).__name__
    else:
        if not isinstance(record, dict):
            bad = "not a JSON object"
    if bad is not None:
        raise BootstrapError(f"register returned an unusable reply ({bad})")
    return record


def mint(
    agent_id: str,
    granted_by: str,
    scope: list[str],
    ttl_seconds: int | None = None,
    expires_at: datetime | None = None,
    *,
    client: Any | None = None,
    delegation_url: str | None = None,
) -> DelegationToken:
    """POST /tokens on delegation-authority. Exactly one of ``ttl_seconds``
    / ``expires_at`` (the server enforces the XOR). Returns the existing
    ``field_core.delegation.DelegationToken`` model — single source of truth."""
    base = (delegation_url or os.environ.get(
        "FIELD_DELEGATION_URL", "http://127.0.0.1:8003"
    )).rstrip("/")
    body: dict[str, Any] = {
        "agent_id": agent_id,
        "granted_by": granted_by,
        "scope": list(scope),
    }
    if ttl_seconds is not None:
        body["ttl_seconds"] = ttl_seconds
    if expires_at is not None:
        body["expires_at"] = expires_at.isoformat()
    try:
        resp = _client(client).post(f"{base}/tokens", json=body)
    except Exception as exc:
        raise BootstrapError(f"delegation-authority unreachable: {exc}") from exc
    if resp.status_code != 201:
        raise BootstrapError(upstream_error(resp, "mint"))
    try:
        return DelegationToken.model_validate(resp.json())
    except Exception as exc:
        bad = type(exc).__name__            # raised below, outside the block: see register() (C-785)
    raise BootstrapError(f"mint returned an unusable reply ({bad})")
