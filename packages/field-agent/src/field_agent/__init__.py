"""field-agent — put a Python agent under FIELD governance in a few lines.

A client, not an authority. The SDK adds ZERO new power: it only makes the
existing services reachable — sentinel-checked actions, metered usage,
kill-switch liveness — and its one local capability is refusal (raising
before ungoverned work runs). An agent that never calls it is not
governed: this is a cooperative perimeter, backstopped server-side (a
killed agent's next sentinel check is BLOCK whether or not it ever polls
the heartbeat).
"""

from field_agent.actions import ActionBlocked, ActionEscalated, Governor, governed
from field_agent.agent import FieldAgent
from field_agent.errors import (
    AgentKilled,
    BootstrapError,
    FieldAgentError,
    HeartbeatUnreachable,
    NoSpendCapError,
    UsageReportError,
)
from field_agent.federation import CrossingBlocked, FederationClient
from field_agent.liveness import Heartbeat, LivenessClient
from field_agent.usage import RogueFinding, UsageClient, UsageReport, extract_usage

__version__ = "0.1.0"

__all__ = [
    "ActionBlocked",
    "ActionEscalated",
    "AgentKilled",
    "BootstrapError",
    "CrossingBlocked",
    "FieldAgent",
    "FieldAgentError",
    "FederationClient",
    "Governor",
    "Heartbeat",
    "HeartbeatUnreachable",
    "LivenessClient",
    "NoSpendCapError",
    "RogueFinding",
    "UsageClient",
    "UsageReport",
    "UsageReportError",
    "extract_usage",
    "governed",
]
