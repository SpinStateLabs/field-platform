"""Key rotation slice R1: operator_keygen --check on an operators file in
format 2 prints ids, slots, windows and 8-hex fingerprints only (never a full
hash), and --add-to refuses a format 2 file. Every key is a fake test value."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import operator_keygen as kg  # noqa: E402
from field_core import operator_auth as oa  # noqa: E402

HEX64 = re.compile(r"[0-9a-f]{64}")
K_CUR = "fok_test-current-not-a-real-key"
K_NEXT = "fok_test-next-not-a-real-key"
K_BG = "fok_test-breakglass-not-a-real-key"


def _sha(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _doc() -> dict:
    return {"format": 2, "generation": 7, "issued_at": "2026-11-20T03:12:09Z",
            "issued_by": "svc-rotator-gb10",
            "operators": [
                {"operator_id": "svc-killswitch", "status": "active", "scopes": ["kill"],
                 "rotation": "auto", "key_sha256": _sha(K_CUR),
                 "key_not_after": "2027-01-09T01:15:00Z",
                 "next_key": {"key_sha256": _sha(K_NEXT), "not_before": "2026-11-20T03:07:09Z",
                              "not_after": "2027-02-03T03:12:09Z"}},
                {"operator_id": "don-breakglass", "status": "active", "scopes": ["kill"],
                 "rotation": "sealed", "key_sha256": _sha(K_BG)}]}


def _write(tmp_path, doc):
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def _now(monkeypatch):
    monkeypatch.setattr(oa, "clock", lambda: oa.parse_time("2026-11-20T03:00:00Z"))


def test_check_format2_prints_slots_windows_and_fingerprints_only(tmp_path, capsys):
    p = _write(tmp_path, _doc())
    assert kg.main(["--check", str(p)]) == 0
    out, err = capsys.readouterr()
    assert "format: 2  generation: 7" in out
    assert "issued: 2026-11-20T03:12:09Z by svc-rotator-gb10" in out
    assert f"current  fingerprint {_sha(K_CUR)[:8]}  until 2027-01-09T01:15:00Z  valid now" in out
    assert (f"next     fingerprint {_sha(K_NEXT)[:8]}  from 2026-11-20T03:07:09Z until "
            "2027-02-03T03:12:09Z  not yet valid") in out
    assert f"current  fingerprint {_sha(K_BG)[:8]}  no expiry (sealed)" in out
    assert "rotation sealed" in out and "rotation auto" in out
    assert "rows: 2 (active 2, revoked 0)" in out and out.rstrip().endswith("(format 2)")
    assert not HEX64.search(out + err)
    for key in (K_CUR, K_NEXT, K_BG):
        assert key not in out + err


def test_check_format2_marks_expired_slots(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(oa, "clock", lambda: oa.parse_time("2027-01-09T01:15:00Z"))
    p = _write(tmp_path, _doc())
    assert kg.main(["--check", str(p)]) == 0
    out = capsys.readouterr().out
    assert "until 2027-01-09T01:15:00Z  EXPIRED" in out
    assert "2027-02-03T03:12:09Z  valid now" in out


def test_check_format2_invalid_file_names_the_rule_never_a_hash(tmp_path, capsys):
    d = _doc()
    d["operators"][1]["rotation"] = "auto"
    d["operators"][0]["rotation"] = "sealed"
    p = _write(tmp_path, d)
    assert kg.main(["--check", str(p)]) == 1
    out, err = capsys.readouterr()
    assert "error:" in err and not HEX64.search(out + err)
    d = _doc()
    d["operators"][0]["next_key"]["key_sha256"] = _sha(K_BG)    # duplicate hash
    assert kg.main(["--check", str(_write(tmp_path, d))]) == 1
    out, err = capsys.readouterr()
    assert "appears twice" in err and not HEX64.search(out + err)


def test_check_format1_output_is_unchanged(tmp_path, capsys):
    rows = [{"operator_id": "don", "key_sha256": _sha(K_CUR), "status": "active",
             "created_at": "2026-10-25", "scopes": ["*"]}]
    assert kg.main(["--check", str(_write(tmp_path, rows))]) == 0
    out = capsys.readouterr().out
    assert "format:" not in out and "rotation" not in out
    assert f"  don  active   fingerprint {_sha(K_CUR)[:8]}" in out
    assert out.rstrip().endswith("passes the registry validation the services apply under REQUIRE")


@pytest.mark.parametrize("extra", [{"generation": 3}, {"issued_at": "2026-11-20T03:12:09Z"},
                                   {"issued_by": "svc-rotator-gb10"}, {"format": "2"},
                                   {"format": True}, {"format": 3}])
def test_add_to_refuses_a_format1_dict_the_services_refuse(tmp_path, extra):
    """Review F4: --add-to validates the whole document it writes, so a format 1
    dict carrying a field the services refuse is never written back."""
    d = {"operators": [{"operator_id": "don", "key_sha256": _sha(K_CUR), "status": "active",
                        "scopes": ["*"]}], **extra}
    p = _write(tmp_path, d)
    before = p.read_bytes()
    with pytest.raises(SystemExit) as e:
        kg.add_entry(p, "svc-new", "a" * 64, ["kill"])
    assert "refusing to write an invalid registry" in str(e.value.code)
    assert p.read_bytes() == before


def test_add_to_still_extends_a_format1_dict(tmp_path):
    d = {"format": 1, "operators": [{"operator_id": "don", "key_sha256": _sha(K_CUR),
                                     "status": "active", "scopes": ["*"]}]}
    p = _write(tmp_path, d)
    kg.add_entry(p, "svc-new", "a" * 64, ["kill"])
    out = json.loads(p.read_text(encoding="utf-8"))
    assert out["format"] == 1
    assert [r["operator_id"] for r in out["operators"]] == ["don", "svc-new"]
    assert len(oa.parse_registry(out)) == 2


def test_add_to_names_the_format2_refusal(tmp_path):
    """The format 2 refusal comes from its own check (with its own advice), not
    only from the whole-document validation that would also refuse it."""
    p = _write(tmp_path, _doc())
    with pytest.raises(SystemExit) as e:
        kg.add_entry(p, "svc-new", "a" * 64, ["kill"])
    assert "--add-to does not edit a format 2 operators file" in str(e.value.code)


def test_add_to_refuses_a_format2_file(tmp_path, capsys):
    p = _write(tmp_path, _doc())
    before = p.read_bytes()
    with pytest.raises(SystemExit) as e:
        kg.add_entry(p, "svc-new", "a" * 64, ["kill"])
    assert "format 2" in str(e.value.code)
    assert p.read_bytes() == before
