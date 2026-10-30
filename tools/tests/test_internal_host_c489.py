"""C-489: the tools carry a copy of ``field_core.hosts.is_internal_host(..., allow_names=False)`` (they run
without field_core on the path); each copy must answer exactly as the one predicate does, and no code outside
field-core may use ``ipaddress.is_private`` (a second private-host policy)."""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

from field_core.hosts import is_internal_host

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ["renew_token", "estate_probe", "phase_g_check"]
SPELLINGS = ["127.0.0.1", "127.1", "10.1", "0x0a.1", "172.16.0.1", "172.32.0.1", "192.168.0.1", "::1", "fd00::1",
             "::ffff:10.0.0.1", "::ffff:8.8.8.8", "::1%25eth0", "169.254.169.254", "0.0.0.0", "255.255.255.255",
             "198.18.0.1", "192.0.0.1", "::", "2002:808:808::", "fe80::1", "8.8.8.8", "134744072", "0x08080808",
             "01001001010", "localhost", "forcegw", "svc.internal", "x.local", "example.com", "", "127.0.0.1.",
             "127.0.0.1 .evil.test"]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"c489_{name}", ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("host", SPELLINGS)
def test_each_tool_copy_answers_as_the_one_predicate(tool, host):
    assert _load(tool)._internal_host(host) is is_internal_host(host, allow_names=False)


# --- no second policy ---------------------------------------------------------------------------------------
# Sites not yet migrated: path -> count and why (the list only shrinks: it must equal the scan).
ALLOWED = {
    "services/force-gateway/src/force_gateway/api.py": 1,   # C-489 follow-up: open PRs 324/341/350 hold this file
}
SKIP = {"tests", "node_modules", "__pycache__", ".venv", "venv", ".git", "build", "dist"}


def _is_private_uses() -> tuple[dict[str, int], int]:
    found: dict[str, int] = {}
    scanned = 0
    for top in ("packages", "services", "tools", "plugins", "integration", "defence-shield"):
        for p in sorted((ROOT / top).rglob("*.py")) if (ROOT / top).is_dir() else []:
            rel = p.relative_to(ROOT)
            if p.name.startswith("test_") or p.name == "conftest.py" or any(x in SKIP for x in rel.parts):
                continue
            scanned += 1
            if rel.parts[:3] == ("packages", "field-core", "src"):
                continue
            n = sum(1 for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))
                                           ) if isinstance(node, ast.Attribute) and node.attr == "is_private")
            if n:
                found[rel.as_posix()] = n
    return found, scanned


def test_no_is_private_outside_field_core_except_the_listed_sites():
    found, scanned = _is_private_uses()
    assert scanned > 100, scanned                      # an empty scan is a failure, not a pass
    assert found == ALLOWED
