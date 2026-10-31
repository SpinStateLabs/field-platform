"""Audit-first writes: the intent is on the sealed ledger before a Tier 2 call is made, or the call is not made.

The record carries the tool, the target, the caller identity (the configured operator id, a per-process session id and
the client's self-declared name, which is unauthenticated), the reason the model gave and a SHA-256 of the request body,
never the body, never a key. The outcome record (status only) follows best effort: a missing outcome is reported in the
result, it does not undo the write.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import unicodedata
import uuid
from collections import deque
from collections.abc import Callable
from typing import Any

from field_core.clients import signed_append_body
from field_mcp.client import ToolError, Upstream

INTENT = "mcp.write.intent"
OUTCOME = "mcp.write.outcome"


def clean_reason(text: str) -> str:
    """The reason as it is stored (C-1014 port, F-C941-2): invisible format characters (category Cf: zero-width, bidi
    overrides and isolates, byte-order mark) are dropped, control characters and line or paragraph separators become a
    space, the ends are trimmed. The result may be empty; the caller refuses an empty one."""
    out = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat == "Cf":
            continue
        out.append(" " if cat in ("Cc", "Zl", "Zp") else ch)
    return "".join(out).strip()


class RateLimiter:
    """A sliding one-minute window per session. ``allow`` records the attempt only when it returns True."""

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.per_minute, self._clock, self._hits = per_minute, clock, deque()
        self._lock = threading.Lock()      # tool calls run on threads: the check and the record are one step

    def allow(self) -> bool:
        with self._lock:
            now = self._clock()
            while self._hits and now - self._hits[0] >= 60.0:
                self._hits.popleft()
            if len(self._hits) >= self.per_minute:
                return False
            self._hits.append(now)
            return True


class Audit:
    def __init__(self, ledger: Upstream | None, operator: str, client_name: str = "", signer: Any = None) -> None:
        self.ledger, self.operator, self.client_name = ledger, operator, client_name
        self.signer = signer          # a field_core CallerSigner: the rows are appended as a caller of the ledger (F2b)
        self.session_id = uuid.uuid4().hex

    def _append(self, event_type: str, agent_id: str | None, payload: dict[str, Any]) -> None:
        if self.ledger is None:
            raise ToolError("audit unavailable; no write made")
        try:
            self.ledger.request("POST", "/events", body=signed_append_body(self.signer, event_type, payload, agent_id))
        except ToolError:
            raise ToolError("audit unavailable; no write made") from None

    def intent(self, *, tool: str, service: str, method: str, path: str, args: dict[str, Any], reason: str) -> str:
        body = args.get("body")
        call_id = uuid.uuid4().hex
        payload = {"call_id": call_id, "tool": tool, "service": service, "method": method, "path": path,
                   "targets": {k: v for k, v in args.items() if k not in ("body", "reason") and isinstance(v, (str, int))},
                   "body_sha256": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() if body is not None else None,
                   "reason": reason, "operator": self.operator, "session_id": self.session_id,
                   "client_name": self.client_name[:100]}
        in_body = body.get("agent_id") if isinstance(body, dict) else None
        agent = next((a for a in (args.get("agent_id"), in_body) if isinstance(a, str)), None)
        self._append(INTENT, agent, payload)
        return call_id

    def outcome(self, call_id: str, tool: str, status: str) -> bool:
        try:
            self._append(OUTCOME, None, {"call_id": call_id, "tool": tool, "status": status,
                                         "session_id": self.session_id})
            return True
        except ToolError:
            return False
