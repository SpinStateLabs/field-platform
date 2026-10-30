"""C-23 (reviewer C-9): the CI test job installs nothing unpinned.

The "Install platform" step of `.github/workflows/ci.yml` pins pip itself (`pip==X.Y.Z`, never `--upgrade`) and every
other `pip install` carries `$C`, which the step defines as the two constraints files; both files exist and every
entry in `integration/ci-constraints.txt` is an exact `name==version`. Each check is run on the shipped files and on a
mutant that must fail it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
CI_CONSTRAINTS = ROOT / "integration" / "ci-constraints.txt"


def _install_script(text: str) -> str:
    steps = yaml.safe_load(text)["jobs"]["tests"]["steps"]
    (script,) = [s["run"] for s in steps if s.get("name") == "Install platform"]
    return script


def _lines(script: str) -> list[str]:
    return [ln.strip() for ln in script.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def problems_in_install_step(text: str) -> list[str]:
    out: list[str] = []
    lines = _lines(_install_script(text))
    if any(re.search(r"(--upgrade|\s-U)\b", ln) for ln in lines):
        out.append("pip is upgraded to whatever is newest")
    if not any(re.fullmatch(r"python -m pip install pip==\d+(\.\d+)+", ln) for ln in lines):
        out.append("pip itself is not pinned to an exact version")
    if 'C="-c integration/constraints.txt -c integration/ci-constraints.txt"' not in lines:
        out.append("$C is not the two constraints files")
    installs = [ln for ln in lines if re.match(r"pip install\b", ln)]
    if not installs:
        out.append("no pip install found (the check is blind)")
    out += [f"unconstrained: {ln}" for ln in installs if "$C" not in ln.split()]
    return out


def problems_in_constraints(text: str) -> list[str]:
    entries = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    out = [f"not an exact pin: {e}" for e in entries if not re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.!+-]+", e)]
    if not any(e.lower().startswith("pytest==") for e in entries):
        out.append("pytest is not pinned")
    return out


INSTALL_MUTANTS = {
    "pip upgraded": ("python -m pip install pip==", "python -m pip install --upgrade pip # "),
    "field-core install loses $C": ('pip install $C -e "packages/field-core[dev]"', 'pip install -e "packages/field-core[dev]"'),
    "service loop loses $C": ('pip install $C --no-deps -e "services/$s"', 'pip install --no-deps -e "services/$s"'),
    "tool install loses $C": ("pip install $C fastapi uvicorn httpx pytest", "pip install fastapi uvicorn httpx pytest"),
    "C names one file": (' -c integration/ci-constraints.txt"', '"'),
}


def test_the_shipped_install_step_is_pinned():
    assert problems_in_install_step(CI.read_text(encoding="utf-8")) == []


def test_both_constraints_files_exist_and_are_exact_pins():
    assert (ROOT / "integration" / "constraints.txt").is_file()
    assert problems_in_constraints(CI_CONSTRAINTS.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("name", sorted(INSTALL_MUTANTS))
def test_each_install_mutant_is_caught(name):
    old, new = INSTALL_MUTANTS[name]
    text = CI.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"mutation anchor not found exactly once: {old!r}"
    assert problems_in_install_step(text.replace(old, new)) != [], "the mutant survived"


@pytest.mark.parametrize("old,new", [("pytest==", "pytest>="), ("pluggy==", "pluggy>=")])
def test_a_floating_constraint_is_caught(old, new):
    text = CI_CONSTRAINTS.read_text(encoding="utf-8")
    assert text.count(old) == 1
    assert problems_in_constraints(text.replace(old, new)) != []
