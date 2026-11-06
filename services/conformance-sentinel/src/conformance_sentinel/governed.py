"""``@governed`` — wrap any Python callable in a sentinel check.

Usage::

    from conformance_sentinel.governed import governed, ActionBlocked

    @governed(agent_id="invoicing-agent", action="draft invoices",
              token_id=lambda: TOKEN_ID)
    def draft_invoice(row):
        ...

    # or imperatively:
    guard = Governor(agent_id="invoicing-agent", token_id=TOKEN_ID)
    guard.check("draft invoices")          # raises unless ALLOW

The decorator asks the sentinel BEFORE the wrapped call runs. BLOCK raises
``ActionBlocked``; ESCALATE raises ``ActionEscalated`` (the human queue has
the item; the caller decides how to wait). The wrapped function runs only on
ALLOW. Fail closed: sentinel unreachable ⇒ ``ActionBlocked``.
"""

from __future__ import annotations

from field_core.authn import auth_headers

import functools
import os
import threading
from typing import Any, Callable

import httpx


class ActionBlocked(RuntimeError):
    def __init__(self, verdict: dict[str, Any]):
        self.verdict = verdict
        super().__init__(
            f"BLOCK [{verdict.get('clause_id')}] {'; '.join(verdict.get('reasons', []))}"
        )

    @property
    def retry_after(self) -> int | None:
        """Seconds until the exhausted rate window frees a slot — the
        governor's ``retry_after_seconds``, carried in the verdict context of
        an ``E.rate_limit`` BLOCK. None for every other block (a cap, a kill,
        a scope refusal have no retry time)."""
        context = self.verdict.get("context")
        if not isinstance(context, dict):
            return None
        value = context.get("retry_after_seconds")
        return value if isinstance(value, int) and not isinstance(value, bool) else None


class ActionEscalated(RuntimeError):
    def __init__(self, verdict: dict[str, Any]):
        self.verdict = verdict
        super().__init__(
            f"ESCALATE [{verdict.get('clause_id')}] {'; '.join(verdict.get('reasons', []))}"
        )


class Governor:
    def __init__(
        self,
        agent_id: str,
        token_id: str | None = None,
        sentinel_url: str | None = None,
        client: Any | None = None,
    ):
        self.agent_id = agent_id
        self.token_id = token_id
        self._base = (sentinel_url or os.environ.get(
            "FIELD_SENTINEL_URL", "http://127.0.0.1:8004"
        )).rstrip("/")
        self._client = client or httpx.Client(timeout=10.0, headers=auth_headers())

    def close(self) -> None:
        """Close the HTTP client (also a client that was passed in: the Governor
        is its user). Safe to call more than once."""
        close = getattr(self._client, "close", None)
        if close is not None:
            close()

    def __enter__(self) -> "Governor":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def check(
        self,
        action: str,
        irreversible: bool = False,
        token_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            resp = self._client.post(
                f"{self._base}/check",
                json={
                    "agent_id": self.agent_id,
                    "action": action,
                    "token_id": token_id or self.token_id,
                    "irreversible": irreversible,
                    "context": context or {},
                },
            )
            resp.raise_for_status()
            verdict = resp.json()
        except Exception as exc:
            raise ActionBlocked(
                {"clause_id": "E.kill_switch",
                 "reasons": [f"sentinel unreachable — failing closed: {exc}"],
                 "decision": "BLOCK"}
            ) from exc
        if verdict["decision"] == "BLOCK":
            raise ActionBlocked(verdict)
        if verdict["decision"] == "ESCALATE":
            raise ActionEscalated(verdict)
        return verdict


def governed(
    agent_id: str,
    action: str,
    token_id: str | Callable[[], str | None] | None = None,
    irreversible: bool = False,
    sentinel_url: str | None = None,
):
    """Decorator form. ``token_id`` may be a value or a zero-arg callable
    (tokens rotate; late binding keeps the decorator honest)."""

    def decorate(fn: Callable) -> Callable:
        # ONE Governor (one connection pool) per decorated function, built on the
        # first call; the token is still read on every call and passed to check().
        guard: Governor | None = None
        guard_lock = threading.Lock()

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal guard
            tid = token_id() if callable(token_id) else token_id
            if guard is None:
                with guard_lock:
                    if guard is None:
                        guard = Governor(agent_id=agent_id, sentinel_url=sentinel_url)
            guard.check(action, irreversible=irreversible, token_id=tid)
            return fn(*args, **kwargs)

        return wrapper

    return decorate
