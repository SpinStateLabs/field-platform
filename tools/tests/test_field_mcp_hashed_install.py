"""The hash-checked install of field-mcp's third-party closure.

The CI step passes ``integration/field-mcp-hashes.txt`` as a constraints file, with ``--require-hashes``, and lists the
names to install on the line; ``--force-reinstall``
makes pip check each of them even when an earlier line already installed it. ``test_ci_pip_pins_c23.py`` does not read what a constraints file holds, so this does:
the file is exact, hashed pins and nothing else, they agree with ``integration/constraints.txt``, and the line installs
exactly the names the file pins.

The file is not parsed the way a lenient reader would: every physical line must be a blank, a plain comment, a pin that
continues, or a hash line of that pin. pip never continues a comment line, so no line may be hidden behind one, and a
comment may carry neither a trailing backslash nor an encoding declaration (pip honours one).

Mutants: H1 a comment may end in a backslash; H2 a comment may declare an encoding; H3 a line starting with "-" is
skipped.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
HASHES = "integration/field-mcp-hashes.txt"
PIN_LINE = re.compile(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.!+-]+) \\")
HASH_LINE = re.compile(r" {4}--hash=sha256:[0-9a-f]{64}( \\)?")
ENCODING_DECLARATION = re.compile(r"coding[:=]")
BEFORE_NAMES = ["pip", "install", "$C", "--require-hashes", "--no-deps", "--force-reinstall", "-c", HASHES]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _folded(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_pins(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """((name, version) of every entry, problems). Strict: anything that is not one of the four line forms is one."""
    pins: list[tuple[str, str]] = []
    out: list[str] = []
    in_entry = False
    for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        if any(not " " <= char <= "~" for char in line):
            out.append(f"line {number}: a character that is not printable ASCII")
        if in_entry:
            found = HASH_LINE.fullmatch(line)
            if found is not None:
                in_entry = found.group(1) is not None
                continue
            out.append(f"line {number}: an entry continues only with its hash lines")
            in_entry = False
        if line == "":
            continue
        if line.startswith("#"):
            if line.rstrip().endswith("\\"):
                out.append(f"line {number}: a comment ends in a backslash")
            if ENCODING_DECLARATION.search(line):
                out.append(f"line {number}: a comment declares an encoding")
            continue
        pin = PIN_LINE.fullmatch(line)
        if pin is None:
            out.append(f"line {number}: not an exact, hashed pin: {line[:60]}")
            continue
        pins.append((pin.group(1), pin.group(2)))
        in_entry = True
    if in_entry:
        out.append("the file ends inside an entry")
    return pins, out


def file_problems(text: str, constraints: str) -> list[str]:
    agreed = {}
    for line in constraints.splitlines():
        name, found, version = line.strip().partition("==")
        if found and not name.startswith("#"):
            agreed[_folded(name)] = version.strip()
    pins, out = read_pins(text)
    if not pins:
        out.append("the hashed file holds no pin (the check would be blind)")
    seen = set()
    for raw_name, version in pins:
        name = _folded(raw_name)
        if name in seen:
            out.append(f"{name} is pinned twice")
        seen.add(name)
        if agreed.get(name) != version:
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
    pinned = [name for name, _version in read_pins(text)[0]]
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


HASH = "    --hash=sha256:" + "0" * 64


@pytest.mark.parametrize("added", [
    "# a note \\\n--index-url http://example.invalid/simple",
    "# a note \\",
    "# a note \\\nrequests==2.0.0",
    "# -*- coding: utf-7 -*-",
    "   # an indented line",
    "--index-url http://example.invalid/simple",
    "anyio==${VERSION} \\\n" + HASH,
    "extra==1.0 \\",
    "extra==1.0 \\\n" + HASH + " \\\n--no-deps",
    "# a note\x0c--index-url http://example.invalid/simple",
    "# a note\u2028--index-url http://example.invalid/simple",
], ids=["option-behind-a-comment", "comment-with-backslash", "pin-behind-a-comment", "encoding", "indented-comment",
        "option", "variable", "pin-without-hash", "option-inside-an-entry", "form-feed", "line-separator"])
def test_nothing_can_be_hidden_in_the_file(added):
    assert file_problems(_read(HASHES) + "\n" + added + "\n", _read("integration/constraints.txt")) != []


@pytest.mark.parametrize("entry,said", [
    ("not-in-constraints==1.0 \\\n" + HASH, "is not the constraints file's pin"),
    ("anyio==0.0.1 \\\n" + HASH, "is pinned twice"),
], ids=["unknown-name", "second-pin"])
def test_a_well_formed_entry_must_still_be_the_agreed_one(entry, said):
    found = file_problems(_read(HASHES) + "\n" + entry + "\n", _read("integration/constraints.txt"))
    assert any(said in problem for problem in found), found


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
