"""C-1114 (reviewer C-1109 F-C1109-1): every service that builds a FastAPI app installs the no-echo 422 handler.

FastAPI's default 422 repeats the rejected input, and anything that keeps response bodies keeps it. The field-core
helper `install_validation_handler` (C-1018) stops that; it was installed in one service only. A text scan of each
`services/*/src/*/api.py`: the file must call the helper, or the service must be in `NOT_YET` with the reason. An
entry whose service now installs the helper fails too, so the list only shrinks.

Stated limit: this reads source text, it does not send a request; the per-service `test_422_no_echo_<service>_c1114.py`
files do that for the services listed in `MEASURED`."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CALL = "install_validation_handler"


def installs_helper(source: str) -> bool:
    """True if the source CALLS ``install_validation_handler`` (a bare name or an attribute): an ``ast`` Call node, so
    a comment, a string, an import or a bare name does not count (C-1128, reviewer C-1123 F2)."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Name) and func.id == CALL) or (isinstance(func, ast.Attribute) and func.attr == CALL):
                return True
    return False


# service -> why it has no field-core install yet (C-1109 F-C1109-3)
NOT_YET = {
    "federation-broker": "keeps its own handler ON PURPOSE (C-1128): it redacts a caller-chosen key name in loc but keeps "
                         "its validators' messages, which the helper would replace with a fixed phrase (F3, Don's decision)",
    "attestation-reporter": "no static body route gave a 422 in the C-1109 probe; not measured (F-C1109-3)",
    "claude-approver": "no static body route gave a 422 in the C-1109 probe; not measured (F-C1109-3)",
    "kill-switch": "its one probed route gave no 422 in the C-1109 probe; not measured (F-C1109-3)",
}
MEASURED = {"agent-registry", "compliance-crosswalk", "conformance-sentinel", "delegation-authority",
            "force-gateway", "incident-replay", "lifecycle-manager", "ops-console", "sealed-ledger",
            "spend-governor"}


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
    installs = installs_helper(_api_files()[service].read_text(encoding="utf-8"))
    if service in NOT_YET:
        assert not installs, f"{service} now installs the helper: remove it from NOT_YET"
    else:
        assert installs, f"{service} builds a FastAPI app without install_validation_handler(app)"


def test_the_measured_services_install_the_helper():
    for service in MEASURED:
        assert installs_helper(_api_files()[service].read_text(encoding="utf-8")), service


# --- C-1128 (reviewer C-1123 F2): the guard looks for a Call node, not for text ---------------------------------------
def test_a_call_is_found_and_a_comment_or_string_is_not():
    """F2: a text scan passes when the call text sits only in a comment or a string. The scan must find a real
    ``install_validation_handler(..)`` Call node (a bare name or an attribute) and nothing else."""
    assert installs_helper("install_validation_handler(app)\n")
    assert installs_helper("import m\nm.install_validation_handler(app)\n")
    assert installs_helper("def f(app):\n    install_validation_handler(app)\n")
    assert not installs_helper("# install_validation_handler(app)\n")
    assert not installs_helper("x = 'install_validation_handler(app)'\n")
    assert not installs_helper("'''install_validation_handler(app)'''\n")
    assert not installs_helper("from m import install_validation_handler\n")   # imported, never called
    assert not installs_helper("install_validation_handler\n")                 # named, never called
