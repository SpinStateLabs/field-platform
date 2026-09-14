"""Federation crossings — ASK the federation-broker before crossing an org boundary.

The SDK asks; it never relays. ``FederationClient.cross`` sends one crossing
request to the broker (``POST /crossing``) and returns the broker's verdict
on ALLOW. It carries no traffic to the counterparty and adds no power: the
decision is the broker's, and the SDK's only local capability is refusal —
raising ``CrossingBlocked`` before the agent does the cross-org work.

Fail-closed contract (the same rule as the sentinel and heartbeat clients):

* BLOCK (or any decision that is not exactly ``ALLOW``) ⇒ ``CrossingBlocked``
  carrying the broker's verdict and its clause;
* broker unreachable ⇒ ``CrossingBlocked`` with ``verdict=None`` and the
  reason "federation-broker unreachable — failing closed". No clause is
  invented: nothing was decided;
* any non-200 answer, or a 200 that is not a verdict ⇒ ``CrossingBlocked``
  with ``verdict=None``, naming what came back.

An agent that never calls this is not federation-gated (cooperative
perimeter, same as every other SDK hook).
"""

from __future__ import annotations

from field_agent._transport import AuthedClient
from field_agent.errors import FieldAgentError

import os
from pathlib import Path
from typing import Any, Callable, Literal

UNREACHABLE_REASON = "federation-broker unreachable — failing closed"
DEFAULT_FEDERATION_URL = "http://127.0.0.1:8010"

Direction = Literal["inbound", "outbound"]


class CrossingBlocked(FieldAgentError):
    """The crossing may not proceed.

    ``verdict`` is the broker's verdict (a dict, with ``clause_id``) when the
    broker decided BLOCK; it is ``None`` when no decision was obtained
    (unreachable, refused request, malformed answer) — fail closed, and no
    clause is invented for a decision that never happened.
    """

    def __init__(self, message: str, verdict: dict[str, Any] | None = None):
        self.verdict = verdict
        self.reason = message
        super().__init__(message)

    @property
    def clause_id(self) -> str | None:
        return self.verdict.get("clause_id") if self.verdict else None


class FederationClient:
    def __init__(self, client: Any | None = None, base_url: str | None = None):
        self._base = (base_url or os.environ.get(
            "FIELD_FEDERATION_URL", DEFAULT_FEDERATION_URL
        )).rstrip("/")
        if client is None:
            import httpx

            client = httpx.Client(timeout=10.0)
        # Auth headers are merged per request (FIELD_SHARED_SECRET read at
        # call time), exactly like the other SDK clients.
        self._client = AuthedClient(client)

    @staticmethod
    def request_body(
        agent_id: str | None,
        counterparty_org: str,
        scope: str,
        data_class: str,
        manifest: dict[str, Any] | str | os.PathLike[str],
        *,
        direction: Direction = "outbound",
        counterparty_agent_id: str | None = None,
        manifest_signature: str | None = None,
        request_summary: str | None = None,
    ) -> dict[str, Any]:
        """The ``POST /crossing`` body, using the broker's names per direction.

        Outbound: ``agent_id`` + ``manifest`` are OUR agent and OUR manifest.
        Inbound: ``manifest`` is the counterparty's, sent as
        ``counterparty_manifest`` with ``counterparty_agent_id`` (required).
        Caller errors raise ``ValueError`` before any request is made.
        """
        if direction not in ("inbound", "outbound"):
            raise ValueError(f"direction must be 'inbound' or 'outbound', not {direction!r}")
        if isinstance(manifest, (str, os.PathLike)):
            from field_core.validation import load_manifest

            manifest = load_manifest(Path(manifest))
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be a mapping or a path to a manifest YAML")
        body: dict[str, Any] = {
            "direction": direction,
            "counterparty_org": counterparty_org,
            "scope": scope,
            "data_class": data_class,
        }
        if direction == "outbound":
            if not agent_id:
                raise ValueError("an outbound crossing needs our agent_id")
            if manifest_signature is not None:
                raise ValueError(
                    "outbound crossings are not signature-checked (the contract "
                    "key is the counterparty's); do not pass manifest_signature"
                )
            body.update(agent_id=agent_id, manifest=manifest)
        else:
            if not counterparty_agent_id:
                raise ValueError("an inbound crossing needs counterparty_agent_id")
            body.update(counterparty_manifest=manifest)
            if manifest_signature is not None:
                body["manifest_signature"] = manifest_signature
        if counterparty_agent_id is not None:
            body["counterparty_agent_id"] = counterparty_agent_id
        if request_summary is not None:
            body["request_summary"] = request_summary
        return body

    def cross(
        self,
        agent_id: str | None,
        counterparty_org: str,
        scope: str,
        data_class: str,
        manifest: dict[str, Any] | str | os.PathLike[str],
        *,
        direction: Direction = "outbound",
        counterparty_agent_id: str | None = None,
        manifest_signature: str | None = None,
        request_summary: str | None = None,
    ) -> dict[str, Any]:
        """Ask the broker; return the verdict on ALLOW, raise ``CrossingBlocked``
        otherwise (including when the broker cannot be asked)."""
        body = self.request_body(
            agent_id, counterparty_org, scope, data_class, manifest,
            direction=direction, counterparty_agent_id=counterparty_agent_id,
            manifest_signature=manifest_signature, request_summary=request_summary,
        )
        try:
            resp = self._client.post(f"{self._base}/crossing", json=body)
        except Exception as exc:
            raise CrossingBlocked(
                f"{UNREACHABLE_REASON} ({type(exc).__name__}: {exc})"
            ) from exc
        if resp.status_code != 200:
            raise CrossingBlocked(
                f"federation-broker answered HTTP {resp.status_code} — no "
                f"crossing decision, failing closed: {resp.text[:300]}"
            )
        try:
            verdict = resp.json()
            decision = verdict["decision"]
        except Exception as exc:
            raise CrossingBlocked(
                "federation-broker returned no verdict — failing closed "
                f"({type(exc).__name__})"
            ) from exc
        if decision != "ALLOW":
            reasons = "; ".join(str(r) for r in verdict.get("reasons") or [])
            raise CrossingBlocked(
                f"crossing {decision} by {verdict.get('clause_id')}: {reasons}",
                verdict=verdict,
            )
        return verdict


# -- ``fieldagent cross`` ------------------------------------------------------

#: Seam for tests: the CLI builds its client through this factory.
_cli_client: Callable[[], FederationClient] = FederationClient


def register_cli(app: Any) -> None:
    """Add ``cross`` to a Typer app (``field_agent.cli`` calls this once).

    Exit 0 ALLOW / 1 BLOCK or no decision (broker unreachable or refused —
    fail closed), mirroring ``fieldagent check``; the verdict JSON is printed
    on stdout whenever the broker produced one.
    """
    import json

    import typer
    import yaml

    @app.command("cross")
    def cross(
        agent_id: str = typer.Argument(
            ..., help="OUR agent (sent outbound; inbound crossings name the "
            "counterparty's agent instead)",
        ),
        counterparty_org: str = typer.Option(..., "--org", help="Counterparty org"),
        scope: str = typer.Option(..., "--scope", help="The action being requested"),
        data_class: str = typer.Option(..., "--data-class"),
        manifest: Path = typer.Option(
            ..., "--manifest",
            help="Manifest YAML — outbound: OUR agent's; inbound: the counterparty's",
        ),
        direction: str = typer.Option(
            "outbound", "--direction", help="outbound (default) | inbound",
        ),
        counterparty_agent_id: str = typer.Option(
            None, "--counterparty-agent-id",
            help="The counterparty's agent (required inbound)",
        ),
        signature: str = typer.Option(
            None, "--signature", help="Inbound only: base64 manifest signature",
        ),
    ) -> None:
        """Ask the federation-broker. Exit 0 ALLOW / 1 BLOCK or broker unreachable."""
        try:
            verdict = _cli_client().cross(
                agent_id, counterparty_org, scope, data_class, manifest,
                direction=direction,  # type: ignore[arg-type]
                counterparty_agent_id=counterparty_agent_id,
                manifest_signature=signature,
            )
        except CrossingBlocked as exc:
            if exc.verdict is not None:
                typer.echo(json.dumps(exc.verdict, indent=2))
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1)
        except (ValueError, OSError, yaml.YAMLError) as exc:  # nothing was asked
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=1)
        typer.echo(json.dumps(verdict, indent=2))


__all__ = [
    "CrossingBlocked",
    "DEFAULT_FEDERATION_URL",
    "FederationClient",
    "UNREACHABLE_REASON",
    "register_cli",
]
