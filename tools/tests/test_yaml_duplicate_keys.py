"""C-286: no duplicate mapping key in a workflow or a compose file.

A duplicate key (two `env:` blocks in one job, from the C-267 stack) made GitHub reject
`.github/workflows/ci.yml` outright (a failed run with zero jobs, no pull_request checks), while
PyYAML parses it silently with the last key winning, so every local test and two reviewers missed it.
This test loads every workflow and every compose file with a loader that fails on a duplicate mapping
key at any depth (the same idea as `field_core.operator_auth._no_duplicate_keys` for JSON).
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


class DuplicateKey(AssertionError):
    pass


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses a repeated key in any mapping; compose tags (`!override`, `!reset`)
    are read as the plain value underneath."""


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False):
    seen: dict = {}
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            continue  # `<<: *anchor` is the merge key, not data
        key = loader.construct_object(key_node, deep=True)
        try:
            hash(key)
        except TypeError:
            continue
        if key in seen:
            raise DuplicateKey(
                f"duplicate key {key!r}: lines {seen[key] + 1} and {key_node.start_mark.line + 1}"
            )
        seen[key] = key_node.start_mark.line
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


def _construct_tagged(loader: _StrictLoader, suffix: str, node: yaml.Node):
    if isinstance(node, yaml.MappingNode):
        return _construct_mapping(loader, node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)
_StrictLoader.add_multi_constructor("!", _construct_tagged)


def load_strict(text: str):
    return yaml.load(text, _StrictLoader)


def _files() -> list[str]:
    pats = (".github/workflows/*.yml", ".github/workflows/*.yaml",
            "integration/**/docker-compose*.yml", "integration/**/docker-compose*.yaml",
            "integration/**/compose*.yml", "integration/**/compose*.yaml")
    found: set[str] = set()
    for pat in pats:
        for p in glob.glob(str(ROOT / pat), recursive=True):
            found.add(os.path.relpath(p, ROOT).replace(os.sep, "/"))
    return sorted(found)


FILES = _files()


def test_the_scan_sees_the_workflow_and_the_compose_files():
    assert ".github/workflows/ci.yml" in FILES
    assert "integration/demo/docker-compose.yml" in FILES
    assert "integration/demo/docker-compose.gb10.yml" in FILES


@pytest.mark.parametrize("rel", FILES)
def test_no_duplicate_mapping_key(rel: str):
    load_strict((ROOT / rel).read_text(encoding="utf-8"))


# --- the checker itself ---------------------------------------------------------------------------

def test_a_clean_document_with_a_compose_tag_and_a_merge_key_loads():
    doc = load_strict("a: &x {k: 1}\nb:\n  <<: *x\n  m: 2\nc: !override [1, 2]\n")
    assert doc["b"] == {"k": 1, "m": 2} and doc["c"] == [1, 2]


def test_a_duplicate_at_the_top_level_is_refused():
    with pytest.raises(DuplicateKey):
        load_strict("a: 1\nb: 2\na: 3\n")


def test_a_duplicate_two_levels_down_is_refused():
    with pytest.raises(DuplicateKey):
        load_strict("jobs:\n  t:\n    env:\n      A: 1\n    runs-on: x\n    env:\n      B: 2\n")


def test_a_duplicate_inside_a_tagged_mapping_is_refused():
    with pytest.raises(DuplicateKey):
        load_strict("services:\n  p:\n    ports: !override\n      a: 1\n      a: 2\n")


# --- mutants: each re-introduced defect must go red ------------------------------------------------

def test_mutant_a_second_env_block_in_the_upgrade_smoke_job_goes_red():
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    marker = "  compose-upgrade-smoke:\n"
    assert marker in text
    mutated = text.replace(marker, marker + "    env:\n      EXTRA: '1'\n", 1)
    assert mutated != text
    with pytest.raises(DuplicateKey):
        load_strict(mutated)


def test_mutant_a_repeated_service_key_in_the_base_compose_goes_red():
    text = (ROOT / "integration/demo/docker-compose.yml").read_text(encoding="utf-8")
    mutated = text.replace("\n  registry:\n", "\n  registry:\n    restart: \"no\"\n    restart: always\n", 1)
    assert mutated != text
    with pytest.raises(DuplicateKey):
        load_strict(mutated)
