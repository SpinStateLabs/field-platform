"""operator_keygen (C-235): every refusal of --add-to comes BEFORE the key is written or printed, so a refused
run never leaves the operator holding a key whose hash was never registered; the success path is unchanged.
Test keys are generated per test and never printed by the test."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import operator_keygen as kg  # noqa: E402

H1, H2 = "a" * 64, "b" * 64


def _row(oid, sha, **kw):
    return {"operator_id": oid, "key_sha256": sha, "status": "active", "scopes": ["kill"],
            "created_at": "2026-10-01T00:00:00+00:00", "names": [], **kw}


def _seed(tmp_path, rows=None, raw=None):
    f = tmp_path / "operators.json"
    f.write_bytes(raw if raw is not None else json.dumps(rows or [_row("don", H1, names=["Shared"])]).encode())
    return f, f.read_bytes()


REFUSED = {
    "duplicate id": ["--operator-id", "don"],
    "alias equal to another row's id": ["--operator-id", "mallory", "--alias", "don"],
    "alias shared with another row": ["--operator-id", "mallory", "--alias", "Shared"],
    "alias *": ["--operator-id", "mallory", "--alias", "*"],
}


@pytest.mark.parametrize("label", list(REFUSED))
@pytest.mark.parametrize("via", ["printed", "key-file"])
def test_a_refused_add_to_prints_no_key_and_writes_no_key_file(tmp_path, capsys, label, via):
    f, before = _seed(tmp_path)
    kf = tmp_path / "mallory.key"
    args = [*REFUSED[label], "--add-to", str(f)] + (["--key-file", str(kf)] if via == "key-file" else [])
    with pytest.raises(SystemExit) as e:
        kg.main(args)
    assert str(e.value).startswith("error: "), e.value
    cap = capsys.readouterr()
    assert "fok_" not in cap.out + cap.err and "key_sha256" not in cap.out and "fingerprint" not in cap.out, cap
    assert "KEY (shown once" not in cap.out and "key written" not in cap.out
    assert not kf.exists(), "a key file was written for a registration that was refused"
    assert f.read_bytes() == before, "the registry changed"


def test_a_format_2_file_is_refused_before_any_key_output(tmp_path, capsys):
    doc = {"format": 2, "operators": []}
    f, before = _seed(tmp_path, raw=json.dumps(doc).encode())
    kf = tmp_path / "k.key"
    with pytest.raises(SystemExit) as e:
        kg.main(["--operator-id", "svc", "--add-to", str(f), "--key-file", str(kf)])
    assert "format 2" in str(e.value)
    cap = capsys.readouterr()
    assert "fok_" not in cap.out + cap.err and cap.out == "" and not kf.exists() and f.read_bytes() == before


def test_an_invalid_resulting_registry_is_refused_before_any_key_output(tmp_path, capsys):
    f, before = _seed(tmp_path, raw=b'{"operators": {"not": "a list"}}')
    with pytest.raises(SystemExit):
        kg.main(["--operator-id", "svc", "--add-to", str(f)])
    cap = capsys.readouterr()
    assert cap.out == "" and "fok_" not in cap.err and f.read_bytes() == before


def test_a_refused_run_neither_writes_a_key_nor_the_registry_whatever_the_order(tmp_path, monkeypatch):
    """Not one of the three side effects may be reached: the key file open, the registry write."""
    f, _ = _seed(tmp_path)
    calls = []
    real_open = kg.os.open

    def spy_open(path, *a, **k):
        if str(path).endswith(".lock"):          # the registry lock (C-393) is not the key file
            return real_open(path, *a, **k)
        calls.append("open")
        return 3

    monkeypatch.setattr(kg.os, "open", spy_open)
    monkeypatch.setattr(kg, "write_registry", lambda *a, **k: calls.append("write_registry"))
    with pytest.raises(SystemExit):
        kg.main(["--operator-id", "don", "--add-to", str(f), "--key-file", str(tmp_path / "k")])
    assert calls == []


# --- the success path is unchanged --------------------------------------------------------------------


def test_success_with_a_key_file_registers_the_hash_of_the_key_in_the_file(tmp_path, capsys):
    f, _ = _seed(tmp_path)
    kf = tmp_path / "svc.key"
    assert kg.main(["--operator-id", "svc", "--scopes", "kill,revive", "--alias", "Svc One",
                    "--add-to", str(f), "--key-file", str(kf)]) == 0
    out = capsys.readouterr().out
    key = kf.read_text(encoding="utf-8").strip()
    sha = hashlib.sha256(key.encode()).hexdigest()
    rows = json.loads(f.read_text(encoding="utf-8"))
    row = next(r for r in rows if r["operator_id"] == "svc")
    assert row["key_sha256"] == sha and row["scopes"] == ["kill", "revive"] and row["names"] == ["Svc One"]
    assert [r["operator_id"] for r in rows] == ["don", "svc"]
    assert f"key written to {kf} (not printed)" in out and f"key_sha256: {sha}" in out
    assert f"registered sha256 for 'svc' in {f}" in out and key not in out


def test_success_printing_the_key_shows_it_once_and_registers_its_hash(tmp_path, capsys):
    f, _ = _seed(tmp_path)
    assert kg.main(["--operator-id", "svc", "--add-to", str(f)]) == 0
    out = capsys.readouterr().out
    key = [ln for ln in out.splitlines() if ln.startswith("fok_")][0]
    assert out.count(key) == 1 and out.index("KEY (shown once") < out.index(key) < out.index("key_sha256:")
    row = json.loads(f.read_text(encoding="utf-8"))[-1]
    assert row["operator_id"] == "svc" and row["key_sha256"] == hashlib.sha256(key.encode()).hexdigest()


def test_without_add_to_the_run_still_makes_a_key_and_registers_nothing(tmp_path, capsys):
    assert kg.main([]) == 0
    out = capsys.readouterr().out
    assert "fok_" in out and "register this sha256 in the operators file" in out


def test_an_existing_key_file_still_stops_the_run_before_the_registry_is_written(tmp_path, capsys):
    f, before = _seed(tmp_path)
    kf = tmp_path / "taken.key"
    kf.write_text("existing", encoding="utf-8")
    with pytest.raises(SystemExit, match="already exists"):             # C-412: an error: exit, not a traceback
        kg.main(["--operator-id", "svc", "--add-to", str(f), "--key-file", str(kf)])
    assert f.read_bytes() == before and kf.read_text(encoding="utf-8") == "existing"


def test_add_entry_still_writes_the_row_for_callers_that_use_it(tmp_path):
    f, _ = _seed(tmp_path)
    kg.add_entry(f, "svc", H2, ["kill"])
    assert json.loads(f.read_text(encoding="utf-8"))[-1]["key_sha256"] == H2
