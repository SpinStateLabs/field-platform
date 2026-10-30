"""C-564 (reviewer C-562, Don's ruling): the CI job that runs the commit-identity guard on pull requests.

The job must exist, run only on `pull_request`, check out with the SAME pinned commit as the other jobs plus
`fetch-depth: 0` (only here), read the range from the PR's base and head (never the merge commit), install nothing,
hold no literal domain (the optional extra domain comes from a repository variable) and pass `--allow-domain` only when
that variable is non-empty. Every rule is run on the shipped workflow and on a mutant that must break it.
"""
from __future__ import annotations

import copy
import re
import shlex
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
SCRIPT = ROOT / "tools" / "check_commit_identity.py"
JOB = "commit-identity"
SHA = re.compile(r"@([0-9a-f]{40})\b")
TLD = re.compile(r"\b[A-Za-z0-9-]+\.(?:com|ca|org|net|io|dev|ai|co|me)\b")


def load(text: str | None = None) -> tuple[dict, str]:
    text = CI.read_text(encoding="utf-8") if text is None else text
    return yaml.safe_load(text), text


def job_text(text: str) -> str:
    start = text.index(f"\n  {JOB}:")
    nxt = re.search(r"\n  [a-z][a-z0-9-]*:\n", text[start + 1:])
    return text[start: start + 1 + nxt.start()] if nxt else text[start:]


def problems(doc: dict, text: str) -> list[str]:
    out: list[str] = []
    job = (doc.get("jobs") or {}).get(JOB)
    if not job:
        return [f"no {JOB} job"]
    cond = str(job.get("if", ""))
    if "pull_request" not in cond or "push" in cond or "==" not in cond:
        out.append(f"the job does not run only on pull_request: if={cond!r}")
    if job.get("permissions") != {"contents": "read"}:
        out.append(f"permissions are not exactly contents: read: {job.get('permissions')!r}")
    steps = job.get("steps") or []
    checkouts = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]
    if len(checkouts) != 1:
        out.append("expected exactly one checkout step")
    else:
        co = checkouts[0]
        m = SHA.search(co["uses"])
        others = {SHA.search(s.get("uses", "")).group(1) for name, j in doc["jobs"].items() if name != JOB
                  for s in j.get("steps", []) if str(s.get("uses", "")).startswith("actions/checkout@") and SHA.search(s["uses"])}
        if not m:
            out.append("the checkout is not pinned by a commit SHA")
        elif others != {m.group(1)}:
            out.append("the checkout SHA differs from the other jobs")
        w = co.get("with") or {}
        if w.get("fetch-depth") != 0:
            out.append(f"fetch-depth is not 0: {w.get('fetch-depth')!r}")
        if w.get("persist-credentials") is not False:
            out.append("persist-credentials is not false")
    for name, j in doc["jobs"].items():
        if name == JOB:
            continue
        for s in j.get("steps", []):
            if str(s.get("uses", "")).startswith("actions/checkout@") and "fetch-depth" in (s.get("with") or {}):
                out.append(f"job {name} also sets fetch-depth (only {JOB} needs the full history)")
    env = job.get("env") or {}
    if "github.base_ref" not in str(env.get("BASE_REF", "")):
        out.append("BASE_REF is not github.base_ref")
    if "github.event.pull_request.head.sha" not in str(env.get("HEAD_SHA", "")):
        out.append("HEAD_SHA is not the pull request head SHA (the merge commit must not be checked)")
    if str(env.get("ALLOW_DOMAIN", "")).replace(" ", "") != "${{vars.COMMIT_IDENTITY_ALLOW_DOMAIN}}":
        out.append("ALLOW_DOMAIN is not read from the repository variable")
    runs = [s["run"] for s in steps if "run" in s]
    if len(runs) != 1:
        out.append("expected exactly one run step")
    else:
        script = runs[0]
        try:
            shlex.split(script)
        except ValueError as exc:
            out.append(f"the run block does not shlex-parse (an apostrophe in a comment?): {exc}")
        lines = [ln.strip() for ln in script.splitlines() if ln.strip()]
        with_domain = [i for i, ln in enumerate(lines) if "--allow-domain" in ln]
        calls = [i for i, ln in enumerate(lines) if "tools/check_commit_identity.py" in ln]
        if len(calls) != 2:
            out.append(f"expected two calls of the script (with and without the domain), found {len(calls)}")
        for i in calls:
            if '--range "origin/$BASE_REF..$HEAD_SHA"' not in lines[i]:
                out.append("a call does not pass the explicit range origin/$BASE_REF..$HEAD_SHA")
        if not lines or not lines[0].startswith("set -"):
            out.append("the script does not start with set -eu")
        try:
            i_if = lines.index('if [ -n "$ALLOW_DOMAIN" ]; then')
            i_else = lines.index("else")
        except ValueError:
            out.append("the domain is not guarded by a test that the variable is non-empty")
        else:
            if len(with_domain) != 1 or not (i_if < with_domain[0] < i_else):
                out.append("--allow-domain is passed outside the non-empty branch")
            if '--allow-domain "$ALLOW_DOMAIN"' not in lines[with_domain[0]] if with_domain else True:
                out.append("--allow-domain does not take the variable")
        if any(re.search(r"\bpip3?\b|\buv\b|\bpipx\b", ln) for ln in lines):
            out.append("the run block installs something")
    if any(str(s.get("uses", "")).startswith("actions/setup-python@") for s in steps):
        out.append("the job needs no setup-python (the script is standard library only)")
    jt = job_text(text)
    if TLD.search(jt):
        out.append("the job holds something that looks like a literal domain")
    comments = [ln for ln in jt.splitlines() if ln.strip().startswith("#")]
    if any("'" in ln for ln in comments):
        out.append("a comment holds an apostrophe")
    return out


def test_the_shipped_job_satisfies_every_rule():
    doc, text = load()
    assert problems(doc, text) == []


def test_the_script_is_standard_library_only():
    import ast
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    mods = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    mods.discard("__future__")
    assert mods and mods <= set(sys.stdlib_module_names), sorted(mods - set(sys.stdlib_module_names))


def test_the_other_jobs_are_unchanged_in_their_checkout():
    doc, _ = load()
    for name in ("tests", "compose-smoke", "fly-image-smoke", "compose-upgrade-smoke"):
        co = [s for s in doc["jobs"][name]["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")]
        assert co and all("fetch-depth" not in (s.get("with") or {}) for s in co), name


def _doc(mut):
    doc, text = load()
    doc = copy.deepcopy(doc)
    return mut(doc, text)


def _steps(doc):
    return doc["jobs"][JOB]["steps"]


def _run(doc):
    return next(s for s in _steps(doc) if "run" in s)


def _co(doc):
    return next(s for s in _steps(doc) if str(s.get("uses", "")).startswith("actions/checkout@"))


MUTANTS = {
    "job removed": lambda d, t: (d["jobs"].pop(JOB), t)[1:] and (d, t),
    "runs on push too": lambda d, t: (d["jobs"][JOB].__setitem__("if", "github.event_name != 'x'"), (d, t))[1],
    "runs on push only": lambda d, t: (d["jobs"][JOB].__setitem__("if", "github.event_name == 'push'"), (d, t))[1],
    "if removed": lambda d, t: (d["jobs"][JOB].pop("if"), (d, t))[1],
    "permissions write": lambda d, t: (d["jobs"][JOB].__setitem__("permissions", {"contents": "write"}), (d, t))[1],
    "permissions broader": lambda d, t: (d["jobs"][JOB].__setitem__("permissions", {"contents": "read", "issues": "write"}), (d, t))[1],
    "checkout by tag": lambda d, t: (_co(d).__setitem__("uses", "actions/checkout@v4"), (d, t))[1],
    "checkout another sha": lambda d, t: (_co(d).__setitem__("uses", "actions/checkout@" + "0" * 40), (d, t))[1],
    "shallow checkout": lambda d, t: (_co(d)["with"].__setitem__("fetch-depth", 1), (d, t))[1],
    "fetch-depth removed": lambda d, t: (_co(d)["with"].pop("fetch-depth"), (d, t))[1],
    "credentials persisted": lambda d, t: (_co(d)["with"].__setitem__("persist-credentials", True), (d, t))[1],
    "fetch-depth in another job": lambda d, t: (next(s for s in d["jobs"]["compose-smoke"]["steps"] if "actions/checkout@" in str(s.get("uses", ""))).setdefault("with", {}).__setitem__("fetch-depth", 0), (d, t))[1],
    "head is the merge commit": lambda d, t: (d["jobs"][JOB]["env"].__setitem__("HEAD_SHA", "${{ github.sha }}"), (d, t))[1],
    "base is not the base ref": lambda d, t: (d["jobs"][JOB]["env"].__setitem__("BASE_REF", "main"), (d, t))[1],
    "domain hardcoded in env": lambda d, t: (d["jobs"][JOB]["env"].__setitem__("ALLOW_DOMAIN", "example.invalid"), (d, t))[1],
    "domain from another variable": lambda d, t: (d["jobs"][JOB]["env"].__setitem__("ALLOW_DOMAIN", "${{ vars.OTHER }}"), (d, t))[1],
    "domain passed unconditionally": lambda d, t: (_run(d).__setitem__("run", 'set -eu\npython3 tools/check_commit_identity.py --range "origin/$BASE_REF..$HEAD_SHA" --allow-domain "$ALLOW_DOMAIN"\n'), (d, t))[1],
    "else branch passes the domain too": lambda d, t: (_run(d).__setitem__("run", _run(d)["run"].replace('else\n  python3 tools/check_commit_identity.py --range "origin/$BASE_REF..$HEAD_SHA"', 'else\n  python3 tools/check_commit_identity.py --range "origin/$BASE_REF..$HEAD_SHA" --allow-domain "$ALLOW_DOMAIN"')), (d, t))[1],
    "domain test removed": lambda d, t: (_run(d).__setitem__("run", _run(d)["run"].replace('if [ -n "$ALLOW_DOMAIN" ]; then', 'if true; then')), (d, t))[1],
    "range dropped": lambda d, t: (_run(d).__setitem__("run", _run(d)["run"].replace(' --range "origin/$BASE_REF..$HEAD_SHA"', '')), (d, t))[1],
    "set -eu dropped": lambda d, t: (_run(d).__setitem__("run", _run(d)["run"].replace("set -eu\n", "")), (d, t))[1],
    "apostrophe in the run block": lambda d, t: (_run(d).__setitem__("run", "# it's here\n" + _run(d)["run"]), (d, t))[1],
    "pip install added": lambda d, t: (_run(d).__setitem__("run", "pip install requests\n" + _run(d)["run"]), (d, t))[1],
    "setup-python added": lambda d, t: (_steps(d).insert(0, {"uses": "actions/setup-python@" + "a" * 40}), (d, t))[1],
    "literal domain in a comment": lambda d, t: (d, t.replace("# C-564 (reviewer C-562):", "# C-564 (reviewer C-562) see corp.example.com:", 1)),
    "apostrophe in a comment": lambda d, t: (d, t.replace("# C-564 (reviewer C-562):", "# C-564 (reviewer C-562) it's:", 1)),
}


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_each_mutant_breaks_a_rule(name):
    doc, text = _doc(lambda d, t: (d, t))
    out = MUTANTS[name](copy.deepcopy(doc), text)
    d, t = out
    assert problems(d, t) != [], "the mutant survived"
