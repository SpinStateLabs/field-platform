"""C-23 / C-459 / C-460 (reviewer C-9, C-450): the CI workflows install nothing unpinned.

Every `run:` of every job of every workflow under `.github/workflows` is read. Any installer call (`pip`,
`python -m pip`, `pip3`, `uv pip`, `pipx`, `$PIP`) is a finding unless it is the one pinned pip bootstrap
(`python -m pip install pip==X.Y.Z`) or it carries `$C` -- which the SAME step must define as the constraint files
plus `--build-constraint` -- or both `-c`/`--constraint` and `--build-constraint` inline. `--index-url`,
`--extra-index-url`, `git+`, `-U` and `--upgrade` are refused. A `$C` that only appears in a comment does not count.
`integration/ci-constraints.txt` and `integration/build-constraints.txt` hold exact pins only.
Each check is run on the shipped files and on mutants that must fail it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
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


def problems(texts: dict[str, str]) -> list[str]:
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


def constraint_problems(name: str, text: str) -> list[str]:
    entries = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    out = [f"{name}: not an exact pin: {e}" for e in entries if not re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.!+-]+", e)]
    if not entries:
        out.append(f"{name}: no pins")
    return out


def shipped() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])}


CI = "ci.yml"


def test_the_shipped_workflows_install_nothing_unpinned():
    assert problems(shipped()) == []


def test_the_constraint_files_exist_and_are_exact_pins():
    assert (ROOT / "integration" / "constraints.txt").is_file()
    for f in CONSTRAINT_FILES:
        text = (ROOT / "integration" / f).read_text(encoding="utf-8")
        assert constraint_problems(f, text) == []
    assert "pytest==" in (ROOT / "integration" / "ci-constraints.txt").read_text(encoding="utf-8")
    assert "hatchling==" in (ROOT / "integration" / "build-constraints.txt").read_text(encoding="utf-8")


def unpinned_build_backends(pyprojects: dict[str, str], pins: str) -> list[str]:
    out = []
    for name, text in pyprojects.items():
        m = re.search(r"requires\s*=\s*\[([^\]]*)\]", text)
        reqs = re.findall(r'"([A-Za-z0-9_.-]+)', m.group(1)) if m else []
        if not reqs:
            out.append(f"{name}: no build requirement found (the check is blind)")
        out += [f"{name} builds with {r}, which is not pinned" for r in reqs if not re.search(rf"(?m)^{re.escape(r)}==", pins)]
    return out


def _pyprojects() -> dict[str, str]:
    paths = [*ROOT.glob("packages/*/pyproject.toml"), *ROOT.glob("services/*/pyproject.toml"),
             *ROOT.glob("defence-shield/*/pyproject.toml")]
    return {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8") for p in paths}


def test_every_project_build_backend_is_pinned_in_build_constraints():
    pins = (ROOT / "integration" / "build-constraints.txt").read_text(encoding="utf-8")
    assert len(_pyprojects()) >= 17
    assert unpinned_build_backends(_pyprojects(), pins) == []


def test_a_project_whose_backend_is_not_pinned_is_caught():
    pins = (ROOT / "integration" / "build-constraints.txt").read_text(encoding="utf-8")
    assert unpinned_build_backends({"x/pyproject.toml": 'requires = ["hatchling"]'}, pins.replace("hatchling==", "# hatchling==")) != []
    assert unpinned_build_backends({"x/pyproject.toml": 'requires = ["setuptools>=61"]'}, pins) != []
    assert unpinned_build_backends({"x/pyproject.toml": "[project]\nname='x'"}, pins) != []


def _mutate(old: str, new: str, extra: str = "") -> dict[str, str]:
    texts = shipped()
    assert texts[CI].count(old) == 1, f"mutation anchor not found exactly once: {old!r}"
    texts[CI] = texts[CI].replace(old, new)
    if extra:
        texts["other.yml"] = extra
    return texts


STEP = "name: x\n    run: |\n"
OTHER_JOB = "on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n"
TWO_JOBS = "on: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n"
TWO_JOBS_C = TWO_JOBS + f"          {C_DEFINITION}\n"
MUTANTS = {
    "pip upgraded": lambda: _mutate("python -m pip install pip==", "python -m pip install --upgrade pip # "),
    "field-core install loses $C": lambda: _mutate('pip install $C -e "packages/field-core[dev]"', 'pip install -e "packages/field-core[dev]"'),
    "service loop loses $C": lambda: _mutate('pip install $C --no-deps -e "services/$s"', 'pip install --no-deps -e "services/$s"'),
    "tool install loses $C": lambda: _mutate("pip install $C fastapi uvicorn httpx pytest", "pip install fastapi uvicorn httpx pytest"),
    "C loses the build constraint": lambda: _mutate(" --build-constraint integration/build-constraints.txt\"", '"'),
    "C names one file": lambda: _mutate(" -c integration/ci-constraints.txt", ""),
    "an unconstrained install in another job": lambda: _mutate("jobs:", "jobs:", OTHER_JOB + "          pip install requests\n"),
    "python -m pip install requests": lambda: _mutate("jobs:", "jobs:", OTHER_JOB + "          python -m pip install requests\n"),
    "pip3 install": lambda: _mutate("jobs:", "jobs:", OTHER_JOB + "          pip3 install requests\n"),
    "after &&": lambda: _mutate("jobs:", "jobs:", OTHER_JOB + "          true && pip install requests\n"),
    "uv pip install": lambda: _mutate("jobs:", "jobs:", OTHER_JOB + "          uv pip install requests\n"),
    "pipx install": lambda: _mutate("jobs:", "jobs:", OTHER_JOB + "          pipx install requests\n"),
    "$PIP install": lambda: _mutate("jobs:", "jobs:", OTHER_JOB + "          $PIP install requests\n"),
    "$C only in a comment": lambda: _mutate("jobs:", "jobs:", OTHER_JOB + "          pip install requests # $C\n"),
    "$C undefined in that step": lambda: _mutate("jobs:", "jobs:", OTHER_JOB + "          pip install $C requests\n"),
    "extra index url": lambda: _mutate("pip install $C fastapi uvicorn httpx pytest", "pip install $C --index-url http://example.invalid/simple fastapi"),
    "git source": lambda: _mutate("pip install $C fastapi uvicorn httpx pytest", "pip install $C git+https://example.invalid/x.git"),
    "-U flag": lambda: _mutate("pip install $C fastapi uvicorn httpx pytest", "pip install -U $C fastapi"),
    "second install after && has no $C": lambda: _mutate("jobs:", "jobs:", TWO_JOBS_C + "          pip install $C -e x && pip install requests\n"),
    "$C in a trailing comment with C defined": lambda: _mutate("jobs:", "jobs:", TWO_JOBS_C + "          pip install requests # $C\n"),
    "index url on a continuation line": lambda: _mutate("jobs:", "jobs:", TWO_JOBS_C + "          pip install $C \\\n            --index-url http://example.invalid/simple requests\n"),
    "install in the second job": lambda: _mutate("jobs:", "jobs:", TWO_JOBS + "          pip install requests\n"),
    "bootstrap without a version": lambda: _mutate("python -m pip install pip==", "python -m pip install pip # "),
    "inline -c without the build constraint": lambda: _mutate("jobs:", "jobs:", TWO_JOBS + "          pip install -c a.txt requests\n"),
    "continuation line": lambda: _mutate("jobs:", "jobs:", OTHER_JOB + "          pip install \\\n            requests\n"),
}


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_each_install_mutant_is_caught(name):
    assert problems(MUTANTS[name]()) != [], "the mutant survived"


def test_a_constrained_install_in_another_job_is_accepted():
    ok = OTHER_JOB + f"          {C_DEFINITION}\n          pip install $C requests\n"
    assert problems(_mutate("jobs:", "jobs:", ok)) == []
    inline = OTHER_JOB + "          pip install -c a.txt --build-constraint b.txt requests\n"
    assert problems(_mutate("jobs:", "jobs:", inline)) == []


@pytest.mark.parametrize("old,new", [("pytest==", "pytest>="), ("pluggy==", "pluggy>=")])
def test_a_floating_ci_constraint_is_caught(old, new):
    text = (ROOT / "integration" / "ci-constraints.txt").read_text(encoding="utf-8")
    assert text.count(old) == 1
    assert constraint_problems("ci-constraints.txt", text.replace(old, new)) != []


@pytest.mark.parametrize("old,new", [("hatchling==", "hatchling>="), ("editables==", "editables")])
def test_a_floating_build_constraint_is_caught(old, new):
    text = (ROOT / "integration" / "build-constraints.txt").read_text(encoding="utf-8")
    assert text.count(old) == 1
    assert constraint_problems("build-constraints.txt", text.replace(old, new)) != []
