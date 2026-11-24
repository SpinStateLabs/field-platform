"""S3-13: `sentinel score` ends every upstream or filesystem failure in a named refusal and exit 1, not a traceback.

`score` builds real `httpx.Client`s; these tests replace `cli.httpx.Client` with clients on a MockTransport per base URL
(no network, no real command). A clean exit shows up as `SystemExit` on the CliRunner result; an uncaught error shows up as
any other exception. The /health non-200 and gate exit codes are pinned elsewhere and are not repeated here."""

from __future__ import annotations

import time

import httpx
import pytest
from typer.testing import CliRunner

from conformance_sentinel import cli as cli_mod

REAL_CLIENT = httpx.Client               # cli.httpx IS the httpx module: capture the class before it is patched
SENTINEL, REGISTRY, DELEGATION = "http://sentinel.test", "http://registry.test", "http://delegation.test"
MARK = "UPSTREAM-BODY-MARKER-7731"        # a made-up string an upstream puts in its body; it must never be printed


def _ok_health(request):
    return httpx.Response(200, json={"mode": "log-only", "judge": "off"})


def _ok_registry(request):
    return httpx.Response(201, json={})


def _ok_delegation(request):
    if request.url.path.endswith("/revoke"):
        return httpx.Response(200, json={})
    return httpx.Response(201, json={"token_id": "tok-" + str(time.monotonic_ns())})


@pytest.fixture()
def run(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_SENTINEL_URL", SENTINEL)
    monkeypatch.setenv("FIELD_REGISTRY_URL", REGISTRY)
    monkeypatch.setenv("FIELD_DELEGATION_URL", DELEGATION)
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    closed = []

    def invoke(sentinel=None, registry=None, delegation=None, manifest_dir=None):
        handlers = {SENTINEL: sentinel or _ok_health, REGISTRY: registry or _ok_registry,
                    DELEGATION: delegation or _ok_delegation}

        def factory(base_url=None, **kw):
            c = REAL_CLIENT(base_url=base_url, transport=httpx.MockTransport(handlers[base_url]))
            closed.append(c)
            return c

        monkeypatch.setattr(cli_mod.httpx, "Client", factory)
        args = ["score", "--manifest-dir", str(manifest_dir or tmp_path)]
        return CliRunner().invoke(cli_mod.app, args)

    invoke.closed = closed
    return invoke


def _named_refusal(result):
    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit), repr(result.exception)    # not an uncaught error
    assert "Traceback" not in result.output
    assert "measurement refused" in result.output, result.output
    assert MARK not in result.output


def test_registry_refusing_post_and_patch_is_a_named_refusal(run):
    r = run(registry=lambda req: httpx.Response(500, text=MARK))
    _named_refusal(r)
    assert "cannot provision seed agent" in r.output


def test_delegation_503_on_mint_is_a_named_refusal(run):
    r = run(delegation=lambda req: httpx.Response(503, text=MARK))
    _named_refusal(r)


def test_a_missing_manifest_dir_is_a_named_refusal_that_does_not_print_the_path(run, tmp_path):
    missing = tmp_path / "no-such-dir-4412"
    r = run(manifest_dir=missing)
    _named_refusal(r)
    assert "no-such-dir-4412" not in r.output


def test_a_non_json_health_body_is_a_named_refusal(run):
    r = run(sentinel=lambda req: httpx.Response(200, text=MARK))
    _named_refusal(r)


def test_a_non_json_check_body_is_a_named_refusal(run):
    def sentinel(req):
        if req.url.path == "/health":
            return _ok_health(req)
        return httpx.Response(200, text=MARK)

    _named_refusal(run(sentinel=sentinel))


def test_a_transport_failure_is_a_named_refusal(run):
    def registry(req):
        raise httpx.ConnectError(MARK)

    _named_refusal(run(registry=registry))


def test_the_three_clients_are_closed_on_a_refusal(run):
    run(registry=lambda req: httpx.Response(500, text=MARK))
    assert len(run.closed) == 3 and all(c.is_closed for c in run.closed)


def test_health_non_200_still_exits_1_with_its_own_message(run):
    """Guard for the re-raise: typer.Exit is a RuntimeError, so a broad except must not swallow it."""
    r = run(sentinel=lambda req: httpx.Response(503))
    assert r.exit_code == 1 and "sentinel /health returned 503" in r.output
    assert "measurement refused" not in r.output
