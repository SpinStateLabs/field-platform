"""``SpendRequest`` and ``UsageRequest`` take an agent id inside the registry's id rule only."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from spend_governor.api import SpendRequest, UsageRequest

VALID = ["invoicing-agent", "a", "0", "a..b_c-", "a" * 128]
INVALID = ["", "A", "-a", ".a", "_a", "a b", "a/b", "a?b", "a#b", "a%2Fb", "a" + chr(10), "a" + chr(0),
           "a" + chr(0x202E), chr(0xE9), "a" * 129]
MODELS = [(SpendRequest, {}), (UsageRequest, {"model": "m"})]


@pytest.mark.parametrize("model,extra", MODELS, ids=["spend", "usage"])
@pytest.mark.parametrize("agent_id", VALID)
def test_a_valid_id_is_accepted_unchanged(model, extra, agent_id):
    assert model(agent_id=agent_id, **extra).agent_id == agent_id


@pytest.mark.parametrize("model,extra", MODELS, ids=["spend", "usage"])
@pytest.mark.parametrize("agent_id", INVALID)
def test_an_id_outside_the_rule_is_refused(model, extra, agent_id):
    with pytest.raises(ValidationError):
        model(agent_id=agent_id, **extra)
