"""G17 (repo side): the ten-row operators file TEMPLATE and the checks that guard its shape.

The template holds placeholder hashes only (all zero but the last digit). Don generates the real keys; this test uses
hashes of keys it generates itself, never prints them, and never touches an estate. ``operator_keygen.py --check`` is
the services' own registry validation."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import secrets
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import operator_keygen as kg  # noqa: E402

TEMPLATE = ROOT / "docs" / "templates" / "operators.g17-template.json"
REQUIRED_IDS = ("don", "don-admin", "don-breakglass", "svc-killswitch", "svc-lifecycle", "svc-registry",
                "svc-delegation", "job-provision-gb10", "job-renewal-gb10", "job-renewal-rog")
PLACEHOLDER = re.compile(r"^0{63}[0-9a-f]$")


def load() -> list[dict]:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def with_test_hashes(rows: list[dict]) -> list[dict]:
    out = copy.deepcopy(rows)
    for r in out:
        r["key_sha256"] = hashlib.sha256(("fok_" + secrets.token_hex(16)).encode()).hexdigest()
    return out


def write(tmp_path: Path, rows, name="operators.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


def missing_ids(path: Path) -> list[str]:
    """The ten ids the Stage 0 checklist (items 10, 11) names; keygen --check validates rows, not the roster."""
    have = {r.get("operator_id") for r in json.loads(path.read_text(encoding="utf-8"))}
    return [i for i in REQUIRED_IDS if i not in have]


def test_the_template_holds_exactly_the_ten_ids_in_order_with_placeholder_hashes_only():
    rows = load()
    assert tuple(r["operator_id"] for r in rows) == REQUIRED_IDS
    assert all(PLACEHOLDER.fullmatch(r["key_sha256"]) for r in rows)
    assert len({r["key_sha256"] for r in rows}) == 10


def test_the_template_and_a_copy_with_generated_test_hashes_pass_keygen_check(tmp_path, capsys):
    assert kg.check_file(TEMPLATE) == 0
    assert "rows: 10 (active 10, revoked 0)" in capsys.readouterr().out
    p = write(tmp_path, with_test_hashes(load()))
    assert kg.check_file(p) == 0 and missing_ids(p) == []


@pytest.mark.parametrize("oid", REQUIRED_IDS)
def test_a_file_missing_any_one_of_the_ten_ids_is_refused(tmp_path, oid):
    rows = [r for r in with_test_hashes(load()) if r["operator_id"] != oid]
    assert missing_ids(write(tmp_path, rows)) == [oid]


def test_no_row_holds_assert_operator_and_keygen_refuses_one_that_does(tmp_path, capsys):
    assert all("assert_operator" not in r["scopes"] for r in load())
    rows = with_test_hashes(load())
    rows[3]["scopes"] = rows[3]["scopes"] + ["assert_operator"]
    assert kg.check_file(write(tmp_path, rows)) == 1
    assert "assert_operator" in capsys.readouterr().err


def test_keygen_refuses_a_verifier_scoped_row_without_the_svc_verifier_prefix(tmp_path, capsys):
    rows = with_test_hashes(load())
    rows[0]["scopes"] = ["kill", "revive", "revoke", "mint", "mint_for_others"]          # the machine verifier's scope set
    assert kg.check_file(write(tmp_path, rows)) == 1
    assert "svc-verifier-" in capsys.readouterr().err


def test_the_template_is_not_the_installed_file_and_names_no_estate_address():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert not re.search(r"\d+\.\d+\.\d+\.\d+|https?://|fok_", text)


def test_service_rows_reach_only_their_own_event_prefixes_and_jobs_hold_no_bypass_or_registry_edit():
    by = {r["operator_id"]: r for r in load()}
    assert by["svc-registry"]["event_prefixes"] == ["registry."] and by["svc-delegation"]["event_prefixes"] == ["delegation."]
    for jid in ("job-provision-gb10", "job-renewal-gb10", "job-renewal-rog"):       # G21 decision: no registry_edit, no bypass
        assert not {"registry_edit", "bypass_operator_list"} & set(by[jid]["scopes"])
    assert "registry_edit" in by["don-admin"]["scopes"] and "registry_edit" not in by["don"]["scopes"]


# G17 scope pins (reviewer-10 found these seven mutations survived): the scopes that matter are pinned per row, and each
# mutant below removes or adds exactly one of them and must be reported.
def scope_pin_violations(rows: list[dict]) -> list[str]:
    by = {r["operator_id"]: r for r in rows}
    bad = []
    if {"kill", "revive"} & set(by["don-admin"]["scopes"]):
        bad.append("don-admin holds kill or revive")
    if "mint_for_others" in by["job-renewal-gb10"]["scopes"]:
        bad.append("job-renewal-gb10 holds mint_for_others")
    if "mint_for_others" not in by["job-provision-gb10"]["scopes"]:
        bad.append("job-provision-gb10 lacks mint_for_others")
    if "bypass_operator_list" in by["svc-registry"]["scopes"]:
        bad.append("svc-registry holds bypass_operator_list")
    if "bypass_operator_list" not in by["svc-killswitch"]["scopes"]:
        bad.append("svc-killswitch lacks bypass_operator_list")
    if by["svc-lifecycle"].get("event_prefixes") != ["lifecycle.", "orphan."]:
        bad.append("svc-lifecycle event prefixes are not lifecycle. and orphan.")
    if set(by["don-breakglass"]["scopes"]) != {"kill", "revive", "bypass_operator_list"}:
        bad.append("don-breakglass is not exactly kill, revive, bypass_operator_list")
    return bad


def _mutate(rows, oid, fn):
    out = copy.deepcopy(rows)
    fn(next(r for r in out if r["operator_id"] == oid))
    return out


def test_the_template_satisfies_every_scope_pin():
    assert scope_pin_violations(load()) == []


@pytest.mark.parametrize("oid,fn,expect", [
    ("don-admin", lambda r: r["scopes"].extend(["kill", "revive"]), "don-admin"),
    ("job-renewal-gb10", lambda r: r["scopes"].append("mint_for_others"), "job-renewal-gb10 holds"),
    ("job-provision-gb10", lambda r: r["scopes"].remove("mint_for_others"), "job-provision-gb10 lacks"),
    ("svc-registry", lambda r: r["scopes"].append("bypass_operator_list"), "svc-registry"),
    ("svc-killswitch", lambda r: r["scopes"].remove("bypass_operator_list"), "svc-killswitch lacks"),
    ("svc-lifecycle", lambda r: r["event_prefixes"].remove("orphan."), "svc-lifecycle"),
    ("don-breakglass", lambda r: r["scopes"].remove("bypass_operator_list"), "don-breakglass"),
])
def test_each_scope_pin_fails_when_its_one_scope_moves(oid, fn, expect):
    got = scope_pin_violations(_mutate(load(), oid, fn))
    assert len(got) == 1 and expect in got[0], got
