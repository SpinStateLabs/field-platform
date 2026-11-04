"""S7-30 — FC-L-01 `ok` and FC-D-02 `revoked` count only as a JSON true, and FC-I-01 needs a non-blank
string owner. `sources` is caller-supplied on POST /crosswalk and /pack, so a string "false" must not
read as a verified chain or a revoked token in an evidence pack."""

from __future__ import annotations

import pytest

from compliance_crosswalk.engine import CONTROLS, EvidenceSources, _evidenced


def control(cid):
    return next(c for c in CONTROLS if c.control_id == cid)


def ev(cid, **src):
    return _evidenced(control(cid), EvidenceSources(**src), "agent-1")


# --- FC-L-01 -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("ok", ["false", "False", "yes", "true", 1, 0, 2, None, [], {}, "", 1.0])
def test_a_non_boolean_ok_is_not_verified(ok):
    evidenced, text = ev("FC-L-01", ledger_verify={"ok": ok, "reason": "r"})
    assert evidenced is False
    assert text.startswith("ledger verify failed")


def test_a_json_true_still_verifies():
    assert ev("FC-L-01", ledger_verify={"ok": True}) == (True, "ledger chain verified")


def test_an_explicit_false_and_a_missing_key_fail_with_the_reason():
    assert ev("FC-L-01", ledger_verify={"ok": False, "reason": "broken at 3"}) == (
        False, "ledger verify failed: broken at 3")
    assert ev("FC-L-01", ledger_verify={}) == (False, "ledger verify failed: None")
    assert ev("FC-L-01", registry_record={"owner": "x"}) == (False, "ledger verify failed: None")


# --- FC-D-02 -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("revoked", ["false", "no", "True", 1, 2, "x", [1], {"a": 1}, None, 0, ""])
def test_a_non_boolean_revoked_is_not_counted(revoked):
    evidenced, text = ev("FC-D-02", tokens=[{"revoked": revoked}])
    assert evidenced is False
    assert text == "0 revoke event(s), 0 revoked token(s)"


def test_a_json_true_revoked_counts():
    assert ev("FC-D-02", tokens=[{"revoked": True}, {"revoked": False}, {"revoked": "false"}]) == (
        True, "0 revoke event(s), 1 revoked token(s)")


def test_a_revoke_event_alone_still_evidences():
    assert ev("FC-D-02", ledger_event_types={"delegation.revoke": 2}) == (True, "2 revoke event(s), 0 revoked token(s)")


# --- FC-I-01 -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("owner", ["", " ", "  ", "\t\n", None, 5, True, ["a"], {"a": 1}])
def test_a_blank_or_non_string_owner_is_no_owner(owner):
    assert ev("FC-I-01", registry_record={"owner": owner}) == (False, "no owner on record")


def test_a_missing_owner_key_and_a_missing_record():
    assert ev("FC-I-01", registry_record={}) == (False, "no owner on record")
    assert ev("FC-I-01", governor_cap={}) == (False, "no owner on record")


@pytest.mark.parametrize("owner", ["Controller, Spin State Labs", " a ", "0"])
def test_a_real_owner_still_passes(owner):
    assert ev("FC-I-01", registry_record={"owner": owner}) == (True, "human owner on registry record")
