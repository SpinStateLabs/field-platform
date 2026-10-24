"""Phase G key tool: the key is shown once, only its sha256 is registered, and
nothing else (file, stderr) ever holds the key."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import operator_keygen as kg  # noqa: E402


def _key_from(out: str) -> str:
    return [ln for ln in out.splitlines() if ln.startswith("fok_")][0]


def test_prints_key_once_and_its_sha256(capsys):
    assert kg.main([]) == 0
    out = capsys.readouterr().out
    key = _key_from(out)
    sha = hashlib.sha256(key.encode()).hexdigest()
    assert out.count(key) == 1
    assert f"key_sha256: {sha}" in out
    assert len(key) >= 40


def test_keys_are_unique_and_high_entropy(capsys):
    seen = set()
    for _ in range(5):
        kg.main([])
        seen.add(_key_from(capsys.readouterr().out))
    assert len(seen) == 5


def test_add_to_writes_only_the_hash(tmp_path, capsys):
    f = tmp_path / "operators.json"
    assert kg.main(["--operator-id", "don", "--scopes", "kill,revive", "--add-to", str(f)]) == 0
    key = _key_from(capsys.readouterr().out)
    text = f.read_text()
    assert key not in text
    row = json.loads(text)[0]
    assert row["operator_id"] == "don" and row["scopes"] == ["kill", "revive"]
    assert row["key_sha256"] == hashlib.sha256(key.encode()).hexdigest()
    assert row["status"] == "active"


def test_key_file_mode_keeps_the_key_off_stdout(tmp_path, capsys):
    kf = tmp_path / "don.key"
    assert kg.main(["--key-file", str(kf)]) == 0
    captured = capsys.readouterr()
    key = kf.read_text().strip()
    assert key.startswith("fok_") and key not in captured.out + captured.err
    with pytest.raises(FileExistsError):
        kg.main(["--key-file", str(kf)])  # exclusive create: never overwrites


def test_second_active_key_for_an_operator_is_refused(tmp_path, capsys):
    f = tmp_path / "operators.json"
    kg.main(["--operator-id", "don", "--add-to", str(f)])
    with pytest.raises(SystemExit):
        kg.main(["--operator-id", "don", "--add-to", str(f)])


def test_unknown_scope_and_bad_id_are_refused(capsys):
    assert kg.main(["--scopes", "launch-missiles"]) == 2
    assert kg.main(["--operator-id", "bad id!"]) == 2


def test_alias_flag_writes_names_without_the_key(tmp_path, capsys):
    f = tmp_path / "operators.json"
    assert kg.main(["--operator-id", "don", "--add-to", str(f),
                    "--alias", "Don Hagell", "--alias", "Don Hagell, Spin State Labs"]) == 0
    key = _key_from(capsys.readouterr().out)
    text = f.read_text()
    assert key not in text
    assert json.loads(text)[0]["names"] == ["Don Hagell", "Don Hagell, Spin State Labs"]


def test_overlong_alias_is_refused_before_a_key_is_made(capsys):
    assert kg.main(["--alias", "x" * 129]) == 2
    assert "fok_" not in capsys.readouterr().out


def test_keygen_refuses_ambiguous_rows(tmp_path, capsys):
    f = tmp_path / "operators.json"
    assert kg.main(["--operator-id", "don", "--add-to", str(f)]) == 0
    for args in (["--operator-id", "don"],                                   # duplicate id
                 ["--operator-id", "mallory", "--alias", "don"],              # alias == an id
                 ["--operator-id", "mallory", "--alias", "*"]):
        with pytest.raises(SystemExit):
            kg.main(args + ["--add-to", str(f)])
    assert kg.main(["--operator-id", "x1", "--alias", "Shared", "--add-to", str(f)]) == 0
    with pytest.raises(SystemExit):
        kg.main(["--operator-id", "x2", "--alias", "Shared", "--add-to", str(f)])
    assert [r["operator_id"] for r in json.loads(f.read_text())] == ["don", "x1"]
