"""The three self-manifest copies under manifests/ (F1) are BYTE-IDENTICAL to
the packaged self-manifests the services ship and validate.

`manifests-admin install conformance-sentinel.yaml force-gateway.yaml
compliance-crosswalk.yaml` (GB10) and the Fly copy install what is under
manifests/; the sentinel resolves the registered ref against that file on
every /check. A copy that drifts from its packaged source (a scope added on
one side only) would register one manifest and govern by another — this
test fails on the first differing byte and names the pair.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from field_core.validation import validate_manifest_data

ROOT = Path(__file__).resolve().parents[2]

#: agent id -> the packaged self-manifest (the source of truth per service)
PACKAGED = {
    "conformance-sentinel": "services/conformance-sentinel/src/conformance_sentinel/self_manifest.yaml",
    "force-gateway": "services/force-gateway/src/force_gateway/self_manifest.yaml",
    "compliance-crosswalk": "services/compliance-crosswalk/src/compliance_crosswalk/self_manifest.yaml",
}


def _copy(agent_id: str) -> Path:
    return ROOT / "manifests" / f"{agent_id}.yaml"


def test_the_three_self_agents_have_a_copy_each():
    assert sorted(PACKAGED) == ["compliance-crosswalk", "conformance-sentinel", "force-gateway"]
    for agent_id in PACKAGED:
        assert _copy(agent_id).is_file(), f"manifests/{agent_id}.yaml is missing"


@pytest.mark.parametrize("agent_id", sorted(PACKAGED))
def test_copy_is_byte_identical_to_the_packaged_self_manifest(agent_id):
    packaged = ROOT / PACKAGED[agent_id]
    copy = _copy(agent_id)
    a, b = packaged.read_bytes(), copy.read_bytes()
    if a != b:
        first = next(i for i, (x, y) in enumerate(zip(a, b)) if x != y) if len(a) and len(b) else 0
        first = min(first, len(a), len(b))
        pytest.fail(f"manifests/{agent_id}.yaml drifted from {PACKAGED[agent_id]} "
                    f"at byte {first}: re-copy the packaged file (cp) — never edit the copy")


@pytest.mark.parametrize("agent_id", sorted(PACKAGED))
def test_copy_validates_and_names_its_agent(agent_id):
    data = yaml.safe_load(_copy(agent_id).read_text(encoding="utf-8"))
    assert validate_manifest_data(data).ok
    assert data["agent"]["name"] == agent_id  # the file name IS the registered id
    assert data["identity"]["principal"] == "Founder & CTO, Spin State Labs"


@pytest.mark.parametrize("agent_id", ["conformance-sentinel", "force-gateway", "compliance-crosswalk"])
def test_every_self_manifest_copy_carries_the_egress_action(agent_id):
    """F1: an enforcing gateway checks `llm.messages` for a self-agent's own
    judge calls; all three self-manifests (and their copies) carry it."""
    data = yaml.safe_load(_copy(agent_id).read_text(encoding="utf-8"))
    assert "llm.messages" in data["delegation"]["scope"]
