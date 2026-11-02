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
    return {(t.service, t.method, t.path) for t in catalog.TOOLS}


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


def tier(n):
    return [t for t in catalog.TOOLS if t.tier == n]


def test_tier1_is_get_or_the_seven_read_only_posts():
    for t in tier(1):
        assert t.method == "GET" or (t.method == "POST" and (t.service, t.path) in catalog.READ_ONLY_POSTS), t
    assert sum(t.method == "POST" for t in tier(1)) == len(catalog.READ_ONLY_POSTS) == 7


#: Don's tier rulings (2026-10-30), written out so that a route moving between tiers is a visible edit of this
#: list, never only of the catalog (C-775 F-6; mutant R4 swaps a Tier 2 and a Tier 3 route and keeps every count).
TIER3 = frozenset({
    ("kill-switch", "POST", "/kill/{agent_id}"), ("kill-switch", "POST", "/kill/domain/{domain}"),
    ("kill-switch", "POST", "/revive/{agent_id}"), ("kill-switch", "POST", "/drill/{agent_id}"),
    ("kill-switch", "POST", "/heartbeat/{agent_id}"),
    ("delegation-authority", "POST", "/tokens"), ("delegation-authority", "POST", "/tokens/{token_id}/revoke"),
    ("sealed-ledger", "POST", "/events"), ("sealed-ledger", "POST", "/rotate"), ("sealed-ledger", "POST", "/hold"),
    ("sealed-ledger", "POST", "/hold/release"), ("sealed-ledger", "POST", "/retention/apply"),
    ("spend-governor", "PUT", "/caps/{agent_id}"), ("spend-governor", "PUT", "/policies/{agent_id}"),
    ("spend-governor", "PUT", "/rate-limits/{agent_id}"), ("spend-governor", "POST", "/spend"),
    ("spend-governor", "POST", "/usage"), ("spend-governor", "POST", "/escalations/{escalation_id}/resolve"),
    ("federation-broker", "PUT", "/contracts/{contract_id}"), ("lifecycle-manager", "POST", "/sweep"),
    ("agent-registry", "POST", "/agents/{agent_id}/attest"),     # a HUMAN re-attestation: ruled Tier 3 (Don, 2026-10-30)
})
TIER2 = frozenset({
    ("conformance-sentinel", "POST", "/check"), ("compliance-crosswalk", "POST", "/regwatch/check"),
    ("agent-registry", "POST", "/agents"), ("agent-registry", "PATCH", "/agents/{agent_id}"),
    ("agent-registry", "POST", "/discover"),
    ("federation-broker", "POST", "/crossing"), ("sealed-ledger", "POST", "/export"),
})


def test_tier2_is_the_seven_state_changing_tools_and_every_one_names_its_blast_radius():
    assert len(tier(2)) == 7 and {t.tier for t in catalog.TOOLS} == {1, 2}
    for t in tier(2):
        assert t.effect.startswith("WRITES (Tier 2):") and len(t.effect) > 60, t
        assert t.method != "GET"
    assert not any(t.effect.startswith("WRITES") for t in tier(1))


def test_the_counts_match_the_rulings():
    assert len(tier(1)) == 49 and sum(t.method == "GET" for t in tier(1)) == 42 and len(catalog.TOOLS) == 56
    t3 = [k for k, w in catalog.EXCLUDED.items() if w.startswith("Tier 3")]
    assert len(t3) == 21        # the 20 ruled on 2026-10-30, plus attest (a HUMAN re-attestation, ruled Tier 3 the same day)
    assert catalog.EXCLUDED[("agent-registry", "POST", "/agents/{agent_id}/attest")].startswith("Tier 3")


def test_nothing_that_changes_status_or_authority_is_a_tier2_tool():
    banned = ("/kill", "/revive", "/drill", "/heartbeat", "/tokens", "/rotate", "/hold", "/retention", "/caps",
              "/policies", "/rate-limits", "/spend", "/usage", "/escalations", "/sweep", "/events", "/contracts", "/attest")
    for t in tier(2):
        assert not any(b in t.path for b in banned), t


def tier_keys(n):
    return {(t.service, t.method, t.path) for t in tier(n)}


def test_the_tier2_and_tier3_sets_are_exactly_the_written_ones():
    """Tier 3 routes are written exclusions (21: the 20 ruled, plus attest); Tier 2 routes are the seven tools."""
    assert {k for k, w in catalog.EXCLUDED.items() if w.startswith("Tier 3")} == TIER3
    assert tier_keys(2) == TIER2
    assert len(TIER3) == 21 and len(TIER2) == 7 and not (TIER3 & TIER2)


def test_no_tier3_route_is_a_tool_and_no_tier2_route_is_tier1_whatever_the_catalog_says():
    assert not (TIER3 & tool_keys())
    assert not ({(s, p) for s, m, p in TIER3 | TIER2} & catalog.READ_ONLY_POSTS)
    assert not (TIER2 & tier_keys(1))


def test_tool_names_are_unique_and_service_prefixed():
    names = [t.name for t in catalog.TOOLS]
    assert len(names) == len(set(names))
    for t in catalog.TOOLS:
        assert t.name.startswith(t.service.replace("-", "_") + "_")


def test_snapshot_matches_the_services_own_models(apps):
    """The checked-in schemas are generated from the services' pydantic models; drift is red. Regenerate with
    ``python scripts/gen_snapshot.py``."""
    on_disk = json.loads(resources.files("field_mcp").joinpath("snapshot.json").read_text("utf-8"))
    assert on_disk == json.loads(json.dumps(build_snapshot(apps)))
    assert set(snapshot()) == {t.name for t in catalog.TOOLS}


def test_server_registers_the_tier_it_is_asked_for():
    assert {s.name for s in build_specs(1)} == {t.name for t in tier(1)}
    assert {s.name for s in build_specs(2)} == {t.name for t in catalog.TOOLS}
