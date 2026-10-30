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


def test_tier1_is_get_or_the_seven_read_only_posts():
    for t in catalog.TOOLS:
        assert t.method == "GET" or (t.method == "POST" and (t.service, t.path) in catalog.READ_ONLY_POSTS), t
    assert sum(t.method == "POST" for t in catalog.TOOLS) == len(catalog.READ_ONLY_POSTS) == 7


def test_the_counts_match_the_ruling():
    assert len(catalog.TOOLS) == 49 and sum(t.method == "GET" for t in catalog.TOOLS) == 42
    t3 = [k for k, w in catalog.EXCLUDED.items() if w.startswith("Tier 3")]
    t2 = [k for k, w in catalog.EXCLUDED.items() if w.startswith("Tier 2")]
    assert len(t3) == 20 and len(t2) == 8


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


def test_server_registers_exactly_the_tier1_tools():
    assert {s.name for s in build_specs(1)} == {t.name for t in catalog.TOOLS}
    assert {s.name for s in build_specs(2)} == {t.name for t in catalog.TOOLS}   # no Tier 2 tools in this build
