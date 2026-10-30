"""Route coverage: every route of every service is a tool or a written exclusion (Don, 2026-10-30).

Builds each service's real app. A new route, a removed route, a route in both lists, a non-read tool in Tier 1, or an
exclusion without a reason turns this red. Mutants: delete a TOOLS entry; add a route to a stub app; empty a reason.
"""
import json
from importlib import resources

import pytest

from field_mcp import catalog
from field_mcp.tools import build_specs, snapshot
from snapshot_build import build_apps, build_snapshot, live_routes


@pytest.fixture(scope="module")
def apps():
    return build_apps()


def tool_keys():
    return {(t.service, t.method, t.path) for t in catalog.TOOLS + catalog.WRITE_TOOLS}


#: The 20 Tier 3 routes, written out here so a swap made in catalog.py alone is red (C-775 F-C775-6).
TIER3 = {
    ("kill-switch", "POST", "/kill/{agent_id}"), ("kill-switch", "POST", "/kill/domain/{domain}"),
    ("kill-switch", "POST", "/revive/{agent_id}"), ("kill-switch", "POST", "/drill/{agent_id}"),
    ("kill-switch", "POST", "/heartbeat/{agent_id}"), ("delegation-authority", "POST", "/tokens"),
    ("delegation-authority", "POST", "/tokens/{token_id}/revoke"), ("sealed-ledger", "POST", "/events"),
    ("sealed-ledger", "POST", "/rotate"), ("sealed-ledger", "POST", "/hold"), ("sealed-ledger", "POST", "/hold/release"),
    ("sealed-ledger", "POST", "/retention/apply"), ("spend-governor", "PUT", "/caps/{agent_id}"),
    ("spend-governor", "PUT", "/policies/{agent_id}"), ("spend-governor", "PUT", "/rate-limits/{agent_id}"),
    ("spend-governor", "POST", "/spend"), ("spend-governor", "POST", "/usage"),
    ("spend-governor", "POST", "/escalations/{escalation_id}/resolve"), ("federation-broker", "PUT", "/contracts/{contract_id}"),
    ("lifecycle-manager", "POST", "/sweep"),
}


def test_the_twenty_tier3_routes_are_written_exclusions_and_never_tools():
    assert len(TIER3) == 20
    assert TIER3 <= set(catalog.EXCLUDED), sorted(TIER3 - set(catalog.EXCLUDED))
    assert not TIER3 & tool_keys()
    for k in TIER3:
        assert catalog.EXCLUDED[k].startswith("Tier 3") and "never in this server" in catalog.EXCLUDED[k], k
    assert {k for k, w in catalog.EXCLUDED.items() if w.startswith("Tier 3")} == TIER3


def test_no_tier2_route_is_still_excluded_and_no_tier3_flag_exists():
    assert not [k for k, w in catalog.EXCLUDED.items() if w.startswith("Tier 2")]
    assert not hasattr(catalog, "FFMCP_ENABLE_DESTRUCTIVE")


def test_write_tools_are_state_changing_methods_and_not_in_the_read_only_post_list():
    for t in catalog.WRITE_TOOLS:
        assert t.method in ("POST", "PATCH") and (t.service, t.path) not in catalog.READ_ONLY_POSTS, t


def test_every_live_route_is_a_tool_or_excluded(apps):
    live = live_routes(apps)
    covered = tool_keys() | set(catalog.EXCLUDED)
    assert not (live - covered), f"routes with no tool and no exclusion: {sorted(live - covered)}"


def test_no_catalog_entry_for_a_route_that_is_gone(apps):
    live = live_routes(apps)
    assert not ((tool_keys() | set(catalog.EXCLUDED)) - live)


def test_no_route_is_both_a_tool_and_excluded():
    assert not (tool_keys() & set(catalog.EXCLUDED))


def test_every_exclusion_has_a_written_reason():
    for key, why in catalog.EXCLUDED.items():
        assert isinstance(why, str) and len(why.strip()) >= 20, key


def test_all_fourteen_services_are_accounted_for(apps):
    assert set(apps) == set(catalog.SERVICES) and len(apps) == 14


def test_tier1_is_get_or_the_seven_read_only_posts():
    for t in catalog.TOOLS:
        assert t.method == "GET" or (t.method == "POST" and (t.service, t.path) in catalog.READ_ONLY_POSTS), t
    assert sum(t.method == "POST" for t in catalog.TOOLS) == len(catalog.READ_ONLY_POSTS) == 7


def test_the_counts_match_the_ruling():
    assert len(catalog.TOOLS) == 49 and sum(t.method == "GET" for t in catalog.TOOLS) == 42
    t3 = [k for k, w in catalog.EXCLUDED.items() if w.startswith("Tier 3")]
    assert len(t3) == 20 and len(catalog.WRITE_TOOLS) == 8 and len(catalog.ALL_TOOLS) == 57


def test_tool_names_are_unique_and_service_prefixed():
    names = [t.name for t in catalog.ALL_TOOLS]
    assert len(names) == len(set(names))
    for t in catalog.ALL_TOOLS:
        assert t.name.startswith(t.service.replace("-", "_") + "_")


def test_snapshot_matches_the_services_own_models(apps):
    """The checked-in schemas are generated from the services' pydantic models; drift is red. Regenerate with
    ``python scripts/gen_snapshot.py``."""
    on_disk = json.loads(resources.files("field_mcp").joinpath("snapshot.json").read_text("utf-8"))
    assert on_disk == json.loads(json.dumps(build_snapshot(apps)))
    assert set(snapshot()) == {t.name for t in catalog.ALL_TOOLS}


def test_server_registers_the_tier1_tools_at_tier1_and_the_eight_more_at_tier2():
    assert {s.name for s in build_specs(1)} == {t.name for t in catalog.TOOLS}
    assert {s.name for s in build_specs(2)} == {t.name for t in catalog.ALL_TOOLS}
