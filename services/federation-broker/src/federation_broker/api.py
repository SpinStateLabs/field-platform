"""FastAPI surface for federation-broker."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request

# operator_auth: the guards below are operator_auth.guard behind operator_health
# (tools/tests/test_operator_plumbing.py finds operator-auth services by this import)
from field_core import operator_auth, operator_health  # noqa: F401
from field_core.startup import warn_open
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from field_core.authn import install as install_authn
from field_core.buildinfo import build_sha
from field_core.http_errors import redacted_loc

from federation_broker import __version__
from federation_broker.engine import (
    BrokerEngine,
    ContractConflict,
    ContractStore,
    CrossingRequest,
    FederationContract,
    home_org,
)
from federation_broker.own_token import TOKEN_HEADER, OwnTokenCheck
from field_core.clients import LedgerClient
from field_core.conformance import ConformanceVerdict


def data_path() -> Path:
    root = Path(os.environ.get("FIELD_DATA_DIR", "./var"))
    return root / "federation" / "contracts.sqlite3"


class _DuplicateKey(ValueError):
    """A JSON object in the request body repeats a key."""


def _refuse_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict:
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise _DuplicateKey
        out[key] = value
    return out


async def refuse_duplicate_json_keys(request: Request) -> None:
    """B13: a body whose JSON repeats a key is refused (422), not read last-wins.

    ``{"allowed_scopes": ["read"], "allowed_scopes": ["*"]}`` would otherwise store the LAST value while a reviewer
    of the request saw the first. Any depth counts. The key is not quoted (C-1128: a field name the caller sent is
    not echoed). A body that is not JSON at all is left to FastAPI's own 422.
    """
    body = await request.body()
    if not body:
        return
    try:
        json.loads(body, object_pairs_hook=_refuse_duplicate_pairs)
    except _DuplicateKey:
        raise HTTPException(422, "request body repeats a JSON key; send each key once") from None
    except (ValueError, RecursionError):
        return


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
        # the whole body. Same response shape, minus ``input``. A field NAME the
        # caller sent lands in ``loc``: it is replaced by the field-core helper
        # (C-1128). The messages the contract validators write stay (C-1123 F3
        # is Don's: the field-core handler would replace them with fixed text).
        errors = [{**{k: v for k, v in e.items() if k != "input"}, "loc": redacted_loc(request.app, e)}
                  for e in exc.errors()]
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
                "build_sha": build_sha(),
                "ledger_appends_dropped": app.state.engine.ledger_appends_dropped,
                "contract_ledger_gaps": getattr(_engine(), "contract_ledger_gaps", 0),
                **op_health.health_fields()}

    guard_federation = op_health.guard("federation")

    @app.put("/contracts/{contract_id}", response_model=FederationContract)
    def put_contract(contract_id: str, contract: FederationContract,
                     _op: object = Depends(guard_federation),
                     _once: None = Depends(refuse_duplicate_json_keys)) -> FederationContract:
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

    app.state.own_token = OwnTokenCheck()
    guard_crossing = op_health.guard("crossing")

    async def _guard(request: Request) -> None:
        # named like the operator guards: guard_dependent_routes (the CLI drift test) finds guarded routes by it
        """Who may ask: the named agent, with its own active token, for its outbound crossing; otherwise an operator
        with the ``crossing`` scope. Follows the operator layer's mode (off: not checked; log-only: recorded)."""
        if operator_auth.mode() == operator_auth.OFF:
            return
        token = request.headers.get(TOKEN_HEADER)
        if token:
            try:
                body = json.loads(await request.body())  # a repeated key is refused before this (dependency order)
            except (ValueError, RecursionError):
                body = None
            if (isinstance(body, dict) and body.get("direction") == "outbound"
                    and isinstance(body.get("agent_id"), str)
                    and await run_in_threadpool(app.state.own_token.bound, token, body["agent_id"])):
                return
        await guard_crossing(request)

    @app.post("/crossing", response_model=ConformanceVerdict)
    def crossing(req: CrossingRequest,
                 _once: None = Depends(refuse_duplicate_json_keys),
                 _caller: None = Depends(_guard)) -> ConformanceVerdict:
        # triage-t12 N1 on #1300: a crossing request that repeats a key (a second "scope" or "counterparty_org") is
        # refused like a contract write, never decided on its last value
        return _engine().decide(req)

    warn_open("federation-broker", operator_layer=True)
    return app
