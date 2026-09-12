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
    #: Set only by ``checkin()`` — the instant the server recorded the
    #: check-in. ``None`` on a read-only ``heartbeat()`` poll.
    last_seen: str | None = None


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
        """Read-only poll. Never records a check-in — see :meth:`checkin`."""
        return self._call("get", agent_id)

    def checkin(self, agent_id: str) -> Heartbeat:
        """POST a check-in: the server records ``last_seen``, then answers
        with the SAME fail-closed semantics as :meth:`heartbeat`.

        Nothing else in the platform writes that row, so an agent that only
        ever calls :meth:`heartbeat` reads stale on ``GET /liveness``
        forever. Call this on the agent's own cadence."""
        return self._call("post", agent_id)

    def _call(self, verb: str, agent_id: str) -> Heartbeat:
        try:
            resp = getattr(self._client, verb)(f"{self._base}/heartbeat/{agent_id}")
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
