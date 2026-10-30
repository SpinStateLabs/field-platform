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
# The "Install platform" checks above read one step. These read EVERY `run:` of EVERY job of EVERY workflow file, and
# every composite-action step under .github/actions: any installer call (`pip*`, `pip.exe`, `python -m pip`, `uv`, `pipx`,
# `$PIP`) with an install/download/wheel/config verb, behind any global option, is a finding unless it is the one pinned
# pip bootstrap, or carries `$C` while the SAME step has defined `$C` as the constraint files plus `--build-constraint`
# EARLIER and not reassigned, unset or blanked it since, or carries non-empty inline `-c`/`--constraint` and
# `--build-constraint`. Refused: --index-url / --extra-index-url / -i / -ihttp, -f / --find-links, --trusted-host,
# --no-build-isolation, -U / --upgrade (also in bundles: -qU, -Ur), -r / --requirement (contents not checked), any URL,
# `pkg@url` or git+/hg+/svn+/bzr+ argument, `pip config`, pip.conf/pip.ini, PIP_* env (workflow, job, step, composite or
# set in a script) other than a harmless allowlist, and a `run:` that is only an `${{ }}` expression. Statements are split
# on && || ; | and newlines outside quotes; a `#` inside quotes is not a comment; `eval "..."`, `bash -c '...'` and `$(...)`
# bodies are read as words.
#
# What this does NOT prove (C-643, reviewer C-627 F-C627-1..6): installs through a variable-named command other than
# *PIP* (`$P install`), `eval "$X"` with a built string, installers reached through scripts or Makefiles the workflow
# calls (`./ci.sh`), `python setup.py install`, `python -c "import pip..."`, a `uses:` action from another repository or an
# unscanned local path, a quoted "$C" (one word), constraint files whose CONTENT is not an exact pin (the tests above cover
# the two shipped files), local wheels or directories as arguments, and a runner image whose global pip.conf differs.
# GX10 / real runners were not used: this is static text analysis only.

CI_NAME = "ci.yml"

WORKFLOWS = ROOT / ".github" / "workflows"
ACTIONS = ROOT / ".github" / "actions"
CONSTRAINT_FILES = ["ci-constraints.txt", "build-constraints.txt"]
C_DEFINITION = ('C="-c integration/constraints.txt -c integration/ci-constraints.txt '
                '--build-constraint integration/build-constraints.txt"')
PIN_LINE = re.compile(r"python3? -m pip install pip==\d+(\.\d+)+")
PIP_NAME = re.compile(r"(?:.*/)?pip[\d.]*(?:\.exe)?|pipx|\$\{?\w*PIP\w*\}?")
VERBS = {"install", "download", "wheel", "config"}
UV_VERBS = {"install", "add", "sync"}
# any option spelling that moves the index/source, upgrades, loads requirement files or weakens isolation
LONG_REFUSED = re.compile(r"--(?:index-url|extra-index-url|find-links|trusted-host|no-build-isolation|upgrade|requirement"
                          r"|break-system-packages)\b")
URL_ARG = re.compile(r"(?:git|hg|svn|bzr)\+|://|^[^-][^=]*@\S")
PIP_ENV = re.compile(r"(?<![\w])(PIP_[A-Z_]+)=")
PIP_ENV_OK = {"PIP_DISABLE_PIP_VERSION_CHECK", "PIP_NO_CACHE_DIR", "PIP_PROGRESS_BAR", "PIP_NO_INPUT", "PIP_QUIET",
              "PIP_ROOT_USER_ACTION"}
EMPTY_FILES = {"", "/dev/null", "nul", "NUL", "-"}


def statements(script: str) -> list[str]:
    """Shell statements: continuations joined, comments dropped (a `#` inside quotes is not a comment), then split on
    && || ; | and newlines, each outside quotes. Quote characters stay in the statement."""
    s = re.sub(r"\\\n\s*", " ", script) + "\n"
    out, cur, quote, i = [], [], "", 0
    while i < len(s):
        ch = s[i]
        if quote:
            cur.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(s):
                cur.append(s[i + 1]); i += 1
            elif ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch; cur.append(ch)
        elif ch == "#" and (not cur or cur[-1].isspace()):
            while i < len(s) and s[i] != "\n":
                i += 1
            continue
        elif ch in "\n;|&" and (ch in "\n;" or s[i:i + 2] in ("&&", "||") or ch == "|"):
            if s[i:i + 2] in ("&&", "||"):
                i += 1
            out.append("".join(cur)); cur = []
        else:
            cur.append(ch)
        i += 1
    out.append("".join(cur))
    return [t.strip() for t in out if t.strip()]


def words(statement: str) -> list[str]:
    """Words of a statement with quote characters removed and `$(`, backticks and parentheses treated as spaces, so an
    installer inside `eval "..."`, `bash -c '...'` or `$(...)` is still seen. Over-approximates on purpose."""
    flat = re.sub(r"\$\(|[`()]", " ", statement).replace("'", "").replace('"', "")
    return flat.split()


def _installer_words(ws: list[str]) -> list[str] | None:
    """The words after the installer command if this statement runs one (install/download/wheel/config verb), else None."""
    for i, w in enumerate(ws):
        if PIP_NAME.fullmatch(w):
            if any(v in VERBS for v in ws[i + 1:]):
                return ws[i + 1:]
        if w == "uv" and any(v in UV_VERBS for v in ws[i + 1:]):
            return ws[i + 1:]
    return None


def _constraint_values(ws: list[str]) -> list[str]:
    vals = []
    for i, w in enumerate(ws):
        if w in ("-c", "--constraint") and i + 1 < len(ws):
            vals.append(ws[i + 1])
        elif w.startswith("--constraint="):
            vals.append(w.split("=", 1)[1])
    return vals


def run_scripts(texts: dict[str, str]) -> list[tuple[str, str, str]]:
    """(file, 'job/step', run script) for every `run:` of every job step and every composite-action step. A `run:`
    that is only an `${{ }}` expression cannot be read and is reported as itself."""
    out = []
    for name, text in texts.items():
        doc = yaml.safe_load(text) or {}
        groups = [(job, body.get("steps")) for job, body in (doc.get("jobs") or {}).items()]
        if isinstance(doc.get("runs"), dict):
            groups.append(("composite", doc["runs"].get("steps")))
        for job, steps in groups:
            for i, step in enumerate(steps or []):
                if isinstance(step, dict) and step.get("run") is not None:
                    out.append((name, f"{job}/{step.get('name', i)}", str(step["run"])))
    return out


def env_problems(texts: dict[str, str]) -> list[str]:
    """PIP_* variables in any workflow-, job-, step- or composite-step `env:` (other than harmless ones) are refused:
    they can move the index, add find-links, switch off isolation, or blank PIP_CONSTRAINT."""
    out = []
    for name, text in texts.items():
        doc = yaml.safe_load(text) or {}
        blocks = [("workflow", doc.get("env"))]
        for job, body in (doc.get("jobs") or {}).items():
            blocks.append((job, body.get("env")))
            blocks += [(f"{job}/{s.get('name', i)}", s.get("env")) for i, s in enumerate(body.get("steps") or []) if isinstance(s, dict)]
        if isinstance(doc.get("runs"), dict):
            blocks += [(f"composite/{s.get('name', i)}", s.get("env")) for i, s in enumerate(doc["runs"].get("steps") or []) if isinstance(s, dict)]
        for where, env in blocks:
            for key in (env or {}) if isinstance(env, dict) else []:
                if str(key).upper().startswith("PIP_") and str(key).upper() not in PIP_ENV_OK:
                    out.append(f"{name} {where}: env {key} can change what pip installs")
    return out


def workflow_problems(texts: dict[str, str]) -> list[str]:
    out: list[str] = list(env_problems(texts))
    installs = 0
    for name, step, script in run_scripts(texts):
        if re.fullmatch(r"\s*\$\{\{.*\}\}\s*", script, re.S):
            out.append(f"{name} {step}: run is only an expression, it cannot be read")
            continue
        c_defined = False
        for st in statements(script):
            ws = words(st)
            where = f"{name} {step}: {st}"
            for var in PIP_ENV.findall(st):
                if var not in PIP_ENV_OK:
                    out.append(f"{var} set in a script can change what pip installs: {where}")
            if re.search(r"pip\.(?:conf|ini)\b", st):
                out.append(f"pip configuration file written or read: {where}")
            # order-aware $C: the exact definition arms it; any other assignment, `unset C` or `read C` disarms it
            if st == C_DEFINITION:
                c_defined = True
                continue
            if any(re.match(r"C\+?=", w) for w in ws) or (ws[0] in ("unset", "read", "declare", "typeset") and "C" in ws):
                c_defined = False
            rest = _installer_words(ws)
            if rest is None:
                continue
            installs += 1
            if PIN_LINE.fullmatch(st):
                continue
            if any(v in rest for v in ("config", "download", "wheel")) and "install" not in rest:
                out.append(f"pip {[v for v in rest if v in VERBS][0]} is not covered by the pin check: {where}")
                continue
            if "install" in rest and ("-U" in ws or "--upgrade" in ws) and "pip==" in st:
                out.append(f"pip is upgraded, not pinned: {where}")
                continue
            for w in rest:
                short = re.fullmatch(r"-[A-Za-z]+.*", w) and not w.startswith("--")
                if LONG_REFUSED.match(w) or (short and re.match(r"-[A-Za-z]*[Uifr]", w) and not re.match(r"-c", w)) \
                        or URL_ARG.search(w):
                    out.append(f"refused option or source ({w}): {where}")
                    break
            consts = _constraint_values(ws)
            build = [ws[i + 1] for i, w in enumerate(ws[:-1]) if w == "--build-constraint"]
            inline = bool(consts) and bool(build) and not (set(consts) | set(build)) & EMPTY_FILES
            if ("$C" in ws or "${C}" in ws) and c_defined:
                continue
            if inline:
                continue
            out.append(f"unconstrained install ($C missing, redefined, undefined or defined later; or inline "
                       f"constraints missing or empty): {where}")
    if not installs:
        out.append("no installer call found in any workflow (the check is blind)")
    return out


def shipped_workflows(root: Path = ROOT) -> dict[str, str]:
    wf, ac = root / ".github" / "workflows", root / ".github" / "actions"
    files = [*wf.glob("*.yml"), *wf.glob("*.yaml"), *ac.glob("**/action.yml"), *ac.glob("**/action.yaml")]
    return {str(p.relative_to(root)) if p.parent != wf else p.name: p.read_text(encoding="utf-8") for p in sorted(files)}


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


# --- C-643: pinned probes from the C-627 review ----------------------------------------------------------------------

C_LINE = f"          {C_DEFINITION}\n"


def _body(script: str, define_c: bool = False) -> dict[str, str]:
    return _mutate_workflow("jobs:", "jobs:", OTHER_JOB + (C_LINE if define_c else "") +
                            "".join(f"          {ln}\n" for ln in script.splitlines()))


BAD = {
    # F-C627-1: global options, other installers, hidden names
    "global option before install": "pip --disable-pip-version-check install x",
    "python -m pip global option": "python -m pip --no-cache-dir install x",
    "pip -q install": "pip -q install x",
    "pip.exe": "pip.exe install x",
    "pip download": "pip download x",
    "pip wheel": "pip wheel x",
    "env wrapper": "env pip install x",
    "xargs": "echo x | xargs pip install",
    "variable named pip": '"$PIP" --quiet install x',
    "eval string": 'eval "pip install x"',
    "bash -c": "bash -c 'pip install x'",
    "command substitution": "y=$(pip install x)",
    "uv add": "uv add x",
    "pip config": "pip config set global.index-url http://example.invalid",
    # F-C627-2: $C order and inline files
    "C cleared": 'C=""\npip install $C x',
    "C reassigned": 'C="-c /dev/null"\npip install $C x',
    "C unset": "unset C\npip install $C x",
    "C defined after": "pip install $C x",
    "inline /dev/null": "pip install -c /dev/null --build-constraint /dev/null x",
    "inline empty build constraint": "pip install -c a.txt --build-constraint /dev/null x",
    "inline c only": "pip install --constraint a.txt x",
    # F-C627-3: refused spellings
    "-ihttp": "pip install -ihttp://example.invalid/simple x",
    "-i": "pip install -i example.invalid x",
    "--index-url=": "pip install --index-url=http://example.invalid/simple x",
    "--extra-index-url": "pip install --extra-index-url example.invalid x",
    "-f": "pip install -f somedir x",
    "--find-links": "pip install --find-links=. x",
    "--trusted-host": "pip install --trusted-host example.invalid x",
    "--no-build-isolation": "pip install --no-build-isolation x",
    "-Ur": "pip install -Ur x",
    "-qU": "pip install -qU x",
    "--upgrade": "pip install --upgrade x",
    "-r": "pip install -r requirements.txt",
    "--requirement": "pip install --requirement r.txt",
    "hg+": "pip install hg+https://example.invalid/x",
    "svn+": "pip install svn+https://example.invalid/x",
    "bzr+": "pip install bzr+https://example.invalid/x",
    "url": "pip install https://example.invalid/x.whl",
    "pkg@url": "pip install x@example.invalid/x.whl",
    "PIP env in a script": "export PIP_INDEX_URL=http://example.invalid/simple",
    "PIP_CONSTRAINT blanked in GITHUB_ENV": 'echo "PIP_CONSTRAINT=" >> "$GITHUB_ENV"',
    "pip.conf": "printf '[global]' > ~/.config/pip/pip.conf",
    # F-C627-4: quotes and comments
    "hash inside a word is not a comment": "pip install x#y --index-url example.invalid",
    "hash in quotes hides the rest": "pip install 'y #' --index-url example.invalid",
    # F-C627-5: unreadable run
    "expression run": "${{ matrix.cmd }}",
    # the pin line has to match whole
    "bootstrap plus extra package": "python -m pip install pip==24.0 requests",
}


# These cases must trip the OPTION/SOURCE rule itself, not the missing-$C rule: they carry a defined $C.
REFUSAL_CASES = {n for n in BAD if n.startswith(("-", "--", "hg+", "svn+", "bzr+", "url", "pkg@url", "hash"))}


@pytest.mark.parametrize("name", sorted(BAD))
def test_each_c643_bad_script_is_caught(name):
    script = BAD[name]
    if name in REFUSAL_CASES:
        script = script.replace("pip install ", "pip install $C ", 1)
    define_c = name in REFUSAL_CASES or name in ("C cleared", "C reassigned", "C unset")
    problems = workflow_problems(_body(script, define_c=define_c))
    assert problems != []
    if name in REFUSAL_CASES:
        assert any("refused" in p for p in problems), problems


def test_a_workflow_with_no_installer_is_reported_as_blind():
    assert workflow_problems({"a.yml": "jobs:\n  j:\n    steps:\n      - run: echo hi\n"}) == [
        "no installer call found in any workflow (the check is blind)"]


@pytest.mark.parametrize("name,script,define_c", [
    ("C defined before", 'pip install $C x', True),
    ("C braced", 'pip install ${C} x', True),
    ("quiet option with C", 'pip --quiet install $C x', True),
    ("pinned bootstrap", 'python -m pip install pip==24.0', False),
    ("inline constraints", 'pip install -c a.txt --build-constraint b.txt x', False),
    ("echo mentioning nothing", 'echo "hello # not a comment"', False),
    ("compose install verb", '$COMPOSE run --rm manifests-admin install canary.yaml', False),
])
def test_each_c643_good_script_is_accepted(name, script, define_c):
    assert workflow_problems(_body(script, define_c=define_c)) == []


def test_a_pip_env_key_in_workflow_env_is_refused_and_a_harmless_one_is_not():
    for env in ("PIP_INDEX_URL", "PIP_FIND_LINKS", "PIP_CONSTRAINT", "PIP_NO_BUILD_ISOLATION", "PIP_CONFIG_FILE"):
        assert workflow_problems(_mutate_workflow("jobs:", f"env:\n  {env}: x\njobs:")) != [], env
    assert workflow_problems(_mutate_workflow("jobs:", "env:\n  PIP_DISABLE_PIP_VERSION_CHECK: '1'\njobs:")) == []


def test_a_pip_env_key_in_job_and_step_env_is_refused():
    jobs = OTHER_JOB.replace("    runs-on", "    env:\n      PIP_INDEX_URL: x\n    runs-on") + "          echo hi\n"
    assert workflow_problems(_mutate_workflow("jobs:", "jobs:", jobs)) != []
    step = OTHER_JOB.replace("      - run: |", "      - env:\n          PIP_FIND_LINKS: x\n        run: |") + "          echo hi\n"
    assert workflow_problems(_mutate_workflow("jobs:", "jobs:", step)) != []


def test_a_composite_action_run_is_scanned():
    texts = shipped_workflows()
    texts[".github/actions/x/action.yml"] = "runs:\n  using: composite\n  steps:\n    - shell: bash\n      run: pip install requests\n"
    assert workflow_problems(texts) != []
    texts[".github/actions/x/action.yml"] = "runs:\n  using: composite\n  steps:\n    - shell: bash\n      run: echo ok\n"
    assert workflow_problems(texts) == []


def test_shipped_workflows_reads_both_extensions_and_composite_actions(tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "actions" / "a").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "a.yml").write_text("jobs: {}\n")
    (tmp_path / ".github" / "workflows" / "b.yaml").write_text("jobs: {}\n")
    (tmp_path / ".github" / "actions" / "a" / "action.yaml").write_text("runs: {}\n")
    assert sorted(shipped_workflows(tmp_path)) == [".github/actions/a/action.yaml", "a.yml", "b.yaml"]
