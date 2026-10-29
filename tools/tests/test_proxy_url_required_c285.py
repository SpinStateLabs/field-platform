"""C-285: the estate base URL is an operator setting with no default in this repository.

`tools/provision_ssl_agents.py` and `tools/field-rest.ps1` used to fall back to the estate's private
address when FIELD_PROXY_URL was unset. Now an unset variable stops each with a clear message before
anything is sent, and none of the files the card names holds a private-range address.
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "provision_ssl_agents.py"
SHIM = REPO / "tools" / "field-rest.ps1"
SKETCH = REPO / "manifests" / "deployment-agent.yaml"

# RFC 1918 10/8 and 192.168/16, and the 100.64/10 shared range
PRIVATE = re.compile(r"(?<![0-9.])(10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+)(?![0-9])")


def _load_tool():
    spec = importlib.util.spec_from_file_location("provision_ssl_agents_c285", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provision_refuses_when_the_proxy_url_is_unset_and_sends_nothing(monkeypatch, capsys):
    monkeypatch.delenv("FIELD_PROXY_URL", raising=False)
    tool = _load_tool()
    monkeypatch.setattr(tool, "health", lambda *a, **k: pytest.fail("a request was attempted"))
    monkeypatch.setattr(tool, "client", lambda *a, **k: pytest.fail("a client was built"))
    assert tool.main([]) == 2
    err = capsys.readouterr().err
    assert "FIELD_PROXY_URL is not set" in err and "Nothing was sent" in err


def test_provision_has_no_proxy_default_in_the_module(monkeypatch):
    monkeypatch.delenv("FIELD_PROXY_URL", raising=False)
    assert _load_tool().PROXY == ""


def test_provision_reads_the_proxy_url_from_the_environment(monkeypatch):
    monkeypatch.setenv("FIELD_PROXY_URL", "http://proxy.invalid:18080/")
    assert _load_tool().PROXY == "http://proxy.invalid:18080"


def _ps():
    return shutil.which("pwsh") or shutil.which("powershell")


@pytest.mark.skipif(_ps() is None, reason="no PowerShell on this host")
def test_the_shim_throws_when_the_proxy_url_is_unset(tmp_path):
    env = {k: v for k, v in __import__("os").environ.items() if k != "FIELD_PROXY_URL"}
    env["FIELD_TOKENS_FILE"] = str(tmp_path / "none.json")
    r = subprocess.run([_ps(), "-NoProfile", "-NonInteractive", "-Command", f". '{SHIM}'; 'LOADED'"],
                       capture_output=True, text=True, env=env, timeout=60)
    assert "LOADED" not in r.stdout
    assert "FIELD_PROXY_URL is not set" in r.stdout + r.stderr


@pytest.mark.parametrize("path", [TOOL, SHIM, SKETCH], ids=lambda p: p.name)
def test_the_named_files_hold_no_private_range_address(path):
    hits = [n for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if PRIVATE.search(line)]
    assert hits == [], f"{path.name} lines {hits}"
