"""A decommission checks ``--by`` and ``--reason`` before its first step, so the kill it sends is never refused for its
text: a refused value changes nothing and sends no kill; an ordinary one still halts."""

from __future__ import annotations

import pytest

from lifecycle_manager.engine import LifecycleError

from test_transitions import _provisioned, stack, valid_manifest  # noqa: F401  (fixtures)

AGENT = "invoicing-agent"


@pytest.mark.parametrize("reason", ["two" + chr(10) + "lines", "a" + chr(9) + "tab", "zero" + chr(0x200D) + "width"],
                         ids=["line-feed", "tab", "zero-width-joiner"])
def test_a_refused_reason_revokes_halts_and_retires_nothing(stack, valid_manifest, reason):
    engine, registry, _, delegation, _, kill_spy = stack
    _provisioned(engine, valid_manifest)
    with pytest.raises(LifecycleError) as exc:
        engine.decommission(AGENT, by="Don", reason=reason)
    assert "--reason" in str(exc.value) and reason not in str(exc.value)
    assert kill_spy.calls == []
    assert registry.get(f"/agents/{AGENT}").json()["status"] == "active"
    assert not any(t["revoked"] for t in delegation.get("/tokens", params={"agent_id": AGENT}).json())


def test_an_ordinary_reason_still_halts(stack, valid_manifest):
    engine, registry, _, _, _, kill_spy = stack
    _provisioned(engine, valid_manifest)
    report = engine.decommission(AGENT, by="Don", reason="incident 42: re-check")
    assert report.killed is True and report.retired is True
    assert kill_spy.calls == [(f"/kill/{AGENT}",
                               {"operator": "Don", "reason": "lifecycle decommission: incident 42: re-check"})]
