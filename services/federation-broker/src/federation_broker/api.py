"""FastAPI surface for federation-broker."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request

# operator_auth: the guards below are operator_auth.guard behind operator_health
# (tools/tests/test_operator_plumbing.py finds operator-auth services by this import)
from field_core import operator_auth, operator_health  # noqa: F401
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from field_core.authn import install as install_authn
from field_core.buildinfo import build_sha

from federation_broker import __version__
from federation_broker.engine import (
    BrokerEngine,
    ContractConflict,
    ContractStore,
    CrossingRequest,
    FederationContract,
    home_org,
)
from field_core.clients import LedgerClient
from field_core.conformance import ConformanceVerdict


def data_path() -> Path:
    root = Path(os.environ.get("FIELD_DATA_DIR", "./var"))
    return root / "federation" / "contracts.sqlite3"


def create_app(engine: BrokerEngine | None = None) -> FastAPI:
    app = FastAPI(
        title="federation-broker",
        version=__version__,
        description="Inter-org crossing-decision service (FIELD letter F): "
        "decides inbound and outbound crossings; it does not carry the traffic.",
    )
    install_authn(app)

    @app.exception_handler(RequestValidationError)
    async def _validation_error_without_input(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # FastAPI's default 422 quotes every error's ``input`` — a contract's
        # key field can be a pasted PRIVATE key, and a ``missing`` error quotes
        # the whole body. Same response shape, minus ``input``.
        errors = [{k: v for k, v in e.items() if k != "input"} for e in exc.errors()]
        return JSONResponse(status_code=422,
                            content={"detail": jsonable_encoder(errors)})

    app.state.engine = engine or BrokerEngine(
        store=ContractStore(data_path()),
        ledger=LedgerClient(),
    )

    def _engine() -> BrokerEngine:
        return app.state.engine

    # C-9: the guard gets the engine's ledger, so a LOG-ONLY unauthenticated
    # contract write leaves its operator.unauthenticated row (C-16: and a
    # refusal under ENFORCE its operator.refused row).
    op_health = operator_health.install(
        app, ledger_getter=lambda a: getattr(a.state.engine, "ledger", None))

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "federation-broker",
                "version": __version__, "home_org": home_org(),
                "build_sha": build_sha(), "contract_ledger_gaps": _engine().contract_ledger_gaps,
                **op_health.health_fields()}

    guard_federation = op_health.guard("federation")

    @app.put("/contracts/{contract_id}", response_model=FederationContract)
    def put_contract(contract_id: str, contract: FederationContract,
                     _op: object = Depends(guard_federation)) -> FederationContract:
        if contract.contract_id != contract_id:
            raise HTTPException(422, "contract_id in path and body must match")
        try:
            result = _engine().store.write(contract)
        except ContractConflict as exc:
            _engine().record_contract_refusal(contract, exc)  # C-553: a refused write leaves a record too
            raise HTTPException(409, str(exc)) from None
        _engine().record_contract_write(result)  # C-553: one federation.contract.* event per write
        return result.contract

    @app.get("/contracts", response_model=list[FederationContract])
    def list_contracts() -> list[FederationContract]:
        return _engine().store.list()

    @app.post("/crossing", response_model=ConformanceVerdict)
    def crossing(req: CrossingRequest) -> ConformanceVerdict:
        return _engine().decide(req)

    return app
