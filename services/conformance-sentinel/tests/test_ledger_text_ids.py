"""Free text the sentinel puts into ledger rows is never cut inside an id."""
import pytest

from tests.test_judge import _arm

TID = "7d3f9a1c-52be-4c08-9e6a-1b2c3d4e5f60"
KEPT = [1, 9, 20, 35]


@pytest.mark.parametrize("kept", KEPT)
def test_a_judges_rationale(stack, kept):
    before = "z" * (300 - kept)
    _arm(stack, rules={"read the new timesheets": (True, 0.1, before + TID + " end")})
    token = stack.mint_token()
    verdict = stack.check("read the new timesheets", token_id=token)
    reasons = " ".join(verdict["reasons"])
    assert before in reasons and TID[:9] not in reasons and before + TID[:1] not in reasons


@pytest.mark.parametrize("kept", KEPT)
def test_a_metering_gap_error(stack, monkeypatch, kept):
    stack.set_cap()
    token = stack.mint_token()
    engine = stack.sentinel.app.state.engine
    before = "z" * (300 - kept)
    rows = []
    real = engine.ledger.append

    def spy(event_type, *args, **kwargs):
        rows.append((event_type, kwargs.get("payload")))
        return real(event_type, *args, **kwargs)

    def broken(*args, **kwargs):
        raise ConnectionError(before + TID + " end")

    monkeypatch.setattr(engine.ledger, "append", spy)
    monkeypatch.setattr(engine.governor, "record_action", broken)
    stack.check("draft invoices", token_id=token)
    assert [p["error"] for t, p in rows if t == "sentinel.metering_gap"] == [before]
