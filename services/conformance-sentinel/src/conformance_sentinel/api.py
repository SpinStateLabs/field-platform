"""FastAPI surface for conformance-sentinel."""

from __future__ import annotations

from fastapi import FastAPI

from field_core.authn import install as install_authn

from conformance_sentinel import __version__
from conformance_sentinel.engine import (
    CheckRequest,
    DelegationIntrospectClient,
    ManifestResolver,
    SentinelEngine,
    SpendStatusClient,
)
from field_core.clients import LedgerClient, RegistryClient
from field_core.conformance import CLAUSES, ConformanceVerdict


def _default_ledger_health(ledger_base: str | None = None):
    import os

    import httpx

    base = (ledger_base or os.environ.get(
        "FIELD_LEDGER_URL", "http://127.0.0.1:8002"
    )).rstrip("/")

    def health() -> bool:
        try:
            return httpx.get(f"{base}/health", timeout=2.0).status_code == 200
        except Exception:
            return False

    return health


def create_app(engine: SentinelEngine | None = None) -> FastAPI:
    app = FastAPI(
        title="conformance-sentinel",
        version=__version__,
        description="The policy-enforcement point: ALLOW / BLOCK / ESCALATE "
        "with the failed clause id (FIELD letter E).",
    )
    install_authn(app)
    app.state.engine = engine or SentinelEngine(
        registry=RegistryClient(),
        delegation=DelegationIntrospectClient(),
        governor=SpendStatusClient(),
        ledger=LedgerClient(),
        ledger_health=_default_ledger_health(),
        manifests=ManifestResolver(),
    )

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "conformance-sentinel", "version": __version__}

    @app.get("/clauses")
    def clauses() -> dict[str, str]:
        """The stable clause registry every verdict cites."""
        return CLAUSES

    @app.post("/check", response_model=ConformanceVerdict)
    def check(req: CheckRequest) -> ConformanceVerdict:
        return app.state.engine.check(req)

    return app
