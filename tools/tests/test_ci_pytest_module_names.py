"""No two test modules collected by one repo-root ``pytest`` step in CI share an import name.

The "Test field-core + non-conftest services" step of .github/workflows/ci.yml
runs ONE ``pytest`` over several ``tests/`` directories, and none of them is a
package (no ``__init__.py``). Under pytest's default ``--import-mode=prepend``
a test module outside a package is imported under its bare file stem. Two
``test_x.py`` files in two of those directories therefore collide: pytest
imports the first, fails every other one with "import file mismatch", and the
step ends with "Interrupted: N errors during collection" before any test runs.
A per-service run (``cd services/<s> && python -m pytest tests``) never sees
the clash. That is how five ``test_store_lock_coverage.py`` files reached the
tree with every service suite green.

``conftest.py`` is exempt: pytest deletes ``sys.modules["conftest"]`` before it
imports each conftest that is not in a package.

The first test applies that rule statically, from ci.yml and the files on disk,
and names the colliding files. The second runs each such multi-path step's own
argument list under ``--collect-only`` in a fresh interpreter and requires a
clean collection, so the static model cannot drift from what pytest does.
Steps with a ``working-directory`` and commands inside a subshell
(``(cd ... && python -m pytest ...)``) do not run from the repo root and are
not checked here.
"""

from __future__ import annotations

import fnmatch
import os
import shlex
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"

# pytest's defaults. pytest takes its configuration from the first config file
# on an argument's ancestor chain (for the services step that is
# packages/field-core/pyproject.toml), so the model is only valid while no
# config file on those chains changes these settings; _multi_path_steps asserts it.
PYTHON_FILES = ("test_*.py", "*_test.py")
NORECURSEDIRS = ("*.egg", ".*", "_darcs", "build", "CVS", "dist", "node_modules", "venv", "{arch}")
CONFIG_FILES = ("pytest.ini", ".pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg")
MODEL_SETTINGS = ("python_files", "norecursedirs", "import-mode", "import_mode", "consider_namespace_packages",
                  "collect_in_virtualenv")


def _root_pytest_steps() -> list[tuple[str, list[str]]]:
    """(job: step name, arguments after ``pytest``) for each CI command run from the repo root."""
    doc = yaml.safe_load(CI.read_text(encoding="utf-8"))
    steps = []
    for job_name, job in doc["jobs"].items():
        if (job.get("defaults") or {}).get("run", {}).get("working-directory"):
            continue
        for step in job.get("steps", []):
            run = step.get("run")
            if not isinstance(run, str) or "pytest" not in run or step.get("working-directory"):
                continue
            for line in run.replace("\\\n", " ").splitlines():
                try:
                    argv = shlex.split(line, comments=True)
                except ValueError:
                    continue
                if argv[:1] == ["pytest"]:
                    args = argv[1:]
                elif len(argv) >= 3 and argv[0] in ("python", "python3") and argv[1:3] == ["-m", "pytest"]:
                    args = argv[3:]
                else:
                    continue
                steps.append((f"{job_name}: {step.get('name', '<unnamed step>')}", args))
    return steps


def _path_args(args: list[str]) -> list[Path]:
    """The positional arguments. Each must exist, so an option value or a shell
    expansion this parser does not understand fails loudly instead of being skipped."""
    paths = [ROOT / a for a in args if not a.startswith("-")]
    missing = [p.relative_to(ROOT).as_posix() for p in paths if not p.exists()]
    assert not missing, f"ci.yml passes pytest arguments this test cannot resolve under {ROOT}: {missing}"
    return paths


def _collected_modules(arg: Path) -> set[Path]:
    """The test modules pytest collects for one path argument, with the default rules."""
    if arg.is_file():
        return {arg.resolve()}
    found = set()
    for dirpath, dirnames, filenames in os.walk(arg):
        dirnames[:] = [
            d for d in dirnames
            if d != "__pycache__"
            and not any(fnmatch.fnmatch(d, pat) for pat in NORECURSEDIRS)
            and not (Path(dirpath, d, "pyvenv.cfg").is_file() or Path(dirpath, d, "conda-meta", "history").is_file())
        ]
        found.update(
            Path(dirpath, f).resolve() for f in filenames
            if f.endswith(".py") and any(fnmatch.fnmatch(f, pat) for pat in PYTHON_FILES)
        )
    return found


def _import_name(module: Path) -> str:
    """The module name pytest's prepend import mode uses (``resolve_package_path`` + stem)."""
    parts = [] if module.stem == "__init__" else [module.stem]
    d = module.parent
    while (d / "__init__.py").is_file() and d.name.isidentifier():
        parts.insert(0, d.name)
        d = d.parent
    return ".".join(parts)


def _model_overrides(paths: list[Path]) -> list[str]:
    """Config files on the arguments' ancestor chains (up to the repo root) that
    mention a setting the static model assumes is at its default."""
    hits = set()
    for path in paths:
        for base in (path, *path.parents):
            if not base.is_relative_to(ROOT):
                break
            for cfg in (base / name for name in CONFIG_FILES):
                if cfg.is_file() and any(s in cfg.read_text(encoding="utf-8", errors="replace") for s in MODEL_SETTINGS):
                    hits.add(cfg.relative_to(ROOT).as_posix())
    return sorted(hits)


def _multi_path_steps() -> list[tuple[str, list[str], list[Path]]]:
    steps = [(name, args, _path_args(args)) for name, args in _root_pytest_steps()]
    multi = [(name, args, paths) for name, args, paths in steps if len({p.resolve() for p in paths}) > 1]
    assert multi, f"no repo-root pytest step over more than one path found in {CI}; this test would be vacuous"
    overrides = _model_overrides([p for _name, _args, paths in multi for p in paths])
    assert not overrides, (
        f"{overrides} set one of {MODEL_SETTINGS}; teach this test that setting before trusting "
        "the pytest defaults it models")
    return multi


def test_no_two_test_modules_in_one_ci_pytest_step_share_an_import_name():
    problems = []
    for name, _args, paths in _multi_path_steps():
        by_import_name: dict[str, set[Path]] = defaultdict(set)
        for path in paths:
            modules = _collected_modules(path)
            assert modules, f"{name}: {path.relative_to(ROOT).as_posix()} holds no test module; this check would be vacuous"
            for module in modules:
                by_import_name[_import_name(module)].add(module)
        for import_name, modules in sorted(by_import_name.items()):
            if len(modules) > 1:
                files = sorted(m.relative_to(ROOT.resolve()).as_posix() for m in modules)
                problems.append(f"{name}: {len(files)} test modules import as {import_name!r}: {files}")
    assert not problems, (
        "one pytest over these directories stops at collection with 'import file mismatch'. "
        "Give each test file a unique basename (do not add __init__.py: it changes how the "
        "tests import):\n" + "\n".join(problems))


def test_each_multi_path_ci_pytest_step_collects_without_errors():
    env = {k: v for k, v in os.environ.items() if k not in ("PYTEST_ADDOPTS", "PYTEST_CURRENT_TEST")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for name, args, _paths in _multi_path_steps():
        # -P: like the bare ``pytest`` script CI runs, do not put the cwd on sys.path.
        cmd = [sys.executable, "-P", "-m", "pytest", "--collect-only", "-p", "no:cacheprovider", *args]
        proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
        lines = (proc.stdout + proc.stderr).strip().splitlines()
        tail = "\n".join(lines[-25:])
        assert proc.returncode == 0, f"{name}: `pytest {' '.join(args)}` --collect-only exited {proc.returncode}:\n{tail}"
        assert lines and "collected" in lines[-1] and "error" not in lines[-1].lower(), (
            f"{name}: collection did not end cleanly:\n{tail}")
