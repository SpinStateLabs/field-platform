"""FastAPI surface for conformance-sentinel."""

from __future__ import annotations

from fastapi import FastAPI

from field_core.authn import install as install_authn
from field_core.buildinfo import build_sha

from conformance_sentinel import __version__
from conformance_sentinel.engine import (
    CheckRequest,
    DelegationIntrospectClient,
    ManifestResolver,
    SentinelEngine,
    SpendStatusClient,
)
from conformance_sentinel.judge import resolve_floor, resolve_judge
from conformance_sentinel.mode import resolve_mode
from field_core.clients import LedgerClient, RegistryClient
from field_core.conformance import CLAUSES, ConformanceVerdict


def _default_ledger_health(ledger_base: str | None = None):
    """The step-1 reachability gate. True only when ``GET /health`` is 200,
    its body says ``ok: true`` AND (F2) it is appendable: a body carrying
    ``appendable`` that is not ``true`` (FIELD_LEDGER_REQUIRE_SIGNING=1 with
    no signing key loaded) is a ledger that will refuse the allow record, so
    the action is refused here. A body with NO ``appendable`` key is an older
    ledger and counts as appendable. Anything else — transport error,
    non-200, non-JSON, ``ok`` not true — is False (fail closed)."""
    import os

    import httpx

    base = (ledger_base or os.environ.get(
        "FIELD_LEDGER_URL", "http://127.0.0.1:8002"
    )).rstrip("/")

    def health() -> bool:
        try:
            resp = httpx.get(f"{base}/health", timeout=2.0)
            if resp.status_code != 200:
                return False
            body = resp.json()
        except Exception:
            return False
        if not isinstance(body, dict) or body.get("ok") is not True:
            return False
        if "appendable" in body and body["appendable"] is not True:
            return False
        return True

    return health


def create_app(engine: SentinelEngine | None = None) -> FastAPI:
    app = FastAPI(
        title="conformance-sentinel",
        version=__version__,
        description="The policy-enforcement point: ALLOW / BLOCK / ESCALATE "
        "with the failed clause id (FIELD letter E).",
    )
    install_authn(app)
    # Served estate is safe-by-default: log-only unless FIELD_SENTINEL_MODE
    # says enforce. An injected engine (tests) keeps its own mode.
    app.state.engine = engine or SentinelEngine(
        registry=RegistryClient(),
        delegation=DelegationIntrospectClient(),
        governor=SpendStatusClient(),
        ledger=LedgerClient(),
        ledger_health=_default_ledger_health(),
        manifests=ManifestResolver(),
        mode=resolve_mode(),
        judge=resolve_judge(),
        judge_floor=resolve_floor(),
    )

    @app.get("/health")
    def health() -> dict:
        engine_ = app.state.engine
        return {"ok": True, "service": "conformance-sentinel",
                "version": __version__, "mode": engine_.mode.value,
                "judge": (getattr(engine_.judge, "name", "custom")
                          if engine_.judge is not None else "off"),
                "build_sha": build_sha()}

    @app.get("/clauses")
    def clauses() -> dict[str, str]:
        """The stable clause registry every verdict cites."""
        return CLAUSES

    @app.post("/check", response_model=ConformanceVerdict)
    def check(req: CheckRequest) -> ConformanceVerdict:
        return app.state.engine.check(req)

    return app
