"""C-511: the route table the outbound clients use for the delegation-authority is this service's own set of guarded routes.

``field_core.guarded_operator.DELEGATION_GUARDED`` lists the routes of the delegation-authority that look for the operator pair. This test
builds the real app and compares the table with the routes that carry ``op_health.guard`` and with the routes
that read the pair another way (``DECLARED_EXTRAS["delegation"]``), in both directions: a new guarded route that is
not in the table, or a table entry that is not a route, fails here instead of with a 401 on the estate.
"""
from __future__ import annotations

from delegation_authority.api import create_app
from delegation_authority.store import TokenStore
from field_core import guarded_operator as go


class _Unused:
    """Ledger and registry: building the app and listing its routes use neither."""


def _app():
    import tempfile
    from pathlib import Path
    return create_app(store=TokenStore(Path(tempfile.mkdtemp()) / "tokens.sqlite3"), ledger=_Unused(), registry=_Unused())


def test_the_table_is_this_services_guarded_routes():
    app = _app()
    assert go.drift_problems(app, go.DELEGATION_TEMPLATES, go.DECLARED_EXTRAS["delegation"]) == []


def test_the_check_is_not_vacuous():
    app = _app()
    guarded = go.guard_dependent_routes(app)
    assert guarded, "the receiver has guarded routes; a scan that finds none is broken"
    # a table missing one guarded route, and a table with an invented one, are both reported
    table = set(go.DELEGATION_TEMPLATES)
    victim = sorted(guarded & table)[0]
    assert go.drift_problems(app, table - {victim}, go.DECLARED_EXTRAS["delegation"]) != []
    assert go.drift_problems(app, table | {("POST", "/invented/{x}")}, go.DECLARED_EXTRAS["delegation"]) != []


def test_the_cli_client_does_not_follow_a_redirect_and_so_never_resends_the_pair(monkeypatch):
    """C-1069 (reviewer C-1057 F-C1057-381-1): httpx keeps the auth object's pair on a followed redirect; the
    delegation CLI client keeps its own copy of the guard, so the no-redirect rule is pinned here, as it is for the
    lifecycle and kill-switch clients."""
    import httpx
    from delegation_authority import cli

    seen: list[httpx.Request] = []

    def handler(req):
        seen.append(req)
        return httpx.Response(307, headers={"location": "http://elsewhere.invalid/tokens"})

    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: real(*a, transport=httpx.MockTransport(handler), **k))
    monkeypatch.setenv("FIELD_DELEGATION_URL", "http://da.invalid")
    client = cli._client(("svc", "made-up-key"))
    assert client.follow_redirects is False
    assert client.post("http://da.invalid/tokens").status_code == 307
    assert len(seen) == 1 and seen[0].url.host == "da.invalid"


def test_the_cli_client_pins_follow_redirects_false_in_its_source():
    """The default of httpx is also False today; the constructor says it, so a change of that default (or of this
    line) is a visible decision and the pair cannot ride a redirect."""
    import inspect
    from delegation_authority import cli

    assert "follow_redirects=False" in inspect.getsource(cli._client)
