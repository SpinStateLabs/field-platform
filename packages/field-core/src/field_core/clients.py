"""HTTP clients for the services delegation-authority depends on.

Both accept an injected httpx-compatible client (FastAPI's TestClient
qualifies), so tests wire real service apps in-process.

Fail-closed rule (ENFORCED): if the sealed ledger cannot acknowledge the
event, the mint/revoke does not happen. Authority changes that cannot be
audited must not occur.
"""

from __future__ import annotations

import os
from typing import Any, Protocol


class HttpLike(Protocol):
    def post(self, url: str, **kwargs: Any) -> Any: ...
    def get(self, url: str, **kwargs: Any) -> Any: ...


class LedgerUnreachableError(Exception):
    pass


class RegistryUnreachableError(Exception):
    pass


class AgentNotRegisteredError(Exception):
    pass


class AgentNotActiveError(Exception):
    def __init__(self, agent_id: str, status: str):
        self.status = status
        super().__init__(f"agent '{agent_id}' has status '{status}'")


class LedgerClient:
    def __init__(self, client: HttpLike | None = None, base_url: str | None = None):
        self._client = client
        self._base = (base_url or os.environ.get(
            "FIELD_LEDGER_URL", "http://127.0.0.1:8002"
        )).rstrip("/")
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=5.0)

    def append(
        self, event_type: str, payload: dict[str, Any], agent_id: str | None = None
    ) -> dict[str, Any]:
        try:
            resp = self._client.post(
                f"{self._base}/events",
                json={"event_type": event_type, "payload": payload, "agent_id": agent_id},
            )
        except Exception as exc:
            raise LedgerUnreachableError(str(exc)) from exc
        if resp.status_code != 201:
            raise LedgerUnreachableError(
                f"ledger append returned {resp.status_code}: {resp.text}"
            )
        return resp.json()


class RegistryClient:
    def __init__(self, client: HttpLike | None = None, base_url: str | None = None):
        self._client = client
        self._base = (base_url or os.environ.get(
            "FIELD_REGISTRY_URL", "http://127.0.0.1:8001"
        )).rstrip("/")
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=5.0)

    def require_active_agent(self, agent_id: str) -> dict[str, Any]:
        try:
            resp = self._client.get(f"{self._base}/agents/{agent_id}")
        except Exception as exc:
            raise RegistryUnreachableError(str(exc)) from exc
        if resp.status_code == 404:
            raise AgentNotRegisteredError(agent_id)
        if resp.status_code != 200:
            raise RegistryUnreachableError(
                f"registry returned {resp.status_code}: {resp.text}"
            )
        record = resp.json()
        if record.get("status") != "active":
            raise AgentNotActiveError(agent_id, record.get("status", "<unknown>"))
        return record
