"""Key rotation slice R4a: diff_guard, the rotator's write policy (design 4.3,
S2, O8, invariant 6.3(6)). The rotator may change the header and the TARGET
row's key fields only: never a scope, a row, an id, a status, an alias, an
event prefix, a rotation, an auth list, and never the break-glass row. The one
format 1 -> format 2 migration may only ADD rotation / key_created_at /
key_not_after and normalise created_at's +00:00 form. Fake hashes only."""

from __future__ import annotations

import copy

import pytest

from field_core import rotation as rot

H = {n: (c * 64) for n, c in zip(("ks", "reg", "don", "bg", "new"), "abcde")}


def _doc():
    return {"format": 2, "generation": 5, "issued_at": "2026-11-20T03:00:00Z",
            "issued_by": "svc-rotator-gb10",
            "operators": [
                {"operator_id": "svc-killswitch", "status": "active", "rotation": "auto",
                 "scopes": ["kill", "revive"], "names": [], "event_prefixes": [],
                 "created_at": "2026-10-26T01:15:00Z", "key_sha256": H["ks"],
                 "key_created_at": "2026-10-26T01:15:00Z",
                 "key_not_after": "2027-01-09T01:15:00Z"},
                {"operator_id": "svc-registry", "status": "active", "rotation": "auto",
                 "scopes": ["registry_edit"], "key_sha256": H["reg"],
                 "key_not_after": "2027-01-09T01:15:00Z"},
                {"operator_id": "don", "status": "active", "rotation": "remote", "scopes": ["*"],
                 "names": ["Don Hagell"], "key_sha256": H["don"], "auth": ["key"],
                 "key_not_after": "2027-03-01T00:00:00Z"},
                {"operator_id": "don-breakglass", "status": "active", "rotation": "sealed",
                 "scopes": ["kill"], "key_sha256": H["bg"]}]}


def _cand(**header):
    c = copy.deepcopy(_doc())
    c["generation"] = 6
    c.update(header)
    return c


def test_target_key_fields_and_header_may_change():
    c = _cand(issued_at="2026-11-21T00:00:00Z")
    r = c["operators"][0]
    r["next_key"] = {"key_sha256": H["new"], "not_before": "2026-11-20T02:55:00Z",
                     "not_after": "2027-02-03T03:00:00Z"}
    r["key_not_after"] = "2026-11-20T04:15:00Z"
    rot.diff_guard(_doc(), c, ["svc-killswitch"])
    c2 = copy.deepcopy(c)
    c2["generation"] = 7
    c2["operators"][0]["key_sha256"] = H["new"]
    del c2["operators"][0]["next_key"]
    c2["operators"][0]["key_created_at"] = "2026-11-21T00:00:00Z"
    rot.diff_guard(c, c2, ["svc-killswitch"])


@pytest.mark.parametrize("row,field,value", [
    (0, "scopes", ["kill", "revive", "drill"]),          # a scope added on the target
    (0, "scopes", ["kill"]),                             # a scope removed on the target
    (1, "scopes", ["*"]),                                # a scope changed elsewhere
    (0, "status", "revoked"),
    (0, "names", ["Kill Switch"]),
    (0, "event_prefixes", ["kill."]),
    (0, "rotation", "remote"),
    (0, "auth", ["key", "session"]),
    (0, "created_at", "2026-10-27T01:15:00Z"),
    (0, "operator_id", "svc-killswitch-2"),
    (0, "passkeys", []),
    (2, "auth", ["session"]),
    (1, "key_sha256", H["new"]),                         # a key field of a NON-target row
    (1, "key_not_after", "2028-01-01T00:00:00Z"),
    (1, "next_key", {"key_sha256": H["new"], "not_before": "2026-11-20T02:55:00Z",
                     "not_after": "2027-02-03T03:00:00Z"}),
])
def test_anything_else_is_refused(row, field, value):
    c = _cand()
    c["operators"][row][field] = value
    with pytest.raises(rot.PolicyRefused):
        rot.diff_guard(_doc(), c, ["svc-killswitch"])


def test_a_removed_field_is_refused():
    c = _cand()
    del c["operators"][0]["names"]
    with pytest.raises(rot.PolicyRefused):
        rot.diff_guard(_doc(), c, ["svc-killswitch"])


@pytest.mark.parametrize("change", ["add", "remove", "reorder", "top", "top_removed"])
def test_rows_and_top_level_are_fixed(change):
    c = _cand()
    ops = c["operators"]
    if change == "add":
        ops.append({"operator_id": "svc-new", "status": "active", "rotation": "auto",
                    "scopes": ["*"], "key_sha256": "f" * 64,
                    "key_not_after": "2027-01-09T01:15:00Z"})
    elif change == "remove":
        ops.pop(1)
    elif change == "reorder":
        ops[0], ops[1] = ops[1], ops[0]
    elif change == "top":
        c["comment"] = "x"
    else:
        cur = _doc()
        cur["note"] = "y"
        with pytest.raises(rot.PolicyRefused):
            rot.diff_guard(cur, c, ["svc-killswitch"])
        return
    with pytest.raises(rot.PolicyRefused):
        rot.diff_guard(_doc(), c, ["svc-killswitch"])


@pytest.mark.parametrize("gen", [5, 4, "6", 6.0, None])
def test_generation_must_go_up(gen):
    c = _cand(generation=gen)
    with pytest.raises(rot.PolicyRefused):
        rot.diff_guard(_doc(), c, ["svc-killswitch"])


def test_the_break_glass_row_is_never_a_target():
    c = _cand()
    c["operators"][3]["key_sha256"] = H["new"]
    with pytest.raises(rot.PolicyRefused):
        rot.diff_guard(_doc(), c, ["don-breakglass"])
    d = _doc()
    d["operators"][3]["rotation"] = "auto"   # still the literal break-glass id
    c = copy.deepcopy(d)
    c["generation"] = 6
    with pytest.raises(rot.PolicyRefused):
        rot.diff_guard(d, c, ["don-breakglass"])


def test_format_rules():
    c = _cand(format=1)
    with pytest.raises(rot.PolicyRefused):
        rot.diff_guard(_doc(), c, ["svc-killswitch"])
    with pytest.raises(rot.PolicyRefused):
        rot.diff_guard(_doc()["operators"], _cand(), ["svc-killswitch"])   # live is format 1
    with pytest.raises(rot.PolicyRefused):
        rot.diff_guard(_doc(), _cand(), ["nobody"])                        # target missing


def _f1():
    return [{"operator_id": "svc-killswitch", "key_sha256": H["ks"], "status": "active",
             "created_at": "2026-10-26T01:15:00+00:00", "scopes": ["kill"], "names": []},
            {"operator_id": "don-breakglass", "key_sha256": H["bg"], "status": "active",
             "created_at": "2026-10-26T01:15:00+00:00", "scopes": ["kill"], "names": []}]


def _migrated():
    rows = copy.deepcopy(_f1())
    rows[0].update({"created_at": "2026-10-26T01:15:00Z", "rotation": "auto",
                    "key_created_at": "2026-10-26T01:15:00Z",
                    "key_not_after": "2027-02-03T00:00:00Z"})
    rows[1].update({"created_at": "2026-10-26T01:15:00Z", "rotation": "sealed",
                    "key_created_at": "2026-10-26T01:15:00Z"})
    return {"format": 2, "generation": 1, "issued_at": "2026-11-20T03:00:00Z",
            "issued_by": "svc-rotator-gb10", "operators": rows}


def test_migration_mode_allows_exactly_the_added_fields_and_the_z_form():
    rot.diff_guard(_f1(), _migrated(), [], migration=True)
    rot.diff_guard({"operators": _f1()}, _migrated(), [], migration=True)
    with pytest.raises(rot.PolicyRefused):
        rot.diff_guard(_f1(), _migrated(), [])            # not without migration mode
    with pytest.raises(rot.PolicyRefused):
        rot.diff_guard(_f1(), _migrated(), ["svc-killswitch"], migration=True)


@pytest.mark.parametrize("tamper", ["key", "next", "scope", "created_other", "created_shift",
                                    "drop_field", "status"])
def test_migration_mode_refuses_everything_else(tamper):
    m = _migrated()
    r = m["operators"][0]
    if tamper == "key":
        r["key_sha256"] = H["new"]
    elif tamper == "next":
        r["next_key"] = {"key_sha256": H["new"], "not_before": "2026-11-20T02:55:00Z",
                         "not_after": "2027-02-03T03:00:00Z"}
    elif tamper == "scope":
        r["scopes"] = ["*"]
    elif tamper == "created_other":
        r["created_at"] = "2026-10-26T01:15:01Z"
    elif tamper == "created_shift":
        r["created_at"] = "2026-10-26T00:15:00Z"
    elif tamper == "drop_field":
        del r["names"]
    else:
        r["status"] = "revoked"
    with pytest.raises(rot.PolicyRefused):
        rot.diff_guard(_f1(), m, [], migration=True)


def test_migration_from_a_format2_file_is_refused():
    with pytest.raises(rot.PolicyRefused):
        rot.diff_guard(_doc(), _cand(), [], migration=True)


def test_messages_never_carry_a_value():
    c = _cand()
    c["operators"][1]["key_sha256"] = H["new"]
    with pytest.raises(rot.PolicyRefused) as exc:
        rot.diff_guard(_doc(), c, ["svc-killswitch"])
    assert H["new"] not in str(exc.value) and H["reg"] not in str(exc.value)
    c = _cand()
    c["fok_pasted-key-as-field"] = 1
    with pytest.raises(rot.PolicyRefused) as exc:
        rot.diff_guard(_doc(), c, ["svc-killswitch"])
    assert "fok_" not in str(exc.value)
