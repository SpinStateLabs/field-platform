"""The lifecycle sweep.

Agents rot in three ways the platform can detect deterministically:

1. **Expiring authority** — delegation tokens lapsing within the horizon
   (default 30 days): renew deliberately or let them die deliberately.
2. **Re-attestation due** — agents whose last human attestation is older
   than the attestation period (default 90 days): someone must confirm the
   agent still does what its manifest says. The basis is the registry
   record's ``attested_at``, falling back to ``created_at`` when nobody has
   ever attested — and NEVER the record's edit timestamp, which any PATCH
   resets: before v1.2 a kill/revive cycle silently hid 90 days of
   staleness. A grep-guard test pins that this module never reads it.
3. **Orphans** — agents whose human owner is not on the current roster
   (owners.csv): nobody is accountable. Escalated always; auto-killed only
   when the operator passes the flag — killing is never a silent default.

Every finding is a ledger event; the sweep is idempotent (re-running
re-reports, it does not duplicate kills).

Two lifecycle *transitions* also live here, each with injected clients so a
test drives the whole sequence without a network:

* ``provision`` — validate manifest, register, cap, mint. Fail closed at
  step one: an INVALID manifest produces ZERO side effects.
* ``decommission`` — revoke authority, halt, retire, record. Act-first
  (like the kill-switch): a ledger outage is reported, never a reason to
  leave an agent running.

Neither pretends to be atomic. Both report step by step and say where they
stopped, because a half-provisioned agent that is reported as provisioned is
worse than one that failed loudly.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from field_core.clients import AgentNotRegisteredError, RegistryUnreachableError
from field_core.manifest import FieldManifest
from field_core.validation import (
    ValidationStatus,
    load_manifest,
    validate_manifest_file,
)

# Runtime dependency (declared in pyproject; precedent: field-agent depends on
# conformance-sentinel). One cents rule for the whole platform: the governor
# rounds, so provisioning must round the same way or the cap it writes and the
# cap the governor would derive disagree by a cent.
from spend_governor.core import SpendCapConfig


class SweepConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expiry_horizon_days: int = Field(default=30, ge=1)
    reattestation_days: int = Field(default=90, ge=1)
    auto_kill_orphans: bool = False
    operator: str = Field(
        default="lifecycle-manager (scheduled)",
        description="Recorded on escalations and any auto-kills",
    )


class ExpiringAuthority(BaseModel):
    token_id: str
    agent_id: str
    granted_by: str
    expires_at: str
    days_left: int
    scope: list[str]


class ReattestationDue(BaseModel):
    agent_id: str
    owner: str
    last_updated: str = Field(
        description="The timestamp the staleness was measured from — the "
        "record's attested_at, or its created_at when nobody has attested. "
        "Named for compatibility; `basis` says which one it is. BREAKING "
        "SEMANTIC CHANGE in v1.2 B4: this key used to carry the record's "
        "edit timestamp, so the same key now reports a DIFFERENT number for "
        "the same agent. Read `basis` before comparing against anything "
        "recorded before v1.2. The identifier of that old field is "
        "deliberately absent from this module — a grep-guard test fails if "
        "it reappears anywhere in the file, docstrings included."
    )
    days_stale: int
    basis: str = Field(
        default="created_at",
        description="attested_at | created_at — which field the clock ran from",
    )
    attested_by: str | None = Field(
        default=None,
        description="Who last attested (a recorded string, not an "
        "authenticated identity); None when nobody ever has",
    )


class Orphan(BaseModel):
    agent_id: str
    owner: str
    status: str
    reason: str
    auto_killed: bool = False


class SweepReport(BaseModel):
    swept_at: str
    config: SweepConfig
    agents_scanned: int
    tokens_scanned: int
    roster_size: int
    expiring: list[ExpiringAuthority]
    reattestation_due: list[ReattestationDue]
    orphans: list[Orphan]
    escalations_written: int
    method: str = (
        "deterministic sweep v0.1 over agent-registry + delegation-authority "
        "vs. owners.csv roster; no LLM"
    )


# ---------------------------------------------------------------------------
# Lifecycle transitions: provision and decommission
# ---------------------------------------------------------------------------


class LifecycleError(Exception):
    """A transition refused before it changed anything. Carries the message
    the CLI prints; the caller exits non-zero and nothing was created."""


class TransitionStep(BaseModel):
    """One step of a multi-service transition, in the order it ran.

    There is no rollback: a provision that fails at `mint` leaves a
    registered, capped agent with no token, and this list says so. Reporting
    a partial run as a success is the failure mode this model exists to
    prevent."""

    model_config = ConfigDict(extra="forbid")

    step: str
    outcome: str = Field(description="ok | failed | skipped")
    detail: str | None = None
    http_status: int | None = None


class ProvisionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    manifest: str
    manifest_ref: str | None = None
    owner: str
    domain: str
    grantor: str
    registry_outcome: str | None = Field(
        default=None, description="registered | updated"
    )
    cap_cents: int | None = None
    cap_period: str | None = None
    scope: list[str] = Field(default_factory=list)
    token_id: str | None = None
    expires_at: str | None = None
    steps: list[TransitionStep] = Field(default_factory=list)
    ok: bool = False
    provisioned_at: str
    note: str = (
        "Not atomic and not pretended to be: steps ran in the listed order "
        "and stopped at the first failure. Nothing is rolled back."
    )


class DecommissionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    by: str
    reason: str
    previous_status: str
    noop: bool = False
    tokens_revoked: list[str] = Field(default_factory=list)
    revoke_failures: list[TransitionStep] = Field(default_factory=list)
    killed: bool = False
    retired: bool = False
    steps: list[TransitionStep] = Field(default_factory=list)
    ok: bool = False
    decommissioned_at: str
    note: str = (
        "Act-first, like the kill-switch: a ledger or revoke failure is "
        "reported and the run continues, then the exit code is non-zero. "
        "An already-retired agent is a recorded no-op, never a second kill."
    )


class RosterEntry(BaseModel):
    """One HUMAN on owners.csv: the `owner` string plus the other strings the
    registry may record for the same person (`aliases`)."""

    model_config = ConfigDict(frozen=True)

    owner: str
    aliases: tuple[str, ...] = ()

    def match_strings(self) -> set[str]:
        """Every string that makes an agent owned by this human, lower-cased."""
        return {self.owner.lower(), *(a.lower() for a in self.aliases)}


def parse_roster_entries(csv_text: str) -> list[RosterEntry]:
    """owners.csv: header row with an `owner` column (`name` is accepted when
    there is no `owner` value) and an OPTIONAL `aliases` column; other columns
    are ignored.

    `aliases` is `;`-separated: one human, several strings. Every value is
    stripped; blank alias entries are dropped, so `;;` or a trailing `;` never
    becomes an empty string that an owner-less agent could match. A row with
    no owner is ignored WITH its aliases — an alias belongs to a named human.

    An unquoted comma is refused by name, never half-read, in the two shapes
    it can be detected: a row with MORE fields than the header, and a value
    that begins with whitespace (a space, TAB, NBSP, U+3000 or any other blank)
    right after an unquoted comma (`Don Hagell, Spin State Labs` under
    `owner,aliases` is exactly two fields, and would otherwise become owner
    `Don Hagell` + alias `Spin State Labs`). Quote any value containing a
    comma. NOT detectable: an unquoted comma with no whitespace after it that
    yields no more fields than the header (`Don Hagell,Spin State Labs` under
    `owner,aliases`, or under `owner,aliases,team` with the last column
    omitted, IS owner + alias to any CSV reader).
    """
    spaced = _lines_with_a_space_after_an_unquoted_comma(csv_text)
    reader = csv.DictReader(io.StringIO(csv_text))
    entries: list[RosterEntry] = []
    for row in reader:
        if None in row:
            raise ValueError(
                f"owners.csv line {reader.line_num}: more fields than the header "
                "(quote any owner or alias that contains a comma)"
            )
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        owner = row.get("owner") or row.get("name") or ""
        if not owner:
            continue
        aliases = tuple(
            a.strip() for a in row.get("aliases", "").split(";") if a.strip()
        )
        entries.append(RosterEntry(owner=owner, aliases=aliases))
    if spaced:  # checked after the loop: a MORE-fields row keeps its own message
        raise ValueError(_SPACED_COMMA.format(line=min(spaced)))
    return entries


_SPACED_COMMA = (
    "owners.csv line {line}: a value starts with whitespace after an unquoted comma — "
    "the signature of an unquoted `Name, Org` read as two values (quote any owner or "
    'alias that contains a comma, e.g. "Don Hagell, Spin State Labs")'
)


def _lines_with_a_space_after_an_unquoted_comma(csv_text: str) -> set[int]:
    """Line numbers of DATA rows where a comma outside quotes is followed by
    whitespace and a non-blank value.

    Two readers walk the same text, one plain and one with
    ``skipinitialspace``. A quoted value is identical in both (its spaces are
    inside the quotes); an unquoted value after `, ` keeps its leading space
    only in the first. The readers can only fall out of step AFTER such a
    difference (a quote recognised by the second reader alone starts with
    `, "` in the first), so the first difference is always seen. The header
    row is exempt: its names are stripped.

    `skipinitialspace` skips only U+0020, so every other blank (TAB, NBSP,
    U+3000, ...) is first mapped to a space in the text BOTH readers see.
    Blanks are neither delimiter nor quote, so field boundaries and line
    numbers are unchanged; CR and LF are left alone.
    """
    blanked = "".join(
        " " if ch.isspace() and ch not in "\r\n" else ch for ch in csv_text
    )
    plain = csv.reader(io.StringIO(blanked))
    skipping = csv.reader(io.StringIO(blanked), skipinitialspace=True)
    lines: set[int] = set()
    for number, (row, skipped) in enumerate(zip(plain, skipping)):
        if number and any(a != b and a.strip() for a, b in zip(row, skipped)):
            lines.add(plain.line_num)
    return lines


def parse_roster(csv_text: str) -> set[str]:
    """Every string that makes an agent non-orphaned: each owner and each of
    its aliases, lower-cased. Matching is case-insensitive and exact after
    strip — no substring, no whitespace folding, no identity resolution.

    A roster without an `aliases` column yields exactly the owner set it
    always did."""
    return {s for entry in parse_roster_entries(csv_text) for s in entry.match_strings()}


class _Unreachable:
    """Stands in for a response when the call itself never happened.

    A transport fault has to become a reported STEP, not a traceback: the
    operator needs to know which step died and that the earlier ones were
    not undone."""

    status_code: int | None = None

    def __init__(self, exc: BaseException):
        self.text = f"transport error: {type(exc).__name__}: {exc}"


def _try(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call an injected client; turn an outage into an `_Unreachable`."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — reported as a step, never hidden
        return _Unreachable(exc)


def _status(resp: Any) -> int | None:
    """Status of an httpx-like response (or of a TestClient response)."""
    return getattr(resp, "status_code", None)


def _json(resp: Any) -> Any:
    """Body of an httpx-like response; plain data passes straight through, so
    a test can hand the engine a list instead of a response object."""
    return resp.json() if hasattr(resp, "json") else resp


def _body(resp: Any) -> str:
    """Verbatim refusal text, truncated. Another service's wording is its own:
    this service never rewrites a refusal into something friendlier."""
    text = getattr(resp, "text", None)
    if text is None:
        text = str(_json(resp))
    return str(text)[:500]


def _parse_ts(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class LifecycleEngine:
    def __init__(
        self,
        registry,
        delegation,
        ledger=None,
        killswitch=None,
        registry_http=None,
        governor=None,
    ):
        """registry: RegistryClient · delegation: http client with GET /tokens
        · ledger: LedgerClient or None · killswitch: http client with
        POST /kill/{agent_id} or None (required for auto-kill and for the
        decommission halt) · registry_http: http client with POST /agents and
        PATCH /agents/{id} (provision only — RegistryClient cannot create) ·
        governor: http client with PUT /caps/{id} (provision only).

        Every one of these is an injection seam: the tests drive the whole
        provision / decommission sequence against in-process apps and spies,
        with no network and no sleeps."""
        self.registry = registry
        self.delegation = delegation
        self.ledger = ledger
        self.killswitch = killswitch
        self.registry_http = registry_http
        self.governor = governor

    def _ledger_note(self, event_type: str, payload: dict, agent_id: str | None) -> int:
        if self.ledger is None:
            return 0
        try:
            self.ledger.append(event_type, payload=payload, agent_id=agent_id)
            return 1
        except Exception:
            return 0

    def sweep(
        self,
        roster_csv: str,
        config: SweepConfig | None = None,
        now: datetime | None = None,
    ) -> SweepReport:
        config = config or SweepConfig()
        now = now or datetime.now(timezone.utc)
        entries = parse_roster_entries(roster_csv)
        # Every owner and alias string, lower-cased. `roster_size` counts
        # HUMANS (distinct owners), never alias strings: without an `aliases`
        # column the two are the same number, as before A1b.
        roster = {s for entry in entries for s in entry.match_strings()}
        roster_size = len({entry.owner.lower() for entry in entries})

        agents: list[dict[str, Any]] = self.registry.list_agents()
        tokens_resp = self.delegation.get("/tokens")
        tokens: list[dict[str, Any]] = (
            tokens_resp.json() if hasattr(tokens_resp, "json") else tokens_resp
        )

        escalations = 0

        # 1. Expiring authorities.
        expiring: list[ExpiringAuthority] = []
        horizon = now + timedelta(days=config.expiry_horizon_days)
        for t in tokens:
            if t.get("revoked"):
                continue
            expires = _parse_ts(t["expires_at"])
            if now <= expires <= horizon:
                days_left = (expires - now).days
                finding = ExpiringAuthority(
                    token_id=t["token_id"], agent_id=t["agent_id"],
                    granted_by=t["granted_by"], expires_at=t["expires_at"],
                    days_left=days_left, scope=t["scope"],
                )
                expiring.append(finding)
                escalations += self._ledger_note(
                    "lifecycle.expiring_authority",
                    {"token_id": finding.token_id, "days_left": days_left,
                     "granted_by": finding.granted_by, "operator": config.operator},
                    finding.agent_id,
                )

        # 2. Re-attestation due.
        reattest: list[ReattestationDue] = []
        stale_before = now - timedelta(days=config.reattestation_days)
        for a in agents:
            if a.get("status") != "active":
                continue
            # attested_at, else created_at. Deliberately NOT the record's edit
            # timestamp: any PATCH moves that, so a kill/revive cycle used to
            # reset the clock to zero and hide a stale agent completely.
            attested = a.get("attested_at")
            basis = "attested_at" if attested else "created_at"
            raw = attested or a["created_at"]
            since = _parse_ts(raw)
            if since < stale_before:
                days_stale = (now - since).days
                finding = ReattestationDue(
                    agent_id=a["agent_id"], owner=a["owner"],
                    last_updated=raw, days_stale=days_stale,
                    basis=basis, attested_by=a.get("attested_by"),
                )
                reattest.append(finding)
                escalations += self._ledger_note(
                    "lifecycle.reattestation_due",
                    # Keys are ADDITIVE: `owner`, `days_stale` and `operator`
                    # keep their meaning so existing counters keep working.
                    {"owner": finding.owner, "days_stale": days_stale,
                     "operator": config.operator, "basis": basis,
                     "attested_by": finding.attested_by},
                    finding.agent_id,
                )

        # 3. Orphans — owner not on the roster.
        orphans: list[Orphan] = []
        for a in agents:
            if a.get("status") == "retired":
                continue
            owner = str(a.get("owner", ""))
            if owner.lower() in roster:
                continue
            orphan = Orphan(
                agent_id=a["agent_id"], owner=owner, status=a.get("status", "?"),
                reason=f"owner '{owner}' not found in roster ({roster_size} entries)",
            )
            escalations += self._ledger_note(
                "lifecycle.orphan",
                {"owner": owner, "operator": config.operator,
                 "auto_kill_requested": config.auto_kill_orphans},
                orphan.agent_id,
            )
            if (
                config.auto_kill_orphans
                and self.killswitch is not None
                and a.get("status") == "active"
            ):
                resp = self.killswitch.post(
                    f"/kill/{orphan.agent_id}",
                    json={"operator": config.operator,
                          "reason": "lifecycle sweep: orphaned agent (auto-kill flag set)"},
                )
                orphan.auto_killed = getattr(resp, "status_code", 0) == 200
            orphans.append(orphan)

        return SweepReport(
            swept_at=now.isoformat(),
            config=config,
            agents_scanned=len(agents),
            tokens_scanned=len(tokens),
            roster_size=roster_size,
            expiring=expiring,
            reattestation_due=reattest,
            orphans=orphans,
            escalations_written=escalations,
        )


    # -- provision ---------------------------------------------------------

    def provision(
        self,
        manifest_path: str | Path,
        owner: str,
        domain: str,
        grantor: str,
        ttl_days: int,
        name: str | None = None,
        manifest_ref: str | None = None,
        now: datetime | None = None,
    ) -> ProvisionReport:
        """validate -> register -> cap -> mint, reported step by step.

        Step one is the gate: an INVALID manifest raises ``LifecycleError``
        having touched nothing — no registry row, no cap, no token, no ledger
        event. Everything after it runs in order and stops at the first
        failure; nothing is rolled back, and the report says exactly where it
        stopped rather than pretending the sequence was atomic.

        Refusals from delegation-authority — the B1 roster gate's 403/422, a
        503 from an unreadable roster — pass through verbatim in the step's
        ``http_status`` and ``detail``. This service never reinterprets
        another service's refusal.
        """
        now = now or datetime.now(timezone.utc)
        path = Path(manifest_path)
        steps: list[TransitionStep] = []

        # 1. validate — BEFORE any side effect.
        result = validate_manifest_file(path)
        if result.status is ValidationStatus.INVALID:
            gaps = "; ".join(result.critical_gaps) or "(no detail)"
            raise LifecycleError(
                f"manifest INVALID: {path} — {gaps}. Nothing was provisioned."
            )
        manifest = FieldManifest.from_dict(load_manifest(path))
        agent_id = manifest.agent.name
        scope = list(manifest.delegation.scope)
        steps.append(
            TransitionStep(step="validate", outcome="ok", detail=result.status.value)
        )

        report = ProvisionReport(
            agent_id=agent_id,
            manifest=str(path),
            manifest_ref=manifest_ref or str(path),
            owner=owner,
            domain=domain,
            grantor=grantor,
            scope=scope,
            steps=steps,
            provisioned_at=now.isoformat(),
        )
        # Pydantic copies the list on validation, so from here on the ONLY
        # list that reaches the caller is report.steps.
        steps = report.steps

        # 2. register (409 => PATCH owner/manifest_ref, reported as `updated`).
        resp = _try(
            self.registry_http.post,
            "/agents",
            json={
                "agent_id": agent_id,
                "name": name or agent_id,
                "owner": owner,
                "domain": domain,
                "manifest_ref": report.manifest_ref,
            },
        )
        status = _status(resp)
        if status == 201:
            report.registry_outcome = "registered"
            steps.append(
                TransitionStep(
                    step="register", outcome="ok", detail="registered",
                    http_status=status,
                )
            )
        elif status == 409:
            # A decommission is meant to be final. Re-provisioning a retired
            # agent cannot resurrect it — the mint refuses a non-active agent
            # — but without this guard the PATCH still rewrote `owner` (audit
            # attribution) and `manifest_ref` (which the kill-switch resolves
            # its halt endpoint from), and the cap step then installed a live
            # spend cap on a decommissioned record. Stop before any of it.
            existing = _try(self.registry_http.get, f"/agents/{agent_id}")
            if _status(existing) == 200:
                try:
                    previous = existing.json().get("status")
                except Exception:  # noqa: BLE001 - fall through to the PATCH
                    previous = None
                if previous == "retired":
                    steps.append(
                        TransitionStep(
                            step="register", outcome="failed",
                            detail=(
                                f"agent '{agent_id}' is retired — a decommission "
                                "is final. Re-provisioning would rewrite owner "
                                "and manifest_ref and re-cap a decommissioned "
                                "agent; use a new agent id, or undo the retire "
                                "at the registry first"
                            ),
                            http_status=409,
                        )
                    )
                    return report
            patch = _try(
                self.registry_http.patch,
                f"/agents/{agent_id}",
                json={"owner": owner, "manifest_ref": report.manifest_ref},
            )
            pstatus = _status(patch)
            if pstatus != 200:
                steps.append(
                    TransitionStep(
                        step="register", outcome="failed",
                        detail=f"already registered; PATCH refused: {_body(patch)}",
                        http_status=pstatus,
                    )
                )
                return report
            report.registry_outcome = "updated"
            steps.append(
                TransitionStep(
                    step="register", outcome="ok",
                    detail="already registered — owner/manifest_ref updated",
                    http_status=pstatus,
                )
            )
        else:
            steps.append(
                TransitionStep(
                    step="register", outcome="failed", detail=_body(resp),
                    http_status=status,
                )
            )
            return report

        # 3. cap — the governor's own arithmetic, so the two cannot disagree
        #    about a cent (SpendCapConfig.from_manifest uses round, not int).
        try:
            cap = SpendCapConfig.from_manifest(manifest, agent_id)
        except ValueError as exc:
            steps.append(TransitionStep(step="cap", outcome="failed", detail=str(exc)))
            return report
        cresp = _try(self.governor.put, f"/caps/{agent_id}", json=cap.model_dump())
        cstatus = _status(cresp)
        if cstatus != 200:
            steps.append(
                TransitionStep(
                    step="cap", outcome="failed", detail=_body(cresp),
                    http_status=cstatus,
                )
            )
            return report
        report.cap_cents = cap.limit_cents
        report.cap_period = cap.period
        steps.append(
            TransitionStep(
                step="cap", outcome="ok",
                detail=f"{cap.currency} {cap.limit_cents} cents/{cap.period}",
                http_status=cstatus,
            )
        )

        # 4. mint.
        mresp = _try(
            self.delegation.post,
            "/tokens",
            json={
                "agent_id": agent_id,
                "granted_by": grantor,
                "scope": scope,
                "ttl_seconds": int(ttl_days) * 86400,
            },
        )
        mstatus = _status(mresp)
        if mstatus != 201:
            steps.append(
                TransitionStep(
                    step="mint", outcome="failed", detail=_body(mresp),
                    http_status=mstatus,
                )
            )
            return report
        token = _json(mresp)
        report.token_id = token.get("token_id")
        report.expires_at = token.get("expires_at")
        steps.append(
            TransitionStep(
                step="mint", outcome="ok",
                detail=f"scope={len(scope)} actions, ttl={ttl_days} d",
                http_status=mstatus,
            )
        )
        report.ok = True
        return report

    # -- decommission ------------------------------------------------------

    def decommission(
        self,
        agent_id: str,
        by: str,
        reason: str,
        now: datetime | None = None,
    ) -> DecommissionReport:
        """Revoke authority, halt, retire, record.

        Order, and why each piece is where it is:

        * unknown agent => ``LifecycleError`` with nothing created — a typo in
          an agent id must not invent a ledger event about an agent that does
          not exist;
        * already ``retired`` => a recorded no-op (``lifecycle.decommissioned``
          with ``noop: true``) and NO kill, so a second decommission cannot
          produce a second ``kill.agent``;
        * every non-revoked token is revoked first. Revoke is ledger-first in
          delegation-authority, so a ledger outage answers 502: that is
          reported and the run CONTINUES (act-first — an audit outage must
          never leave an agent holding authority), and the exit code is
          non-zero at the end;
        * the kill is sent only when the status is ``active`` — an already
          killed agent must not get a second ``kill.agent`` event;
        * then the registry goes to ``retired``, which the kill-switch refuses
          to undo (409 on both ``/kill`` and ``/revive``).
        """
        now = now or datetime.now(timezone.utc)
        try:
            record = self.registry.get_agent(agent_id)
        except AgentNotRegisteredError:
            raise LifecycleError(
                f"agent '{agent_id}' is not registered — nothing decommissioned"
            )
        except RegistryUnreachableError as exc:
            raise LifecycleError(
                f"registry unreachable — refusing to decommission '{agent_id}': {exc}"
            )

        previous = str(record.get("status", "<unknown>"))
        report = DecommissionReport(
            agent_id=agent_id, by=by, reason=reason, previous_status=previous,
            decommissioned_at=now.isoformat(),
        )

        if previous == "retired":
            report.noop = True
            report.ok = True
            report.steps.append(
                TransitionStep(
                    step="decommission", outcome="skipped",
                    detail="already retired — no kill, no revoke, no status change",
                )
            )
            self._ledger_note(
                "lifecycle.decommissioned",
                {"noop": True, "by": by, "reason": reason,
                 "previous_status": previous, "tokens_revoked": 0,
                 "killed": False},
                agent_id,
            )
            return report

        ok = True

        # 1. revoke every token that is not already revoked. Expired ones are
        #    included on purpose: a revocation is a fact, an expiry is a clock.
        listing = _try(
            self.delegation.get, "/tokens", params={"agent_id": agent_id}
        )
        if isinstance(listing, _Unreachable):
            # Act-first: we cannot enumerate the authority, but we can still
            # halt and retire. Say so instead of stopping.
            ok = False
            report.revoke_failures.append(
                TransitionStep(step="revoke", outcome="failed",
                               detail=f"could not list tokens: {listing.text}")
            )
            tokens: list = []
        else:
            tokens = _json(listing) or []
        for token in tokens:
            if token.get("revoked"):
                continue
            token_id = token["token_id"]
            resp = _try(self.delegation.post, f"/tokens/{token_id}/revoke")
            status = _status(resp)
            if status == 200:
                report.tokens_revoked.append(token_id)
            else:
                ok = False
                report.revoke_failures.append(
                    TransitionStep(
                        step="revoke", outcome="failed",
                        detail=f"{token_id}: {_body(resp)}", http_status=status,
                    )
                )
        report.steps.append(
            TransitionStep(
                step="revoke", outcome="ok" if not report.revoke_failures else "failed",
                detail=f"{len(report.tokens_revoked)} revoked, "
                       f"{len(report.revoke_failures)} failed",
            )
        )

        # 2. kill — ONLY an active agent, and only through the kill-switch.
        if previous != "active":
            report.steps.append(
                TransitionStep(
                    step="kill", outcome="skipped",
                    detail=f"status is '{previous}' — already halted, no second kill",
                )
            )
        elif self.killswitch is None:
            ok = False
            report.steps.append(
                TransitionStep(
                    step="kill", outcome="failed",
                    detail="no kill-switch client configured",
                )
            )
        else:
            resp = _try(
                self.killswitch.post,
                f"/kill/{agent_id}",
                json={"operator": by, "reason": f"lifecycle decommission: {reason}"},
            )
            status = _status(resp)
            report.killed = status == 200
            if not report.killed:
                ok = False
            report.steps.append(
                TransitionStep(
                    step="kill", outcome="ok" if report.killed else "failed",
                    detail=None if report.killed else _body(resp),
                    http_status=status,
                )
            )

        # 3. retire.
        try:
            self.registry.set_status(agent_id, "retired")
            report.retired = True
            report.steps.append(TransitionStep(step="retire", outcome="ok"))
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed
            ok = False
            report.steps.append(
                TransitionStep(
                    step="retire", outcome="failed",
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )

        # 4. record.
        wrote = self._ledger_note(
            "lifecycle.decommissioned",
            {"by": by, "reason": reason,
             "tokens_revoked": len(report.tokens_revoked),
             "killed": report.killed, "previous_status": previous,
             "retired": report.retired, "noop": False,
             "token_ids": report.tokens_revoked},
            agent_id,
        )
        report.steps.append(
            TransitionStep(
                step="ledger", outcome="ok" if wrote else "failed",
                detail=None if wrote else (
                    "ledger unreachable — the gap is visible as a missing "
                    "lifecycle.decommissioned event"
                ),
            )
        )
        if not wrote:
            ok = False
        report.ok = ok
        return report


def render_markdown(report: SweepReport) -> str:
    lines: list[str] = []
    add = lines.append
    add("# Lifecycle sweep report")
    add("")
    add(f"*Swept:* {report.swept_at} · *Agents:* {report.agents_scanned} · "
        f"*Tokens:* {report.tokens_scanned} · *Roster:* {report.roster_size} humans")
    add(f"*Horizons:* expiry {report.config.expiry_horizon_days} d · "
        f"re-attestation {report.config.reattestation_days} d · "
        f"auto-kill orphans: {'ON' if report.config.auto_kill_orphans else 'off'}")
    add("")
    add(f"## Expiring authorities ({len(report.expiring)})")
    for e in report.expiring:
        add(f"- `{e.token_id[:8]}…` {e.agent_id} — {e.days_left} d left "
            f"(granted by {e.granted_by}; scope {', '.join(e.scope)})")
    if not report.expiring:
        add("- none within horizon")
    add("")
    add(f"## Re-attestation due ({len(report.reattestation_due)})")
    for r in report.reattestation_due:
        who = f", last attested by {r.attested_by}" if r.attested_by else ""
        add(f"- {r.agent_id} — owner {r.owner}, {r.days_stale} d since "
            f"{r.basis}{who}")
    if not report.reattestation_due:
        add("- none")
    add("")
    add(f"## Orphans ({len(report.orphans)})")
    for o in report.orphans:
        killed = " → AUTO-KILLED" if o.auto_killed else ""
        add(f"- {o.agent_id} ({o.status}) — {o.reason}{killed}")
    if not report.orphans:
        add("- none")
    add("")
    add(f"*Escalations written to ledger:* {report.escalations_written}")
    add(f"\n---\n*Method:* {report.method}")
    return "\n".join(lines)
