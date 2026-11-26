"""FastAPI surface for ops-console.

Design rule: the console is a CLIENT, not an authority. Every mutation
proxies through the service that owns it (kill-switch, delegation-authority,
spend-governor), so every action lands on the sealed ledger exactly as if a
CLI operator had done it. The console adds zero new power — it only makes
existing power visible and reachable.

Aggregation follows the attestation-reporter rule: an unreachable service
renders as unavailable, never as a fabricated empty state.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import hashlib
import io
import json
import logging
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from field_core import operator_auth, operator_health
from field_core.startup import warn_open
from field_core.authn import HEADER as AUTH_HEADER, install as install_authn, shared_secret
from field_core.http import get_retrying_once, pooled_limits
from field_core.http_errors import install_validation_handler
from field_core.ids import REGISTRY_ID_MAX_LENGTH, REGISTRY_ID_PATTERN, registry_id_ok
from field_core.buildinfo import build_sha
from field_core.clients import (
    CallerSigner,
    LedgerUnreachableError,
    ManifestResolver,
    signed_append_body,
)
from ops_console import __version__

#: Phase G C-14: the console never holds an operator identity of its own. Any
#: of these set (non-blank) in its environment and it refuses to start; its
#: upstream clients carry ``x-field-auth`` only, and a human action carries the
#: signed-in human's pair, forwarded per request (``_operator_kw``).
OWN_IDENTITY_ENV = (operator_auth.ENV_OPERATOR, operator_auth.ENV_OPERATOR_KEY,
                    "FIELD_OPERATOR_KEY_FILE")


class ConsoleIdentityRefused(RuntimeError):
    """The console was started with an operator identity of its own."""


def own_identity_vars(env=None) -> list[str]:
    """Names (never values) of the OWN_IDENTITY_ENV variables set non-blank."""
    env = os.environ if env is None else env
    return [n for n in OWN_IDENTITY_ENV if (env.get(n) or "").strip()]


def refuse_own_identity(env=None) -> None:
    """Raise ConsoleIdentityRefused when the console has an identity of its own.
    The message names the variables only, never their values."""
    names = own_identity_vars(env)
    if names:
        raise ConsoleIdentityRefused(
            f"ops-console refuses to start: {', '.join(names)} set in its environment. "
            "The console never acts under an operator identity of its own; a human "
            "action carries the signed-in human's headers. Unset them.")


def _console_headers() -> dict[str, str]:
    """``x-field-auth`` only (when FIELD_SHARED_SECRET is set): never an
    operator pair, whatever the environment holds (C-14)."""
    secret = shared_secret()
    return {AUTH_HEADER: secret} if secret else {}


def _seg(value: str) -> str:
    """One URL path segment from a caller-chosen id (C-554, reviewer C-523 F-C523-1): every reserved character is
    percent-encoded (an encoded ``?``, ``#`` or ``/`` stays inside the segment) and a pure-dot segment is encoded too,
    so ``..`` can never collapse the upstream path."""
    seg = quote(value, safe="")
    return seg.replace(".", "%2E") if seg and set(seg) == {"."} else seg   # "." and ".." (httpx drops a "." segment)


def _http_status(status: int) -> int:
    """The status the console answers with for a failed upstream call: 0 (unreachable) and a 1xx-3xx (a redirect is
    never followed and has no meaning to the page) are a 502 (C-936 F-C936-6a)."""
    return status if status >= 400 else 502


def _relay(status: int, data: Any, refusals: bool = True) -> Any:
    """What a failed upstream call shows the caller (C-554, F-C523-3): a 4xx body is the refusal the operator needs and
    is relayed; a 5xx body is a fixed text, because the body of a failing service can carry a traceback or an
    environment line. An unreachable upstream (status 0) shows the class name of the failure and nothing else (C-504:
    the exception text of a transport error can carry a URL, a proxy or an address). The 5xx body is not logged at any level (C-936 F-C936-2: the status only)."""
    if status == 0 or (refusals and 400 <= status < 500):
        return data
    if status < 500:
        # C-763 F-C763-1: a READ shows no 4xx body (a validation error can echo what the caller sent); only the
        # status and a fixed text. The write routes keep ``refusals=True``: the refusal text is what the operator acts on.
        return {"message": "upstream refused", "status": status}
    logging.getLogger("ops_console").info("upstream answered %s (body not logged)", status)
    return {"message": "upstream error", "status": status}


def _error_text(status: int, data: Any) -> str:
    """The same rule as ``_relay`` for a section or message string (C-651 F-C651-1): ``status N: <4xx body>``,
    ``status N: upstream error`` for a 5xx, the failure's class name for an unreachable upstream (status 0)."""
    shown = _relay(status, data, refusals=False)
    if status == 0:
        return str(shown)
    return f"status {status}: {shown['message']}"


#: What the page reads of a failed drill (console.html ``drillReportOf``): numbers, a boolean and a short status. The
#: report's free-text ``note`` and ``endpoint_result`` are not relayed (C-651 F-C651-3).
DRILL_REPORT_FIELDS = ("agent_id", "kill_confirmed_ms", "heartbeat_confirmed_ms", "restored", "restored_status", "restore_skipped", "total_ms")


def _drill_report_only(status: int, data: Any) -> Any:
    """A failed drill's answer: only the report fields above (still nested as ``{"detail": report}``, which the page
    unwraps), anything else through ``_relay``."""
    rep = data.get("detail") if isinstance(data, dict) else None
    if isinstance(rep, dict) and "restored" in rep and rep.get("total_ms") is not None:
        out = {k: rep[k] for k in DRILL_REPORT_FIELDS if k in rep}
        if isinstance(out.get("restored_status"), str):
            out["restored_status"] = out["restored_status"][:64]
        return {"detail": out}
    return _relay(status, data)


def _decode(resp) -> tuple[int, Any]:
    """An upstream answer as ``(status, body)``. A non-JSON answer keeps its HTTP status (C-644 F-C644-3): a 2xx that
    is not JSON is still an error here (status 0 and the parse error's class name); any other status gets a fixed
    body, so an HTML error page from a proxy is neither relayed nor mistaken for an unreachable upstream."""
    try:
        return resp.status_code, resp.json()
    except ValueError as exc:
        if 200 <= resp.status_code < 300:
            return 0, type(exc).__name__
        return resp.status_code, {"detail": "non-JSON answer"}


class ServiceClient:
    """Thin httpx-compatible wrapper with graceful failure. A client built
    here carries ``x-field-auth`` only, never an operator identity (C-14)."""

    def __init__(self, client=None, base_url: str | None = None,
                 env: str = "", default: str = ""):
        self._client = client
        self.base = (base_url or os.environ.get(env, default)).rstrip("/")
        if self._client is None:
            import httpx

            # B16: idle connections expire before the upstream's keep-alive closes them
            self._client = httpx.Client(
                base_url=self.base, timeout=10.0, headers=_console_headers(), limits=pooled_limits()
            )

    def get(self, path: str, **kw) -> tuple[int, Any]:
        try:
            return _decode(get_retrying_once(self._client, path, **kw))   # B16: once more on a dead connection
        except Exception as exc:
            return 0, type(exc).__name__

    def post(self, path: str, **kw) -> tuple[int, Any]:
        try:
            return _decode(self._client.post(path, **kw))
        except Exception as exc:
            return 0, type(exc).__name__


#: the most per-agent usage rows one overview carries (S5-20)
MAX_USAGE_ROWS = 200


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    source: str
    data: Any = None
    error: str | None = None


class Overview(BaseModel):
    generated_at: str
    agents: Section
    tokens: Section
    escalations: Section
    ledger_verify: Section
    recent_events: Section
    token_usage: Section


#: The kill-switch's own bounds for the same two fields (its KillRequest: operator at most 200, reason at most 1000), so a bad
#: value is one 422 here and not one refusal per agent or domain upstream (S9-31). ``resolved_by`` uses the operator bound.
MAX_OPERATOR_CHARS = 200
MAX_REASON_CHARS = 1000


class OperatorAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: str = Field(min_length=1, max_length=MAX_OPERATOR_CHARS, description="Human operator — recorded")
    reason: str = Field(default="via ops-console", min_length=1, max_length=MAX_REASON_CHARS)


class ResolveAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_by: str = Field(min_length=1, max_length=MAX_OPERATOR_CHARS)


#: The registry's agent id grammar (agent_registry/models.py), the only ids a bulk action may name.
AGENT_ID_RE = re.compile(REGISTRY_ID_PATTERN)


class BulkAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["kill", "drill", "revive"]
    agent_ids: list[str] = Field(min_length=1, max_length=100)
    operator: str = Field(min_length=1, max_length=MAX_OPERATOR_CHARS, description="Human operator — recorded")
    reason: str = Field(default="via ops-console (bulk)", min_length=1, max_length=MAX_REASON_CHARS)

    @field_validator("agent_ids")
    @classmethod
    def _registry_ids_only(cls, ids: list[str]) -> list[str]:
        # C-936 F-C936-1: the upstream decodes an encoded "/", so the id ``domain/x`` would reach the whole-domain
        # kill route. Only an id the registry can hold (its own grammar) is forwarded; this also refuses "".
        bad = [i for i in ids if not AGENT_ID_RE.fullmatch(i)]
        if bad:
            raise ValueError("agent_ids must match " + AGENT_ID_RE.pattern)
        return ids


class FleetHalt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: str = Field(min_length=1, max_length=MAX_OPERATOR_CHARS, description="Human operator — recorded")
    reason: str = Field(min_length=1, max_length=MAX_REASON_CHARS)
    confirm: Literal["HALT"] = Field(
        description="Must be the literal word HALT — a typed confirmation")
    domains: list[str] | None = Field(
        default=None, max_length=100,
        description="Default: every domain with a non-retired agent")

    @field_validator("domains")
    @classmethod
    def _no_slash_or_empty(cls, domains: list[str] | None) -> list[str] | None:
        # C-936 F-C936-1: a domain is free text in the registry, but never "" and never a "/" (decoded upstream).
        if domains is not None and any(not d or "/" in d for d in domains):
            raise ValueError("a domain must be non-empty and contain no '/'")
        # S3-19: one kill-switch POST per domain, so each string is bounded, and text that cannot be encoded
        # (a lone surrogate) is refused here as a 422 instead of raising in _seg().
        if domains is not None and any(len(d) > 128 for d in domains):
            raise ValueError("a domain must be at most 128 characters")
        if domains is not None:
            for d in domains:
                try:
                    d.encode("utf-8")
                except UnicodeEncodeError:
                    raise ValueError("a domain must be valid text") from None
        return domains


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # B-S11-31: bounded here because the sentinel does not bound them and the verdict lands on the ledger.
    agent_id: str = Field(min_length=1, max_length=REGISTRY_ID_MAX_LENGTH)
    action: str = Field(min_length=1, max_length=500)
    token_id: str | None = Field(default=None, min_length=1, max_length=200)
    irreversible: bool = False

    @field_validator("agent_id")
    @classmethod
    def _registry_id_only(cls, v: str) -> str:
        if not AGENT_ID_RE.fullmatch(v):
            raise ValueError("agent_id must match " + AGENT_ID_RE.pattern)
        return v

    @field_validator("action", mode="before")
    @classmethod
    def _strip_action(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("action", "token_id")
    @classmethod
    def _one_line(cls, v: str | None) -> str | None:
        # C0, DEL and C1 controls (Cc, NEL U+0085 included) and the line / paragraph separators (Zl U+2028, Zp U+2029):
        # none can forge a ledger record, but each can start a new line in a viewer or a terminal (reviewer C1 on #1246)
        if v is not None and (not v or any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in v)):
            raise ValueError("must be one line with no control characters")
        return v


#: Manifest viewer guard. The console reads a file named by a registrant-set
#: ``manifest_ref`` from a volume it shares with signing keys, so it serves
#: ONLY manifest-shaped files that really live under FIELD_MANIFEST_DIR.
MANIFEST_SUFFIXES = (".yaml", ".yml", ".json")
MANIFEST_MAX_BYTES = 256 * 1024

#: The twelve governance services, in Caddy prefix order (status strip).
PLATFORM_SERVICES = ("registry", "ledger", "delegation", "sentinel",
                     "killswitch", "governor", "replay", "crosswalk",
                     "gateway", "federation", "lifecycle", "attest")


class ManifestRefused(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


def guarded_manifest_path(manifest_dir: str | Path | None,
                          manifest_ref: str) -> Path:
    """Resolve ``manifest_ref`` to a readable manifest file or refuse.

    Refuses (403) when the manifest dir is not configured, when the real path
    (symlinks followed) escapes it, when the suffix is not a manifest suffix,
    or when the file is over MANIFEST_MAX_BYTES; 404 when nothing is there.
    """
    if not manifest_dir:
        raise ManifestRefused(403, "FIELD_MANIFEST_DIR is not configured")
    if not isinstance(manifest_ref, str):
        raise ManifestRefused(403, "manifest_ref is not text")
    try:
        base = Path(manifest_dir).resolve(strict=True)
    except (OSError, ValueError, RuntimeError):  # RuntimeError: a symlink loop on Python 3.12
        raise ManifestRefused(404, "manifest directory does not exist")
    path = Path(manifest_ref)
    if not path.is_absolute():
        path = base / path
    outside = ManifestRefused(403, "manifest_ref resolves outside FIELD_MANIFEST_DIR")
    # Containment BEFORE existence: answering 404 for an absent outside path
    # but 403 for a present one would be a file-existence oracle.
    try:
        if not path.resolve(strict=False).is_relative_to(base):
            raise outside
        real = path.resolve(strict=True)
    except (OSError, ValueError, RuntimeError):  # RuntimeError: a symlink loop on Python 3.12
        raise ManifestRefused(404, "no manifest file at that ref")
    if not real.is_relative_to(base):  # a symlink inside pointing out
        raise outside
    if real.suffix.lower() not in MANIFEST_SUFFIXES or not real.is_file():
        raise ManifestRefused(403, "not a manifest file (.yaml/.yml/.json)")
    if real.stat().st_size > MANIFEST_MAX_BYTES:
        raise ManifestRefused(403, f"manifest larger than {MANIFEST_MAX_BYTES} bytes")
    return real


# A spreadsheet evaluates a cell that starts with one of these (C-200 F-C200-1,
# OWASP "CSV injection"): the CSV export prefixes a single quote.
CSV_FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")


def _csv_cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(CSV_FORMULA_LEADS):
        return "'" + value
    return value


#: Per-agent outcomes of a kill-switch domain kill (its DomainAgentResult.outcome).
DOMAIN_OUTCOMES = ("killed", "already_killed", "skipped_retired", "error")
#: Errored agents listed per domain in a fleet-halt answer (the count is exact).
MAX_LISTED_ERRORS = 50
#: C-19 EXCEPTION to "no upstream 5xx body is shown" (C-936 F-C936-3): a fleet-halt row lists, per errored agent, the
#: kill-switch's own one-line error text (``502: <detail>``), because the operator must know which agents were not
#: stopped and why. It is the kill-switch's text, not a raw body, and it is cut to this many characters.
MAX_ERROR_TEXT = 200


#: the most skipped registry rows one fleet-halt answer (and its ledger row) lists
MAX_LISTED_SKIPPED = 50

#: The registry's write rule for a NEW domain (agent_registry.models._NEW_DOMAIN, backlog B80). Copied, not imported: the
#: console does not depend on the registry package. tests/test_fleet_halt_uncovered_b80.py pins that the two are equal.
REGISTRY_DOMAIN_RE = re.compile(r"[A-Za-z0-9]+(?:[ ._-][A-Za-z0-9]+)*")


def _named_halt_uncovered(registry: Any, results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """B80: the agents a fleet halt that NAMED its domains cannot have reached. The registry's domain filter folds ASCII
    case and trims spaces only, so a stored row whose domain is outside the registry's write rule (a look-alike such as
    "fin" + zero-width space + "ance", written before the rule existed) is in no named domain's listing: the halt never
    touches it, and the completeness check, built from that same listing, cannot see it. The registry is read ONCE, after
    every kill was sent (it never delays one). Returned: each active row whose domain is outside the rule and whose id no
    domain report confirmed, by id only (never the domain text; an unusable id is None), and whether the read worked. A
    failed read cannot show the halt complete. Nothing is killed here: the operator named the domains; the fallback is a
    halt by id or a fleet halt naming no domain."""
    reached: set[str] = set()
    for r in results:
        try:
            reached |= _result_ids(r.get("result", r.get("error"))) or set()
        except Exception:  # noqa: BLE001 - an odd report confirms nothing
            pass
    try:
        status, rows = registry.get("/agents")
    except Exception:  # noqa: BLE001 - the halt already happened; the check just cannot be made
        return [], False
    if status != 200 or not isinstance(rows, list):
        return [], False
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("status") in ("retired", "killed"):
            continue
        d = row["domain"] if row.get("domain") is not None else "general"
        # strip(" ") exactly as the registry filter's SQLite trim() (U+0020 only): str.strip() would also drop a TAB, a LF or a
        # no-break space, judge "finance" + NBSP conforming, and leave out the very row the listing for "finance" missed
        if isinstance(d, str) and REGISTRY_DOMAIN_RE.fullmatch(d.strip(" ")):
            continue
        aid = row.get("agent_id")
        aid = aid if registry_id_ok(aid) else None
        if aid is not None and aid in reached:
            continue
        out.append({"agent_id": aid, "reason": "domain is outside the registry rule: no named halt reaches it"})
    return out, True


def _result_ids(data: Any) -> set[str] | None:
    """The agent ids a kill-switch domain report CONFIRMS as halted (outcome killed or already_killed), in the body or in
    a non-2xx answer's ``detail``; None when there is no ``results`` list."""
    for cand in (data, data.get("detail") if isinstance(data, dict) else None):
        if isinstance(cand, dict) and isinstance(cand.get("results"), list):
            return {r["agent_id"] for r in cand["results"]
                    if isinstance(r, dict) and isinstance(r.get("agent_id"), str)
                    and r.get("outcome") in ("killed", "already_killed")}
    return None


def _domain_outcomes(data: Any) -> tuple[dict[str, int] | None, list[dict]]:
    """C-19: (counts per outcome, errored agents) from a kill-switch domain-kill
    answer. The per-agent ``results`` are read from the body, or from its
    ``detail`` when a non-2xx answer carries the report there. (None, []) when
    no per-agent results are present. An outcome this console does not know
    counts as an error, never as a success."""
    report = None
    for cand in (data, data.get("detail") if isinstance(data, dict) else None):
        if isinstance(cand, dict) and isinstance(cand.get("results"), list):
            report = cand
            break
    if report is None:
        return None, []
    counts = dict.fromkeys(DOMAIN_OUTCOMES, 0)
    errors: list[dict] = []
    for r in report["results"]:
        outcome = r.get("outcome") if isinstance(r, dict) else None
        # isinstance first: `in counts` hashes the outcome, and a list or an object is unhashable (TypeError), which
        # used to stop the whole fleet halt at this domain
        if isinstance(outcome, str) and outcome in counts and outcome != "error":
            counts[outcome] += 1
            continue
        counts["error"] += 1
        if len(errors) < MAX_LISTED_ERRORS:
            r = r if isinstance(r, dict) else {}
            fallback = f"outcome {outcome!r}" if isinstance(outcome, str) or outcome is None else "outcome is not a string"
            errors.append({"agent_id": r.get("agent_id"),
                           "error": str(r.get("error") or fallback)[:MAX_ERROR_TEXT]})
    return counts, errors


def _drill_not_restored(data: Any) -> str | None:
    """C-19: why a drill answer is a failure although it came back 2xx (the
    agent was not restored), or None when ``restored`` is true."""
    if (isinstance(data, dict) and data.get("restored") is True
            and data.get("restore_skipped", False) is False         # absent or exactly False: "true", 1, null contradict
            and data.get("ok", True) is not False and "error" not in data
            and data.get("restored_status") == "active"):           # an allowlist: only the status a drill restores to
        return None                      # restored=True is only believed when nothing in the report contradicts it
    d = data if isinstance(data, dict) else {}
    return (f"drill did not restore the agent (restored={d.get('restored')}, "
            f"restored_status={d.get('restored_status')})")


def _overview_digest(overview: dict) -> str:
    """Change detector for the stream: everything except the timestamp."""
    body = {k: v for k, v in overview.items() if k != "generated_at"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def _page() -> str:
    root = resources.files("ops_console") / "static"
    return Path(str(root / "console.html")).read_text(encoding="utf-8")


def _max_streams_from_env() -> int:
    """FIELD_CONSOLE_MAX_STREAMS, default 8. A non-integer or negative value
    refuses to start with a fixed message naming only the variable: the
    value is operator input and is never echoed (no ``from`` chain either)."""
    raw = os.environ.get("FIELD_CONSOLE_MAX_STREAMS", "8")
    try:
        value = int(raw)
    except ValueError:
        value = -1
    if value < 0:
        raise ValueError(
            "FIELD_CONSOLE_MAX_STREAMS must be a non-negative integer") from None
    return value


def create_app(
    registry: ServiceClient | None = None,
    ledger: ServiceClient | None = None,
    delegation: ServiceClient | None = None,
    governor: ServiceClient | None = None,
    killswitch: ServiceClient | None = None,
    sentinel: ServiceClient | None = None,
    lifecycle: ServiceClient | None = None,
    attest: ServiceClient | None = None,
    crosswalk: ServiceClient | None = None,
    federation: ServiceClient | None = None,
    replay: ServiceClient | None = None,
    gateway: ServiceClient | None = None,
    manifest_dir: str | Path | None = None,
    stream_interval: float = 2.0,
    stream_keepalive: float = 15.0,
    max_streams: int | None = None,
) -> FastAPI:
    @contextlib.asynccontextmanager
    async def _lifespan(_app: FastAPI):
        # C-14: an ASGI server serving this app (``console serve``, or uvicorn
        # directly) fails startup when the console has an identity of its own.
        refuse_own_identity()
        yield

    app = FastAPI(
        title="ops-console",
        version=__version__,
        description="Dashboard over every governed agent (client, not authority).",
        lifespan=_lifespan,
    )
    # The HTML shell holds no data; /api/* requires the secret when set.
    install_authn(app, open_paths={"/"})
    install_validation_handler(app)
    if operator_auth.operator_headers() and operator_auth.mode() != operator_auth.ENFORCE:
        # The console forwards the HUMAN's headers; its own FIELD_OPERATOR is
        # never used for a human action. Setting it without REQUIRE is a
        # config that suggests otherwise.
        logging.getLogger("ops_console").warning(
            "FIELD_OPERATOR is set on the ops-console but FIELD_OPERATOR_REQUIRE is not: "
            "the console never acts under its own identity for a human action; unset it")

    app.state.registry = registry or ServiceClient(
        env="FIELD_REGISTRY_URL", default="http://127.0.0.1:8001")
    app.state.ledger = ledger or ServiceClient(
        env="FIELD_LEDGER_URL", default="http://127.0.0.1:8002")
    app.state.delegation = delegation or ServiceClient(
        env="FIELD_DELEGATION_URL", default="http://127.0.0.1:8003")
    app.state.governor = governor or ServiceClient(
        env="FIELD_GOVERNOR_URL", default="http://127.0.0.1:8006")
    app.state.killswitch = killswitch or ServiceClient(
        env="FIELD_KILLSWITCH_URL", default="http://127.0.0.1:8005")
    app.state.sentinel = sentinel or ServiceClient(
        env="FIELD_SENTINEL_URL", default="http://127.0.0.1:8004")
    app.state.replay = replay or ServiceClient(
        env="FIELD_REPLAY_URL", default="http://127.0.0.1:8007")
    app.state.crosswalk = crosswalk or ServiceClient(
        env="FIELD_CROSSWALK_URL", default="http://127.0.0.1:8008")
    app.state.gateway = gateway or ServiceClient(
        env="FIELD_GATEWAY_URL", default="http://127.0.0.1:8009")
    app.state.federation = federation or ServiceClient(
        env="FIELD_FEDERATION_URL", default="http://127.0.0.1:8010")
    app.state.lifecycle = lifecycle or ServiceClient(
        env="FIELD_LIFECYCLE_URL", default="http://127.0.0.1:8012")
    app.state.attest = attest or ServiceClient(
        env="FIELD_ATTEST_URL", default="http://127.0.0.1:8013")
    # No "." default: an unset dir means the viewer refuses, never that it
    # reads relative to wherever the console happened to start.
    app.state.manifest_dir = (manifest_dir if manifest_dir is not None
                              else os.environ.get("FIELD_MANIFEST_DIR") or None)
    app.state.max_streams = (max_streams if max_streams is not None
                             else _max_streams_from_env())
    app.state.open_streams = 0

    def _section(client: ServiceClient, path: str, label: str,
                 **kw) -> Section:
        status, data = client.get(path, **kw)
        if status == 200:
            return Section(available=True, source=f"GET {path}",
                           data=data)
        return Section(available=False, source=f"GET {path}",
                       error=_error_text(status, data))

    # F2b: the console's caller key (FIELD_LEDGER_CALLER_ID / _KEY, GB10:
    # ``console``), loaded once here. Its operator.refused records are signed
    # exactly like every other service's appends (signed_append_body): a
    # ledger with FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1 refuses an unsigned
    # operator.* record (it is not a stop type).
    refusal_signer = CallerSigner.from_env()

    class _RefusalLedger:
        """C-16: operator.refused over the console's own ledger client, which
        carries x-field-auth only (C-14); the ledger stores it self_reported."""

        def __init__(self, client: ServiceClient):
            self.client = client

        def append(self, event_type: str, payload: dict, agent_id: str | None = None) -> None:
            body = {"event_type": event_type, "payload": payload, "agent_id": agent_id}
            if refusal_signer is not None:
                raw = getattr(self.client, "_client", None)
                sent = dict(getattr(raw, "headers", None) or {})
                body = signed_append_body(refusal_signer, event_type, payload, agent_id, sent)
            status, _ = self.client.post("/events", json=body)
            if status != 201:
                raise LedgerUnreachableError(f"ledger append returned {status}",
                                             status_code=status or None)

    op_health = operator_health.install(
        app, ledger_getter=lambda a: _RefusalLedger(a.state.ledger))

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "ops-console", "version": __version__,
                "build_sha": build_sha(), **op_health.health_fields()}

    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return _page()

    def _token_usage_section(agents_section: Section) -> Section:
        """Per-agent token usage + cost + rogue flags, from the governor."""
        gov = app.state.governor
        source = "GET /usage/{agent_id} (per registered agent)"
        if not agents_section.available or not isinstance(agents_section.data, list):
            # C-936 F-C936-6d: a 200 that is not a list is "unavailable", not a TypeError (a 500 from /api/overview).
            return Section(available=False, source=source,
                           error="agents unavailable")
        rows = []
        unreadable = 0
        capped = False
        for agent in agents_section.data:
            agent_id = agent.get("agent_id") if isinstance(agent, dict) else None
            if not isinstance(agent_id, str) or not agent_id:
                continue
            # C-936 F-C936-6c: a registry-supplied id is one path segment, whatever it holds.
            status, data = gov.get(f"/usage/{_seg(agent_id)}")
            if status != 200:
                continue
            if not isinstance(data, dict):
                # S5-20: a 200 that is not an object (a list, a string, a number, null) is no usage row and no 500;
                # it is counted so the section says so instead of showing the agent as idle
                unreadable += 1
                continue
            if (data.get("total_input_tokens") or data.get("total_output_tokens")
                    or data.get("open_rogue_flags")):
                if len(rows) >= MAX_USAGE_ROWS:
                    capped = True
                    break
                rows.append(data)
        notes = []
        if unreadable:
            notes.append(f"{unreadable} agent usage answer(s) were not readable and are not shown")
        if capped:
            notes.append(f"only the first {MAX_USAGE_ROWS} agents with usage are shown")
        return Section(available=True, source=source, data=rows, error="; ".join(notes) or None)

    def _build_overview() -> Overview:
        agents = _section(app.state.registry, "/agents", "agents")
        return Overview(
            generated_at=datetime.now(timezone.utc).isoformat(),
            agents=agents,
            tokens=_section(app.state.delegation, "/tokens", "tokens"),
            escalations=_section(app.state.governor, "/escalations", "escalations"),
            ledger_verify=_section(app.state.ledger, "/verify", "verify"),
            recent_events=_section(
                app.state.ledger, "/events", "events", params={"limit": 25}
            ),
            token_usage=_token_usage_section(agents),
        )

    @app.get("/api/overview", response_model=Overview)
    def overview() -> Overview:
        return _build_overview()

    @app.get("/api/stream")
    async def stream(request: Request,
                     frames: int | None = Query(default=None, ge=1)) -> Any:
        """Server-sent events: an ``overview`` frame on every change.

        The upstreams have no push, so this polls them every
        ``stream_interval`` seconds server-side and pushes only changes (plus
        a keep-alive comment). Behind the shared secret like every /api/*
        route: browsers read it with fetch(), which can send x-field-auth.
        ``frames`` bounds the stream (tests, diagnostics).
        """
        if app.state.open_streams >= app.state.max_streams:
            raise HTTPException(503, detail="stream limit reached — poll /api/overview")

        async def events():
            # Counted inside the generator: an unstarted generator never runs
            # its finally, so counting earlier would leak a slot per drop.
            app.state.open_streams += 1
            sent, last_digest, last_send = 0, None, time.monotonic()
            try:
                while frames is None or sent < frames:
                    if await request.is_disconnected():
                        break
                    o = (await asyncio.to_thread(_build_overview)).model_dump()
                    digest = _overview_digest(o)
                    now = time.monotonic()
                    if digest != last_digest:
                        last_digest, last_send = digest, now
                        sent += 1
                        yield f"event: overview\ndata: {json.dumps(o, default=str)}\n\n"
                    elif now - last_send >= stream_keepalive:
                        last_send = now
                        sent += 1
                        yield ": keep-alive\n\n"
                    if frames is None or sent < frames:
                        await asyncio.sleep(stream_interval)
            finally:
                app.state.open_streams -= 1

        return StreamingResponse(
            events(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---- drill to details -------------------------------------------------

    @app.get("/api/agents/{agent_id}")
    def agent_detail(agent_id: str) -> dict:
        q = _seg(agent_id)
        record = _section(app.state.registry, f"/agents/{q}", "agent")
        if not record.available and record.error and record.error.startswith("status 404"):
            raise HTTPException(404, detail=f"agent '{agent_id}' not registered")
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "agent": record,
            "heartbeat": _section(app.state.killswitch, f"/heartbeat/{q}", "hb"),
            "tokens": _section(app.state.delegation, "/tokens", "tokens",
                               params={"agent_id": agent_id}),
            "usage": _section(app.state.governor, f"/usage/{q}", "usage"),
            "events": _section(app.state.ledger, "/events", "events",
                               params={"agent_id": agent_id, "limit": 50}),
        }

    @app.get("/api/agents/{agent_id}/manifest")
    def agent_manifest(agent_id: str) -> dict:
        """Read-only view of the agent's FIELD manifest, behind the path guard."""
        status, record = app.state.registry.get(f"/agents/{_seg(agent_id)}")
        if status != 200:
            raise HTTPException(_http_status(status), detail=_relay(status, record, refusals=False))
        if not isinstance(record, dict):  # a 200 of the wrong shape: fixed text, never the body
            raise HTTPException(502, detail="registry answered an unexpected shape")
        ref = record.get("manifest_ref")
        if ref is None or (isinstance(ref, str) and not ref):
            return {"agent_id": agent_id, "ref": None, "validation": "no_ref",
                    "raw": None}
        if not isinstance(ref, str):  # the value is never echoed
            raise HTTPException(403, detail={
                "agent_id": agent_id, "ref": None, "validation": "refused",
                "reason": "manifest_ref is not text"})
        try:
            path = guarded_manifest_path(app.state.manifest_dir, ref)
        except ManifestRefused as exc:
            raise HTTPException(exc.status, detail={
                "agent_id": agent_id, "ref": ref, "validation": "refused"
                if exc.status == 403 else "missing", "reason": exc.reason})
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise HTTPException(403, detail={
                "agent_id": agent_id, "ref": ref, "validation": "refused",
                "reason": f"unreadable: {type(exc).__name__}"})
        _, validation = ManifestResolver(path.parent).resolve_detail(str(path))
        return {"agent_id": agent_id, "ref": ref, "validation": validation,
                "raw": raw}

    # ---- newer-service panels ---------------------------------------------

    @app.get("/api/platform")
    def platform() -> dict:
        """Health of all twelve services plus the read panels of the newer
        ones. Fetched in parallel; each unreachable piece is marked, alone."""
        jobs = {f"health:{name}": (getattr(app.state, name), "/health")
                for name in PLATFORM_SERVICES}
        jobs.update({
            "lifecycle": (app.state.lifecycle, "/findings"),
            "federation": (app.state.federation, "/contracts"),
            "crosswalk": (app.state.crosswalk, "/staleness"),
        })
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {k: pool.submit(c.get, p) for k, (c, p) in jobs.items()}
            raw = {k: f.result() for k, f in futures.items()}

        def sec(key: str) -> Section:
            client, path = jobs[key]
            status, data = raw[key]
            src = f"GET {path}"
            if status == 200:
                return Section(available=True, source=src, data=data)
            if key == "lifecycle" and status == 404:
                # Reachable, but no sweep has run yet: a fact, not an outage.
                return Section(available=True, source=src,
                               data={"no_sweep_yet": True})
            return Section(available=False, source=src,
                           error=_error_text(status, data))

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "health": {n: sec(f"health:{n}") for n in PLATFORM_SERVICES},
            "lifecycle": sec("lifecycle"),
            "federation": sec("federation"),
            "crosswalk": sec("crosswalk"),
            "attest": sec("health:attest"),
        }

    # ---- ledger filter + export -------------------------------------------

    def _ledger_events(agent_id, event_type, since, until, limit) -> list:
        params = {k: v for k, v in {
            "agent_id": agent_id, "event_type": event_type,
            "since": since, "until": until, "limit": limit}.items() if v}
        status, data = app.state.ledger.get("/events", params=params)
        if status != 200:
            raise HTTPException(_http_status(status), detail=_relay(status, data, refusals=False))
        if not isinstance(data, list) or not all(isinstance(e, dict) for e in data):
            # a 200 that is not a list of event dicts is a misbehaving or substituted upstream: a fixed text, never its body
            raise HTTPException(502, detail={"message": "ledger answered an unexpected shape", "status": 200})
        return data

    @app.get("/api/events")
    def events(agent_id: str | None = None, event_type: str | None = None,
               since: str | None = None, until: str | None = None,
               limit: int = Query(default=100, ge=1, le=10000)) -> list:
        return _ledger_events(agent_id, event_type, since, until, limit)

    @app.get("/api/events/export")
    def export_events(format: Literal["csv", "json"] = "csv",
                      agent_id: str | None = None, event_type: str | None = None,
                      since: str | None = None, until: str | None = None,
                      limit: int = Query(default=1000, ge=1, le=10000)) -> Response:
        """Unsigned convenience copy of matching events. The evidence bundle
        is the ledger's own POST /export; this only saves what the screen shows."""
        rows = _ledger_events(agent_id, event_type, since, until, limit)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = f"field-ledger-{stamp}.{format}"
        disposition = {"Content-Disposition": f'attachment; filename="{name}"'}
        if format == "json":
            body = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "source": "GET /events",
                "filters": {"agent_id": agent_id, "event_type": event_type,
                            "since": since, "until": until, "limit": limit},
                "count": len(rows),
                "note": "unsigned convenience export from ops-console; a "
                        "filtered subset does not verify as a chain on its own. "
                        "Evidence bundles come from the ledger's POST /export.",
                "events": rows,
            }
            return Response(json.dumps(body, indent=2), media_type="application/json",
                            headers=disposition)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["ts", "event_id", "event_type", "agent_id", "clause_id",
                    "hash", "prev_hash", "payload_json"])
        for e in rows:
            payload = e.get("payload") or {}
            clause_id = payload.get("clause_id") if isinstance(payload, dict) else None
            w.writerow([_csv_cell(c) for c in (
                e.get("ts"), e.get("event_id"), e.get("event_type"),
                e.get("agent_id") or "", clause_id or "",
                e.get("hash"), e.get("prev_hash"),
                json.dumps(payload, sort_keys=True))])
        return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers=disposition)

    def _operator_kw(request: Request) -> dict:
        """Phase G: the HUMAN's operator headers are forwarded so the
        downstream service authenticates the human, not this console's
        service identity. Under REQUIRE a missing pair is a 401 here - the
        console never falls back to its own identity for a human action."""
        # C-16: a refusal here is counted and, under ENFORCE, ledgered as
        # operator.refused; the action is the route's last path segment.
        action = request.url.path.rstrip("/").rsplit("/", 1)[-1]
        try:
            op, key = operator_auth.parse_headers(request.headers)
        except operator_auth.OperatorRefused as exc:
            raise op_health.http_refusal(exc, action=action, path=request.url.path,
                                         headers=request.headers,
                                         agent_id=request.path_params.get("agent_id")) from None
        if op and key:
            return {"headers": {operator_auth.HEADER_OPERATOR: op,
                                operator_auth.HEADER_KEY: key}}
        if operator_auth.mode() == operator_auth.ENFORCE:
            raise op_health.http_refusal(
                operator_auth.OperatorRefused(401, operator_auth.UNAUTH_DETAIL),
                action=action, path=request.url.path, headers=request.headers,
                agent_id=request.path_params.get("agent_id"))
        return {}

    def _proxy(client: ServiceClient, path: str, body: dict | None,
               ok_codes=(200, 201), failure=_relay, **kw) -> Any:
        """``failure(status, data)`` decides what a failing upstream shows: ``_relay`` (a 4xx body, a fixed text for a
        5xx, C-554) for every route but the drill, whose 500 report the page reads (C-19) and which shows only the
        report fields (C-651 F-C651-3)."""
        status, data = client.post(path, json=body, **kw)
        if status in ok_codes:
            return data
        raise HTTPException(_http_status(status), detail=failure(status, data))

    @app.post("/api/agents/{agent_id}/kill")
    def kill(agent_id: str, action: OperatorAction, request: Request) -> Any:
        return _proxy(app.state.killswitch, f"/kill/{_seg(agent_id)}",
                      action.model_dump(), **_operator_kw(request))

    @app.post("/api/agents/{agent_id}/revive")
    def revive(agent_id: str, action: OperatorAction, request: Request) -> Any:
        return _proxy(app.state.killswitch, f"/revive/{_seg(agent_id)}",
                      action.model_dump(), **_operator_kw(request))

    @app.post("/api/agents/{agent_id}/drill")
    def drill(agent_id: str, action: OperatorAction, request: Request) -> Any:
        data = _proxy(app.state.killswitch, f"/drill/{_seg(agent_id)}",
                      action.model_dump(), failure=_drill_report_only, **_operator_kw(request))
        failed = _drill_not_restored(data)
        if failed:
            # fail closed: a 2xx drill answer that does not say restored=true (an older kill-switch, a shape this
            # console does not know) is an error on the page, never a success
            raise HTTPException(502, detail=failed)
        return data

    @app.post("/api/agents/bulk")
    def bulk(req: BulkAction, request: Request) -> dict:
        """Sequential per-agent calls to the kill-switch — one ledgered action
        each, exactly as if clicked one by one. A refusal is recorded for that
        agent and the rest continue."""
        results = []
        okw = _operator_kw(request)
        for agent_id in dict.fromkeys(req.agent_ids):  # de-dupe, keep order
            status, data = app.state.killswitch.post(
                f"/{req.action}/{_seg(agent_id)}",
                json={"operator": req.operator, "reason": req.reason}, **okw)
            http_ok = status in (200, 201)
            row = {"agent_id": agent_id, "ok": http_ok, "status": status,
                   "result" if http_ok else "error": (
                       data if http_ok else
                       (_drill_report_only if req.action == "drill" else _relay)(status, data))}
            if http_ok and req.action == "drill":
                failed = _drill_not_restored(data)
                if failed:
                    # C-19: a drill that did not restore left the agent stopped;
                    # it is an error here, whatever the HTTP status said.
                    row["ok"], row["error"] = False, failed
            results.append(row)
        return {"action": req.action, "operator": req.operator,
                "all_ok": all(r["ok"] for r in results),
                "error_count": sum(1 for r in results if not r["ok"]),
                "results": results}

    @app.post("/api/fleet/halt")
    def fleet_halt(req: FleetHalt, request: Request) -> dict:
        """Kill every non-retired agent, domain by domain, through the
        kill-switch's own domain halt (POST /kill/domain/{d})."""
        okw = _operator_kw(request)
        domains = req.domains
        explicit = bool(domains)                  # the caller named the domains: the registry is read per domain below
        skipped: list[dict[str, Any]] = []        # registry rows that could not be placed in a domain (id when known)
        fallback_ids: dict[str, None] = {}        # skipped rows with a VALID agent_id (AGENT_ID_RE): killed one by one
        expected: dict[str, set[str]] = {}        # domain -> the non-retired agent ids the registry listed for it
        if not domains:
            status, agents = app.state.registry.get("/agents")
            if status != 200:
                raise HTTPException(502, detail=f"registry unavailable — cannot "
                                    f"enumerate domains: {_error_text(status, agents)}")
            if not isinstance(agents, list):
                raise HTTPException(502, detail="registry answered an unexpected body — cannot enumerate domains")
            # One malformed row must never stop the halt of the others: it is skipped, REPORTED BY ID and ledgered (an
            # error in the report, a banner that is not green), and every domain that can be named is still halted.
            # A skipped row whose agent_id is usable is killed on its own (/kill/{id}) so a malformed domain cannot
            # leave a live agent behind; that is reported separately from the domain halts.
            found: set[str] = set()
            for a in agents:
                if not isinstance(a, dict):
                    skipped.append({"agent_id": None, "reason": "row is not an object"})
                    continue
                if a.get("status") == "retired":
                    continue
                aid = a.get("agent_id")
                # a usable id is ONE valid path segment (AGENT_ID_RE, at most 128 chars): anything else (a "/" would
                # reach the whole-domain route, C-936 F-C936-1) is reported but never used to build a URL
                aid = aid if registry_id_ok(aid) else None
                # a missing key or null is the default domain; any other non-string (0, False, [], {}) or a blank or
                # slashed string is malformed, never silently "general"
                d = a["domain"] if a.get("domain") is not None else "general"
                if not isinstance(d, str) or not d.strip() or "/" in d:
                    skipped.append({"agent_id": aid, "reason": "domain is not a usable string"})
                    if aid is not None:
                        fallback_ids[aid] = None
                    continue
                found.add(d)
                if aid is None:
                    # a good domain but no usable agent_id: the domain halt still covers the agent, but this row cannot
                    # be named, so it is reported, ledgered and keeps the page not-green
                    skipped.append({"agent_id": None, "reason": "agent_id is not usable"})
                else:
                    expected.setdefault(d, set()).add(aid)
            domains = sorted(found)
        bad_rows = len(skipped)
        results = []
        for domain in dict.fromkeys(domains):
            expectation_failed = False
            if explicit:
                # Explicit domains: the registry still decides which agents a halt must account for. The halt itself is
                # NEVER skipped for a failed read; the domain is just not ok (the answer cannot be checked).
                st_e, rows_e = app.state.registry.get("/agents", params={"domain": domain})
                if st_e == 200 and isinstance(rows_e, list):
                    expected[domain] = {r["agent_id"] for r in rows_e
                                        if isinstance(r, dict) and r.get("status") != "retired"
                                        and isinstance(r.get("agent_id"), str) and r["agent_id"].strip()}
                else:
                    expectation_failed = True
            status, data = app.state.killswitch.post(
                f"/kill/domain/{_seg(domain)}",
                json={"operator": req.operator, "reason": req.reason}, **okw)
            http_ok = status in (200, 201)
            try:
                counts, errors = _domain_outcomes(data)
                # C-19: a domain is halted only when the HTTP answer was 2xx AND it carries a valid per-agent results
                # list AND no result is an error (a 200 with every agent errored is not a halt; neither is a 2xx
                # that does not say what happened to any agent).
                ids = _result_ids(data)
                # A halt report must account for every agent the registry listed for the domain (an empty or short list,
                # or one naming other ids, is not a halt). Only 200/201 count as a successful answer (never a 202).
                complete = (ids is not None and len(ids) >= 1 and not expectation_failed
                            and expected.get(domain, set()) <= ids)
                ok = http_ok and counts is not None and counts["error"] == 0 and complete
                row = {"domain": domain, "ok": ok, "status": status,
                       "counts": counts, "errors": errors,
                       "result" if http_ok else "error": data if http_ok else _relay(status, data)}
            except Exception:  # noqa: BLE001 - nothing in ONE domain's answer may stop the kills still to be sent
                row = {"domain": domain, "ok": False, "status": status, "counts": None, "errors": [],
                       "error": "the kill-switch answer for this domain could not be read"}
            results.append(row)
        agent_kills = []
        for aid in fallback_ids:   # (an ordered set: each id once)
            st, data = app.state.killswitch.post(
                f"/kill/{_seg(aid)}", json={"operator": req.operator, "reason": req.reason}, **okw)
            good = st in (200, 201) and isinstance(data, dict) and data.get("agent_id") == aid
            agent_kills.append({"agent_id": aid, "ok": good, "status": st})
        # B80: a halt that named its domains also reports the active agents no named halt can reach (after the kills)
        uncovered, coverage_checked = _named_halt_uncovered(app.state.registry, results) if explicit else ([], True)
        if skipped:
            # best effort, never a reason to stop: the halt already happened
            try:
                _RefusalLedger(app.state.ledger).append(
                    "fleet.halt.skipped_rows",
                    {"operator": req.operator, "reason": req.reason, "count": len(skipped),
                     "skipped": skipped[:MAX_LISTED_SKIPPED],
                     "fallback_kills": [{"agent_id": k["agent_id"], "ok": k["ok"]}
                                        for k in agent_kills[:MAX_LISTED_SKIPPED]]},
                    None)
            except Exception:  # noqa: BLE001
                pass
        return {"operator": req.operator, "domains": list(dict.fromkeys(domains)),
                "all_ok": (bad_rows == 0 and all(r["ok"] for r in results) and all(k["ok"] for k in agent_kills)
                           and coverage_checked and not uncovered),
                "agent_errors": sum(r["counts"]["error"] for r in results if r["counts"]) + bad_rows,
                "bad_rows": bad_rows,
                "skipped_rows": skipped[:MAX_LISTED_SKIPPED],
                "agent_kills": agent_kills,
                "coverage_checked": coverage_checked,
                "uncovered_count": len(uncovered),
                "uncovered_rows": uncovered[:MAX_LISTED_SKIPPED],
                "domains_failed": sum(1 for r in results if not r["ok"]),
                "results": results}

    @app.post("/api/tokens/{token_id}/revoke")
    def revoke(token_id: str, request: Request) -> Any:
        return _proxy(app.state.delegation, f"/tokens/{_seg(token_id)}/revoke", None,
                      **_operator_kw(request))

    @app.post("/api/escalations/{escalation_id}/resolve")
    def resolve(escalation_id: str, action: ResolveAction, request: Request) -> Any:
        return _proxy(app.state.governor,
                      f"/escalations/{_seg(escalation_id)}/resolve",
                      action.model_dump(), **_operator_kw(request))

    @app.post("/api/check")
    def check(req: CheckRequest) -> Any:
        """Dry-run harness: ask the sentinel what WOULD happen. The verdict
        is real and lands on the ledger like any other check."""
        return _proxy(app.state.sentinel, "/check", req.model_dump())

    warn_open("ops-console", operator_layer=True)
    return app
