"""C-23 (reviewer C-9): every package the CI test job installs is pinned (C-459: and the build backend).

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
    if (
        'C="-c integration/constraints.txt -c integration/ci-constraints.txt'
        ' --build-constraint integration/build-constraints.txt"'
    ) not in lines:
        out.append("$C is not the two constraints files plus the build constraints")
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
    "C names one file": (' -c integration/ci-constraints.txt --build', ' --build'),
    "C loses the build constraint": (" --build-constraint integration/build-constraints.txt\"", "\""),
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


# --- C-459 (reviewer C-450 F-C450-1): the build environment is pinned too ---------------------------------------------

BUILD_CONSTRAINTS = ROOT / "integration" / "build-constraints.txt"


def _entries(path: Path) -> list[str]:
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def _build_requires() -> set[str]:
    """Every distribution named in a `[build-system] requires = [...]` of a project the CI step installs."""
    import tomllib

    names: set[str] = set()
    for pyproject in ROOT.glob("**/pyproject.toml"):
        if ".git" in pyproject.parts or "node_modules" in pyproject.parts:
            continue
        for req in tomllib.loads(pyproject.read_text(encoding="utf-8")).get("build-system", {}).get("requires", []):
            names.add(re.split(r"[<>=!~;\[ ]", req, maxsplit=1)[0].strip().lower())
    return names


def test_the_build_constraints_are_exact_pins_and_pin_hatchling_and_editables():
    entries = _entries(BUILD_CONSTRAINTS)
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.!+-]+", e) for e in entries), entries
    pinned = {e.split("==")[0].lower() for e in entries}
    assert {"hatchling", "editables", "packaging", "pathspec", "pluggy", "tomlkit", "trove-classifiers"} <= pinned


def test_every_build_backend_a_project_declares_is_pinned():
    declared = _build_requires()
    assert declared, "no [build-system] requires found: the scan is blind"
    pinned = {e.split("==")[0].lower() for e in _entries(BUILD_CONSTRAINTS)}
    assert declared <= pinned, f"unpinned build requirements: {sorted(declared - pinned)}"


def test_the_ci_constraint_variable_carries_the_build_constraints_into_every_install():
    text = CI.read_text(encoding="utf-8")
    assert "--build-constraint integration/build-constraints.txt" in text
    assert problems_in_install_step(text) == []


@pytest.mark.parametrize("old,new", [
    ("hatchling==", "hatchling>="), ("editables==", "editables>="), ("pathspec==", "pathspec~="),
])
def test_a_floating_build_constraint_is_caught(old, new):
    text = BUILD_CONSTRAINTS.read_text(encoding="utf-8")
    assert text.count(old) == 1
    mutated = text.replace(old, new)
    assert not all(re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.!+-]+", e) for e in
                   [ln.strip() for ln in mutated.splitlines() if ln.strip() and not ln.lstrip().startswith("#")])


# --- C-460 (reviewer C-450 F-C450-2): every run of every job of every workflow ---------------------------------------
#
# The "Install platform" checks above read one step. These read EVERY `run:` of EVERY job of EVERY workflow file: any
# installer call (`pip`, `python -m pip`, `pip3`, `uv pip`, `pipx`, `$PIP`) is a finding unless it is the one pinned pip
# bootstrap, or carries `$C` (which the SAME step must define as the constraint files plus `--build-constraint`), or both
# `-c`/`--constraint` and `--build-constraint` inline; `--index-url`, `--extra-index-url`, `git+`, `-U` and `--upgrade`
# are refused; a `$C` only in a comment does not count; continuations, `&&` / `;` / `|` and comments are handled.

CI_NAME = "ci.yml"

WORKFLOWS = ROOT / ".github" / "workflows"
CONSTRAINT_FILES = ["ci-constraints.txt", "build-constraints.txt"]
C_DEFINITION = ('C="-c integration/constraints.txt -c integration/ci-constraints.txt '
                '--build-constraint integration/build-constraints.txt"')
PIN_LINE = re.compile(r"python3? -m pip install pip==\d+(\.\d+)+")
INSTALLER = re.compile(r"(?<![\w-])(?:(?:python3?\s+-m\s+)?pip3?|uv\s+pip|pipx|\$\{?PIP\}?)\s+install\b")
REFUSED = re.compile(r"--index-url|--extra-index-url|(?<![\w-])-i\s|git\+|(?<![\w-])-U\b|--upgrade")


def run_scripts(texts: dict[str, str]) -> list[tuple[str, str, str]]:
    """(workflow file, 'job/step', run script) for every step with a `run:` of every job."""
    out = []
    for name, text in texts.items():
        for job, body in (yaml.safe_load(text).get("jobs") or {}).items():
            for i, step in enumerate(body.get("steps") or []):
                if isinstance(step, dict) and step.get("run"):
                    out.append((name, f"{job}/{step.get('name', i)}", step["run"]))
    return out


def statements(script: str) -> list[str]:
    """Shell statements of a script: continuations joined, comments dropped, split on && || ; | and newlines."""
    joined = re.sub(r"\\\n\s*", " ", script)
    lines = [re.sub(r"(^|\s)#.*$", "", ln).strip() for ln in joined.splitlines()]
    return [s.strip() for ln in lines for s in re.split(r"&&|\|\||;|\|", ln) if s.strip()]


def workflow_problems(texts: dict[str, str]) -> list[str]:
    out: list[str] = []
    installs = 0
    for name, step, script in run_scripts(texts):
        stmts = statements(script)
        defines_c = C_DEFINITION in stmts
        for st in stmts:
            m = INSTALLER.search(st)
            if not m:
                continue
            installs += 1
            where = f"{name} {step}: {st}"
            if PIN_LINE.fullmatch(st):
                continue
            if re.search(r"(?<![\w-])-U\b|--upgrade", st) and "pip install" in st and "pip==" in st:
                out.append(f"pip is upgraded, not pinned: {where}")
                continue
            if REFUSED.search(st):
                out.append(f"refused option or source: {where}")
            words = st.split()
            inline = ("-c" in words or "--constraint" in words) and "--build-constraint" in words
            if "$C" not in words and "${C}" not in words and not inline:
                out.append(f"unconstrained install: {where}")
            elif "$C" in words and not defines_c:
                out.append(f"$C is not defined as the constraint files in the same step: {where}")
    if not installs:
        out.append("no installer call found in any workflow (the check is blind)")
    return out

def shipped_workflows() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])}

def _mutate_workflow(old: str, new: str, extra: str = "") -> dict[str, str]:
    texts = shipped_workflows()
    assert texts[CI_NAME].count(old) == 1, f"mutation anchor not found exactly once: {old!r}"
    texts[CI_NAME] = texts[CI_NAME].replace(old, new)
    if extra:
        texts["other.yml"] = extra
    return texts


STEP = "name: x\n    run: |\n"
OTHER_JOB = "on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n"
TWO_JOBS = "on: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n"
TWO_JOBS_C = TWO_JOBS + f"          {C_DEFINITION}\n"
WORKFLOW_MUTANTS = {
    "pip upgraded": lambda: _mutate_workflow("python -m pip install pip==", "python -m pip install --upgrade pip # "),
    "field-core install loses $C": lambda: _mutate_workflow('pip install $C -e "packages/field-core[dev]"', 'pip install -e "packages/field-core[dev]"'),
    "service loop loses $C": lambda: _mutate_workflow('pip install $C --no-deps -e "services/$s"', 'pip install --no-deps -e "services/$s"'),
    "tool install loses $C": lambda: _mutate_workflow("pip install $C fastapi uvicorn httpx pytest", "pip install fastapi uvicorn httpx pytest"),
    "C loses the build constraint": lambda: _mutate_workflow(" --build-constraint integration/build-constraints.txt\"", '"'),
    "C names one file": lambda: _mutate_workflow(" -c integration/ci-constraints.txt", ""),
    "an unconstrained install in another job": lambda: _mutate_workflow("jobs:", "jobs:", OTHER_JOB + "          pip install requests\n"),
    "python -m pip install requests": lambda: _mutate_workflow("jobs:", "jobs:", OTHER_JOB + "          python -m pip install requests\n"),
    "pip3 install": lambda: _mutate_workflow("jobs:", "jobs:", OTHER_JOB + "          pip3 install requests\n"),
    "after &&": lambda: _mutate_workflow("jobs:", "jobs:", OTHER_JOB + "          true && pip install requests\n"),
    "uv pip install": lambda: _mutate_workflow("jobs:", "jobs:", OTHER_JOB + "          uv pip install requests\n"),
    "pipx install": lambda: _mutate_workflow("jobs:", "jobs:", OTHER_JOB + "          pipx install requests\n"),
    "$PIP install": lambda: _mutate_workflow("jobs:", "jobs:", OTHER_JOB + "          $PIP install requests\n"),
    "$C only in a comment": lambda: _mutate_workflow("jobs:", "jobs:", OTHER_JOB + "          pip install requests # $C\n"),
    "$C undefined in that step": lambda: _mutate_workflow("jobs:", "jobs:", OTHER_JOB + "          pip install $C requests\n"),
    "extra index url": lambda: _mutate_workflow("pip install $C fastapi uvicorn httpx pytest", "pip install $C --index-url http://example.invalid/simple fastapi"),
    "git source": lambda: _mutate_workflow("pip install $C fastapi uvicorn httpx pytest", "pip install $C git+https://example.invalid/x.git"),
    "-U flag": lambda: _mutate_workflow("pip install $C fastapi uvicorn httpx pytest", "pip install -U $C fastapi"),
    "second install after && has no $C": lambda: _mutate_workflow("jobs:", "jobs:", TWO_JOBS_C + "          pip install $C -e x && pip install requests\n"),
    "$C in a trailing comment with C defined": lambda: _mutate_workflow("jobs:", "jobs:", TWO_JOBS_C + "          pip install requests # $C\n"),
    "index url on a continuation line": lambda: _mutate_workflow("jobs:", "jobs:", TWO_JOBS_C + "          pip install $C \\\n            --index-url http://example.invalid/simple requests\n"),
    "install in the second job": lambda: _mutate_workflow("jobs:", "jobs:", TWO_JOBS + "          pip install requests\n"),
    "bootstrap without a version": lambda: _mutate_workflow("python -m pip install pip==", "python -m pip install pip # "),
    "inline -c without the build constraint": lambda: _mutate_workflow("jobs:", "jobs:", TWO_JOBS + "          pip install -c a.txt requests\n"),
    "continuation line": lambda: _mutate_workflow("jobs:", "jobs:", OTHER_JOB + "          pip install \\\n            requests\n"),
}


@pytest.mark.parametrize("name", sorted(WORKFLOW_MUTANTS))
def test_each_workflow_mutant_is_caught(name):
    assert workflow_problems(WORKFLOW_MUTANTS[name]()) != [], "the mutant survived"


def test_a_constrained_install_in_another_job_of_another_workflow_is_accepted():
    ok = OTHER_JOB + f"          {C_DEFINITION}\n          pip install $C requests\n"
    assert workflow_problems(_mutate_workflow("jobs:", "jobs:", ok)) == []
    inline = OTHER_JOB + "          pip install -c a.txt --build-constraint b.txt requests\n"
    assert workflow_problems(_mutate_workflow("jobs:", "jobs:", inline)) == []


def test_the_shipped_workflows_install_nothing_unpinned():
    assert workflow_problems(shipped_workflows()) == []
