"""FastAPI surface for the sealed ledger."""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, HTTPException, Query, Response

from field_core.authn import install as install_authn
from field_core.buildinfo import build_sha
from pydantic import BaseModel, Field, StrictBool, TypeAdapter, model_serializer

from field_core.ledger import ChainVerification, LedgerEvent
from sealed_ledger import __version__
from sealed_ledger.retention import RetentionCheck, retention_check
from sealed_ledger.store import (
    CALLER_KEYRING_ENV,
    REQUIRE_CALLER_SIGNATURE_ENV,
    REQUIRE_SIGNING_ENV,
    SEAL_UNSIGNED,
    SIGN_KEY_ENV,
    ArchiveRefused,
    CallerPolicy,
    CallerRefused,
    ExportSummary,
    HoldConflict,
    InvalidTimeBound,
    LedgerBusy,
    LedgerCorrupt,
    LedgerStore,
    LegalHoldActive,
    NoAnchorKey,
    RotationRefused,
    RotationResult,
    SigningConfig,
    SigningRequired,
    load_caller_policy,
    load_signing_config,
)

ANCHOR_KEY_ENV = "FIELD_LEDGER_ANCHOR_KEY"
ARCHIVE_DIR_ENV = "FIELD_LEDGER_ARCHIVE_DIR"
_UNSET: Any = object()


class AppendRequest(BaseModel):
    event_type: str = Field(min_length=1)
    agent_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    # F2b (additive): the caller's claim. All three absent = a pre-F2b body.
    # A ledger without F2b ignores them (this model never forbade extras).
    caller_id: str | None = None
    caller_ts: str | None = None
    caller_signature: str | None = None

    def caller_claim(self) -> dict[str, Any] | None:
        """The three caller fields, or None when the body carried none."""
        claim = {"caller_id": self.caller_id, "caller_ts": self.caller_ts,
                 "caller_signature": self.caller_signature}
        return None if all(v is None for v in claim.values()) else claim


class RotateRequest(BaseModel):
    operator: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class HoldRequest(BaseModel):
    by: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class HoldReleaseRequest(BaseModel):
    by: str = Field(min_length=1)


class HoldStatus(BaseModel):
    held: bool
    hold: dict[str, Any] | None = None


class RetentionApplyRequest(BaseModel):
    days: int = Field(ge=0, description="archive closed segments closed more than this many days ago")
    operator: str = Field(min_length=1)
    archive_dir: str | None = Field(
        None, description="default FIELD_LEDGER_ARCHIVE_DIR, else FIELD_DATA_DIR/ledger-archive"
    )
    allow_external: StrictBool = False


class RetentionApplyResult(BaseModel):
    archived_segments: list[int]
    completed_moves: list[int]
    pending_moves: list[dict[str, Any]]
    archive_dir: str
    retention_event_hash: str | None = None


class HealthResponse(BaseModel):
    ok: bool
    service: str = "sealed-ledger"
    version: str = __version__
    event_count: int  # GLOBAL chain length (== /verify length)
    head_hash: str
    earliest_live_index: int = 0  # > 0 once old segments are archived
    earliest_live_ts: str | None = None
    build_sha: str | None = None  # FIELD_BUILD_SHA; "unknown" when unset
    # F2 per-event signing (every field always present except key_error):
    appendable: bool = True  # false exactly when signing is required and no key is loaded
    signing: str = "off"  # "on" | "off" | "error" (path set, key not loadable)
    key_fingerprint: str | None = None  # sha-256 over the raw 32-byte public key
    seal_algorithm: str = SEAL_UNSIGNED  # ed25519-signed-chain when on, sha-256-chain otherwise
    require_signing: bool = False  # FIELD_LEDGER_REQUIRE_SIGNING=1
    key_error: str | None = None  # ONLY when signing == "error" (omitted otherwise)
    # F2b caller signatures (always present):
    caller_keyring: str = "off"  # "on" when FIELD_LEDGER_CALLER_KEYRING names a directory
    caller_keys: int = 0  # <caller_id>.pub.pem files in it (0 when off or unreadable)
    require_caller_signature: bool = False  # FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1

    # No return annotation on purpose (OpenAPI keeps the fields; see ledger.py).
    @model_serializer(mode="wrap")
    def _omit_key_error_unless_error(self, handler):
        data = handler(self)
        if isinstance(data, dict) and data.get("signing") != "error":
            data.pop("key_error", None)
        return data


def data_root() -> Path:
    return Path(os.environ.get("FIELD_DATA_DIR", "./var"))


def data_path() -> Path:
    return data_root() / "ledger" / "events.jsonl"


def require_signing_from_env() -> bool:
    """FIELD_LEDGER_REQUIRE_SIGNING: exactly ``1`` (or true/yes/on, any case)
    arms the fail-closed policy; unset, blank, ``0`` or anything else is off
    (the default, today's behaviour)."""
    return os.environ.get(REQUIRE_SIGNING_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def signing_config_from_env() -> SigningConfig:
    """F2: FIELD_LEDGER_SIGN_KEY (a PEM path; blank = no key) and
    FIELD_LEDGER_REQUIRE_SIGNING, read ONCE at store/app start. A missing,
    unreadable or malformed key never raises: ``signing: error`` on /health
    and behaviour follows the require flag. The anchor key
    (FIELD_LEDGER_ANCHOR_KEY) is a separate key and is not read here."""
    return load_signing_config(os.environ.get(SIGN_KEY_ENV), require_signing_from_env())


def require_caller_signature_from_env() -> bool:
    """FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE: the same parse as
    ``require_signing_from_env`` (exactly 1/true/yes/on arms it)."""
    return os.environ.get(REQUIRE_CALLER_SIGNATURE_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def caller_policy_from_env() -> CallerPolicy:
    """F2b: FIELD_LEDGER_CALLER_KEYRING (a directory of ``<caller_id>.pub.pem``;
    blank = no keyring, every caller claim refused) and
    FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE, read ONCE at store/app start. A
    missing directory never raises: ``caller_keys: 0`` on /health and every
    caller is unknown."""
    return load_caller_policy(os.environ.get(CALLER_KEYRING_ENV), require_caller_signature_from_env())


def open_store(path: str | Path | None = None) -> LedgerStore:
    """A store on ``path`` (default the served data path) with the F2 signing
    policy and the F2b caller policy from the environment — the served app
    and every CLI verb open stores through this, so an offline ``ledger
    append --path`` on the box signs with the same key the service does
    (and, as the ledger's own append, carries no caller fields)."""
    return LedgerStore(path if path is not None else data_path(), signing=signing_config_from_env(),
                       caller=caller_policy_from_env())


def default_archive_dir() -> Path:
    """FIELD_LEDGER_ARCHIVE_DIR when set (blank = unset), else FIELD_DATA_DIR/ledger-archive."""
    raw = os.environ.get(ARCHIVE_DIR_ENV, "").strip()
    return Path(raw) if raw else data_root() / "ledger-archive"


def load_anchor_key(key_path: str | Path | None = None) -> str:
    """The rotation signing key: the PEM file ``key_path``, else the one named
    by FIELD_LEDGER_ANCHOR_KEY, read on every call (the served route calls it
    per request). Every failure is ``NoAnchorKey`` (HTTP 503) — never a
    process exit, never an unsigned rotation. Messages name the failure, never
    key material."""
    source = "--key" if key_path else ANCHOR_KEY_ENV
    key_path = key_path or os.environ.get(ANCHOR_KEY_ENV)
    if not key_path:
        raise NoAnchorKey("no anchor key configured")
    try:
        pem = Path(key_path).read_text(encoding="ascii")
    except (OSError, UnicodeError, ValueError) as exc:
        raise NoAnchorKey(f"anchor key unreadable ({source}): {type(exc).__name__}") from None
    try:
        key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    except (TypeError, ValueError, UnicodeError, UnsupportedAlgorithm) as exc:
        raise NoAnchorKey(
            f"anchor key unusable ({source}): not a PEM private key ({type(exc).__name__})"
        ) from None
    if not isinstance(key, Ed25519PrivateKey):
        raise NoAnchorKey(f"anchor key unusable ({source}): not Ed25519")
    return pem


def _open_default_store() -> LedgerStore:
    """The served store. A crashed rotation is finished (or undone) at startup,
    and ONLY if one is pending: a clean ledger is never written at startup.
    If reconcile cannot run, the service still starts: reads report the break
    and every write answers 500/503 until an operator acts."""
    store = open_store()  # F2: the signing key is loaded here, once; never a process exit
    try:
        if store.needs_reconcile():
            store.reconcile()
    except (LedgerCorrupt, LedgerBusy):
        pass
    return store


def create_app(store: LedgerStore | None = None, registry: Any = _UNSET) -> FastAPI:
    """``registry`` feeds ``/retention/check`` (anything with ``list_agents()``).
    Not given: disabled when ``store`` is injected (deterministic, no network —
    every test stack), else a ``RegistryClient()`` built per request from the
    environment (the ledger starts before the registry). ``None`` disables:
    the check then answers ``unavailable``."""
    app = FastAPI(
        title="sealed-ledger",
        version=__version__,
        description="Append-only, sha-256 hash-chained event ledger (FIELD letter L).",
    )
    install_authn(app)
    app.state.store = store if store is not None else _open_default_store()
    if registry is _UNSET and store is not None:
        registry = None
    app.state.registry = registry
    # Lanes (C2 perf): Starlette runs every sync route on one 40-thread pool, so
    # 40 heavy reads queued on the read gate used to starve /health and
    # appends. /health and POST /events get their own threads; /verify, GET
    # /events and /export queue as work items (no thread held) on a pool no
    # wider than the store's read gate, and serialize their JSON there too.
    read_width = getattr(app.state.store, "read_concurrency", 1) or 32
    app.state.lanes = {
        "health": ThreadPoolExecutor(4, thread_name_prefix="ledger-health"),
        "append": ThreadPoolExecutor(8, thread_name_prefix="ledger-append"),
        "read": ThreadPoolExecutor(read_width, thread_name_prefix="ledger-read"),
    }

    def _store() -> LedgerStore:
        return app.state.store

    def _registry() -> Any:
        if app.state.registry is _UNSET:
            from field_core.clients import RegistryClient

            return RegistryClient()
        return app.state.registry

    async def _in_lane(lane: str, fn: Callable[[], Any]) -> Any:
        return await asyncio.get_running_loop().run_in_executor(app.state.lanes[lane], fn)

    def _json(adapter: TypeAdapter, value: Any, status_code: int = 200) -> Response:
        # what FastAPI's default response path does, but in the worker thread
        return Response(content=adapter.dump_json(value, by_alias=True), status_code=status_code,
                        media_type="application/json")

    events_json = TypeAdapter(list[LedgerEvent])
    verification_json = TypeAdapter(ChainVerification)
    export_json = TypeAdapter(ExportSummary)
    event_json = TypeAdapter(LedgerEvent)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        # Never locks, never walks the chain: the cached global count and head,
        # re-counted without pydantic only if another process changed the files.
        info = await _in_lane("health", _store().health_info)
        # F2: appendable / signing / key_fingerprint / seal_algorithm /
        # require_signing (+ key_error only on "error") from the config loaded
        # at start — no key file is read here. F2b: caller_keyring /
        # caller_keys (one directory listing) / require_caller_signature.
        return HealthResponse(ok=True, build_sha=build_sha(), **info,
                              **_store().signing.health_fields(),
                              **_store().caller_policy.health_fields())

    @app.post("/events", response_model=LedgerEvent, status_code=201)
    async def append_event(req: AppendRequest) -> Response:
        """Append one event. F2: signed when the ledger holds a key; with
        FIELD_LEDGER_REQUIRE_SIGNING=1 and no key loaded, a start-type event
        is 503 (detail names the env var) and a stop-type event
        (delegation.revoke, kill.*, lifecycle.decommissioned) is 201 with
        ``signing_failed: true`` stamped by the ledger. F2b: a body carrying
        ``caller_id`` / ``caller_ts`` / ``caller_signature`` is stored with
        them only after the claim verified against the keyring (unknown
        caller, bad signature, ``caller_ts`` outside the replay window, no
        keyring configured: 403, nothing written); with
        FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1 a start-type body without
        them is 403 (detail names the env var) and a stop-type body without
        them — or whose claim does not verify — is 201 with the claim
        dropped and ``caller_unsigned: true`` stamped (a stop is never
        refused by a caller-key fault)."""
        def run() -> Response:
            event = _store().append_for_caller(
                event_type=req.event_type, payload=req.payload, agent_id=req.agent_id,
                claim=req.caller_claim(),
            )
            return _json(event_json, event, status_code=201)

        try:
            return await _in_lane("append", run)
        except CallerRefused as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (LedgerBusy, SigningRequired) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except LedgerCorrupt as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/events", response_model=list[LedgerEvent])
    async def list_events(
        agent_id: str | None = None,
        event_type: str | None = None,
        since: str | None = Query(None, description="ISO 8601 lower bound (inclusive)"),
        until: str | None = Query(None, description="ISO 8601 upper bound (inclusive)"),
        limit: int | None = Query(None, ge=1, le=10_000),
    ) -> Response:
        def run() -> Response:
            return _json(events_json, _store().events(
                agent_id=agent_id,
                event_type=event_type,
                since=since,
                until=until,
                limit=limit,
            ))

        try:
            return await _in_lane("read", run)
        except InvalidTimeBound as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except LedgerBusy as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/verify", response_model=ChainVerification)
    async def verify() -> Response:
        # a snapshot that cannot stabilise is ok=false "ledger busy: …", HTTP 200
        return await _in_lane("read", lambda: _json(verification_json, _store().verify()))

    @app.post("/export", response_model=ExportSummary)
    async def export(
        out_dir: str | None = Query(
            None,
            description="Server-side directory; the bundle lands in out_dir/<stamp>/ "
            "on the LEDGER HOST (default <ledger dir>/exports).",
        ),
        since: str | None = Query(None, description="ISO 8601 lower bound (inclusive)"),
        until: str | None = Query(None, description="ISO 8601 upper bound (inclusive)"),
        agent_id: str | None = None,
        event_type: str | None = None,
    ) -> Response:
        """Write an auditor export bundle. The served export is never signed
        (`signed: false`); signing is `ledger export --sign-key` only."""
        s = _store()
        target = Path(out_dir) if out_dir else s.path.parent / "exports"

        def run() -> Response:
            return _json(export_json, s.export(
                target,
                since=since,
                until=until,
                agent_id=agent_id,
                event_type=event_type,
            ))

        try:
            return await _in_lane("read", run)
        except InvalidTimeBound as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except LedgerBusy as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/rotate", response_model=RotationResult)
    def rotate(req: RotateRequest) -> RotationResult:
        """Close the open segment (retention by rotation). Signed with the key
        at FIELD_LEDGER_ANCHOR_KEY; unset, unreadable or unusable => 503 and
        nothing is written. The rotation event (operator, reason, signed
        anchor) is the ledger record; ship `anchor` off-box."""
        if not req.operator.strip() or not req.reason.strip():
            raise HTTPException(status_code=422, detail="operator and reason must not be blank")
        try:
            pem = load_anchor_key()
            return _store().rotate(private_key_pem=pem, operator=req.operator, reason=req.reason)
        except (NoAnchorKey, LedgerBusy, SigningRequired) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RotationRefused as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except LedgerCorrupt as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/hold", response_model=HoldStatus)
    def hold_status() -> HoldStatus:
        try:
            hold = _store().hold_status()
        except OSError as exc:
            raise HTTPException(status_code=503, detail=f"ledger busy: hold marker unreadable: {exc}") from exc
        return HoldStatus(held=hold is not None, hold=hold)

    @app.post("/hold", status_code=201)
    def place_hold(req: HoldRequest) -> dict[str, Any]:
        """Place the legal hold (retention apply refuses while it exists).
        Ledgered as ``ledger.legal_hold.placed``. 409 if one is in place."""
        if not req.by.strip() or not req.reason.strip():
            raise HTTPException(status_code=422, detail="by and reason must not be blank")
        try:
            return _store().place_hold(by=req.by, reason=req.reason)
        except HoldConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (LedgerBusy, SigningRequired) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except LedgerCorrupt as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/hold/release")
    def release_hold(req: HoldReleaseRequest) -> dict[str, Any]:
        """Release the legal hold, ledgered as ``ledger.legal_hold.released``
        (written before the marker is removed). 409 if none is in place."""
        if not req.by.strip():
            raise HTTPException(status_code=422, detail="by must not be blank")
        try:
            return _store().release_hold(by=req.by)
        except HoldConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (LedgerBusy, SigningRequired) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except LedgerCorrupt as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/retention/apply", response_model=RetentionApplyResult)
    def retention_apply(req: RetentionApplyRequest) -> RetentionApplyResult:
        """Archive closed segments closed more than ``days`` ago (never the open
        one). 423 under a legal hold; 422 for an archive dir inside the live
        ledger dir, outside FIELD_DATA_DIR (unless ``allow_external``) or on
        another filesystem; 503 busy; 500 if a segment does not verify (then
        nothing of it is archived)."""
        if not req.operator.strip():
            raise HTTPException(status_code=422, detail="operator must not be blank")
        try:
            result = _store().archive_closed_segments(
                older_than_days=req.days,
                archive_dir=Path(req.archive_dir) if req.archive_dir else default_archive_dir(),
                operator=req.operator,
                allow_external=req.allow_external,
                data_dir=data_root(),
            )
        except LegalHoldActive as exc:
            raise HTTPException(status_code=423, detail=str(exc)) from exc
        except ArchiveRefused as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (LedgerBusy, SigningRequired) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (LedgerCorrupt, OSError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return RetentionApplyResult(**result)

    @app.get("/retention/check", response_model=RetentionCheck)
    def retention_check_route() -> RetentionCheck:
        """Estate policy FIELD_LEDGER_RETENTION_DAYS vs every registered
        manifest's ledger.retention_days. Always 200; ``ok`` is true only for
        status ``ok``."""
        return retention_check(_store(), _registry())

    return app
