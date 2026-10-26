"""FastAPI surface for claude-approver.

Routes:

* ``GET /health`` - open. ``{ok, service, version, build_sha,
  key_file_present, polling}``. Says only WHETHER the key file is present;
  never the key or any part of it.
* ``GET /stats`` - behind ``x-field-auth`` when ``FIELD_SHARED_SECRET`` is
  set: counters, the last 500 decisions, p50/p95 latency.
* ``POST /halt/{field_agent_id}`` - the kill-switch endpoint for the
  allowlist. Requires ``x-field-kill-origin: kill-switch`` (403 otherwise and
  nothing changes); unmapped FIELD agent 404; no client 503. EXEMPT from the
  perimeter middleware for the FIELD ids mapped when the app was created,
  because the kill-switch's outbound halt signal carries no ``x-field-auth``
  (``kill_switch/api.py``), exactly like the X3 canary's ``/halt``. The origin
  header is a marker, not authentication (README, Declared).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from field_core.authn import install as install_authn
from field_core.buildinfo import build_sha

from claude_approver import SERVICE, __version__, config
from claude_approver.core import ORIGIN_HEADER, ORIGIN_VALUE, REASON_HEADER, Approver, decode_reason


def halt_open_paths() -> set[str]:
    """``/halt/<id>`` for every usable FIELD id in the map, read NOW.

    Computed once at app creation: an agent added to the map later needs an
    approver restart before the kill-switch (which sends no perimeter header)
    can reach its ``/halt``; until then that path answers 401 under an armed
    perimeter."""
    return {f"/halt/{fid}" for fid in config.load_agent_map().field_ids()}


def create_app(approver: Approver | None = None) -> FastAPI:
    app = FastAPI(title="claude-approver", version=__version__)
    install_authn(app, open_paths=halt_open_paths())
    app.state.approver = approver if approver is not None else Approver()

    @app.get("/health")
    def health() -> dict:
        a: Approver = app.state.approver
        return {
            "ok": True,
            "service": SERVICE,
            "version": __version__,
            "build_sha": build_sha(),
            "key_file_present": config.key_file_present(),
            "polling": a.polling(),
        }

    @app.get("/stats")
    def stats() -> dict:
        return app.state.approver.stats()

    @app.post("/halt/{field_agent_id}")
    def halt(field_agent_id: str, request: Request) -> JSONResponse:
        if request.headers.get(ORIGIN_HEADER) != ORIGIN_VALUE:
            return JSONResponse(
                {"detail": f"{ORIGIN_HEADER}: {ORIGIN_VALUE} header required"}, status_code=403,
            )
        reason = decode_reason(request.headers.get(REASON_HEADER))
        status, body = app.state.approver.halt(field_agent_id, reason)
        return JSONResponse(body, status_code=status)

    return app
