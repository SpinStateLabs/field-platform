"""S3-3 (G21 decision, point 1b): every manifest with a non-empty ``enforcement.kill_switch.authorized_operators``
lists ``don-admin``, so the registered manifest does not lock out the one identity the Stage 3 plan keeps for a
kill. An empty list (everyone authenticated may act) needs nothing. Repo files only; no estate value."""

from pathlib import Path

import pytest
import yaml

MANIFESTS = sorted((Path(__file__).resolve().parents[2] / "manifests").glob("*.yaml"))


def _operators(path: Path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    enforcement = doc.get("enforcement") if isinstance(doc, dict) else None
    ks = enforcement.get("kill_switch") if isinstance(enforcement, dict) else None
    ops = ks.get("authorized_operators") if isinstance(ks, dict) else None
    return list(ops) if ops else []


def test_the_walk_is_not_blind():
    listed = [p.name for p in MANIFESTS if _operators(p)]
    assert len(MANIFESTS) >= 8, MANIFESTS
    assert {"canary-fly.yaml", "canary-gb10.yaml", "deployment-agent.yaml"} <= set(listed), listed


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.name)
def test_a_non_empty_authorized_operators_list_names_don_admin(path):
    ops = _operators(path)
    if not ops:
        pytest.skip("empty list: nothing to name")
    assert "don-admin" in ops, f"{path.name}: authorized_operators lacks don-admin: {ops}"
