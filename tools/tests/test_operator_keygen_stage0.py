"""Phase G Stage 0 (C-18, C-10): operator_keygen writes the operators file
temp-then-rename and only when the result passes the registry checks; --check
runs the services' validation and prints ids, status and fingerprints only;
--event-prefix writes the ledger_attribute reach. Test keys are generated per
test and never printed by the test."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import operator_keygen as kg  # noqa: E402

HEX64 = re.compile(r"[0-9a-f]{64}")


def _sha(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _row(oid, sha, status="active", **kw):
    return {"operator_id": oid, "key_sha256": sha, "status": status,
            "created_at": "2026-10-25", "scopes": ["kill"], **kw}


def _write(tmp_path, doc, name="operators.json"):
    p = tmp_path / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


# --- write temp-then-rename ----------------------------------------------------------


def test_add_to_replaces_the_file_by_rename_and_a_failed_rename_leaves_it_intact(tmp_path, monkeypatch, capsys):
    f = tmp_path / "operators.json"
    assert kg.main(["--operator-id", "don", "--add-to", str(f)]) == 0
    before = f.read_bytes()
    calls = []

    def failing_replace(src, dst):
        calls.append((Path(src).parent, Path(dst)))
        raise OSError("simulated crash before the rename")

    monkeypatch.setattr(kg.os, "replace", failing_replace)
    with pytest.raises(SystemExit) as exc:             # C-305: an `error:` exit, no longer an OSError traceback
        kg.main(["--operator-id", "svc", "--scopes", "kill", "--add-to", str(f)])
    assert str(exc.value).startswith("error: cannot write ")
    assert calls == [(tmp_path, f)]                    # temp file in the SAME directory
    assert f.read_bytes() == before                    # never truncated or half written
    # the temp file is removed; the registry lock file stays beside the registry by design (C-393)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["operators.json", "operators.json.lock"]
    capsys.readouterr()


def test_add_to_keeps_the_object_form_and_a_bom(tmp_path, capsys):
    f = tmp_path / "operators.json"
    f.write_bytes(b"\xef\xbb\xbf" + json.dumps({"operators": []}).encode())
    assert kg.main(["--operator-id", "don", "--add-to", str(f)]) == 0
    doc = json.loads(f.read_text(encoding="utf-8"))
    assert list(doc) == ["operators"] and doc["operators"][0]["operator_id"] == "don"
    capsys.readouterr()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_add_to_keeps_the_files_permission_bits(tmp_path, capsys):
    f = tmp_path / "operators.json"
    f.write_text("[]", encoding="utf-8")
    os.chmod(f, 0o640)
    assert kg.main(["--operator-id", "don", "--add-to", str(f)]) == 0
    assert (f.stat().st_mode & 0o777) == 0o640
    capsys.readouterr()


def test_add_to_refuses_a_file_the_services_would_reject(tmp_path, capsys):
    f = _write(tmp_path, [{"operator_id": "old", "key_sha256": "a" * 64, "scopes": ["*"]}])  # no status
    before = f.read_bytes()
    with pytest.raises(SystemExit) as e:
        kg.main(["--operator-id", "don", "--add-to", str(f)])
    assert "status is missing" in str(e.value.code)
    assert f.read_bytes() == before
    capsys.readouterr()


# --- --check --------------------------------------------------------------------------


def test_check_prints_ids_status_and_fingerprints_only(tmp_path, capsys):
    f = tmp_path / "operators.json"
    assert kg.main(["--operator-id", "don", "--alias", "Don Hagell", "--add-to", str(f)]) == 0
    assert kg.main(["--operator-id", "svc-registry", "--scopes", "ledger_attribute",
                    "--event-prefix", "registry.", "--add-to", str(f)]) == 0
    capsys.readouterr()
    doc = json.loads(f.read_text())
    doc[1]["status"] = "revoked"
    f.write_text(json.dumps(doc), encoding="utf-8")
    assert kg.main(["--check", str(f)]) == 0
    cap = capsys.readouterr()
    out = cap.out
    assert re.search(r"^\s+don\s+active\s+fingerprint " + doc[0]["key_sha256"][:8] + "$", out, re.M)
    assert re.search(r"^\s+svc-registry\s+revoked\s+fingerprint " + doc[1]["key_sha256"][:8] + "$",
                     out, re.M)
    assert "rows: 2 (active 1, revoked 1)" in out
    assert hashlib.sha256(f.read_bytes()).hexdigest()[:16] in out
    assert not HEX64.search(out + cap.err)             # no full hash anywhere
    for r in doc:
        assert r["key_sha256"][8:16] not in out         # nothing beyond the fingerprint
    assert "fok_" not in out                           # --check makes no key
    assert "Don Hagell" not in out and "registry." not in out and "ledger_attribute" not in out


BAD_DOCS = {
    "missing-status": [{"operator_id": "don", "key_sha256": "b" * 64, "scopes": ["*"]}],
    "capital-status": [_row("don", "b" * 64, status="Active")],
    "upper-hex": [_row("don", "B" * 64)],
    "zero-rows": {"operators": []},
    "all-revoked": [_row("don", "b" * 64, status="revoked")],
    "duplicate-id": [_row("don", "b" * 64), _row("don", "c" * 64)],
    "bad-prefix": [_row("svc", "b" * 64, scopes=["ledger_attribute"], event_prefixes=["operator."])],
}


@pytest.mark.parametrize("name", sorted(BAD_DOCS))
def test_check_rejects_what_the_services_reject_without_printing_hashes(tmp_path, capsys, name):
    f = _write(tmp_path, BAD_DOCS[name])
    assert kg.main(["--check", str(f)]) == 1
    cap = capsys.readouterr()
    assert cap.err.startswith("error: ")
    assert not HEX64.search(cap.out + cap.err) and not re.search(r"[0-9a-fA-F]{32}", cap.out + cap.err)
    assert "OK:" not in cap.out


@pytest.mark.parametrize("content", [None, b"garbage", b"\xff\xfe"])
def test_check_unreadable_or_non_json_file_is_exit_1(tmp_path, capsys, content):
    f = tmp_path / "operators.json"
    if content is not None:
        f.write_bytes(content)
    assert kg.main(["--check", str(f)]) == 1
    assert capsys.readouterr().err.startswith("error: ")


@pytest.mark.parametrize("extra", [["--operator-id", "x"], ["--add-to", "y.json"],
                                   ["--scopes", "kill"], ["--key-file", "k"], ["--alias", "A"],
                                   ["--event-prefix", "kill."]])
def test_check_takes_no_other_option_and_makes_no_key(tmp_path, capsys, extra):
    f = _write(tmp_path, [_row("don", "b" * 64)])
    assert kg.main(["--check", str(f)] + extra) == 2
    out = capsys.readouterr().out
    assert "fok_" not in out
    assert not (tmp_path / "k").exists()


# --- --event-prefix (C-10) ------------------------------------------------------------


def test_event_prefix_is_written_for_a_ledger_attribute_row(tmp_path, capsys):
    f = tmp_path / "operators.json"
    assert kg.main(["--operator-id", "svc-killswitch", "--scopes",
                    "kill,revive,drill,bypass_operator_list,ledger_attribute",
                    "--event-prefix", "kill.", "--add-to", str(f)]) == 0
    capsys.readouterr()
    row = json.loads(f.read_text())[0]
    assert row["event_prefixes"] == ["kill."]
    assert row["scopes"] == ["kill", "revive", "drill", "bypass_operator_list", "ledger_attribute"]
    assert kg.main(["--check", str(f)]) == 0


@pytest.mark.parametrize("args", [
    ["--scopes", "ledger_attribute"],                                  # no prefix: attributes nothing
    ["--scopes", "kill", "--event-prefix", "kill."],                  # prefix without the scope
    ["--scopes", "ledger_attribute", "--event-prefix", "operator."],  # reserved namespace
    ["--scopes", "ledger_attribute", "--event-prefix", "kill"],       # must end in '.'
    ["--scopes", "ledger_attribute", "--event-prefix", "Kill."],
])
def test_bad_event_prefix_usage_is_refused_before_a_key_is_made(tmp_path, capsys, args):
    f = tmp_path / "operators.json"
    assert kg.main(["--operator-id", "svc"] + args + ["--add-to", str(f)]) == 2
    assert "fok_" not in capsys.readouterr().out
    assert not f.exists()


def test_assert_operator_scope_is_refused_before_a_key_is_made(tmp_path, capsys):
    f = tmp_path / "operators.json"
    assert kg.main(["--operator-id", "svc", "--scopes", "kill,assert_operator", "--add-to", str(f)]) == 2
    assert "fok_" not in capsys.readouterr().out
    assert not f.exists()


def test_check_rejects_a_file_that_still_grants_assert_operator(tmp_path, capsys):
    f = _write(tmp_path, [_row("svc", "b" * 64, scopes=["kill", "assert_operator"])])
    assert kg.main(["--check", str(f)]) == 1
    assert "assert_operator" in capsys.readouterr().err


# --- PG0-CORE-R1-03: --check never echoes a status value ------------------------------

#: A base64url-looking test constant shaped like a 47-char operator key (fok_ + 43),
#: as if a field swap had put a key into ``status``. Not a key.
SWAPPED_STATUS = "fok_" + "Tq9xWv3LkR7bN2mYc8HdZp4sGf6uJe1aXo5iKt0QwEr"


def test_check_never_prints_a_key_shaped_status_value(tmp_path, capsys):
    assert len(SWAPPED_STATUS) == 47
    f = _write(tmp_path, [_row("don", "b" * 64), _row("svc", "c" * 64, status=SWAPPED_STATUS)])
    assert kg.main(["--check", str(f)]) == 1
    cap = capsys.readouterr()
    both = cap.out + cap.err
    assert cap.err.startswith("error: ") and "row 2 ('svc')" in cap.err
    assert "status must be 'active' or 'revoked'" in cap.err
    for i in range(len(SWAPPED_STATUS) - 4):
        assert SWAPPED_STATUS[i:i + 5] not in both


# --- PG0-CORE-R1-10: --check never echoes a key-shaped operator_id ----------------------

#: fok_ + 43 base64url characters, inside the operator id charset: as if a field swap
#: had put a key into ``operator_id``. Not a key.
SWAPPED_ID = "fok_" + "Hn3Lq8ZrWb2Vt6Ck9Yp1Xs4Df7Gm0Ja5Ue2Ri8Oz3Ny"


def _no_window(text):
    for i in range(len(SWAPPED_ID) - 4):
        assert SWAPPED_ID[i:i + 5] not in text


def test_check_never_prints_a_key_shaped_operator_id_on_a_bad_row(tmp_path, capsys):
    f = _write(tmp_path, [_row("don", "b" * 64), _row(SWAPPED_ID, "c" * 64, status="Active")])
    assert kg.main(["--check", str(f)]) == 1
    cap = capsys.readouterr()
    assert cap.err.startswith("error: ") and "row 2 (id not shown)" in cap.err
    _no_window(cap.out + cap.err)


def test_check_masks_a_key_shaped_operator_id_in_the_listing(tmp_path, capsys):
    f = _write(tmp_path, [_row("don", "b" * 64), _row(SWAPPED_ID, "c" * 64)])
    assert kg.main(["--check", str(f)]) == 0
    cap = capsys.readouterr()
    assert "don" in cap.out and "(not shown)" in cap.out and "fingerprint cccccccc" in cap.out
    _no_window(cap.out + cap.err)
