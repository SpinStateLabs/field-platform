"""The replay reports the chain "intact" only for `ok is True` (scout S-C5). It used
`bool(verification.get("ok"))`, so {"ok": "false"} or {"ok": 1} read as intact. Anything
that is not a boolean is "unverified": no verification result, never intact, never a break."""
from __future__ import annotations

import pytest
from test_raci_from_data import Estate, StubLedgerHttp


@pytest.fixture
def estate(tmp_path):
    e = Estate(tmp_path)
    e.register()
    return e


def _replay(estate, verify_extra):
    return estate.replay(ledger_http=StubLedgerHttp(estate.ledger, verify_extra=verify_extra))


def test_the_clean_estate_is_intact(estate):
    assert estate.replay().ledger_integrity_status == "intact"


@pytest.mark.parametrize("ok", ["false", "true", "yes", 1, 2, 1.5, [0], ["x"], {"a": 1}])
def test_a_truthy_non_boolean_ok_is_never_intact(estate, ok):
    pm = _replay(estate, {"ok": ok})
    assert pm.ledger_integrity_status == "unverified"
    assert pm.ledger_integrity_ok is False
    assert pm.ledger_integrity_detail.startswith("INTEGRITY NOT VERIFIED")
    assert "intact" not in pm.ledger_integrity_detail.lower().replace("not verified", "")


@pytest.mark.parametrize("ok", [0, 0.0, "", None, [], {}])
def test_a_falsy_non_boolean_ok_is_unverified_too(estate, ok):
    assert _replay(estate, {"ok": ok}).ledger_integrity_status == "unverified"


def test_false_is_still_a_broken_chain(estate):
    pm = _replay(estate, {"ok": False, "reason": "link break at index 5"})
    assert pm.ledger_integrity_status == "broken"
    assert pm.ledger_integrity_detail == "CHAIN BROKEN: link break at index 5"


def test_the_detail_does_not_echo_the_value(estate):
    marker = "zz-marker-do-not-echo"
    assert marker not in _replay(estate, {"ok": marker}).ledger_integrity_detail
