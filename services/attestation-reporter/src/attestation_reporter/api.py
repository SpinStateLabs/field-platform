"""FastAPI surface for attestation-reporter — the board pack, served.

What is served is what ``attest render`` writes for the same window: a
WINDOWED, UNSIGNED draft. ``period`` ("2026-Q3" / "Q3 2026") or
``since``/``until`` set the window (mutually exclusive; neither ⇒ all-time;
a bad window ⇒ 422 before any upstream is queried). The served pack is ALWAYS
unsigned: an unattended server cannot be the named human signer, so this
module never imports the signer and has no key (F4 revisits). PDF stays
CLI-only.

Every data route is protected by ``x-field-auth`` when
``FIELD_SHARED_SECRET`` is set; only ``/health`` is open. ``/pack.html``
is a data route (it prints every number), so it is NOT an open path — a
browser on a secret estate cannot present the header and gets 401; the
HTML route is API-only there.
"""

from __future__ import annotations

import copy
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from field_core.authn import auth_headers, install as install_authn
from field_core.buildinfo import build_sha

from attestation_reporter import __version__
from attestation_reporter.engine import BoardPack, PackEngine
from attestation_reporter.render import render_html
from attestation_reporter.window import InvalidWindow

# (env var, default base URL) — the same four upstreams as `attest render`.
UPSTREAMS = (
    ("registry", "FIELD_REGISTRY_URL", "http://127.0.0.1:8001"),
    ("ledger", "FIELD_LEDGER_URL", "http://127.0.0.1:8002"),
    ("delegation", "FIELD_DELEGATION_URL", "http://127.0.0.1:8003"),
    ("governor", "FIELD_GOVERNOR_URL", "http://127.0.0.1:8006"),
)


def engine_from_env(org: str = "Spin State Labs") -> PackEngine:
    """The shared engine builder: one httpx client per upstream, base URL
    from the environment, ``auth_headers()`` attached. Used by both
    ``attest render`` and ``attest serve`` so the CLI and the API can never
    drift on where the numbers come from."""
    import httpx

    kwargs: dict = {"org": org}
    for name, env, default in UPSTREAMS:
        base = os.environ.get(env, default)
        kwargs[name] = httpx.Client(base_url=base, timeout=10.0, headers=auth_headers())
        kwargs[f"{name}_base"] = base
    return PackEngine(**kwargs)


def create_app(engine: PackEngine | None = None) -> FastAPI:
    app = FastAPI(
        title="attestation-reporter",
        version=__version__,
        description=(
            "The governance board pack, served — every number with its "
            "literal source query. A windowed, UNSIGNED draft."
        ),
    )
    install_authn(app)  # no open_paths: /pack.html prints data, so it is protected
    app.state.engine = engine or engine_from_env()

    def _build(
        period: str | None, org: str | None, since: str | None, until: str | None
    ) -> BoardPack:
        eng: PackEngine = app.state.engine
        if org is not None:
            # Per-request override; a shallow copy so concurrent requests
            # (uvicorn runs sync handlers in a threadpool) never see it.
            eng = copy.copy(eng)
            eng.org = org
        try:
            pack = eng.build(period=period, since=since, until=until)
        except InvalidWindow as exc:
            # A window must never silently degrade to all-time counts.
            raise HTTPException(422, str(exc)) from exc
        if pack.signed:  # build() never signs; an injected engine must not either
            raise HTTPException(500, "served packs are unsigned drafts")
        return pack

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "attestation-reporter", "version": __version__,
                "build_sha": build_sha()}

    period_doc = '"2026-Q3" or "Q3 2026" — that UTC quarter; excludes since/until'
    since_doc = "inclusive; ISO 8601 date or timestamp (a date alone = start of that UTC day)"
    until_doc = "inclusive; ISO 8601 date or timestamp (a date alone = end of that UTC day)"

    @app.get("/pack", response_model=BoardPack)
    def pack(
        period: str | None = Query(None, description=period_doc),
        org: str | None = Query(None, description="overrides the engine's org"),
        since: str | None = Query(None, description=since_doc),
        until: str | None = Query(None, description=until_doc),
    ) -> BoardPack:
        return _build(period, org, since, until)

    @app.get("/pack.html", response_class=HTMLResponse)
    def pack_html(
        period: str | None = Query(None, description=period_doc),
        org: str | None = Query(None, description="overrides the engine's org"),
        since: str | None = Query(None, description=since_doc),
        until: str | None = Query(None, description=until_doc),
    ) -> HTMLResponse:
        return HTMLResponse(render_html(_build(period, org, since, until)))

    return app
