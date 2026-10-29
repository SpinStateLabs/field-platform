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
import re
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
    merges = 0
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            # `<<: *anchor` is the merge key, not data; but a second one is a repeated key
            merges += 1
            if merges > 1:
                raise DuplicateKey(f"duplicate merge key '<<': line {key_node.start_mark.line + 1}")
            continue
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


def _files(root: Path = ROOT) -> list[str]:
    pats = (".github/workflows/*.yml", ".github/workflows/*.yaml",
            "integration/**/docker-compose*.yml", "integration/**/docker-compose*.yaml",
            "integration/**/compose*.yml", "integration/**/compose*.yaml")
    found: set[str] = set()
    for pat in pats:
        for p in glob.glob(str(root / pat), recursive=True):
            found.add(os.path.relpath(p, root).replace(os.sep, "/"))
    return sorted(found)


FILES = _files()


def test_the_scan_sees_the_workflow_and_the_compose_files():
    assert ".github/workflows/ci.yml" in FILES
    assert "integration/demo/docker-compose.yml" in FILES
    assert "integration/demo/docker-compose.gb10.yml" in FILES


def scan_file(rel: str, suffix: str = ""):
    """The one place a discovered file is loaded; `suffix` lets a test append a defect to the copy."""
    return load_strict((ROOT / rel).read_text(encoding="utf-8") + suffix)


@pytest.mark.parametrize("rel", FILES)
def test_no_duplicate_mapping_key(rel: str):
    scan_file(rel)


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


def _first_top_level_key(text: str) -> str:
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):", line)
        if m:
            return m.group(1)
    raise AssertionError("no top-level key found")


@pytest.mark.parametrize("rel", FILES)
def test_every_scanned_file_refuses_a_repeated_top_level_key(rel: str):
    """C-294: the scan is proven live on each discovered file, not only on the two the mutants below
    name: a copy with its first top-level key repeated must raise."""
    key = _first_top_level_key((ROOT / rel).read_text(encoding="utf-8"))
    with pytest.raises(DuplicateKey):
        scan_file(rel, "\n" + key + ": repeated\n")


def test_a_compose_file_nested_deeper_than_one_directory_is_discovered(tmp_path: Path):
    nested = tmp_path / "integration" / "a" / "b" / "docker-compose.x.yml"
    nested.parent.mkdir(parents=True)
    nested.write_text("services: {}\n", encoding="utf-8")
    assert "integration/a/b/docker-compose.x.yml" in _files(tmp_path)


def test_keys_differing_only_in_case_are_not_duplicates():
    assert load_strict("env: 1\nENV: 2\n") == {"env": 1, "ENV": 2}


def test_keys_differing_only_in_type_are_not_duplicates():
    assert load_strict("1: a\n'1': b\n") == {1: "a", "1": "b"}


def test_two_merge_keys_in_one_mapping_are_refused():
    with pytest.raises(DuplicateKey):
        load_strict("x: &x {a: 1}\ny: &y {b: 2}\nz:\n  <<: *x\n  <<: *y\n")


def test_a_merge_list_is_still_accepted():
    assert load_strict("x: &x {a: 1}\ny: &y {b: 2}\nz:\n  <<: [*x, *y]\n")["z"] == {"a": 1, "b": 2}


# --- C-325 (reviewer C-303 F-C303-1..4) -------------------------------------------------------------

def test_the_discovered_file_set_is_not_empty():
    """An empty set makes every per-file test SKIP (parametrize over nothing), which is not red."""
    assert FILES, "no workflow or compose file discovered: the per-file tests above would skip"


@pytest.mark.parametrize("rel", [
    ".github/workflows/x.yml",
    ".github/workflows/x.yaml",
    "integration/a/docker-compose.x.yml",
    "integration/a/docker-compose.x.yaml",
    "integration/a/compose.x.yml",
    "integration/a/compose.x.yaml",
])
def test_each_discovery_pattern_finds_its_file(tmp_path: Path, rel: str):
    f = tmp_path / rel
    f.parent.mkdir(parents=True)
    f.write_text("a: 1\n", encoding="utf-8")
    assert _files(tmp_path) == [rel]


def test_a_file_no_pattern_names_is_not_discovered(tmp_path: Path):
    for rel in (".github/workflows/x.txt", "integration/a/other.yml", "docs/docker-compose.yml"):
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("a: 1\n", encoding="utf-8")
    assert _files(tmp_path) == []


def test_an_unhashable_key_is_skipped_by_the_check_not_raised_on():
    """The key is left to PyYAML (which refuses it as a ConstructorError); the checker neither crashes
    with a TypeError nor stops looking for a real duplicate after it."""
    with pytest.raises(yaml.constructor.ConstructorError):
        load_strict("? [1, 2]\n: a\n")
    with pytest.raises(DuplicateKey):
        load_strict("? [1, 2]\n: a\nk: 1\nk: 2\n")


def _first_mapping_header(lines: list[str]) -> tuple[int, str]:
    """(line index, child indent) of the first top-level `key:` that opens a block mapping."""
    for i, line in enumerate(lines):
        if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*:\s*$", line):
            for nxt in lines[i + 1:]:
                if nxt.strip() and not nxt.lstrip().startswith("#"):
                    indent = nxt[: len(nxt) - len(nxt.lstrip())]
                    if indent and not nxt.lstrip().startswith("-"):
                        return i, indent
                    break
    raise AssertionError("no top-level block mapping found")


@pytest.mark.parametrize("rel", FILES)
def test_every_scanned_file_refuses_a_duplicate_nested_below_its_first_mapping(rel: str):
    """A duplicate one level down, not only at the top: the pair is injected as the first children of
    the file's first top-level block mapping."""
    lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
    i, indent = _first_mapping_header(lines)
    lines[i + 1:i + 1] = [indent + "zz-c325: 1", indent + "zz-c325: 2"]
    with pytest.raises(DuplicateKey):
        load_strict("\n".join(lines) + "\n")


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
