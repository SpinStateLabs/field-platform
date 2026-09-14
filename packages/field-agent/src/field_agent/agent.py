"""The ``FieldAgent`` facade — the three governance hooks on one object.

A client, not an authority: every decision is made server-side by the
sentinel, governor, and kill-switch. The facade's only local power is
refusal — raise before an ungoverned action runs, raise when metering
fails, raise when the heartbeat says stop. An agent that never constructs
one is not governed (cooperative perimeter); the server-side backstop is
that a killed agent's next sentinel check is BLOCK regardless.
"""

from __future__ import annotations

from field_agent._transport import AuthedClient
from field_agent.actions import Governor
from field_agent.errors import AgentKilled
from field_agent.federation import FederationClient
from field_agent.liveness import Heartbeat, LivenessClient
from field_agent.usage import UsageClient, UsageReport, extract_usage

import functools
import os
import time
from typing import Any, Callable, Literal, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


class FieldAgent:
    def __init__(
        self,
        agent_id: str,
        token_id: str | Callable[[], str | None] | None = None,
        *,
        sentinel_client: Any | None = None,
        governor_client: Any | None = None,
        killswitch_client: Any | None = None,
        sentinel_url: str | None = None,
        governor_url: str | None = None,
        killswitch_url: str | None = None,
        federation_client: Any | None = None,
        federation_url: str | None = None,
        heartbeat_max_age: float | None = None,
    ):
        self.agent_id = agent_id
        # A value or a zero-arg callable — tokens rotate; late binding keeps
        # the facade honest (same contract as the @governed decorator).
        self._token_id = token_id
        if sentinel_client is None:
            import httpx

            sentinel_client = httpx.Client(timeout=10.0)
        # The Governor is handed a pre-wrapped client so auth headers are
        # read per request, not captured at construction.
        self._sentinel = Governor(
            agent_id=agent_id,
            sentinel_url=sentinel_url,
            client=AuthedClient(sentinel_client),
        )
        self._usage = UsageClient(client=governor_client, base_url=governor_url)
        self._liveness = LivenessClient(
            client=killswitch_client, base_url=killswitch_url
        )
        self._federation = FederationClient(
            client=federation_client, base_url=federation_url
        )
        self._heartbeat_max_age = heartbeat_max_age
        self._alive_at: float | None = None

    def _resolve_token(self) -> str | None:
        return self._token_id() if callable(self._token_id) else self._token_id

    # -- hook 1: ACTIONS ----------------------------------------------------

    def check(
        self,
        action: str,
        irreversible: bool = False,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ask the sentinel; returns the verdict on ALLOW, raises
        ``ActionBlocked`` / ``ActionEscalated`` otherwise (fail closed on an
        unreachable sentinel — inherited from ``Governor``)."""
        if self._heartbeat_max_age is not None and (
            self._alive_at is None
            or time.monotonic() - self._alive_at > self._heartbeat_max_age
        ):
            self.ensure_alive()
        return self._sentinel.check(
            action,
            irreversible=irreversible,
            token_id=self._resolve_token(),
            context=context,
        )

    def governed(
        self, action: str, irreversible: bool = False
    ) -> Callable[[F], F]:
        """Instance-bound decorator: the wrapped callable runs only on ALLOW."""

        def decorate(fn: F) -> F:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                self.check(action, irreversible=irreversible)
                return fn(*args, **kwargs)

            return wrapper  # type: ignore[return-value]

        return decorate

    # -- hook 2: USAGE ------------------------------------------------------

    def report_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        note: str | None = None,
    ) -> UsageReport:
        return self._usage.report(
            self.agent_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            note=note,
        )

    def report_usage_from(self, response: Any, note: str | None = None) -> UsageReport:
        """Sugar: report straight from an Anthropic Messages response."""
        return self.report_usage(**extract_usage(response), note=note)

    def report_spend(
        self,
        cents: int = 0,
        tokens: int = 0,
        actions: int = 0,
        note: str | None = None,
        action: str | None = None,
    ):
        """Record non-LLM operating spend against the same cap (strict).

        ``action`` attributes the row to one action. A sentinel that meters
        every ALLOW already counts each checked action once; self-reporting
        ``actions`` for a checked action is not double-counted (the governor
        takes max(self, metered) per action), so report cents only for work
        that went through ``check()``."""
        return self._usage.spend(
            self.agent_id, cents=cents, tokens=tokens, actions=actions, note=note,
            action=action,
        )

    # -- FEDERATION: ask before crossing an org boundary --------------------

    def cross(
        self,
        counterparty_org: str,
        scope: str,
        data_class: str,
        manifest: dict[str, Any] | str | os.PathLike[str],
        *,
        direction: Literal["inbound", "outbound"] = "outbound",
        counterparty_agent_id: str | None = None,
        manifest_signature: str | None = None,
        request_summary: str | None = None,
    ) -> dict[str, Any]:
        """Ask the federation-broker whether this crossing may proceed.

        Returns the verdict on ALLOW; raises ``CrossingBlocked`` otherwise,
        including when the broker is unreachable (``verdict=None``, fail
        closed). It ASKS — the SDK carries no traffic to the counterparty.
        Same opt-in liveness gate as :meth:`check`."""
        if self._heartbeat_max_age is not None and (
            self._alive_at is None
            or time.monotonic() - self._alive_at > self._heartbeat_max_age
        ):
            self.ensure_alive()
        return self._federation.cross(
            self.agent_id,
            counterparty_org,
            scope,
            data_class,
            manifest,
            direction=direction,
            counterparty_agent_id=counterparty_agent_id,
            manifest_signature=manifest_signature,
            request_summary=request_summary,
        )

    # -- hook 3: LIVENESS ---------------------------------------------------

    def heartbeat(self) -> Heartbeat:
        """The observer form: returns the heartbeat, never raises on
        ``killed=true``. Transport failure still raises
        ``HeartbeatUnreachable`` (⊂ ``AgentKilled``) — liveness unknown is
        not liveness."""
        return self._liveness.heartbeat(self.agent_id)

    def checkin(self) -> Heartbeat:
        """Record a server-side check-in and read the verdict back.

        Same observer contract as :meth:`heartbeat` — it returns
        ``killed=true`` rather than raising, and a transport failure still
        raises ``HeartbeatUnreachable``. The difference is the write: this is
        the only call in the SDK that makes the agent visible to the
        kill-switch's ``GET /liveness``. It is evidence of a check-in, not
        evidence that the process is healthy."""
        return self._liveness.checkin(self.agent_id)

    def ensure_alive(self) -> Heartbeat:
        """Halt gate: raises ``AgentKilled`` unless the kill-switch says
        this agent is active."""
        hb = self.heartbeat()
        if hb.killed:
            raise AgentKilled(
                f"kill-switch reports '{self.agent_id}' status={hb.status!r}"
                " — halting",
                heartbeat=hb,
            )
        self._alive_at = time.monotonic()
        return hb
