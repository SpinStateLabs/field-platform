"""Shadow-agent discovery v0.1 — deterministic heuristic scanner.

Ingests two artifact types an IT org can actually produce today:

1. An n8n workflow export (JSON): workflows containing AI/LLM/agent nodes
   are agent candidates.
2. A service-account inventory (CSV): accounts whose name or type matches
   automation patterns are agent candidates.

A candidate is *shadow* if no registered agent matches it by id or name
(case-insensitive substring in either direction).

Everything here is regex/string matching. No LLM. The README labels the
method heuristic — expect false positives; the point is a review queue,
not a verdict.
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, Iterable

from agent_registry.models import AgentRecord, DiscoveryReport, ShadowCandidate

# n8n node-type substrings that indicate an AI/agent workload.
AI_NODE_MARKERS = (
    "openai",
    "anthropic",
    "lmchat",
    "chainllm",
    "agent",
    "langchain",
    "huggingface",
    "geminiai",
    "vectorstore",
    "embeddings",
)

# Service-account naming patterns that indicate automation identity.
ACCOUNT_PATTERNS = re.compile(r"(^svc[-_.]|^bot[-_.]|[-_.]bot$|agent|automation|ai[-_.])", re.I)
ACCOUNT_TYPE_MARKERS = ("service", "bot", "application", "automation")


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _is_registered(identifier: str, display: str, registered: Iterable[AgentRecord]) -> bool:
    norm_id, norm_display = _normalize(identifier), _normalize(display)
    for record in registered:
        for known in (_normalize(record.agent_id), _normalize(record.name)):
            if not known:
                continue
            for candidate in (norm_id, norm_display):
                if candidate and (known in candidate or candidate in known):
                    return True
    return False


def scan_n8n_export(
    export: dict[str, Any] | list[dict[str, Any]],
    registered: list[AgentRecord],
) -> list[ShadowCandidate]:
    """n8n exports are either a single workflow object or a list of them."""
    workflows = export if isinstance(export, list) else [export]
    candidates = []
    for wf in workflows:
        name = str(wf.get("name", "<unnamed workflow>"))
        wf_id = str(wf.get("id", name))
        ai_nodes = []
        for node in wf.get("nodes", []):
            node_type = str(node.get("type", "")).lower()
            if any(marker in node_type for marker in AI_NODE_MARKERS):
                ai_nodes.append(f"{node.get('name', '?')} ({node.get('type')})")
        if not ai_nodes:
            continue
        if _is_registered(wf_id, name, registered):
            continue
        candidates.append(
            ShadowCandidate(
                source="n8n",
                identifier=wf_id,
                display_name=name,
                reason=f"workflow contains {len(ai_nodes)} AI/agent node(s) "
                "but matches no registered agent",
                evidence={"ai_nodes": "; ".join(ai_nodes[:5])},
            )
        )
    return candidates


def scan_service_accounts(
    csv_text: str,
    registered: list[AgentRecord],
) -> tuple[list[ShadowCandidate], int]:
    """CSV columns (header required): account,type[,owner][,notes] — extras ignored."""
    reader = csv.DictReader(io.StringIO(csv_text))
    candidates, scanned = [], 0
    for row in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        account = row.get("account") or row.get("name") or ""
        if not account:
            continue
        scanned += 1
        acc_type = row.get("type", "")
        looks_automated = bool(ACCOUNT_PATTERNS.search(account)) or any(
            marker in acc_type.lower() for marker in ACCOUNT_TYPE_MARKERS
        )
        if not looks_automated:
            continue
        if _is_registered(account, account, registered):
            continue
        candidates.append(
            ShadowCandidate(
                source="service-accounts",
                identifier=account,
                display_name=account,
                reason="automation-pattern account matches no registered agent",
                evidence={"type": acc_type, "owner": row.get("owner", "")},
            )
        )
    return candidates, scanned


def discover(
    registered: list[AgentRecord],
    n8n_export: dict[str, Any] | list[dict[str, Any]] | None = None,
    accounts_csv: str | None = None,
) -> DiscoveryReport:
    n8n_candidates: list[ShadowCandidate] = []
    workflows_scanned = 0
    if n8n_export is not None:
        workflows = n8n_export if isinstance(n8n_export, list) else [n8n_export]
        workflows_scanned = len(workflows)
        n8n_candidates = scan_n8n_export(n8n_export, registered)

    account_candidates: list[ShadowCandidate] = []
    accounts_scanned = 0
    if accounts_csv is not None:
        account_candidates, accounts_scanned = scan_service_accounts(
            accounts_csv, registered
        )

    return DiscoveryReport(
        scanned_workflows=workflows_scanned,
        scanned_accounts=accounts_scanned,
        registered_agents=len(registered),
        candidates=n8n_candidates + account_candidates,
    )


def load_n8n_file(path: str) -> dict[str, Any] | list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
