"""Board-pack assembly. THE RULE: no number without a source.

Every metric carries the literal HTTP query it came from — enforced at the
model level (`source_query` must be non-empty, and `value` may only be set
when `status` is "ok"). A service that can't be reached yields an
``unavailable`` metric with the query that failed; it never yields a
fabricated zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: int | float | str | None = None
    unit: str | None = None
    source_query: str = Field(min_length=1, description="Literal HTTP query — the rule")
    status: Literal["ok", "unavailable"] = "ok"
    note: str | None = None

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
    generated_at: str
    sections: list[Section]
    method: str = (
        "every figure is a live query result from the named endpoint at "
        "generation time; unavailable services are shown as unavailable, "
        "never as zero. No LLM."
    )

    def all_metrics(self) -> list[Metric]:
        return [m for s in self.sections for m in s.metrics]


def _fetch(client, base: str, path: str, params: dict[str, Any] | None = None):
    """Return (raw_json, query, ok). Query string is the literal source.
    Raw data is returned untouched — transforms run on the real payload,
    never on a pre-collapsed count."""
    query = f"GET {base}{path}"
    if params:
        query += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    try:
        resp = client.get(path, params=params or None)
        if resp.status_code != 200:
            return None, query, False
        return resp.json(), query, True
    except Exception:
        return None, query, False


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
                transform=None, note=None) -> Metric:
        if client is None:
            query = f"GET {base}{path}" + (
                "?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else ""
            )
            return Metric(name=name, source_query=query, status="unavailable",
                          note="service not configured/reachable at generation time")
        data, query, ok = _fetch(client, base, path, params)
        if not ok:
            return Metric(name=name, source_query=query, status="unavailable",
                          note="service not configured/reachable at generation time")
        if transform is not None:
            value = transform(data)
        elif isinstance(data, list):
            value = len(data)
        else:
            value = data
        return Metric(name=name, value=value, unit=unit,
                      source_query=query, note=note)

    def _event_count(self, name: str, event_type: str) -> Metric:
        return self._metric(
            name, self.ledger, self.ledger_base, "/events",
            params={"event_type": event_type}, unit="events",
        )

    def build(self, period: str | None = None,
              now: datetime | None = None) -> BoardPack:
        now = now or datetime.now(timezone.utc)
        period = period or f"as of {now.date().isoformat()}"

        # --- Agents ---
        agents_total = self._metric(
            "Agents registered", self.registry, self.registry_base, "/agents",
            unit="agents",
        )
        agents_active = self._metric(
            "Agents in production (active)", self.registry, self.registry_base,
            "/agents", params={"status": "active"}, unit="agents",
        )
        agents_killed = self._metric(
            "Agents currently killed", self.registry, self.registry_base,
            "/agents", params={"status": "killed"}, unit="agents",
        )

        # --- Conformance ---
        allows = self._event_count("Conformance ALLOW verdicts", "conformance.allow")
        blocks = self._event_count("Conformance BLOCK verdicts", "conformance.block")
        escalates = self._event_count(
            "Conformance ESCALATE verdicts", "conformance.escalate"
        )
        if all(m.status == "ok" for m in (allows, blocks, escalates)):
            total = int(allows.value) + int(blocks.value) + int(escalates.value)
            pct = round(100 * int(allows.value) / total, 1) if total else None
            conformance = Metric(
                name="Conformance rate (ALLOW / all verdicts)",
                value=pct if pct is not None else "n/a — no verdicts in ledger",
                unit="%" if pct is not None else None,
                source_query=f"{allows.source_query} ; {blocks.source_query} ; "
                             f"{escalates.source_query}",
                note=f"= {allows.value} / ({allows.value}+{blocks.value}"
                     f"+{escalates.value})",
            )
        else:
            conformance = Metric(
                name="Conformance rate (ALLOW / all verdicts)",
                source_query=f"{allows.source_query} ; {blocks.source_query} ; "
                             f"{escalates.source_query}",
                status="unavailable", note="ledger unavailable",
            )

        # --- Enforcement ---
        kills = self._event_count("Kill-switch activations", "kill.agent")
        drills = self._event_count("Kill drills completed", "kill.drill.complete")
        spend_escs = self._metric(
            "Open spend escalations (human queue)", self.governor,
            self.governor_base, "/escalations", unit="open items",
        )

        # --- Delegation ---
        tokens_all = self._metric(
            "Delegation tokens issued (all time)", self.delegation,
            self.delegation_base, "/tokens", unit="tokens",
        )
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
                 "now <= expires_at <= now+30d",
        )
        revoked = self._metric(
            "Tokens revoked (all time)", self.delegation,
            self.delegation_base, "/tokens", unit="tokens",
            transform=lambda toks: sum(1 for t in toks if t.get("revoked"))
            if isinstance(toks, list) else toks,
            note="computed client-side from the token list: revoked == true",
        )

        # --- Incidents & federation ---
        fed_allow = self._event_count("Federation crossings allowed", "federation.allow")
        fed_block = self._event_count("Federation crossings blocked", "federation.block")
        orphans = self._event_count("Lifecycle orphan escalations", "lifecycle.orphan")

        # --- Ledger integrity (the number the rest stand on) ---
        integrity_query = f"GET {self.ledger_base}/verify"
        try:
            v = self.ledger.get("/verify").json() if self.ledger else None
            if v is None:
                integrity = Metric(
                    name="Ledger chain integrity", source_query=integrity_query,
                    status="unavailable", note="ledger unreachable",
                )
            else:
                integrity = Metric(
                    name="Ledger chain integrity",
                    value=("INTACT" if v.get("ok") else
                           f"BROKEN — {v.get('reason')}"),
                    source_query=integrity_query,
                    note=f"chain length {v.get('length')}",
                )
        except Exception:
            integrity = Metric(
                name="Ledger chain integrity", source_query=integrity_query,
                status="unavailable", note="ledger unreachable",
            )

        return BoardPack(
            org=self.org,
            period=period,
            generated_at=now.isoformat(),
            sections=[
                Section(title="Ledger integrity", metrics=[integrity]),
                Section(title="Agents", metrics=[agents_total, agents_active,
                                                 agents_killed]),
                Section(title="Conformance", metrics=[conformance, allows,
                                                      blocks, escalates]),
                Section(title="Enforcement", metrics=[kills, drills, spend_escs]),
                Section(title="Delegation", metrics=[tokens_all, expiring, revoked]),
                Section(title="Federation & lifecycle",
                        metrics=[fed_allow, fed_block, orphans]),
            ],
        )
