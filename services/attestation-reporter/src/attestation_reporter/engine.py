"""Board-pack assembly. THE RULE: no number without a source.

Every metric carries the literal HTTP query it came from — enforced at the
model level (`source_query` must be non-empty, and `value` may only be set
when `status` is "ok"). A service that can't be reached yields an
``unavailable`` metric with the query that failed; it never yields a
fabricated zero.

C4 — the window, the canary row and the signature fields:
- Every ledger-derived metric (each whose query hits ``/events``) is counted
  inside ``BoardPack.window``: its printed query carries ``since``/``until``
  and ``basis='window'``. Registry, token, governor, integrity and retention
  figures are ``basis='point_in_time'`` — as they stood at generation.
- The printed query is the request sent, byte for byte (``_target``).
- Gate-verification (canary) agents — ``CANARY_AGENTS`` — are ONE labelled
  row; their events, registry records, tokens and escalations are excluded
  from every governance metric, and a metric that dropped any says how many.
- ``BoardPack`` carries ``signed/signer/signed_at/key_fingerprint/signature``
  and (F4) the provenance ``signed_via``; signing lives in
  ``attestation_reporter.signing``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from attestation_reporter.window import InvalidWindow, Window, normalise_bound, resolve_window

#: The FIELD canary agents — tools/estate_probe.py CANARIES | RETIRED_CANARIES
#: (plan rule 7). EXACT ids, never a prefix: a real agent may be called
#: canary-anything. A test pins this set to the probe's.
CANARY_AGENTS = frozenset({"canary-gb10", "canary-fly", "canary-gb10-retired", "canary-fly-retired"})

POINT_IN_TIME = "point-in-time: at generation"
UNREACHABLE = "service not configured/reachable at generation time"


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: int | float | str | None = None
    unit: str | None = None
    source_query: str = Field(min_length=1, description="Literal HTTP query — the rule")
    status: Literal["ok", "unavailable"] = "ok"
    note: str | None = None
    basis: Literal["window", "point_in_time"] = Field(
        "point_in_time",
        description="window: counted inside BoardPack.window; point_in_time: as at generation",
    )

    @model_validator(mode="after")
    def _no_number_without_source_and_no_fake_numbers(self) -> "Metric":
        if self.status == "unavailable" and self.value is not None:
            raise ValueError(
                f"metric '{self.name}': unavailable metrics must not carry a value"
            )
        if self.status == "ok" and self.value is None:
            raise ValueError(f"metric '{self.name}': ok metrics must carry a value")
        return self


class Section(BaseModel):
    title: str
    metrics: list[Metric]


class BoardPack(BaseModel):
    org: str
    period: str
    window: Window
    generated_at: str
    sections: list[Section]
    method: str = (
        "every figure is a live query result from the named endpoint at "
        "generation time; basis=window figures count ledger events inside the "
        "window and their query carries its bounds, basis=point_in_time "
        "figures are as they stood at generation; unavailable services are "
        "shown as unavailable, never as zero; gate-verification (canary) "
        "activity is one labelled row, excluded from every other figure. No LLM."
    )
    # Signature (C4) and provenance (F4). `attest render --signer --sign-key`
    # sets these with signed_via "cli"; the served app sets them with
    # signed_via "estate-key" when FIELD_ATTEST_SIGNER + FIELD_ATTEST_SIGN_KEY
    # are configured, and otherwise serves an unsigned draft. See
    # attestation_reporter.signing.
    signed: bool = False
    signer: str | None = None
    signed_at: str | None = None
    key_fingerprint: str | None = None
    signature: str | None = None
    signed_via: Literal["cli", "estate-key"] | None = Field(
        None,
        description=(
            "F4 provenance, inside the signed bytes: cli (attest render --signer "
            "--sign-key) or estate-key (served under FIELD_ATTEST_SIGNER). Absent — "
            "never null — on an unsigned pack and on a pack signed before F4."
        ),
    )

    @model_validator(mode="after")
    def _signed_means_every_signature_field(self) -> "BoardPack":
        fields = (self.signer, self.signed_at, self.key_fingerprint, self.signature)
        if self.signed and not (all(fields) and self.signer.strip()):
            raise ValueError("a signed pack needs signer, signed_at, key_fingerprint and signature")
        if not self.signed and (any(f is not None for f in fields) or self.signed_via is not None):
            raise ValueError("an unsigned pack carries no signer, signed_at, key_fingerprint, "
                             "signature or signed_via")
        return self

    @model_serializer(mode="wrap")
    def _omit_absent_provenance(self, handler, info):
        """F4: ``signed_via`` is OMITTED from every dump in which it is None —
        never written as ``null`` — so an unsigned pack keeps the C4 wire shape
        (older readers see no new key) and a pack signed before F4 dumps to
        exactly the bytes it was signed over (signing.py, THE BYTES). Every
        other absent field keeps its ``null``."""
        data = handler(self)
        if isinstance(data, dict) and data.get("signed_via") is None:
            data.pop("signed_via", None)
        return data

    def all_metrics(self) -> list[Metric]:
        return [m for s in self.sections for m in s.metrics]


def _target(path: str, params: dict[str, Any] | None = None) -> str:
    """Path + query exactly as sent. ``+`` in a UTC offset is %2B-escaped (a
    bare ``+`` decodes to a space); ``:`` stays readable."""
    if not params:
        return path
    return path + "?" + "&".join(
        f"{quote(str(k), safe='')}={quote(str(v), safe=':')}" for k, v in params.items()
    )


def _fetch_answer(client, base: str, path: str, params: dict[str, Any] | None = None):
    """Return (raw_json, query, ok, http_status): ``_fetch`` plus the HTTP
    status the service answered with — None when no answer came back (not
    configured, or the request itself failed)."""
    target = _target(path, params)
    query = f"GET {base}{target}"
    if client is None:
        return None, query, False, None
    try:
        resp = client.get(target)
    except Exception:
        return None, query, False, None
    if resp.status_code != 200:
        return None, query, False, resp.status_code
    try:
        return resp.json(), query, True, 200
    except Exception:
        return None, query, False, 200


def _fetch(client, base: str, path: str, params: dict[str, Any] | None = None):
    """Return (raw_json, query, ok). Query string is the literal source.
    Raw data is returned untouched — transforms run on the real payload,
    never on a pre-collapsed count."""
    data, query, ok, _ = _fetch_answer(client, base, path, params)
    return data, query, ok


def _verify_unanswered(http_status: int | None) -> str:
    """Why the integrity metric has no value. 'Unreachable' only when no
    answer came back: a ledger that ANSWERED without a verification result
    (a 500 from any cause, a 404, a 200 that is not a verification) is
    reported as exactly that — the chain was NOT verified — never as an
    outage. (The ledger reports an unparseable record as a break, HTTP 200.)"""
    if http_status is None:
        return "ledger unreachable"
    if http_status in (401, 403):
        return f"ledger refused /verify (HTTP {http_status}) — chain not verified by this pack"
    if http_status == 503:
        return "ledger answered HTTP 503 to /verify (busy or unavailable) — chain not verified; retry"
    if http_status == 200:
        return "ledger answered /verify with no verification result — chain NOT verified; investigate"
    return f"ledger answered HTTP {http_status} to /verify — chain NOT verified; investigate"


def _without_canaries(data: Any) -> tuple[Any, int]:
    """Drop gate-verification records (any dict whose ``agent_id`` is a canary)."""
    if not isinstance(data, list):
        return data, 0
    kept = [x for x in data if not (isinstance(x, dict) and x.get("agent_id") in CANARY_AGENTS)]
    return kept, len(data) - len(kept)


def _join(*parts: str | None) -> str | None:
    return "; ".join(p for p in parts if p) or None


def _excluded(n: int) -> str | None:
    return f"excludes {n} gate-verification (canary) record(s) this query returned" if n else None


class PackEngine:
    """Clients are httpx-like with base_url set (TestClient qualifies).
    base labels are only used to print the source queries."""

    def __init__(
        self,
        registry=None, registry_base: str = "http://127.0.0.1:8001",
        ledger=None, ledger_base: str = "http://127.0.0.1:8002",
        delegation=None, delegation_base: str = "http://127.0.0.1:8003",
        governor=None, governor_base: str = "http://127.0.0.1:8006",
        org: str = "Spin State Labs",
    ):
        self.registry, self.registry_base = registry, registry_base
        self.ledger, self.ledger_base = ledger, ledger_base
        self.delegation, self.delegation_base = delegation, delegation_base
        self.governor, self.governor_base = governor, governor_base
        self.org = org

    def _metric(self, name, client, base, path, params=None, unit=None,
                transform=None, note=None, basis="point_in_time") -> Metric:
        data, query, ok = _fetch(client, base, path, params)
        if not ok:
            return Metric(name=name, source_query=query, status="unavailable",
                          note=UNREACHABLE, basis=basis)
        data, excluded = _without_canaries(data)
        if transform is not None:
            value = transform(data)
        elif isinstance(data, list):
            value = len(data)
        else:
            value = data
        return Metric(name=name, value=value, unit=unit, source_query=query,
                      note=_join(note, _excluded(excluded)), basis=basis)

    def _retention_metrics(self) -> tuple[Metric, Metric]:
        """Two SCALAR metrics from the ledger's ``GET /retention/check`` (C2):
        the estate policy in days, and how many manifests declare more
        retention than the estate keeps (the ids go in ``note``, never in
        ``value``). Retention is estate-level: one policy for the one chain.
        Ledger not configured / unreachable / non-200, or no estate policy =>
        both unavailable; a registry the ledger could not read => the count is
        unavailable. Notes carry no timestamps (served == rendered). Canary
        agents are dropped from the offending/unresolvable lists (C4)."""
        policy_name = "Estate ledger retention policy (days)"
        count_name = "Manifests declaring more retention than the estate keeps"
        query = f"GET {self.ledger_base}/retention/check"

        def unavailable(name: str, unit: str, note: str) -> Metric:
            return Metric(name=name, unit=unit, source_query=query, status="unavailable", note=note)

        data, _, ok = _fetch(self.ledger, self.ledger_base, "/retention/check")
        if not ok or not isinstance(data, dict):
            return unavailable(policy_name, "days", UNREACHABLE), unavailable(count_name, "manifests", UNREACHABLE)
        estate = data.get("estate_retention_days")
        if data.get("status") == "no_estate_policy" or not isinstance(estate, int) or isinstance(estate, bool):
            note = "no estate policy (FIELD_LEDGER_RETENTION_DAYS unset)"
            return unavailable(policy_name, "days", note), unavailable(count_name, "manifests", note)
        policy = Metric(
            name=policy_name, value=estate, unit="days", source_query=query,
            note="estate-level: one policy for the one shared chain; each manifest's "
                 "retention_days is a floor the estate must meet",
        )
        if data.get("status") == "unavailable":
            return policy, unavailable(count_name, "manifests",
                                       "the ledger could not read the agent registry at generation time")
        offending, n_off = _without_canaries(data.get("offending") or [])
        unresolvable, n_unres = _without_canaries(data.get("unresolvable") or [])
        offending = sorted(offending, key=lambda o: str(o.get("agent_id")))
        unresolvable = sorted(unresolvable, key=lambda u: str(u.get("agent_id")))
        parts = []
        if offending:
            parts.append("offending: " + ", ".join(
                f"{o.get('agent_id')} ({o.get('retention_days')} d)" for o in offending))
        if unresolvable:
            parts.append("unresolvable: " + ", ".join(
                f"{u.get('agent_id')} ({u.get('reason')})" for u in unresolvable))
            parts.append(f"a lower bound: {len(unresolvable)} manifest ref(s) could not be read")
        if not parts:
            parts.append(f"none among {data.get('manifests_checked', 0)} resolvable manifest(s)")
        if data.get("agents_without_manifest"):
            parts.append(f"{data['agents_without_manifest']} agent(s) without a manifest_ref not checked")
        if n_off or n_unres:
            parts.append(f"excludes {n_off + n_unres} gate-verification (canary) finding(s)")
        count = Metric(name=count_name, value=len(offending), unit="manifests",
                       source_query=query, note="; ".join(parts))
        return policy, count

    def _event_count(self, name: str, event_type: str, window: Window,
                     note: str | None = None) -> Metric:
        return self._metric(
            name, self.ledger, self.ledger_base, "/events",
            params={"event_type": event_type, **window.params()}, unit="events",
            note=note, basis="window",
        )

    def _sweep_rows(self, window: Window) -> list[Metric]:
        """Windowed counts of the lifecycle sweep's ``reattestation_due`` and
        ``expiring_authority`` EVENTS, each with a de-duplicated companion:
        one fetch per event type feeds both rows (same printed query)."""
        sweep_note = ("sweep EVENTS, not distinct findings: each lifecycle sweep writes one "
                      "event per flagged {what}, so under a daily A1 schedule this counts "
                      "finding-days (see the distinct row)")
        rows: list[Metric] = []
        for event_type, count_name, what, distinct_name, key_label, key in (
            ("lifecycle.reattestation_due", "Re-attestation due (sweep events)", "agent",
             "Distinct agents flagged for re-attestation", "agent_id",
             lambda e: e.get("agent_id")),
            ("lifecycle.expiring_authority", "Expiring authority (sweep events)", "token",
             "Distinct tokens flagged as expiring", "payload.token_id",
             lambda e: (e.get("payload") or {}).get("token_id")),
        ):
            data, query, ok = _fetch(self.ledger, self.ledger_base, "/events",
                                     {"event_type": event_type, **window.params()})
            if not ok or not isinstance(data, list):
                for name, unit in ((count_name, "events"), (distinct_name, f"{what}s")):
                    rows.append(Metric(name=name, unit=unit, source_query=query,
                                       status="unavailable", note=UNREACHABLE, basis="window"))
                continue
            events, excluded = _without_canaries(data)
            keys = [key(e) if isinstance(e, dict) else None for e in events]
            missing = sum(1 for k in keys if k is None)
            rows.append(Metric(
                name=count_name, value=len(events), unit="events", source_query=query,
                note=_join(sweep_note.format(what=what), _excluded(excluded)), basis="window",
            ))
            rows.append(Metric(
                name=distinct_name, value=len({k for k in keys if k is not None}), unit=f"{what}s",
                source_query=query, basis="window",
                note=_join(
                    f"= count of distinct {key_label} over the {len(events)} {event_type} "
                    f"event(s) in the window — each {what} counted once however many sweeps flagged it",
                    f"{missing} event(s) without {key_label} not counted" if missing else None,
                    _excluded(excluded),
                ),
            ))
        return rows

    def _gate_verification_row(self, window: Window) -> Metric:
        """ONE labelled row for canary activity in the window: the exact
        canary ids, queried by agent_id (never a prefix match)."""
        name = "Gate-verification events (canary agents, excluded from every other figure)"
        queries, counts, failed = [], {}, False
        for agent in sorted(CANARY_AGENTS):
            data, query, ok = _fetch(self.ledger, self.ledger_base, "/events",
                                     {"agent_id": agent, **window.params()})
            queries.append(query)
            if ok and isinstance(data, list):
                counts[agent] = len(data)
            else:
                failed = True
        query = " ; ".join(queries)
        if failed:
            return Metric(name=name, unit="events", source_query=query, status="unavailable",
                          note=UNREACHABLE, basis="window")
        return Metric(
            name=name, value=sum(counts.values()), unit="events", source_query=query,
            basis="window",
            note="rule-7 canary activity (gate verification, not governance): "
                 + ", ".join(f"{a} {n}" for a, n in counts.items())
                 + "; these agents' events, registry records, tokens, escalations and "
                   "retention findings are excluded from every governance metric in this pack",
        )

    def _integrity(self, window: Window) -> Metric:
        """The whole live chain at generation (point-in-time), plus C3's
        earliest-live note when the window starts before the earliest live
        event. A busy ledger is unavailable, never BROKEN (sealed-ledger's
        ``ledger busy:`` contract): BROKEN means the chain failed to verify.
        A ledger that answers /verify without a result is unavailable with
        the HTTP status and "chain NOT verified" (``_verify_unanswered``)."""
        name = "Ledger chain integrity"
        query = f"GET {self.ledger_base}/verify ; GET {self.ledger_base}/health"
        v, _, ok, answered = _fetch_answer(self.ledger, self.ledger_base, "/verify")
        if not ok or not isinstance(v, dict):
            return Metric(name=name, source_query=query, status="unavailable",
                          note=_verify_unanswered(answered))
        reason = v.get("reason")
        if not v.get("ok") and isinstance(reason, str) and reason.startswith("ledger busy:"):
            return Metric(name=name, source_query=query, status="unavailable",
                          note=f"{reason} — not a verification result; retry")
        return Metric(
            name=name,
            value="INTACT" if v.get("ok") else f"BROKEN — {reason}",
            source_query=query,
            note=_join(f"chain length {v.get('length')}",
                       f"{POINT_IN_TIME} (the whole live chain, not the window)",
                       self._earliest_live_note(window, v)),
        )

    def _earliest_live_note(self, window: Window, verification: dict[str, Any]) -> str | None:
        """C2 retention: archived segments are not in ``/events``. A window
        that starts before the earliest LIVE event (an all-time or open-start
        window always does, once anything is archived) says so — C3's note.
        A pre-C2 ledger's ``/health`` has no ``earliest_live_*`` ⇒ no note."""
        health, _, ok = _fetch(self.ledger, self.ledger_base, "/health")
        if not ok or not isinstance(health, dict):
            return "earliest-live check unavailable: ledger /health unreadable"
        earliest_ts = health.get("earliest_live_ts")
        earliest_index = health.get("earliest_live_index")
        # index 0 is the first event ever written: nothing is archived.
        if (not earliest_ts or isinstance(earliest_index, bool)
                or not isinstance(earliest_index, int) or earliest_index <= 0):
            return None
        if window.since is not None:
            try:
                before = normalise_bound("since", window.since, end=False) < normalise_bound(
                    "earliest_live_ts", str(earliest_ts), end=False)
            except InvalidWindow:
                return (f"earliest-live check unavailable: ledger /health "
                        f"earliest_live_ts is not ISO 8601 ({earliest_ts!r})")
            if not before:
                return None
        archived = health.get("archived_segments", verification.get("archived_segments"))
        return (
            f"window starts before the earliest live event (segments archived: "
            f"{'unknown' if archived is None else archived}) — the earliest live event "
            f"is global index {earliest_index} at {earliest_ts}; earlier events are not "
            f"in the live ledger and not counted in this pack"
        )

    def build(self, period: str | None = None, now: datetime | None = None, *,
              since: str | None = None, until: str | None = None) -> BoardPack:
        """``period`` ("2026-Q3" / "Q3 2026") and ``since``/``until`` are
        mutually exclusive; neither ⇒ all-time. A bad window raises
        ``InvalidWindow`` before any service is queried."""
        now = now or datetime.now(timezone.utc)
        window, label = resolve_window(period, since, until, now=now)

        # --- Agents (point-in-time) ---
        agents_total = self._metric(
            "Agents registered", self.registry, self.registry_base, "/agents",
            unit="agents", note=POINT_IN_TIME,
        )
        agents_active = self._metric(
            "Agents in production (active)", self.registry, self.registry_base,
            "/agents", params={"status": "active"}, unit="agents", note=POINT_IN_TIME,
        )
        agents_killed = self._metric(
            "Agents currently killed", self.registry, self.registry_base,
            "/agents", params={"status": "killed"}, unit="agents", note=POINT_IN_TIME,
        )

        # --- Conformance (windowed) ---
        # A log-only estate (the served default since S1) records violations
        # as shadow verdicts and never writes conformance.block/escalate; a
        # rate computed from enforced verdicts alone would read 100% while
        # violations shadow-ledger. Shadow verdicts therefore count in the
        # denominator and get their own rows (S2-R).
        allows = self._event_count("Conformance ALLOW verdicts", "conformance.allow", window)
        blocks = self._event_count("Conformance BLOCK verdicts", "conformance.block", window)
        escalates = self._event_count(
            "Conformance ESCALATE verdicts", "conformance.escalate", window
        )
        shadow_note = ("log-only mode: violation observed and ledgered, "
                       "caller NOT blocked")
        shadow_blocks = self._event_count(
            "Shadow BLOCK verdicts (log-only, not enforced)",
            "conformance.shadow_block", window, note=shadow_note,
        )
        shadow_escalates = self._event_count(
            "Shadow ESCALATE verdicts (log-only, not enforced)",
            "conformance.shadow_escalate", window, note=shadow_note,
        )
        verdicts = (allows, blocks, escalates, shadow_blocks, shadow_escalates)
        rate_query = " ; ".join(m.source_query for m in verdicts)
        if all(m.status == "ok" for m in verdicts):
            total = sum(int(m.value) for m in verdicts)
            pct = round(100 * int(allows.value) / total, 1) if total else None
            shadow_total = int(shadow_blocks.value) + int(shadow_escalates.value)
            note = (f"= {allows.value} / ({allows.value}+{blocks.value}"
                    f"+{escalates.value}+{shadow_blocks.value}"
                    f"+{shadow_escalates.value})")
            if shadow_total:
                note += (f"; includes {shadow_total} log-only shadow "
                         f"verdict(s) — violations observed, NOT enforced")
            conformance = Metric(
                name="Conformance rate (ALLOW / all verdicts incl. shadow)",
                value=pct if pct is not None else "n/a — no verdicts in ledger",
                unit="%" if pct is not None else None,
                source_query=rate_query,
                note=note,
                basis="window",
            )
        else:
            conformance = Metric(
                name="Conformance rate (ALLOW / all verdicts incl. shadow)",
                source_query=rate_query,
                status="unavailable", note="ledger unavailable", basis="window",
            )

        # --- Enforcement ---
        kills = self._event_count("Kill-switch activations", "kill.agent", window)
        drills = self._event_count("Kill drills completed", "kill.drill.complete", window)
        spend_escs = self._metric(
            "Open spend escalations (human queue)", self.governor,
            self.governor_base, "/escalations", unit="open items", note=POINT_IN_TIME,
        )

        # --- Delegation (point-in-time: the token list at generation) ---
        tokens_all = self._metric(
            "Delegation tokens issued (all time)", self.delegation,
            self.delegation_base, "/tokens", unit="tokens",
            note=f"{POINT_IN_TIME}: every token on record, not windowed",
        )
        revoked = self._metric(
            "Tokens revoked (all time)", self.delegation,
            self.delegation_base, "/tokens", unit="tokens",
            transform=lambda toks: sum(1 for t in toks if t.get("revoked"))
            if isinstance(toks, list) else toks,
            note="computed client-side from the token list: revoked == true; "
                 f"{POINT_IN_TIME}, not windowed",
        )

        # --- Expirations & re-attestation ---
        expiring = self._metric(
            "Authorities expiring within 30 days", self.delegation,
            self.delegation_base, "/tokens", unit="tokens",
            transform=lambda toks: sum(
                1 for t in toks
                if not t.get("revoked")
                and now <= datetime.fromisoformat(
                    t["expires_at"].replace("Z", "+00:00")
                ) <= now + timedelta(days=30)
            ) if isinstance(toks, list) else toks,
            note="computed client-side from the token list: not revoked AND "
                 f"now <= expires_at <= now+30d; {POINT_IN_TIME} (now = generated_at)",
        )
        sweep_rows = self._sweep_rows(window)

        # --- Incidents & federation ---
        fed_allow = self._event_count("Federation crossings allowed", "federation.allow", window)
        fed_block = self._event_count("Federation crossings blocked", "federation.block", window)
        orphans = self._event_count("Lifecycle orphan escalations", "lifecycle.orphan", window)

        # --- Ledger integrity (the number the rest stand on) ---
        integrity = self._integrity(window)
        retention_policy, retention_offending = self._retention_metrics()

        return BoardPack(
            org=self.org,
            period=label,
            window=window,
            generated_at=now.isoformat(),
            sections=[
                Section(title="Ledger integrity",
                        metrics=[integrity, retention_policy, retention_offending]),
                Section(title="Agents", metrics=[agents_total, agents_active,
                                                 agents_killed]),
                Section(title="Conformance", metrics=[conformance, allows,
                                                      blocks, escalates,
                                                      shadow_blocks,
                                                      shadow_escalates]),
                Section(title="Enforcement", metrics=[kills, drills, spend_escs]),
                Section(title="Delegation", metrics=[tokens_all, revoked]),
                Section(title="Expirations & re-attestation",
                        metrics=[expiring, *sweep_rows]),
                Section(title="Federation & lifecycle",
                        metrics=[fed_allow, fed_block, orphans]),
                Section(title="Gate verification",
                        metrics=[self._gate_verification_row(window)]),
            ],
        )
