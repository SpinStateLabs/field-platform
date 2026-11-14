"""Key rotation slice R4a, carry-forward F4: ``operator_keygen.py --add-to``
never writes an operators file the R1 parser refuses, and for an entry it
cannot register it makes no key at all (nothing printed, no --key-file
written). Every value here is a fake test value."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import operator_keygen as kg  # noqa: E402
from field_core import operator_auth as oa  # noqa: E402

REFUSED = [
    {"format": 2, "generation": 1, "operators": []},                    # format 2: the rotator's
    {"generation": 3, "operators": []},                                 # a format 2 field in format 1
    {"format": "2", "operators": []},                                   # format not the integer 1 or 2
    [{"operator_id": "x", "key_sha256": "a" * 64, "status": "Active"}],  # a row R1 refuses
]


@pytest.mark.parametrize("doc", REFUSED)
def test_add_to_a_refused_file_makes_no_key_and_writes_nothing(tmp_path, capsys, doc):
    f = tmp_path / "operators.json"
    f.write_text(json.dumps(doc), encoding="utf-8")
    before = f.read_bytes()
    kf = tmp_path / "new.key"
    with pytest.raises(SystemExit):
        kg.main(["--operator-id", "svc-new", "--scopes", "kill", "--key-file", str(kf),
                 "--add-to", str(f)])
    assert f.read_bytes() == before
    assert not kf.exists()
    out = capsys.readouterr().out
    assert "KEY" not in out and oa.KEY_PREFIX not in out and "key_sha256" not in out


def test_add_to_a_duplicate_id_makes_no_key(tmp_path, capsys):
    f = tmp_path / "operators.json"
    assert kg.main(["--operator-id", "don", "--add-to", str(f)]) == 0
    capsys.readouterr()
    with pytest.raises(SystemExit):
        kg.main(["--operator-id", "don", "--add-to", str(f)])
    assert oa.KEY_PREFIX not in capsys.readouterr().out


def test_every_file_add_to_writes_parses(tmp_path):
    f = tmp_path / "operators.json"
    for i, scopes in enumerate(["kill", "*", "registry_edit"]):
        assert kg.main(["--operator-id", f"op{i}", "--scopes", scopes, "--add-to", str(f)]) == 0
        oa.parse_registry_doc(json.loads(f.read_text()), require_active=True)
