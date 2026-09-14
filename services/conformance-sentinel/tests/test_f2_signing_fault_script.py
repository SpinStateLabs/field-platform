"""The CI fault-path script (integration/demo/fixtures/upgrade-smoke/
signing_fault.py) against the REAL ledger and sentinel apps, over a real
socket (a stub proxy with the /ledger and /sentinel prefixes), with the
sentinel's step-1 gate being the real ``_default_ledger_health``.

Positive: the ledger in the A9 fault state (FIELD_LEDGER_REQUIRE_SIGNING=1,
an unreadable key) => every check PASSes, exit 0. Negative control: a
healthy ledger => the script FAILS (exit 1), so a green run means the fault
path was exercised, not that the script cannot fail.
"""

from __future__ import annotations

import importlib.util
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conformance_sentinel.api import _default_ledger_health
from conformance_sentinel.api import create_app as create_sentinel_app
from conformance_sentinel.engine import (
    DelegationIntrospectClient,
    ManifestResolver,
    SentinelEngine,
    SpendStatusClient,
)
from field_core.clients import LedgerClient, RegistryClient
from sealed_ledger.store import load_signing_config
from tests.conftest import Stack

SCRIPT = Path(__file__).resolve().parents[3] / "integration" / "demo" / "fixtures" / "upgrade-smoke" / "signing_fault.py"
SECRET = "ci-test-secret-not-a-real-one"


def _load_script():
    spec = importlib.util.spec_from_file_location("signing_fault", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Proxy(ThreadingHTTPServer):
    daemon_threads = True
    routes: dict[str, TestClient] = {}


def _handler(routes: dict[str, TestClient]):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # quiet
            pass

        def _forward(self):
            prefix, _, rest = self.path.lstrip("/").partition("/")
            client = routes.get(prefix)
            if client is None:
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            headers = {k: v for k, v in self.headers.items()
                       if k.lower() in ("x-field-auth", "content-type", "accept")}
            resp = client.request(self.command, "/" + rest, content=body, headers=headers)
            self.send_response(resp.status_code)
            self.send_header("Content-Type", resp.headers.get("content-type", "application/json"))
            self.send_header("Content-Length", str(len(resp.content)))
            self.end_headers()
            self.wfile.write(resp.content)

        do_GET = do_POST = _forward

    return Handler


@pytest.fixture()
def estate(tmp_path, monkeypatch):
    """The Stack's real apps behind a socket proxy; the sentinel engine uses
    the REAL step-1 gate pointed at the proxied ledger."""
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    stack = Stack(tmp_path)
    routes: dict[str, TestClient] = {"ledger": stack.ledger}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(routes))
    base = f"http://127.0.0.1:{server.server_port}"
    engine = SentinelEngine(
        registry=RegistryClient(client=stack.registry, base_url="http://t"),
        delegation=DelegationIntrospectClient(client=stack.delegation, base_url="http://t"),
        governor=SpendStatusClient(client=stack.governor, base_url="http://t"),
        ledger=LedgerClient(client=stack.ledger, base_url="http://t"),
        ledger_health=_default_ledger_health(f"{base}/ledger"),
        manifests=ManifestResolver(manifest_dir=tmp_path),
    )
    routes["sentinel"] = TestClient(create_sentinel_app(engine=engine))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield stack, base
    finally:
        server.shutdown()
        server.server_close()


def test_signing_fault_script_passes_in_the_a9_fault_state(estate, tmp_path, capsys, monkeypatch):
    stack, base = estate
    stack.ledger_store.signing = load_signing_config(tmp_path / "keys" / "missing.pem", True)
    script = _load_script()
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    assert script.main([base, "upgrade-smoke-agent"]) == 0
    out = capsys.readouterr().out
    assert "5/5 checks passed" in out and "[FAIL]" not in out
    assert SECRET not in out
    # the event it appended is really on the ledger, stamped, unsigned
    [ev] = stack.ledger.get("/events", params={"event_type": "kill.agent"},
                            headers={"x-field-auth": SECRET}).json()
    assert ev["signing_failed"] is True and "signature" not in ev
    assert ev["payload"] == {"reason": "F2 fault-path proof"}


def test_signing_fault_script_fails_on_a_healthy_ledger(estate, capsys, monkeypatch):
    """Negative control: nothing in the fault state => every check FAILs."""
    _, base = estate
    script = _load_script()
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    assert script.main([base, "upgrade-smoke-agent"]) == 1
    out = capsys.readouterr().out
    assert "0/5 checks passed" in out


def test_signing_fault_script_refuses_without_the_secret_or_args(monkeypatch, capsys):
    script = _load_script()
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    assert script.main(["http://127.0.0.1:9", "agent"]) == 2
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    assert script.main(["only-one-arg"]) == 2
    assert SECRET not in capsys.readouterr().err
