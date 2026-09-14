"""Shadow-agent discovery v0.1 — deterministic heuristic scanner.

Ingests two artifact types an IT org can actually produce today:

1. An n8n workflow export (JSON): workflows containing AI/LLM/agent nodes
   are agent candidates.
2. A service-account inventory (CSV): accounts whose name or type matches
   automation patterns are agent candidates.

A candidate is *shadow* if no registered agent matches it by id or name
(case-insensitive substring in either direction).

v1.2 D3 adds two more inputs:

3. An API-key / credential inventory (CSV you export yourself — there is no
   live IAM, cloud or secret-manager connector): keys whose owner is blank,
   is not a registered agent's owner, or that were last used by a principal
   the registry does not know, are candidates (:func:`scan_api_keys`).
4. Free text (a config dump, a repo grep, a paste): credential-shaped
   strings are reported, REDACTED, with a breadth label saying how often the
   pattern is wrong (:func:`scan_secrets_text`).

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

from agent_registry.models import (
    AgentRecord,
    DiscoveryReport,
    SecretHit,
    ShadowCandidate,
)
from agent_registry.redaction import ScanInputError, check_size, find_secrets

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


class _CountedLines:
    """The physical lines a csv reader pulls, counted — so a ``csv.Error``
    names the line it failed on without leaning on the reader's own
    ``line_num``, which lags by one when the error is raised mid-line."""

    def __init__(self, text: str) -> None:
        self._lines = iter(io.StringIO(text))
        self.count = 0

    def __iter__(self) -> "_CountedLines":
        return self

    def __next__(self) -> str:
        line = next(self._lines)
        self.count += 1
        return line


def _unreadable_csv(label: str, line: int, exc: csv.Error) -> ScanInputError:
    """v1.2 D3-R2: a CSV the csv module cannot read — a field over its
    131072-character limit (far under the 1 MiB cap), a bare CR inside an
    unquoted field — is refused BY NAME (422 / exit 2), never a 500 or a
    traceback. ``csv.Error`` messages carry no field content ("field larger
    than field limit (131072)"), so the message is safe to return."""
    return ScanInputError(f"{label} line {line}: unreadable CSV ({exc})")


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
    """CSV columns (header required): account,type[,owner][,notes] — extras ignored.

    Raises ScanInputError (by line) on a CSV the csv module cannot read."""
    lines = _CountedLines(csv_text)
    reader = csv.DictReader(lines)
    try:
        parsed = [row for row in reader]
    except csv.Error as exc:
        raise _unreadable_csv("accounts_csv", lines.count, exc) from None
    candidates, scanned = [], 0
    for row in parsed:
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


# --- v1.2 D3: API-key inventory ---------------------------------------------

#: Columns an API-key inventory must carry (header required; values may be
#: blank). ``last_used_by`` is OPTIONAL: the spec's ``last_used`` is a
#: timestamp, so "last used by an unknown principal" needs its own column.
API_KEY_COLUMNS = ("key_name", "owner", "service", "created", "last_used")

REASON_UNOWNED = "unowned API key"
REASON_OWNER = "owner is not a registered agent's owner"
REASON_LAST_USED_BY = "last used by unknown principal"


def _spaced_comma_lines(csv_text: str, label: str) -> set[int]:
    """Line numbers of DATA rows where an unquoted comma is followed by
    whitespace and a value — an unquoted ``Name, Org`` read as two fields.

    The same rule, and the same two-reader method, as lifecycle-manager's
    ``_lines_with_a_space_after_an_unquoted_comma`` (the registry does not
    depend on lifecycle-manager, so it is restated, not imported): a plain
    reader and a ``skipinitialspace`` reader disagree only on such a value.
    Every non-newline blank is mapped to a space first, because
    ``skipinitialspace`` skips U+0020 alone.

    The ``skipinitialspace`` reader CAN raise ``csv.Error`` on text the plain
    reader accepted: ``k, "a`` opens a quoted field for it, not for the plain
    reader, and that field runs on to the end of the text, past the csv
    field limit. That is refused by name too (D3-R2)."""
    blanked = "".join(" " if ch.isspace() and ch not in "\r\n" else ch
                      for ch in csv_text)
    counted = _CountedLines(blanked)
    plain = csv.reader(counted)
    skipping = csv.reader(io.StringIO(blanked), skipinitialspace=True)
    lines: set[int] = set()
    try:
        for number, (row, skipped) in enumerate(zip(plain, skipping)):
            if number and any(a != b and a.strip() for a, b in zip(row, skipped)):
                lines.add(plain.line_num)
    except csv.Error as exc:
        raise _unreadable_csv(label, counted.count, exc) from None
    return lines


def _csv_rows(
    csv_text: str, label: str
) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    """(normalised header, [(line, row)]) — a row with more fields than the
    header, an unquoted ``Name, Org``, or a CSV the csv module cannot read is
    refused BY NAME, never half-read. ``line`` is the row's last physical line."""
    check_size(csv_text, label)
    text = csv_text.lstrip("\ufeff")  # an Excel export's BOM is not a header
    counted = _CountedLines(text)
    reader = csv.DictReader(counted)
    rows: list[tuple[int, dict[str, str]]] = []
    try:
        header = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
        for row in reader:
            if None in row:
                raise ScanInputError(
                    f"{label} line {reader.line_num}: more fields than the header "
                    "(quote any value that contains a comma)"
                )
            rows.append((reader.line_num,
                         {(k or "").strip().lower(): (v or "").strip()
                          for k, v in row.items()}))
    except csv.Error as exc:
        raise _unreadable_csv(label, counted.count, exc) from None
    spaced = _spaced_comma_lines(text, label)
    if spaced:
        raise ScanInputError(
            f"{label} line {min(spaced)}: a value starts with whitespace after an "
            "unquoted comma — an unquoted `Name, Org` read as two values (quote it)"
        )
    return header, rows


def parse_principals(csv_text: str) -> set[str]:
    """``owners.csv`` (lifecycle-manager's roster format): an ``owner`` column
    (``name`` when ``owner`` is blank) and an OPTIONAL ``;``-separated
    ``aliases`` column. Every string lower-cased after strip; blank aliases
    dropped; a row with no owner is ignored WITH its aliases.

    A header with neither ``owner`` nor ``name`` is refused (D3-R4): it would
    otherwise widen nothing while the caller believes it widened the scan."""
    header, rows = _csv_rows(csv_text, "principals_csv")
    if "owner" not in header and "name" not in header:
        raise ScanInputError(
            "principals_csv header has no owner (or name) column (expected "
            "owners.csv: owner[,aliases])"
        )
    known: set[str] = set()
    for _line, row in rows:
        owner = row.get("owner") or row.get("name") or ""
        if not owner:
            continue
        known.add(owner.lower())
        known.update(a.strip().lower() for a in row.get("aliases", "").split(";")
                     if a.strip())
    return known


def scan_api_keys(
    csv_text: str,
    registered: list[AgentRecord],
    known_principals: set[str] | None = None,
) -> tuple[list[ShadowCandidate], int]:
    """CSV ``key_name,owner,service,created,last_used[,last_used_by]`` (header
    required, extras ignored) -> (candidates, keys scanned).

    One candidate per surfaced key; ``reason`` names every rule it broke, in
    this order:

    * blank owner -> ``unowned API key``;
    * owner not a registered agent's owner -> ``owner is not a registered
      agent's owner``. Matching is lifecycle-manager's roster rule:
      case-insensitive and exact after strip — no substring, no identity
      resolution. It applies EVEN WHEN ``key_name`` looks like a registered
      agent: a key named after the invoicing agent but owned by someone who
      owns no agent is exactly the shadow credential this exists to find;
    * ``last_used_by`` set and not an owner, agent id or agent name ->
      ``last used by unknown principal``.

    A key whose owner matches and whose ``last_used_by`` is blank or known is
    not surfaced. ``known_principals`` (lower-cased, e.g. from
    :func:`parse_principals`) widens BOTH known sets — IAM exports carry
    emails where the registry carries names, so without it expect false
    positives."""
    header, rows = _csv_rows(csv_text, "api_keys_csv")
    missing = [c for c in API_KEY_COLUMNS if c not in header]
    if missing:
        raise ScanInputError(
            f"api_keys_csv header is missing {', '.join(missing)} (expected "
            f"{','.join(API_KEY_COLUMNS)}[,last_used_by])"
        )
    widen = {p.strip().lower() for p in (known_principals or set()) if p.strip()}
    owners = {r.owner.strip().lower() for r in registered} | widen
    principals = owners | {
        s.strip().lower() for r in registered for s in (r.agent_id, r.name)
    }
    candidates, scanned = [], 0
    for line, row in rows:
        key_name = row.get("key_name", "")
        if not key_name:
            # D3-R3: a row that carries ANY value but no key_name is refused by
            # line — dropping it made an inventory whose identifiers sit in
            # another column (``key_id``) a 200 that scanned nothing. A row of
            # only blank values is not a key and is skipped uncounted.
            if any(row.values()):
                raise ScanInputError(
                    f"api_keys_csv line {line}: key_name is blank — every key "
                    "needs a name (is the identifier in a differently named "
                    "column?)"
                )
            continue
        scanned += 1
        owner = row.get("owner", "")
        last_used_by = row.get("last_used_by", "")
        reasons = []
        if not owner:
            reasons.append(REASON_UNOWNED)
        elif owner.lower() not in owners:
            reasons.append(REASON_OWNER)
        if last_used_by and last_used_by.lower() not in principals:
            reasons.append(REASON_LAST_USED_BY)
        if not reasons:
            continue
        candidates.append(
            ShadowCandidate(
                source="api-keys",
                identifier=key_name,
                display_name=key_name,
                reason="; ".join(reasons),
                evidence={
                    "owner": owner,
                    "service": row.get("service", ""),
                    "created": row.get("created", ""),
                    "last_used": row.get("last_used", ""),
                    "last_used_by": last_used_by,
                },
            )
        )
    return candidates, scanned


def scan_secrets_text(text: str, include_very_broad: bool = False) -> list[SecretHit]:
    """Credential-shaped strings in ``text`` (at most 1 MiB), in text order,
    each REDACTED by the model that carries it. The very-broad
    ``api_key|secret|token = value`` pattern is OFF unless asked for."""
    check_size(text, "secrets_text")
    return [
        SecretHit(pattern=hit.pattern, breadth=hit.breadth, value=hit.value,
                  line=text.count("\n", 0, hit.start) + 1)
        for hit in find_secrets(text, include_very_broad=include_very_broad)
    ]


def discover(
    registered: list[AgentRecord],
    n8n_export: dict[str, Any] | list[dict[str, Any]] | None = None,
    accounts_csv: str | None = None,
    api_keys_csv: str | None = None,
    secrets_text: str | None = None,
    principals_csv: str | None = None,
    include_very_broad: bool = False,
) -> DiscoveryReport:
    """Raises ScanInputError on a malformed or oversized D3 input (the API maps it
    to 422, the CLI to exit 2) — a scan that could not read its input must
    never look like a scan that found nothing."""
    known = parse_principals(principals_csv) if principals_csv is not None else None
    key_candidates: list[ShadowCandidate] = []
    keys_scanned = 0
    if api_keys_csv is not None:
        key_candidates, keys_scanned = scan_api_keys(api_keys_csv, registered, known)
    secret_hits: list[SecretHit] = []
    if secrets_text is not None:
        secret_hits = scan_secrets_text(secrets_text, include_very_broad)

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
        candidates=n8n_candidates + account_candidates + key_candidates,
        scanned_api_keys=keys_scanned,
        scanned_secret_hits=len(secret_hits),
        secret_hits=secret_hits,
    )


def load_n8n_file(path: str) -> dict[str, Any] | list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
