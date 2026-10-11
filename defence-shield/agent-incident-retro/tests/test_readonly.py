"""Read-only and no-network guarantees — the two structural claims in the
Enforced-vs-Declared table."""

import socket
from pathlib import Path

import pytest

from field_core.signing import generate_keypair

from agent_incident_retro.engine import run_retro, write_outputs
from agent_incident_retro.evidence import verify_pack
from agent_incident_retro.synth import generate


def test_inputs_are_not_modified(tmp_path: Path):
    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    before = log.read_bytes()
    priv, _ = generate_keypair()
    result = run_retro([log], fmt="clf")
    write_outputs(result, tmp_path / "out", priv, "2026-10-11T00:00:00+00:00", [log])
    assert log.read_bytes() == before


def test_write_outputs_refuses_to_clobber_an_input(tmp_path: Path):
    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    priv, _ = generate_keypair()
    result = run_retro([log], fmt="clf")
    # point the output dir's report.md at the input path
    with pytest.raises(ValueError, match="input"):
        write_outputs(result, tmp_path, priv, "2026-10-11T00:00:00+00:00", [tmp_path / "report.md"])


def test_no_network_sockets(tmp_path: Path, monkeypatch):
    """A full scan + pack build + verify must open no socket and resolve no
    hostname. The guard raises BaseException so a bare ``except Exception``
    anywhere in the path could not silently swallow it."""
    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    priv, pub = generate_keypair()

    class _NetworkAttempted(BaseException):
        pass

    def _blocked(*a, **k):
        raise _NetworkAttempted("network access attempted")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)

    result = run_retro([log], fmt="clf")
    report_path, pack_path = write_outputs(result, tmp_path / "out", priv, "2026-10-11T00:00:00+00:00", [log])
    import json

    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    assert verify_pack(pack, pub, report_path.read_bytes(), {"synth.log": log.read_bytes()}).ok


def test_no_network_client_imported():
    """Structural: importing the package pulls in no network client."""
    import importlib
    import sys

    for name in list(sys.modules):
        if name.startswith("agent_incident_retro"):
            del sys.modules[name]
    importlib.import_module("agent_incident_retro")
    importlib.import_module("agent_incident_retro.engine")
    importlib.import_module("agent_incident_retro.evidence")
    forbidden = {"httpx", "requests", "aiohttp", "urllib.request", "urllib3"}
    assert forbidden.isdisjoint(sys.modules), forbidden & set(sys.modules)


def test_write_outputs_refuses_a_hardlinked_input(tmp_path: Path):
    """A hard link to the input inside the out dir must not be overwritten,
    even with --force (resolve() alone misses hard links; samefile catches them)."""
    import os

    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    link = out / "report.md"
    try:
        os.link(log, link)
    except (OSError, NotImplementedError):
        pytest.skip("hard links unsupported here")
    priv, _ = generate_keypair()
    result = run_retro([log], fmt="clf")
    before = log.read_bytes()
    with pytest.raises(ValueError, match="input"):
        write_outputs(result, out, priv, "2026-10-11T00:00:00+00:00", [log], force=True)
    assert log.read_bytes() == before


def test_jsonl_lone_surrogate_does_not_crash_scan(tmp_path: Path):
    """A JSON user-agent with a lone surrogate must not abort the scan on a
    later utf-8 encode (hashing / canonical pack)."""
    log = tmp_path / "s.jsonl"
    log.write_text(
        '{"ts":"2026-09-01T00:00:00Z","ip":"203.0.113.9","method":"GET",'
        '"uri":"/search?q=\\u0027 OR \\u00271\\u0027=\\u00271 -- ","status":200,"user_agent":"x\\ud800y"}\n',
        encoding="utf-8",
    )
    priv, pub = generate_keypair()
    result = run_retro([log], fmt="jsonl", preset="generic")
    report_path, pack_path = write_outputs(result, tmp_path / "o", priv, "2026-10-11T00:00:00+00:00", [log])
    import json

    assert verify_pack(json.loads(pack_path.read_text(encoding="utf-8")), pub, report_path.read_bytes()).ok


def test_force_required_to_overwrite(tmp_path: Path):
    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    priv, _ = generate_keypair()
    result = run_retro([log], fmt="clf")
    out = tmp_path / "out"
    write_outputs(result, out, priv, "2026-10-11T00:00:00+00:00", [log])
    with pytest.raises(FileExistsError):
        write_outputs(result, out, priv, "2026-10-11T00:00:00+00:00", [log])
    write_outputs(result, out, priv, "2026-10-11T00:00:00+00:00", [log], force=True)
