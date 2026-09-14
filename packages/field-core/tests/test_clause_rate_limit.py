"""Pins the EXISTING clauses D1 cites (clause ids are never repurposed).

The sentinel's step 8 maps a governor THROTTLED status to BLOCK
``E.rate_limit``, and D1e's token spend ceiling BLOCKs ``E.spend_cap``. Both
ids predate D1; this test fails if either is removed or repurposed."""

from field_core.conformance import CLAUSES, ConformanceVerdict, Decision


def test_rate_limit_clause_exists_with_its_meaning():
    assert "E.rate_limit" in CLAUSES
    text = CLAUSES["E.rate_limit"]
    assert text.startswith("enforcement:")
    assert "rate limit" in text and "exhausted" in text


def test_spend_cap_clause_exists_with_its_meaning():
    assert CLAUSES["E.spend_cap"] == "enforcement: spend cap reached"


def test_rate_limit_verdict_round_trips_with_retry_context():
    verdict = ConformanceVerdict(
        decision=Decision.BLOCK, agent_id="a", action="draft invoices",
        clause_id="E.rate_limit", reasons=["rate limit"],
        context={"retry_after_seconds": 42},
    )
    again = ConformanceVerdict.model_validate_json(verdict.model_dump_json())
    assert again.clause_text() == CLAUSES["E.rate_limit"]
    assert again.context["retry_after_seconds"] == 42
