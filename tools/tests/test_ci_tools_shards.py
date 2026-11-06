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
import shutil
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
    shard2 = (r"^\s*2\)\s+FILES=\$\(ls tools/tests/test_\*\.py \| grep -vxF -f <\(printf '%s\\n' \$HEAVY\)\); "
              r'\[ -n "\$FILES" \] \|\| \{ echo "shard 2 is empty[^"]*" >&2; exit 1; \}; '
              r"printf '%s\\n' \$FILES \| xargs -r pytest -q ;;\s*$")
    if not re.search(shard2, step["run"], re.M):
        out.append("shard 2 is not the computed complement of HEAVY with the empty-shard refusal")
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
    "shard 2 filters with --ignore": ("| xargs -r pytest -q ;;", "| xargs -r pytest -q --ignore=tools/tests/test_ci_tools_shards.py ;;"),
    "shard 2 loses the empty-shard refusal": ('[ -n "$FILES" ] || { echo "shard 2 is empty: every tools test module is in HEAVY" >&2; exit 1; }; ', ""),
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



# ---- the step itself, run under a recording pytest shim (reviewer Q-52 O3 and F-Q52-2): the guard above
# pins the text; these run the extracted shell and check what pytest is handed.

def _tools_step_script() -> str:
    return _tools_step(_job(CI.read_text(encoding="utf-8")))["run"]


def _run_step(tmp_path: Path, shard: str, modules: list[str]) -> tuple[int, list[list[str]]]:
    """Run the real tools step in a scratch tree holding only `modules` and a pytest shim that records its
    arguments and exits 0; (exit code, the argument lists pytest received)."""
    import json
    import os
    import subprocess

    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash is not on PATH")
    tree = tmp_path / "tree"
    (tree / "tools" / "tests").mkdir(parents=True)
    for m in modules:
        (tree / m).write_text("", encoding="utf-8")
    shim = tmp_path / "bin"
    shim.mkdir()
    log = tmp_path / "calls.jsonl"
    (shim / "pytest").write_text("#!/usr/bin/env python3\nimport json, sys\n"
                                 f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + chr(10))\n",
                                 encoding="utf-8")
    (shim / "pytest").chmod(0o755)
    script = tmp_path / "step.sh"
    script.write_text(_tools_step_script(), encoding="utf-8")
    env = {**os.environ, "PATH": f"{shim}{os.pathsep}{os.environ.get('PATH', '')}", "TOOLS_SHARD": shard}
    proc = subprocess.run([bash, "-e", str(script)], cwd=tree, env=env, capture_output=True, text=True, timeout=120)
    calls = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return proc.returncode, calls


def test_the_step_hands_shard_1_the_literal_list_and_shard_2_the_rest(tmp_path):
    heavy, _ = _lists(_tools_step(_job(CI.read_text(encoding="utf-8"))))
    extra = ["tools/tests/test_zz_new_module.py", "tools/tests/test_aa_other.py"]
    rc1, calls1 = _run_step(tmp_path / "one", "1", heavy + extra)
    assert (rc1, calls1) == (0, [["-q", *heavy]])
    rc2, calls2 = _run_step(tmp_path / "two", "2", heavy + extra)
    assert rc2 == 0 and len(calls2) == 1 and calls2[0][0] == "-q"
    assert sorted(calls2[0][1:]) == sorted(extra)


def test_an_empty_shard_2_exits_1_and_never_calls_pytest(tmp_path):
    heavy, _ = _lists(_tools_step(_job(CI.read_text(encoding="utf-8"))))
    rc, calls = _run_step(tmp_path, "2", heavy)
    assert (rc, calls) == (1, [])


def test_an_unknown_shard_exits_1_and_never_calls_pytest(tmp_path):
    heavy, _ = _lists(_tools_step(_job(CI.read_text(encoding="utf-8"))))
    rc, calls = _run_step(tmp_path, "3", heavy)
    assert (rc, calls) == (1, [])
