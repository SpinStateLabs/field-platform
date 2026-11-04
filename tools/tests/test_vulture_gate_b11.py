"""B-11: the vulture dead-code gate (`tools/vulture_gate.py`) and its CI wiring.

Behaviour is proven on small temporary trees (clean passes; an unused import, unreachable code, a second unused
parameter and a stale allowlist entry each fail; a listed framework parameter passes), the shipped tree is proven
clean, and every check is run against mutants of the gate that must fail it. vulture itself is installed by the CI
`Install platform` step from the pinned constraints; where it is missing locally the behaviour tests skip, but under
CI (`CI` set) they FAIL instead, so a missing install cannot turn the gate into a silent no-op.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "tools" / "vulture_gate.py"
CI = ROOT / ".github" / "workflows" / "ci.yml"
CI_CONSTRAINTS = ROOT / "integration" / "ci-constraints.txt"

HAVE_VULTURE = importlib.util.find_spec("vulture") is not None


def _need_vulture() -> None:
    if HAVE_VULTURE:
        return
    if os.environ.get("CI"):
        pytest.fail("vulture is not installed under CI: the dead-code gate would not run")
    pytest.skip("vulture is not installed (the CI Install step pins and installs it)")


def _load(path: Path, name: str = "vulture_gate_under_test"):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _tree(base: Path, source: str | None) -> Path:
    root = base / "tree"
    pkg = root / "packages" / "x" / "src" / "x"
    if source is not None:
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "m.py").write_text(source)
    else:
        root.mkdir()
    return root


M = "packages/x/src/x/m.py"
CLEAN = "import os\n\n\ndef f():\n    return os.getcwd()\n"
UNUSED_IMPORT = "import os\nimport json\n\n\ndef f():\n    return os.getcwd()\n"
UNREACHABLE = "def f():\n    return 1\n    print('never')\n"
PARAM = "def redirect(msg):\n    return 1\n\n\nredirect(0)\n"
TWO_PARAMS = "def a(msg):\n    return 1\n\n\ndef b(msg):\n    return 2\n\n\na(0), b(0)\n"
DEAD_FUNCTION = "def dead():\n    return 1\n"  # vulture reports this at 60%, below the gate's 80%


def behaviour_problems(mod) -> list[str]:
    """What the gate gets wrong on small trees; empty for the shipped gate."""
    out: list[str] = []
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)

        def run(case: str, source: str | None, allow: list[tuple[str, str]], want: int, needle: str = "") -> None:
            sub = base / case
            sub.mkdir()
            rc, report = mod.gate(_tree(sub, source), allow)
            text = "\n".join(report)
            if rc != want:
                out.append(f"{case}: exit {rc}, wanted {want}")
            elif needle and needle not in text:
                out.append(f"{case}: report lacks {needle!r}")

        run("clean", CLEAN, [], 0)
        run("unused import", UNUSED_IMPORT, [], 1, "unused import 'json'")
        run("unreachable", UNREACHABLE, [], 1, "unreachable code")
        run("unused function is not reported at 80", DEAD_FUNCTION, [], 0)
        run("noqa suppresses the finding on its line", "import os  # noqa\n", [], 0)
        sub = base / "unscanned tools"
        sub.mkdir()
        unscanned = _tree(sub, CLEAN)
        (unscanned / "tools").mkdir()
        (unscanned / "tools" / "t.py").write_text(UNUSED_IMPORT)  # tools/ is documented as not scanned
        rc, report = mod.gate(unscanned, [])
        if rc != 0:
            out.append(f"unscanned tools: exit {rc}, report {report!r}")
        sub = base / "name used elsewhere"
        sub.mkdir()
        shared = _tree(sub, "import os\n\n\ndef f():\n    return 1\n")  # os is unused here ...
        (shared / "packages" / "x" / "src" / "x" / "n.py").write_text("import os\n\n\ndef g():\n    return os.getcwd()\n")
        rc, report = mod.gate(shared, [])  # ... but vulture matches by name across the tree, so nothing is reported
        if rc != 0:
            out.append(f"name used elsewhere: exit {rc}, report {report!r}")
        run("listed param", PARAM, [(M, "msg")], 0)
        run("duplicate entries cover two findings", TWO_PARAMS, [(M, "msg"), (M, "msg")], 0)
        run("unlisted param", PARAM, [], 1, "unused variable 'msg'")
        run("second param", TWO_PARAMS, [(M, "msg")], 1, "unused variable 'msg'")
        run("stale entry", CLEAN, [(M, "msg")], 1, "stale allowlist entry")
        run("no source dir", None, [], 2, "blind")

        def exit_code(case: str, source: str | None, want: int) -> None:
            sub = base / case
            sub.mkdir()
            real_defaults = mod.gate.__defaults__
            mod.gate.__defaults__ = ([],)  # main() uses the shipped ALLOWLIST: on a tiny tree it is all stale entries
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    rc = mod.main(["vulture_gate", str(_tree(sub, source))])
            finally:
                mod.gate.__defaults__ = real_defaults
            if rc != want:
                out.append(f"main {case}: exit {rc}, wanted {want}")

        exit_code("main clean", CLEAN, 0)
        exit_code("main unused import", UNUSED_IMPORT, 1)
        exit_code("main syntax error", "def f(:\n", 2)  # vulture itself exits 1 here: the gate must say 2
        exit_code("main no source dir", None, 2)

        sub = base / "vulture exit 5"
        sub.mkdir()
        real = mod.run_vulture
        mod.run_vulture = lambda root, dirs: (5, "", "boom")  # neither 0 nor 3: vulture did not run
        try:
            rc, report = mod.gate(_tree(sub, CLEAN), [])
        finally:
            mod.run_vulture = real
        if rc != 2 or "vulture did not run" not in "\n".join(report):
            out.append(f"vulture exit 5: exit {rc}, report {report!r}")
    return out


def test_gate_behaviour_on_small_trees():
    _need_vulture()
    assert behaviour_problems(_load(GATE)) == []


def test_shipped_tree_is_clean():
    _need_vulture()
    rc, report = _load(GATE).gate(ROOT)
    assert (rc, report) == (0, [])


def test_the_script_exit_code_is_the_gate_result(tmp_path):
    _need_vulture()
    (tmp_path / "f").mkdir()
    (tmp_path / "b").mkdir()
    for case, root, want, needle in (
        ("clean", ROOT, 0, "vulture gate: clean"),  # the shipped tree: the only root the shipped ALLOWLIST fits
        ("findings", _tree(tmp_path / "f", UNUSED_IMPORT), 1, "unused import 'json'"),
        ("blind", _tree(tmp_path / "b", None), 2, "vulture gate: FAILED"),
    ):
        proc = subprocess.run([sys.executable, str(GATE), str(root)], capture_output=True, text=True)
        assert proc.returncode == want, (case, proc.stdout, proc.stderr)
        assert needle in proc.stdout, (case, proc.stdout)
        if case == "findings":  # the report names file and line, as the docstring says
            assert re.search(r"m\.py:\d+: unused import 'json'", proc.stdout), proc.stdout


def test_every_allowlist_entry_names_an_existing_file():
    mod = _load(GATE)
    assert len(mod.ALLOWLIST) == 6
    assert [p for p, _ in mod.ALLOWLIST if not (ROOT / p).is_file()] == []


GATE_MUTANTS = {
    "confidence raised to 100 (an unused import is 90)": ('MIN_CONFIDENCE = "80"', 'MIN_CONFIDENCE = "100"'),
    "confidence lowered to 60 (an unused function is reported)": ('MIN_CONFIDENCE = "80"', 'MIN_CONFIDENCE = "60"'),
    "an allowlist entry is not consumed": ("allowed[(path, name)] -= 1", "pass"),
    "every finding counts as allowed": ("if allowed[(path, name)] > 0:", "if True:"),
    "findings exit treated as vulture failure": ("if rc not in (0, 3):", "if rc not in (0,):"),
    "stale entries are not reported": ("for _ in range(left)", "for _ in range(0)"),
    "a missing source directory is not blind": ("if not dirs:", "if False:"),
    "tools/ is scanned too": ('("packages/*/src", "services/*/src")', '("packages/*/src", "services/*/src", "tools")'),
    "the allowlist is a set (duplicate entries cover one finding)": ("allowed = Counter(allowlist)", "allowed = Counter(set(allowlist))"),
    "main always exits 0": ('item(s))")\n    return rc', 'item(s))")\n    return 0'),
    "vulture did not run exits 1": ('return 2, [f"vulture did not run', 'return 1, [f"vulture did not run'),
}


@pytest.mark.parametrize("label", sorted(GATE_MUTANTS))
def test_gate_mutants_fail_the_behaviour_checks(label, tmp_path):
    _need_vulture()
    old, new = GATE_MUTANTS[label]
    src = GATE.read_text()
    assert src.count(old) == 1, f"mutation pattern does not apply exactly once: {label}"
    mutant = tmp_path / "vulture_gate_mutant.py"
    mutant.write_text(src.replace(old, new))
    assert behaviour_problems(_load(mutant, "vulture_gate_mutant")) != [], f"mutant survived: {label}"


def test_the_gate_texts_do_not_claim_what_vulture_reports_only_at_60():
    claims = (
        "unused variable or function", "unused function or variable", "unused variable, function",
        "unused function, variable", "new unused function", "new unused class", "new unused method",
    )
    for path in (GATE, CI):
        text = " ".join(path.read_text().lower().split())
        assert [c for c in claims if c in text] == [], path
    assert "by name" in " ".join(GATE.read_text().lower().split())  # the name-matching limit is stated
    assert "anywhere else" in " ".join(CI.read_text().lower().split())


def _steps() -> list[dict]:
    return yaml.safe_load(CI.read_text())["jobs"]["tests"]["steps"]


def test_ci_runs_the_gate_after_the_platform_install():
    steps = _steps()
    names = [s.get("name") for s in steps]
    gate = [s for s in steps if s.get("run", "").strip() == "python tools/vulture_gate.py"]
    assert len(gate) == 1
    assert names.index("Install platform") < steps.index(gate[0])


def test_ci_installs_vulture_through_the_pinned_constraints():
    (install,) = [s["run"] for s in _steps() if s.get("name") == "Install platform"]
    lines = [ln.strip() for ln in install.splitlines() if ln.strip().startswith("pip install")]
    assert any("$C" in ln.split() and "vulture" in ln.split() for ln in lines)
    pins = [ln.strip() for ln in CI_CONSTRAINTS.read_text().splitlines() if ln.strip().lower().startswith("vulture==")]
    assert len(pins) == 1 and pins[0].count("==") == 1


GATE_RUN = "python tools/vulture_gate.py"


def wiring_problems(text: str) -> list[str]:
    """How the gate step could be skipped or made advisory; empty for the shipped workflow."""
    job = yaml.safe_load(text)["jobs"]["tests"]
    gate = [s for s in job["steps"] if s.get("run", "").strip() == GATE_RUN]
    if len(gate) != 1:
        return [f"{len(gate)} gate steps, wanted exactly 1"]
    out = []
    for key in ("continue-on-error", "if"):
        if key in gate[0]:
            out.append(f"the gate step has {key!r}")
        if key in job:
            out.append(f"the tests job has {key!r}")
    return out


def test_the_gate_step_cannot_be_skipped_or_made_advisory():
    assert wiring_problems(CI.read_text()) == []


WIRING_MUTANTS = {
    "continue-on-error on the gate step (C03)": (f"        run: {GATE_RUN}\n", f"        run: {GATE_RUN}\n        continue-on-error: true\n"),
    "an if on the gate step (C04)": (f"        run: {GATE_RUN}\n", f"        run: {GATE_RUN}\n        if: github.event_name == 'never'\n"),
    "continue-on-error on the tests job": ("  tests:\n    runs-on: ubuntu-latest\n", "  tests:\n    runs-on: ubuntu-latest\n    continue-on-error: true\n"),
    "the gate step runs twice": (f"        run: {GATE_RUN}\n", f"        run: {GATE_RUN}\n      - run: {GATE_RUN}\n"),
}


@pytest.mark.parametrize("label", sorted(WIRING_MUTANTS))
def test_wiring_mutants_are_caught(label):
    old, new = WIRING_MUTANTS[label]
    text = CI.read_text()
    assert text.count(old) == 1, f"mutation pattern does not apply exactly once: {label}"
    assert wiring_problems(text.replace(old, new)) != [], f"mutant survived: {label}"


def test_static_mutants_of_the_ci_wiring_are_caught():
    text = CI.read_text()
    assert "python tools/vulture_gate.py" in text
    stripped = text.replace("python tools/vulture_gate.py", "python tools/does_not_exist.py")
    steps = yaml.safe_load(stripped)["jobs"]["tests"]["steps"]
    assert not [s for s in steps if s.get("run", "").strip() == "python tools/vulture_gate.py"]
    unpinned = CI_CONSTRAINTS.read_text().replace("vulture==", "# vulture==")
    assert not [ln for ln in unpinned.splitlines() if ln.strip().lower().startswith("vulture==")]
