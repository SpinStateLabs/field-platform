"""Hook 3 — LIVENESS. Poll the kill-switch heartbeat; halt on killed.

Fail-closed contract: the kill-switch answers ``killed=true`` for unknown
agents, and this client treats ANY transport failure or non-200 as killed
(``HeartbeatUnreachable`` ⊂ ``AgentKilled``). Liveness unknown ⇒ stop.
"""

from __future__ import annotations

from field_agent._transport import AuthedClient
from field_agent.errors import HeartbeatUnreachable

import os
from typing import Any

from pydantic import BaseModel, ConfigDict


class Heartbeat(BaseModel):
    """Client-side mirror of the kill-switch response. ``extra="ignore"``
    on purpose: the server may add fields without breaking agents."""

    model_config = ConfigDict(extra="ignore")

    agent_id: str
    status: str
    killed: bool
    checked_at: str


class LivenessClient:
    def __init__(self, client: Any | None = None, base_url: str | None = None):
        self._base = (base_url or os.environ.get(
            "FIELD_KILLSWITCH_URL", "http://127.0.0.1:8005"
        )).rstrip("/")
        if client is None:
            import httpx

            client = httpx.Client(timeout=5.0)
        self._client = AuthedClient(client)

    def heartbeat(self, agent_id: str) -> Heartbeat:
        try:
            resp = self._client.get(f"{self._base}/heartbeat/{agent_id}")
        except Exception as exc:
            raise HeartbeatUnreachable(
                f"kill-switch unreachable — liveness unknown, halting: {exc}"
            ) from exc
        if resp.status_code != 200:
            raise HeartbeatUnreachable(
                f"heartbeat returned {resp.status_code} — liveness unknown, "
                f"halting: {resp.text}"
            )
        return Heartbeat.model_validate(resp.json())
