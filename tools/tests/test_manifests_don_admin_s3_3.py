"""S3-3 (G21 decision, point 1b): every manifest with a non-empty ``enforcement.kill_switch.authorized_operators``
lists ``don-admin``, so the registered manifest does not lock out the one identity the Stage 3 plan keeps for a
kill. An explicit empty list puts no list restriction on an authenticated operator; it needs no name and passes for
now. Every agent manifest declares the list: a missing block, a missing or misspelled key, or a value that is not a
list fails. Repo files only; no estate value."""

from pathlib import Path

import pytest
import yaml

MANIFEST_DIR = Path(__file__).resolve().parents[2] / "manifests"
NOT_A_MANIFEST = {"doa-roster.example.yaml"}  # a delegation roster example that lives beside the manifests
MANIFESTS = sorted(p for p in MANIFEST_DIR.glob("*.yaml") if p.name not in NOT_A_MANIFEST)


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _operators(doc, name: str) -> list:
    """The declared list. Nothing is defaulted: each level has to be there."""
    node = doc
    for key in ("enforcement", "kill_switch", "authorized_operators"):
        assert isinstance(node, dict) and key in node, f"{name}: no {key}"
        node = node[key]
    assert isinstance(node, list), f"{name}: authorized_operators is not a list ({type(node).__name__})"
    return node


def _check(doc, name: str) -> None:
    """The rule: the list is declared, and one that names anybody names don-admin."""
    ops = _operators(doc, name)
    if ops:
        assert "don-admin" in ops, f"{name}: authorized_operators lacks don-admin: {ops}"


def test_the_walk_is_not_blind():
    assert len(MANIFESTS) >= 8, MANIFESTS
    listed = [p.name for p in MANIFESTS if _operators(_load(p), p.name)]
    assert {"canary-fly.yaml", "canary-gb10.yaml", "deployment-agent.yaml"} <= set(listed), listed


@pytest.mark.parametrize("name", sorted(NOT_A_MANIFEST))
def test_an_excluded_file_is_not_an_agent_manifest(name):
    doc = _load(MANIFEST_DIR / name)
    assert isinstance(doc, dict) and "grantors" in doc and "enforcement" not in doc, name


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.name)
def test_a_non_empty_authorized_operators_list_names_don_admin(path):
    _check(_load(path), path.name)


def _doc(kill_switch):
    return {"enforcement": {"kill_switch": kill_switch}}


@pytest.mark.parametrize("doc", [
    None,
    [],
    {},
    {"enforcement": None},
    {"enforcement": {}},
    _doc(None),
    _doc({}),
    _doc({"authorised_operators": ["don-admin"]}),  # misspelled
    _doc({"authorized_operators": None}),
    _doc({"authorized_operators": "don-admin"}),
    _doc({"authorized_operators": {}}),
])
def test_a_list_that_is_not_declared_is_refused_by_the_rule(doc):
    with pytest.raises(AssertionError):
        _operators(doc, "example.yaml")


def test_an_explicit_empty_authorized_operators_list_still_passes_for_now():
    _check(_doc({"authorized_operators": []}), "example.yaml")


def test_a_list_that_names_somebody_without_don_admin_is_refused():
    with pytest.raises(AssertionError):
        _check(_doc({"authorized_operators": ["someone-else"]}), "example.yaml")


def test_a_declared_list_is_read_as_written():
    assert _operators(_doc({"authorized_operators": []}), "example.yaml") == []
    assert _operators(_doc({"authorized_operators": ["don-admin"]}), "example.yaml") == ["don-admin"]
