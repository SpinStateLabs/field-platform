"""Read-only and no-network guarantees — the two structural claims in the
Enforced-vs-Declared table."""

import socket
from pathlib import Path

import pytest

from field_core.signing import generate_keypair

from agent_incident_retro.engine import run_retro, write_outputs
from agent_incident_retro.evidence import verify_pack
from agent_incident_retro.synth import generate


def test_inputs_are_not_modified(tmp_path: Path, monkeypatch):
    """Three independent checks: (1) every open() of the input, through any of
    the three open entry points, is read-only; (2) the inode, size, mtime and
    ctime are unchanged after a full scan + write; (3) the bytes are equal. A
    byte comparison alone would pass a rewrite-with-identical-content, which is
    still a write."""
    import builtins
    import io
    import os

    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    before = log.read_bytes()
    stat_before = log.stat()
    opens: list[tuple[str, str]] = []
    real_open, real_os_open = io.open, os.open
    writing_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

    def spy_open(file, mode="r", *a, **k):
        if str(file) == str(log):
            opens.append(("io.open", mode))
        return real_open(file, mode, *a, **k)

    def spy_os_open(path, flags, *a, **k):
        if str(path) == str(log):
            opens.append(("os.open", "rb" if not (flags & writing_flags) else f"flags={flags:#x}"))
        return real_os_open(path, flags, *a, **k)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(io, "open", spy_open)
    monkeypatch.setattr(os, "open", spy_os_open)

    priv, _ = generate_keypair()
    result = run_retro([log], fmt="clf")
    write_outputs(result, tmp_path / "out", priv, "2026-10-11T00:00:00+00:00", [log])

    assert opens, "the input was never opened through a patched entry point: the tripwire is not armed"
    assert all(mode == "rb" for _, mode in opens), opens
    stat_after = log.stat()
    for field in ("st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"):
        assert getattr(stat_after, field) == getattr(stat_before, field), field
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


#: Modules that a network call would need. ``socket`` is here deliberately:
#: ``http.client``, ``ssl`` and every HTTP client sit on top of it.
FORBIDDEN_MODULES = {"httpx", "requests", "aiohttp", "urllib.request", "urllib3", "socket", "http.client", "ssl"}


def test_no_network_client_imported():
    """Structural: importing the package (all four CLI-reachable modules) pulls
    in none of FORBIDDEN_MODULES. Checked in a fresh interpreter: inside pytest
    ``socket`` is always already imported (by pytest itself, and by this very
    test file), so an in-process check could never assert on it. The C
    extension ``_socket`` is pulled in by ``typing_extensions`` (a pydantic
    dependency) and is not a client; it is not in the set."""
    import subprocess
    import sys

    probe = (
        "import sys, json\n"
        "import agent_incident_retro, agent_incident_retro.engine, agent_incident_retro.evidence, agent_incident_retro.cli\n"
        f"print(json.dumps(sorted(set({sorted(FORBIDDEN_MODULES)!r}) & set(sys.modules))))"
    )
    src = str(Path(__file__).resolve().parents[1] / "src")
    r = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, cwd=src, check=True)
    assert r.stdout.strip() == "[]", r.stdout


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


# second independent review (2026-10-12), MEDIUM-4: outputs are written atomically,
# pack first, so a failed write leaves no partial file and no orphaned report.


def _scan(tmp_path: Path):
    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    priv, _ = generate_keypair()
    return log, priv, run_retro([log], fmt="clf")


def test_pack_write_failure_leaves_no_report(tmp_path: Path, monkeypatch):
    """v0.1 wrote report.md first; a pack write failure (disk full, EACCES)
    left an orphaned, unsigned report that looked like a result."""
    from agent_incident_retro import engine

    log, priv, result = _scan(tmp_path)
    real = engine._replace_atomic

    def failing(target: Path, text: str) -> None:
        if target.name == "evidence-pack.json":
            raise OSError(28, "No space left on device")
        real(target, text)

    monkeypatch.setattr(engine, "_replace_atomic", failing)
    out = tmp_path / "out"
    with pytest.raises(OSError):
        write_outputs(result, out, priv, "2026-10-11T00:00:00+00:00", [log])
    assert sorted(p.name for p in out.iterdir()) == []  # no report.md, no pack, no temp file


def test_failed_rename_leaves_no_partial_output(tmp_path: Path, monkeypatch):
    """The temp file is written whole and renamed into place; if the rename
    fails nothing is left behind, not even the temp file."""
    import os

    log, priv, result = _scan(tmp_path)
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError(5, "Input/output error")))
    out = tmp_path / "out"
    with pytest.raises(OSError):
        write_outputs(result, out, priv, "2026-10-11T00:00:00+00:00", [log])
    assert sorted(p.name for p in out.iterdir()) == []


def test_pack_lands_before_report(tmp_path: Path, monkeypatch):
    from agent_incident_retro import engine

    log, priv, result = _scan(tmp_path)
    order: list[str] = []
    real = engine._replace_atomic

    def recording(target: Path, text: str) -> None:
        order.append(target.name)
        real(target, text)

    monkeypatch.setattr(engine, "_replace_atomic", recording)
    write_outputs(result, tmp_path / "out", priv, "2026-10-11T00:00:00+00:00", [log])
    assert order == ["evidence-pack.json", "report.md"]


def test_force_overwrite_is_atomic_and_leaves_no_temp_files(tmp_path: Path):
    log, priv, result = _scan(tmp_path)
    out = tmp_path / "out"
    write_outputs(result, out, priv, "2026-10-11T00:00:00+00:00", [log])
    write_outputs(result, out, priv, "2026-10-11T00:00:01+00:00", [log], force=True)
    assert sorted(p.name for p in out.iterdir()) == ["evidence-pack.json", "report.md"]
    assert "2026-10-11T00:00:01+00:00" in (out / "report.md").read_text(encoding="utf-8")
