"""operator_keygen (C-305, reviewer C-251 F-C251-1/-2/-3): the registry write is the last step that can fail, so it
happens BEFORE any key is shown, a key FILE already created is removed when it fails, and the failure is an
`error:` exit, never a traceback. A key whose sha256 is registered nowhere (an identity that authenticates as
nobody) is never left behind. A concurrent edit of the registry during the run is refused, not overwritten.
Test keys are generated per test and never printed by the test."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import operator_keygen as kg  # noqa: E402

H1 = "a" * 64


def _seed(tmp_path):
    f = tmp_path / "operators.json"
    f.write_bytes(json.dumps([{"operator_id": "don", "key_sha256": H1, "status": "active", "scopes": ["kill"],
                               "created_at": "2026-10-01T00:00:00+00:00", "names": []}]).encode())
    return f, f.read_bytes()


def _fail_write(monkeypatch, exc=PermissionError(13, "Permission denied")):
    def boom(path, text):
        raise exc
    monkeypatch.setattr(kg, "atomic_write_text", boom)


@pytest.mark.parametrize("via", ["printed", "key-file"])
def test_a_failed_registry_write_leaves_no_key_and_is_an_error_exit(tmp_path, capsys, monkeypatch, via):
    f, before = _seed(tmp_path)
    kf = tmp_path / "new.key"
    _fail_write(monkeypatch)
    args = ["--operator-id", "new", "--add-to", str(f)] + (["--key-file", str(kf)] if via == "key-file" else [])
    with pytest.raises(SystemExit) as e:        # not a PermissionError traceback
        kg.main(args)
    assert str(e.value).startswith("error: cannot write "), e.value
    cap = capsys.readouterr()
    assert "fok_" not in cap.out + cap.err, "a key was shown for a registration that failed"
    assert "KEY (shown once" not in cap.out and "key written" not in cap.out and "registered sha256" not in cap.out
    assert not kf.exists(), "a key file with an unregistered hash was left behind"
    assert f.read_bytes() == before


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="a read-only directory only blocks a non-root POSIX user")
@pytest.mark.parametrize("via", ["printed", "key-file"])
def test_a_registry_in_a_read_only_directory_is_an_error_exit_with_no_key(tmp_path, capsys, via):
    d = tmp_path / "ro"
    d.mkdir()
    f = d / "operators.json"
    f.write_bytes(json.dumps([{"operator_id": "don", "key_sha256": H1, "status": "active", "scopes": ["kill"],
                               "created_at": "2026-10-01T00:00:00+00:00", "names": []}]).encode())
    before = f.read_bytes()
    kf = tmp_path / "new.key"
    d.chmod(0o555)
    try:
        args = ["--operator-id", "new", "--add-to", str(f)] + (["--key-file", str(kf)] if via == "key-file" else [])
        with pytest.raises(SystemExit) as e:
            kg.main(args)
    finally:
        d.chmod(0o755)
    assert str(e.value).startswith("error: cannot write "), e.value
    cap = capsys.readouterr()
    assert "fok_" not in cap.out + cap.err
    assert not kf.exists() and f.read_bytes() == before


def test_the_key_file_removal_failing_does_not_hide_the_error(tmp_path, monkeypatch):
    f, _ = _seed(tmp_path)
    kf = tmp_path / "new.key"
    _fail_write(monkeypatch)

    def no_unlink(path):
        raise OSError("cannot remove")
    monkeypatch.setattr(kg.os, "unlink", no_unlink)
    with pytest.raises(SystemExit) as e:
        kg.main(["--operator-id", "new", "--add-to", str(f), "--key-file", str(kf)])
    assert str(e.value).startswith("error: cannot write ")


def _edit_during_the_run(monkeypatch, f: Path):
    """A concurrent writer replaces the registry after this run has read it, before it writes."""
    real = kg.prepare_entry

    def prepare_then_edit(*a, **kw):
        out = real(*a, **kw)
        f.write_bytes(f.read_bytes() + b" ")
        return out
    monkeypatch.setattr(kg, "prepare_entry", prepare_then_edit)


@pytest.mark.parametrize("via", ["printed", "key-file"])
def test_a_registry_edited_during_the_run_is_refused_not_overwritten(tmp_path, capsys, monkeypatch, via):
    f, before = _seed(tmp_path)
    kf = tmp_path / "new.key"
    _edit_during_the_run(monkeypatch, f)
    args = ["--operator-id", "new", "--add-to", str(f)] + (["--key-file", str(kf)] if via == "key-file" else [])
    with pytest.raises(SystemExit) as e:
        kg.main(args)
    assert "changed while the key was being made" in str(e.value)
    cap = capsys.readouterr()
    assert "fok_" not in cap.out + cap.err and not kf.exists()
    assert f.read_bytes() == before + b" ", "the concurrent writer's bytes were overwritten"


def test_the_registry_is_written_with_two_space_json_and_a_final_newline(tmp_path):
    """F-C251-3: the success path's bytes are pinned (the success tests only read the file back as JSON)."""
    f, _ = _seed(tmp_path)
    kg.main(["--operator-id", "new", "--add-to", str(f), "--key-file", str(tmp_path / "k.key")])
    text = f.read_text(encoding="utf-8")
    assert text == json.dumps(json.loads(text), indent=2) + "\n"
    assert text.startswith('[\n  {\n    "')


def test_a_successful_run_still_registers_and_prints_the_key_after_the_write(tmp_path, capsys):
    f, _ = _seed(tmp_path)
    assert kg.main(["--operator-id", "new", "--add-to", str(f)]) == 0
    out = capsys.readouterr().out
    assert out.index("registered sha256") > out.index("KEY (shown once") and "fok_" in out
    assert [r["operator_id"] for r in json.loads(f.read_text(encoding="utf-8"))] == ["don", "new"]
