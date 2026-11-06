"""G27: d16_record_check finds Don's positive write in the ledger and never prints key material.

Every id, hash and fingerprint here is made up."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import d16_record_check as dc  # noqa: E402

OP = "don"
KEY = "fok_" + "A1b2C3d4" * 4          # a made-up key; must never be printed
KEY_SHA = "f" * 64                      # a made-up key hash; must never be printed
H = "0123456789abcdef" * 4


def row(**payload):
    return {"event_type": "kill.revive", "agent_id": "canary-gb10", "hash": H, "payload": payload}


SIGNED = row(operator_id_authenticated=OP, operator_claimed="Don H", operator_key_fp="0a1b2c3d")


def run(tmp_path, capsys, events, *extra):
    f = tmp_path / "events.json"
    f.write_text(json.dumps(events), encoding="utf-8")
    code = dc.main(["--operator-id", OP, "--events", str(f), *extra])
    return code, capsys.readouterr().out


def test_a_signed_authenticated_row_passes_and_prints_ids_and_a_hash_prefix_only(tmp_path, capsys):
    ev = dict(SIGNED)
    ev["payload"] = {**SIGNED["payload"], "key": KEY, "key_sha256": KEY_SHA, "secret": "S3CRET-VALUE"}
    code, out = run(tmp_path, capsys, [ev])
    assert code == 0 and "[PASS] D16 positive write recorded" in out
    assert H[:12] in out and H[:13] not in out
    for forbidden in (KEY, KEY_SHA, "S3CRET-VALUE", "0a1b2c3d"):
        assert forbidden not in out


def test_a_claimed_name_only_row_fails(tmp_path, capsys):
    code, out = run(tmp_path, capsys, [row(operator_claimed=OP)])
    assert code == 1 and "[FAIL] D16 positive write recorded" in out and "CLAIM only" in out


@pytest.mark.parametrize("payload", [
    {"operator_id_authenticated": OP, "operator_key_fp": "0a1b2c3d"},                       # no claimed name
    {"operator_id_authenticated": OP, "operator_claimed": "", "operator_key_fp": "0a1b2c3d"},
    {"operator_id_authenticated": OP, "operator_claimed": "Don H"},                          # no fingerprint
    {"operator_id_authenticated": OP, "operator_claimed": "Don H", "operator_key_fp": "XYZ"},
    {"operator_id_authenticated": "someone-else", "operator_claimed": "Don H", "operator_key_fp": "0a1b2c3d"},
], ids=["no-claim", "empty-claim", "no-fp", "bad-fp", "other-id"])
def test_an_incomplete_or_foreign_row_is_not_proof(tmp_path, capsys, payload):
    assert run(tmp_path, capsys, [row(**payload)])[0] == 1


def test_an_empty_ledger_fails(tmp_path, capsys):
    assert run(tmp_path, capsys, [])[0] == 1


def test_a_wrapped_events_object_is_accepted(tmp_path, capsys):
    f = tmp_path / "e.json"
    f.write_text(json.dumps({"events": [SIGNED]}), encoding="utf-8")
    assert dc.main(["--operator-id", OP, "--events", str(f)]) == 0


def test_a_key_given_as_the_id_is_refused_and_not_echoed(tmp_path, capsys):
    code = dc.main(["--operator-id", KEY, "--events", str(tmp_path / "x.json")])
    assert code == 2 and KEY not in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["--events", "x", "--base", "http://h"], ["--base", "http://h"]])
def test_usage_errors_exit_2(argv, capsys):
    assert dc.main(["--operator-id", OP, *argv]) == 2


def test_an_unreadable_events_file_exits_2(tmp_path, capsys):
    assert dc.main(["--operator-id", OP, "--events", str(tmp_path / "missing.json")]) == 2


def test_a_hostile_event_type_or_hash_is_not_printed(tmp_path, capsys):
    ev = row(operator_id_authenticated=OP, operator_claimed="Don H", operator_key_fp="0a1b2c3d")
    ev["event_type"] = "evil\nINJECT " + KEY
    ev["hash"] = "not-a-hash " + KEY
    code, out = run(tmp_path, capsys, [ev])
    assert code == 0 and KEY not in out and "INJECT" not in out and "(no hash)" in out
