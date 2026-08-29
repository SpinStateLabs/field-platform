"""Hook 1 — ACTIONS. Pure re-export of the sentinel's own client surface.

``Governor`` / ``@governed`` / ``ActionBlocked`` / ``ActionEscalated`` are
conformance-sentinel's classes, unchanged: catching
``field_agent.ActionBlocked`` and catching
``conformance_sentinel.governed.ActionBlocked`` is the same thing
(identity-asserted in tests). The SDK adds no verdict logic of its own.
"""

from conformance_sentinel.governed import (  # noqa: F401
    ActionBlocked,
    ActionEscalated,
    Governor,
    governed,
)

__all__ = ["ActionBlocked", "ActionEscalated", "Governor", "governed"]
