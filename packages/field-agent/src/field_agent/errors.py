"""Typed failures for the field-agent SDK.

The hierarchy is the contract: ``HeartbeatUnreachable`` SUBCLASSES
``AgentKilled`` so that ``except AgentKilled`` halts on an outage too —
an agent must never fail open because the kill-switch was down. Same rule
the sentinel client already applies (unreachable ⇒ ``ActionBlocked``).
"""

from __future__ import annotations

from typing import Any


class FieldAgentError(RuntimeError):
    """Base class for every failure raised by this SDK."""


class AgentKilled(FieldAgentError):
    """The kill-switch says stop: killed, unknown, or non-active status."""

    def __init__(self, message: str, heartbeat: Any | None = None):
        self.heartbeat = heartbeat
        super().__init__(message)


class HeartbeatUnreachable(AgentKilled):
    """Liveness unknown ⇒ assume killed."""


class UsageReportError(FieldAgentError):
    """The usage report did not land — this spend is NOT metered."""


class NoSpendCapError(UsageReportError):
    """The governor refused: no spend cap configured for this agent."""


class BootstrapError(FieldAgentError):
    """Operator-side register/mint call failed."""
