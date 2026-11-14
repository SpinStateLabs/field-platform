"""S9-8: two time knobs fail open when given a value that is not a real duration.

(a) `FieldClient(timeout=None)` reaches `OpenerDirector.open(timeout=None)`, which means "no timeout": `check()` and `killed()` never
return on a peer that accepts and then stalls, the opposite of the module's fail-closed rules; NaN and inf behave as no limit
too. A timeout must be a finite number greater than 0 (ValueError at construction, like the base_url checks).
(b) `FieldAgent(heartbeat_max_age=NaN)`: `time.monotonic() - alive_at > NaN` is False, so after the first successful `ensure_alive` the
kill-switch is never asked again. NaN, a negative number and a non-number are refused; 0 stays valid (the tests use 0.0), None stays
"off", and inf stays what it says ("never re-ask")."""

import math

import pytest

from field_agent.agent import FieldAgent
from field_agent.field_client import FieldClient

BASE = "http://127.0.0.1:9"


def fc(timeout):
    return FieldClient(BASE, "agent-1", "tok-1", timeout=timeout)


def agent(**kw):
    return FieldAgent("agent-1", token_id="t", sentinel_client=object(), governor_client=object(),
                      killswitch_client=object(), federation_client=object(), **kw)


@pytest.mark.parametrize("bad", [None, 0, 0.0, -1, -0.5, math.nan, math.inf, -math.inf, True, False, "5", [1]],
                         ids=["none", "zero", "zero-float", "neg", "neg-float", "nan", "inf", "-inf", "true", "false", "str", "list"])
def test_a_timeout_that_is_not_a_finite_positive_number_is_refused(bad):
    with pytest.raises(ValueError, match="timeout"):
        fc(bad)


@pytest.mark.parametrize("good", [0.5, 1, 10, 10.0, 3600, 1e-3])
def test_a_finite_positive_timeout_is_accepted_and_stored(good):
    assert fc(good).timeout == good


def test_the_default_timeout_is_still_ten_seconds():
    assert FieldClient(BASE, "agent-1", "tok-1").timeout == 10.0


@pytest.mark.parametrize("bad", [math.nan, -1, -0.001, -math.inf, "30", True, [1]],
                         ids=["nan", "neg", "neg-small", "-inf", "str", "true", "list"])
def test_a_heartbeat_max_age_that_is_nan_negative_or_not_a_number_is_refused(bad):
    with pytest.raises(ValueError, match="heartbeat_max_age"):
        agent(heartbeat_max_age=bad)


@pytest.mark.parametrize("good", [0.0, 0, 30, 30.0, 0.5, math.inf, None], ids=["zero-float", "zero", "int", "float", "half", "inf", "none"])
def test_zero_a_positive_number_inf_and_none_are_accepted(good):
    assert agent(heartbeat_max_age=good)._heartbeat_max_age == good
