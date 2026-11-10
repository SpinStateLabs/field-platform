"""S11-10: decommission refuses a `by` or `reason` the kill-switch would refuse,
before any client call, so the revoke can never run and then the halt fail."""

from __future__ import annotations

import pytest

from kill_switch.api import KillRequest
from lifecycle_manager import engine as engine_mod
from lifecycle_manager.engine import LifecycleEngine, LifecycleError

PREFIX = "lifecycle decommission: "


class _Boom:
    """Any use of a client is a test failure."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _call(*a, **k):
            self.calls.append(name)
            raise AssertionError(f"client call {name} before validation")
        return _call


def _engine():
    spy = _Boom()
    eng = LifecycleEngine(registry=spy, delegation=spy, ledger=spy,
                          killswitch=spy, registry_http=spy, governor=spy)
    return eng, spy


def test_constants_match_kill_request_limits():
    fields = KillRequest.model_fields
    by_max = next(m.max_length for m in fields["operator"].metadata if hasattr(m, "max_length"))
    reason_max = next(m.max_length for m in fields["reason"].metadata if hasattr(m, "max_length"))
    assert engine_mod.MAX_DECOMMISSION_BY == by_max
    assert engine_mod.MAX_DECOMMISSION_REASON == reason_max - len(PREFIX)


@pytest.mark.parametrize("by,reason,needle", [
    ("", "ok", "by"),
    ("   ", "ok", "by"),
    ("\t", "ok", "by"),
    ("x" * 201, "ok", "200"),
    ("Don", "", "reason"),
    ("Don", " \n", "reason"),
    ("Don", "r" * 977, "976"),
])
def test_refused_before_any_client_call(by, reason, needle):
    eng, spy = _engine()
    with pytest.raises(LifecycleError) as exc:
        eng.decommission("some-agent", by=by, reason=reason)
    assert needle in str(exc.value)
    assert spy.calls == []


def test_boundary_values_pass_validation_and_build_an_acceptable_kill_request():
    # 200-char by and 976-char reason are the largest the kill-switch accepts.
    KillRequest(operator="b" * 200, reason=PREFIX + "r" * 976)
    eng, spy = _engine()
    # Past validation the first client call is the registry lookup: reaching it
    # (an AssertionError from the spy) proves validation let the value through.
    with pytest.raises(AssertionError):
        eng.decommission("some-agent", by="b" * 200, reason="r" * 976)
    assert spy.calls == ["get_agent"]
