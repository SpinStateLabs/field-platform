"""The hash-checked install of field-mcp's third-party closure.

The CI step passes ``integration/field-mcp-hashes.txt`` as a constraints file, with ``--require-hashes``, and lists the
names to install on the line; ``--force-reinstall``
makes pip check each of them even when an earlier line already installed it. ``test_ci_pip_pins_c23.py`` does not read what a constraints file holds, so this does:
the file is exact, hashed pins and nothing else, they agree with ``integration/constraints.txt``, and the line installs
exactly the names the file pins.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
HASHES = "integration/field-mcp-hashes.txt"
ENTRY = re.compile(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.!+-]+)(?: --hash=sha256:[0-9a-f]{64})+")
BEFORE_NAMES = ["pip", "install", "$C", "--require-hashes", "--no-deps", "--force-reinstall", "-c", HASHES]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _folded(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _entries(text: str) -> list[str]:
    """Logical lines: a trailing backslash joins, comment lines and blank lines drop, spaces collapse."""
    joined = re.sub(r"\\\r?\n", " ", text)
    return [" ".join(ln.split()) for ln in joined.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def file_problems(text: str, constraints: str) -> list[str]:
    pins = {}
    for line in constraints.splitlines():
        name, found, version = line.strip().partition("==")
        if found and not name.startswith("#"):
            pins[_folded(name)] = version.strip()
    entries = _entries(text)
    out = [] if entries else ["the hashed file holds no pin (the check would be blind)"]
    seen = set()
    for entry in entries:
        match = ENTRY.fullmatch(entry)
        if match is None:
            out.append(f"not an exact, hashed pin: {entry[:60]}")
            continue
        name, version = _folded(match.group(1)), match.group(2)
        if name in seen:
            out.append(f"{name} is pinned twice")
        seen.add(name)
        if pins.get(name) != version:
            out.append(f"{name}=={version} is not the constraints file's pin")
    return out


def line_problems(workflow: str, text: str) -> list[str]:
    runs = [str(step.get("run", "")) for job in yaml.safe_load(workflow)["jobs"].values() for step in job["steps"]]
    lines = [ln.strip() for run in runs for ln in run.splitlines()
             if HASHES in ln and not ln.strip().startswith("#")]
    if len(lines) != 1:
        return [f"expected one statement naming the hashed file, found {len(lines)}"]
    words = shlex.split(lines[0])
    if words[: len(BEFORE_NAMES)] != BEFORE_NAMES:
        return ["the install does not start as the hash-checked form does"]
    listed = words[len(BEFORE_NAMES):]
    pinned = [m.group(1) for m in map(ENTRY.fullmatch, _entries(text)) if m]
    if sorted(map(_folded, listed)) != sorted(map(_folded, pinned)):
        return ["the names on the line are not the names the file pins"]
    return []


def test_the_hashed_file_is_only_exact_hashed_pins_that_agree_with_the_constraints():
    assert file_problems(_read(HASHES), _read("integration/constraints.txt")) == []


def test_the_ci_line_installs_exactly_the_pinned_names_with_hashes_required():
    assert line_problems(_read(".github/workflows/ci.yml"), _read(HASHES)) == []


@pytest.mark.parametrize("added", [
    "--index-url http://example.invalid/simple",
    "--extra-index-url http://example.invalid/simple",
    "--find-links ./wheels",
    "--trusted-host example.invalid",
    "-r other.txt",
    "-c other.txt",
    "requests==2.0.0",
    "requests>=2 --hash=sha256:" + "0" * 64,
    "pkg @ http://example.invalid/x.whl",
    "not-in-constraints==1.0 --hash=sha256:" + "0" * 64,
    "anyio==0.0.1 --hash=sha256:" + "0" * 64,
], ids=["index", "extra-index", "find-links", "trusted-host", "nested-r", "nested-c", "no-hash", "floating", "url",
        "unknown-name", "second-pin"])
def test_anything_else_in_the_file_is_caught(added):
    assert file_problems(_read(HASHES) + "\n" + added + "\n", _read("integration/constraints.txt")) != []


def test_an_empty_file_is_caught():
    assert file_problems("# nothing\n", _read("integration/constraints.txt")) != []


@pytest.mark.parametrize("old,new", [
    (" --require-hashes", ""),
    (" --no-deps --force-reinstall", " --force-reinstall"),
    (" --no-deps --force-reinstall", " --no-deps"),
    ("pip install $C --require-hashes", "pip install --require-hashes"),
    ("-c " + HASHES + " ", "-c " + HASHES + " requests "),
    ("-c " + HASHES + " annotated-types ", "-c " + HASHES + " "),
], ids=["no-hash-check", "with-dependencies", "no-reinstall", "no-constraints-variable", "extra-name",
        "missing-name"])
def test_any_other_form_of_the_line_is_caught(old, new):
    workflow = _read(".github/workflows/ci.yml")
    assert workflow.count(old) == 1, old
    assert line_problems(workflow.replace(old, new), _read(HASHES)) != []
