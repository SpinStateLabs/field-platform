"""C-511: the route table the outbound clients use for the kill-switch is this service's own set of guarded routes.

``field_core.guarded_operator.KILLSWITCH_GUARDED`` lists the routes of the kill-switch that look for the operator pair. This test
builds the real app and compares the table with the routes that carry ``op_health.guard`` and with the routes
that read the pair another way (``DECLARED_EXTRAS["killswitch"]``), in both directions: a new guarded route that is
not in the table, or a table entry that is not a route, fails here instead of with a 401 on the estate.
"""
from __future__ import annotations

from kill_switch.api import create_app
from field_core import guarded_operator as go


class _Unused:
    """Registry and ledger: building the app and listing its routes use neither."""


def _app():
    return create_app(registry=_Unused(), ledger=_Unused())


def test_the_table_is_this_services_guarded_routes():
    app = _app()
    assert go.drift_problems(app, go.KILLSWITCH_TEMPLATES, go.DECLARED_EXTRAS["killswitch"]) == []


def test_the_check_is_not_vacuous():
    app = _app()
    guarded = go.guard_dependent_routes(app)
    assert guarded, "the receiver has guarded routes; a scan that finds none is broken"
    # a table missing one guarded route, and a table with an invented one, are both reported
    table = set(go.KILLSWITCH_TEMPLATES)
    victim = sorted(guarded & table)[0]
    assert go.drift_problems(app, table - {victim}, go.DECLARED_EXTRAS["killswitch"]) != []
    assert go.drift_problems(app, table | {("POST", "/invented/{x}")}, go.DECLARED_EXTRAS["killswitch"]) != []
