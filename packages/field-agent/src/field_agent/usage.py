"""Hook 2 — USAGE. Report LLM token usage to the spend-governor.

Strict by design: a failed report RAISES. A best-effort reporter produces
an agent that believes it is metered while spending unmetered — the exact
overclaim the platform's Enforced-vs-Declared discipline exists to kill.
Callers that truly want fire-and-forget write the ``try/except`` at the
call site, visibly. The governor's 404 ("no spend cap") surfaces as
``NoSpendCapError`` — ungoverned spend is refused, not dropped.

Self-reported counts trust the reporter. For observed metering, route LLM
calls through force-gateway ``POST /v1/messages`` with the
``x-field-agent-id`` header instead (see docs/INTEGRATION.md).
"""

from __future__ import annotations

from field_agent._transport import AuthedClient
from field_agent.errors import NoSpendCapError, UsageReportError

import os
from typing import Any

from pydantic import BaseModel, ConfigDict


class RogueFinding(BaseModel):
    """``kind`` stays a plain str — new server-side kinds must not break clients."""

    model_config = ConfigDict(extra="ignore")

    kind: str
    detail: str


class UsageRecordLite(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cost_units: int | None = None
    priced: bool = True
    note: str | None = None


class SpendStatusLite(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent_id: str
    state: str  # "OK" | "ESCALATE" | "BLOCK"
    spent_cents: int = 0
    limit_cents: int | None = None
    spent_tokens: int = 0
    token_limit: int | None = None
    detail: str = ""
    token_cost_units: int = 0
    token_cost_display: str = ""


class UsageReport(BaseModel):
    record: UsageRecordLite
    rogue: list[RogueFinding]
    status: SpendStatusLite


class UsageClient:
    def __init__(self, client: Any | None = None, base_url: str | None = None):
        self._base = (base_url or os.environ.get(
            "FIELD_GOVERNOR_URL", "http://127.0.0.1:8006"
        )).rstrip("/")
        if client is None:
            import httpx

            client = httpx.Client(timeout=5.0)
        self._client = AuthedClient(client)

    def report(
        self,
        agent_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        note: str | None = None,
    ) -> UsageReport:
        try:
            resp = self._client.post(
                f"{self._base}/usage",
                json={
                    "agent_id": agent_id,
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_read_tokens": cache_read_tokens,
                    "note": note,
                },
            )
        except Exception as exc:
            raise UsageReportError(
                f"spend-governor unreachable — usage NOT metered: {exc}"
            ) from exc
        if resp.status_code == 404:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise NoSpendCapError(detail)
        if resp.status_code != 201:
            raise UsageReportError(
                f"usage report returned {resp.status_code}: {resp.text}"
            )
        return UsageReport.model_validate(resp.json())

    def spend(
        self,
        agent_id: str,
        cents: int = 0,
        tokens: int = 0,
        actions: int = 0,
        note: str | None = None,
    ) -> SpendStatusLite:
        """Record non-LLM operating spend (POST /spend). Same strict rules
        as ``report``: failure raises, no-cap 404 raises ``NoSpendCapError``."""
        try:
            resp = self._client.post(
                f"{self._base}/spend",
                json={"agent_id": agent_id, "cents": cents, "tokens": tokens,
                      "actions": actions, "note": note},
            )
        except Exception as exc:
            raise UsageReportError(
                f"spend-governor unreachable — spend NOT metered: {exc}"
            ) from exc
        if resp.status_code == 404:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise NoSpendCapError(detail)
        if resp.status_code != 201:
            raise UsageReportError(
                f"spend report returned {resp.status_code}: {resp.text}"
            )
        return SpendStatusLite.model_validate(resp.json())


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def extract_usage(response: Any) -> dict[str, Any]:
    """Pull ``{model, input_tokens, output_tokens, cache_read_tokens}`` from
    an Anthropic Messages response — dict or SDK object, no anthropic import.
    Maps Anthropic's ``cache_read_input_tokens`` → ``cache_read_tokens``.
    Raises ``ValueError`` rather than guessing zeros for missing token
    counts (a guessed meter is worse than a loud one); only the cache field
    defaults to 0.
    """
    usage = _get(response, "usage")
    model = _get(response, "model")
    if usage is None or model is None:
        raise ValueError(
            "response carries no usage/model — cannot report; "
            "call report_usage(...) with explicit token counts"
        )
    input_tokens = _get(usage, "input_tokens")
    output_tokens = _get(usage, "output_tokens")
    if input_tokens is None or output_tokens is None:
        raise ValueError(
            "usage block lacks input_tokens/output_tokens — cannot report"
        )
    return {
        "model": str(model),
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "cache_read_tokens": int(_get(usage, "cache_read_input_tokens") or 0),
    }
