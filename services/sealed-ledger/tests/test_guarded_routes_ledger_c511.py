"""C-511: the route table the outbound clients use for the sealed-ledger is this service's own set of guarded routes.

``field_core.guarded_operator.LEDGER_GUARDED`` lists the routes of the sealed-ledger that look for the operator pair. This test
builds the real app and compares the table with the routes that carry ``op_health.guard`` and with the routes
that read the pair another way (``DECLARED_EXTRAS["ledger"]``), in both directions: a new guarded route that is
not in the table, or a table entry that is not a route, fails here instead of with a 401 on the estate.
"""
from __future__ import annotations

from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore
from field_core import guarded_operator as go


def _app(tmp=None):
    import tempfile
    from pathlib import Path
    return create_app(store=LedgerStore(Path(tempfile.mkdtemp()) / "events.jsonl"))


def test_the_table_is_this_services_guarded_routes():
    app = _app()
    assert go.drift_problems(app, go.LEDGER_TEMPLATES, go.DECLARED_EXTRAS["ledger"]) == []


def test_the_check_is_not_vacuous():
    app = _app()
    guarded = go.guard_dependent_routes(app)
    assert guarded, "the receiver has guarded routes; a scan that finds none is broken"
    # a table missing one guarded route, and a table with an invented one, are both reported
    table = set(go.LEDGER_TEMPLATES)
    victim = sorted(guarded & table)[0]
    assert go.drift_problems(app, table - {victim}, go.DECLARED_EXTRAS["ledger"]) != []
    assert go.drift_problems(app, table | {("POST", "/invented/{x}")}, go.DECLARED_EXTRAS["ledger"]) != []
