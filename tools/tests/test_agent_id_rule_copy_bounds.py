"""The length bounds of the copies of the registry's agent-id rule, as ``field_core.ids`` describes them.

``test_agent_id_rule_copies.py`` holds the pattern and the watcher; these hold which copy carries which bound."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import renew_token  # noqa: E402
from agent_registry import models as registry_models  # noqa: E402
from compliance_crosswalk import api as crosswalk_api  # noqa: E402
from conformance_sentinel import engine as sentinel_engine  # noqa: E402
from field_core.ids import REGISTRY_ID_MAX_LENGTH, REGISTRY_ID_PATTERN, REGISTRY_ID_RE  # noqa: E402
from incident_replay import engine as replay_engine  # noqa: E402
from kill_switch import api as kill_api  # noqa: E402
from ops_console import api as console_api  # noqa: E402
from spend_governor import api as governor_api  # noqa: E402
from spend_governor import core as governor_core  # noqa: E402

LONG = "a" * (REGISTRY_ID_MAX_LENGTH + 1)


def test_a_new_registry_id_is_shorter_than_the_shared_bound():
    assert registry_models.MAX_AGENT_ID_LENGTH == 64 < REGISTRY_ID_MAX_LENGTH


def test_the_governor_applies_the_shared_bound():
    assert governor_api.MAX_ID_LEN == governor_core.MAX_ID_LEN == REGISTRY_ID_MAX_LENGTH == 128


@pytest.mark.parametrize("module", [sentinel_engine, replay_engine], ids=["sentinel", "replay"])
def test_the_pattern_check_has_no_bound_of_its_own_and_the_request_bound_is_longer(module):
    assert module._REGISTRY_ID is REGISTRY_ID_RE
    assert module._REGISTRY_ID.fullmatch(LONG) is not None
    assert module.AGENT_ID_MAX == 200 > REGISTRY_ID_MAX_LENGTH


def test_the_kill_switch_heartbeat_check_uses_the_shared_pattern():
    assert kill_api._HEARTBEAT_ID_RE is REGISTRY_ID_RE


def test_the_crosswalk_query_bound_is_the_longer_one():
    assert crosswalk_api.AGENT_ID_MAX == 200 > REGISTRY_ID_MAX_LENGTH


@pytest.mark.parametrize("value", ["", "a", "invoicing-agent", "a.b_c-d", LONG, "A", "-a", ".a", "_a", "a b", "a/b"])
def test_the_crosswalk_pattern_is_the_registry_rule_or_empty(value):
    accepted = re.fullmatch(crosswalk_api.AGENT_ID_PATTERN, value) is not None
    assert accepted is (value == "" or re.fullmatch(REGISTRY_ID_PATTERN, value) is not None)


def test_the_console_bulk_list_checks_the_pattern_only():
    request = console_api.BulkAction(action="kill", agent_ids=[LONG, "invoicing-agent"], operator="don", reason="bound")
    assert request.agent_ids == [LONG, "invoicing-agent"]
    with pytest.raises(ValueError):
        console_api.BulkAction(action="kill", agent_ids=["Invoicing-Agent"], operator="don", reason="bound")


def test_the_renewal_tool_leaves_the_bound_to_the_services():
    assert renew_token.AGENT_ID.fullmatch(LONG) is not None
