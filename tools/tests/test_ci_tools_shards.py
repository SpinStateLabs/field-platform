"""B-21 (Don via C-497): the two tools-test shards of the CI `tests` matrix drop nothing.

Shard 1 of `.github/workflows/ci.yml` runs a LITERAL list of tools test modules (the slowest
four by the B-02 measurement plus the two signed-operator modules the caller-signed guard needs
named); shard 2 runs every other `tools/tests/test_*.py`, computed from a `HEAVY` list that must
equal the literal one. A module named in only one of the two lists would run twice or never;
a misspelled name would run never; a step placed on a shard that does not exist would never run.
Each check is run on the shipped file and on a mutant that must fail it.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
SIGNED = ("tools/tests/test_phase_g_check_caller_signed.py", "tools/tests/test_signed_opev_eight_services.py")
STEP_SHARDS = {
    "Test field-core + non-conftest services": 1,
    "Test services with local conftest/imports": 2,
    "Deployed-topology lint (fail-open env vars armed on deployed estates)": 2,
}
PYTHON_VERSIONS = ["3.11", "3.12", "3.13", "3.14"]


def _job(text: str) -> dict:
    return yaml.safe_load(text)["jobs"]["tests"]


def _tools_step(job: dict) -> dict:
    (step,) = [s for s in job["steps"] if str(s.get("name", "")).startswith("Test tools")]
    return step


def _lists(step: dict) -> tuple[list[str], list[str]]:
    """(the HEAVY list, the literal shard-1 pytest arguments)."""
    run = step["run"]
    heavy = re.search(r'^\s*HEAVY="([^"]*)"\s*$', run, re.M)
    one = re.search(r"^\s*1\)\s+pytest\s+(.*?)\s*;;\s*$", run, re.M)
    assert heavy and one, "the tools step no longer has a HEAVY list and a literal shard-1 pytest line"
    return heavy.group(1).split(), [a for a in shlex.split(one.group(1)) if not a.startswith("-")]


def problems(text: str) -> list[str]:
    out: list[str] = []
    job = _job(text)
    matrix = job["strategy"]["matrix"]
    shards = matrix.get("shard")
    if shards != [1, 2]:
        out.append(f"matrix.shard is {shards!r}, not [1, 2]")
    # F-Q52-1 (reviewer Lane 7): an exclude or include, a dropped version or continue-on-error shrinks CI
    # with every remaining check still green; the matrix is exactly the two pinned axes, nothing more
    if set(matrix) != {"python-version", "shard"}:
        out.append(f"matrix keys are {sorted(matrix)}, not python-version and shard (no include, no exclude)")
    if matrix.get("python-version") != PYTHON_VERSIONS:
        out.append(f"python-version is {matrix.get('python-version')!r}, not {PYTHON_VERSIONS}")
    if "continue-on-error" in job or any("continue-on-error" in s for s in job["steps"]):
        out.append("continue-on-error would let a red shard pass the job")
    step = _tools_step(job)
    if "if" in step:
        out.append("the tools step is conditional; it must run on every shard")
    if str((step.get("env") or {}).get("TOOLS_SHARD")) != "${{ matrix.shard }}":
        out.append("TOOLS_SHARD is not matrix.shard")
    heavy, literal = _lists(step)
    if heavy != literal:
        out.append(f"HEAVY {heavy} differs from the literal shard-1 list {literal}")
    for f in dict.fromkeys(heavy + literal):
        if not (ROOT / f).is_file():
            out.append(f"not a file: {f}")
        if not re.fullmatch(r"tools/tests/test_[\w]+\.py", f):
            out.append(f"not a tools test module: {f}")
    if len(set(literal)) != len(literal):
        out.append("a module is listed twice in shard 1")
    for m in SIGNED:
        if m not in literal:
            out.append(f"shard 1 does not name {m}")
    if not re.search(r"^\s*2\)\s+ls tools/tests/test_\*\.py \| grep -vxF -f <\(printf '%s\\n' \$HEAVY\) \| xargs pytest -q ;;\s*$", step["run"], re.M):
        out.append("shard 2 is not the computed complement of HEAVY")
    for s in job["steps"]:
        cond = s.get("if")
        if cond is None:
            continue
        m = re.fullmatch(r"matrix\.shard == (\d+)", str(cond).strip())
        if not m:
            out.append(f"step {s.get('name')!r}: unrecognised condition {cond!r}")
        elif int(m.group(1)) not in (shards or []):
            out.append(f"step {s.get('name')!r} is placed on shard {m.group(1)}, which does not exist")
    for name, shard in STEP_SHARDS.items():
        hits = [s for s in job["steps"] if s.get("name") == name]
        if len(hits) != 1 or str(hits[0].get("if", "")).strip() != f"matrix.shard == {shard}":
            out.append(f"step {name!r} is not on shard {shard} exactly once")
    # F-Q52-4: the lint step must still run the lint, not only exist
    lint = [s for s in job["steps"] if s.get("name", "").startswith("Deployed-topology lint")]
    if not lint or str(lint[0].get("run", "")).strip() != "python tools/topology_lint.py":
        out.append("the topology-lint step no longer runs python tools/topology_lint.py")
    return out


def test_the_shipped_shards_drop_nothing():
    assert problems(CI.read_text(encoding="utf-8")) == []


def test_shard_1_and_shard_2_together_are_every_tools_test_module():
    heavy, _ = _lists(_tools_step(_job(CI.read_text(encoding="utf-8"))))
    every = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "tools" / "tests").glob("test_*.py"))
    complement = [f for f in every if f not in heavy]
    assert sorted(heavy) + complement and set(heavy) | set(complement) == set(every)
    assert not set(heavy) & set(complement)
    assert Path(__file__).relative_to(ROOT).as_posix() in complement


MUTANTS = {
    "HEAVY drops a module": ('HEAVY="tools/tests/test_topology_lint.py tools/tests/test_phase_g_check.py ',
                             'HEAVY="tools/tests/test_topology_lint.py '),
    "shard 1 misspells a module": ("1) pytest -q tools/tests/test_topology_lint.py", "1) pytest -q tools/tests/test_topology_lnt.py"),
    "a signed module leaves shard 1": ("tools/tests/test_signed_opev_eight_services.py ;;", ";;"),
    "a step on a third shard": ("- name: Test services with local conftest/imports\n        if: matrix.shard == 2",
                                "- name: Test services with local conftest/imports\n        if: matrix.shard == 3"),
    "the field-core step on no shard": ("- name: Test field-core + non-conftest services\n        if: matrix.shard == 1\n",
                                        "- name: Test field-core + non-conftest services\n"),
    "shard 2 filters with --ignore": ("| xargs pytest -q ;;", "| xargs pytest -q --ignore=tools/tests/test_ci_tools_shards.py ;;"),
    "a third shard in the matrix": ("shard: [1, 2]", "shard: [1, 2, 3]"),
    # F-Q52-1 and F-Q52-4 (reviewer Lane 7, Q-52): a matrix exclude or include, a dropped version,
    # continue-on-error, or a deleted topology-lint step each silently shrank CI
    "a matrix exclude drops one shard of one version": ("        shard: [1, 2]\n", "        shard: [1, 2]\n        exclude:\n          - python-version: \"3.14\"\n            shard: 2\n"),
    "a matrix include adds a job outside the pins": ("        shard: [1, 2]\n", "        shard: [1, 2]\n        include:\n          - python-version: \"3.10\"\n            shard: 1\n"),
    "a python version dropped": ('python-version: ["3.11", "3.12", "3.13", "3.14"]', 'python-version: ["3.11", "3.13", "3.14"]'),
    "continue-on-error on the tests job": ("    runs-on: ubuntu-latest\n    strategy:\n", "    runs-on: ubuntu-latest\n    continue-on-error: true\n    strategy:\n"),
    "continue-on-error on the tools step": ("        env:\n          TOOLS_SHARD: ${{ matrix.shard }}\n", "        continue-on-error: true\n        env:\n          TOOLS_SHARD: ${{ matrix.shard }}\n"),
    "the topology-lint step deleted": ("        if: matrix.shard == 2\n        run: python tools/topology_lint.py\n", "        if: matrix.shard == 2\n        run: true\n"),
}


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_each_mutant_is_caught(name):
    old, new = MUTANTS[name]
    text = CI.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"mutant {name!r}: anchor not found exactly once"
    assert problems(text.replace(old, new)), f"mutant {name!r} was not caught"
