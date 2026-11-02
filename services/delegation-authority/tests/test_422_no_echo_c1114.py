"""C-1114 (seam audit C-1109 S1): a 422 from delegation-authority never repeats the caller's text.

field-core's ``install_validation_handler`` is the rule (C-1018): FastAPI's default 422 puts the rejected input back in
the reply, and anything that keeps response bodies (a proxy, a log, a browser console) keeps it. Probe: send a JSON
STRING holding a made-up marker to every static-path POST, PUT and PATCH route (a string is never a valid body for a
model), and fail if the marker comes back in any 422 body. At least one route must answer 422, so a service whose
routes all moved cannot pass by measuring nothing. Kill: remove ``install_validation_handler(app)`` from ``create_app``.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from delegation_authority.api import create_app

MARKER = "c1114-made-up-marker-not-a-real-value"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def _static_body_routes(app):
    for route in app.routes:
        path, methods = getattr(route, "path", ""), getattr(route, "methods", None) or ()
        if path and "{" not in path:
            for method in sorted(set(methods) & {"POST", "PUT", "PATCH"}):
                yield method, path


def test_a_422_never_repeats_the_callers_text(client):
    answers = []
    for method, path in _static_body_routes(client.app):
        response = client.request(method, path, json=MARKER)
        if response.status_code == 422:
            answers.append((method, path))
            assert MARKER not in response.text, f"{method} {path} echoed the caller's text in a 422"
    assert answers, "no static route answered 422: the probe measured nothing"
