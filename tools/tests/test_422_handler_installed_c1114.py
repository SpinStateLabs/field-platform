"""C-1114 (reviewer C-1109 F-C1109-1): every service that builds a FastAPI app installs the no-echo 422 handler.

FastAPI's default 422 repeats the rejected input, and anything that keeps response bodies keeps it. The field-core
helper `install_validation_handler` (C-1018) stops that; it was installed in one service only. A text scan of each
`services/*/src/*/api.py`: the file must call the helper, or the service must be in `NOT_YET` with the reason. An
entry whose service now installs the helper fails too, so the list only shrinks.

Stated limit: this reads source text, it does not send a request; the per-service `test_422_no_echo_<service>_c1114.py`
files do that for the services listed in `MEASURED`."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CALL = "install_validation_handler("

# service -> why it has no field-core install yet (C-1109 F-C1109-2, F-C1109-3)
NOT_YET = {
    "agent-registry": "keeps its own handler, validation_errors_without_values (api.py); moving it onto the helper is F-C1109-2",
    "federation-broker": "keeps its own handler (api.py); moving it onto the helper is F-C1109-2",
    "attestation-reporter": "no static body route gave a 422 in the C-1109 probe; not measured (F-C1109-3)",
    "claude-approver": "no static body route gave a 422 in the C-1109 probe; not measured (F-C1109-3)",
    "kill-switch": "its one probed route gave no 422 in the C-1109 probe; not measured (F-C1109-3)",
}
MEASURED = {"compliance-crosswalk", "conformance-sentinel", "delegation-authority", "force-gateway", "incident-replay",
            "lifecycle-manager", "ops-console", "sealed-ledger", "spend-governor"}


def _api_files() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for svc in sorted((ROOT / "services").iterdir()):
        for api in sorted(svc.glob("src/*/api.py")):
            if "FastAPI(" in api.read_text(encoding="utf-8"):
                out[svc.name] = api
    return out


def test_the_scan_sees_every_service():
    found = _api_files()
    assert len(found) >= 14, sorted(found)


@pytest.mark.parametrize("service", sorted(_api_files()))
def test_a_service_installs_the_helper_or_is_named_with_a_reason(service):
    installs = CALL in _api_files()[service].read_text(encoding="utf-8")
    if service in NOT_YET:
        assert not installs, f"{service} now installs the helper: remove it from NOT_YET"
    else:
        assert installs, f"{service} builds a FastAPI app without install_validation_handler(app)"


def test_the_measured_services_install_the_helper():
    for service in MEASURED:
        assert CALL in _api_files()[service].read_text(encoding="utf-8"), service
