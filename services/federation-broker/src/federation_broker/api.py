"""FastAPI surface for federation-broker."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from field_core.authn import install as install_authn

from federation_broker import __version__
from federation_broker.engine import (
    BrokerEngine,
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
        description="Inter-org crossing gateway (FIELD letter F).",
    )
    install_authn(app)
    app.state.engine = engine or BrokerEngine(
        store=ContractStore(data_path()),
        ledger=LedgerClient(),
    )

    def _engine() -> BrokerEngine:
        return app.state.engine

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "federation-broker",
                "version": __version__, "home_org": home_org()}

    @app.put("/contracts/{contract_id}", response_model=FederationContract)
    def put_contract(contract_id: str, contract: FederationContract) -> FederationContract:
        if contract.contract_id != contract_id:
            raise HTTPException(422, "contract_id in path and body must match")
        return _engine().store.save(contract)

    @app.get("/contracts", response_model=list[FederationContract])
    def list_contracts() -> list[FederationContract]:
        return _engine().store.list()

    @app.post("/crossing", response_model=ConformanceVerdict)
    def crossing(req: CrossingRequest) -> ConformanceVerdict:
        return _engine().decide(req)

    return app
