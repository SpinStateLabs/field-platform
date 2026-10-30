"""B-08 (reviewer C-143 / C-149), extended by C-375 (reviewer C-372): a security lint over `.github/workflows`
and any composite action under `.github/actions`.

Three rules, each a way a pull request from a fork turns into code running with the repository's token:
  1. no attacker-controlled expression inside a `run:` script (script injection: the expression is pasted into the
     shell text before the shell parses it; pass it through `env:` and read `"$VAR"` instead). Flagged: any
     `github.event` (the whole event, `github.event.<x>`, `toJSON(github.event)`), `github.head_ref`, bracket access
     on `github` for either (`github['head_ref']`), and `inputs.<x>` / `inputs[...]` (workflow_dispatch and
     workflow_call inputs), in any letter case (GitHub reads context names case-insensitively). `github.event_name`,
     `github.sha`, `secrets.*` and the rest are not flagged. An expression is read to its closing `}}` with string
     literals respected, so a `}}` inside `'...'` does not end it, and over several lines;
  2. no `pull_request_target` trigger (it runs the base branch's workflow with write access and secrets
     while the PR's contents are checked out or fetched by the job);
  3. a top-level `permissions:` block (without it the job inherits the repository default token scope).
Rules 2 and 3 are about workflows; a composite action (`runs.using: composite`) is only scanned for rule 1.

Also flagged (C-388): the WHOLE `github` or `inputs` context used as a value (`toJSON(github)`, `format('{0}', inputs)`),
the object filter (`join(github.*, ',')`, `github.*.event`) and a dynamic key (`github[format('{0}','event')]`).

NOT covered, by design or for lack of a case: `permissions: write-all` and job-level write scopes are accepted
(presence is the rule, and a test pins that); `github.base_ref` (a base-branch name is chosen by a maintainer, so it is
not flagged, nor is it listed as safe); values that reach the script through `env.*` or `steps.*.outputs` after being
set from event data upstream; an expression built from a context held in a variable the lint cannot see; `workflow_run` and `issue_comment` triggers; other contexts that can carry a branch name or
a user name (`github.ref_name`, `github.actor`, `steps.*.outputs`, `needs.*.outputs`, `matrix.*`); `actions/github-script`
`script:` and `with:` values (another injection sink); the same expressions in `with:`, `if:` and a step `name:`
are NOT sinks for the shell and stay green. Duplicate keys (which `safe_load` resolves to the last) are the
duplicate-key lint's job (test_yaml_duplicate_keys.py).
The checks are stdlib + PyYAML, the same pattern as test_yaml_duplicate_keys.py.
"""
from __future__ import annotations

import glob
import os
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

# Spellings of the attacker-controlled contexts, matched on an expression with its string literals blanked.
_TAINTED = [re.compile(p, re.IGNORECASE) for p in (
    r"\bgithub\s*\.\s*event\b",              # github.event, github.event.x, toJSON(github.event); not event_name
    r"\bgithub\s*\.\s*head_ref\b",
    r"(?<![.\w])inputs\s*[.\[]",             # workflow_dispatch / workflow_call inputs (github.event.inputs is the first)
    # the WHOLE context used as a value (C-388): `toJSON(github)`, `format('{0}', inputs)`: a bare `github` or `inputs`
    # token that is not followed by `.` or `[` (so `github.sha`, `github.event_name` and `secrets.*` stay green) ...
    r"(?<![.\w])(?:github|inputs)\b(?!\s*[.\[])",
    # ... and the object filter, `join(github.*, ',')`, `github.*.event`
    r"(?<![.\w])(?:github|inputs)\s*\.\s*\*",
)]
# bracket access on `github`, matched on the raw expression because the key IS a string literal
_BRACKET_TAINTED = re.compile(r"""\bgithub\s*\[\s*['"]\s*(?:event|head_ref)\s*['"]\s*\]""", re.IGNORECASE)
# a dynamic key on `github`, `github[format('{0}', 'event')]`: anything in the brackets that is not a plain literal
_DYNAMIC_KEY = re.compile(r"""\bgithub\s*\[(?!\s*(?:''|"[^"]*")\s*\])""", re.IGNORECASE)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")


def _expressions(script: str):
    """Yield (whole `${{ ... }}` text, body) for every expression of a script. The end is the first `}}` that is
    not inside a single-quoted string literal (`''` escapes a quote); an unterminated expression runs to the end."""
    pos = 0
    while True:
        start = script.find("${{", pos)
        if start < 0:
            return
        i = start + 3
        in_string = False
        while i < len(script):
            ch = script[i]
            if ch == "'":
                in_string = not in_string      # an escaped quote (two quotes) is two toggles: no special case
            elif not in_string and script.startswith("}}", i):
                break
            i += 1
        end = min(i + 2, len(script))
        yield script[start:end], script[start + 3:i]
        pos = end


def _tainted(body: str) -> bool:
    blank = _STRING_LITERAL.sub("''", body)
    return (any(p.search(blank) for p in _TAINTED) or bool(_BRACKET_TAINTED.search(body))
            or bool(_DYNAMIC_KEY.search(blank)))


def _files(root: Path = ROOT) -> list[str]:
    found: set[str] = set()
    for pat in (".github/workflows/*.yml", ".github/workflows/*.yaml",
                ".github/actions/**/action.yml", ".github/actions/**/action.yaml"):
        for p in glob.glob(str(root / pat), recursive=True):
            found.add(os.path.relpath(p, root).replace(os.sep, "/"))
    return sorted(found)


FILES = _files()


def _triggers(doc: dict) -> set[str]:
    """The `on:` triggers; YAML 1.1 loads the key `on` as the boolean True."""
    on = doc["on"] if "on" in doc else doc.get(True)
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return {str(t) for t in on}
    if isinstance(on, dict):
        return {str(t) for t in on}
    return set()


def _is_composite_action(doc: dict) -> bool:
    runs = doc.get("runs")
    return isinstance(runs, dict) and runs.get("using") == "composite" and "jobs" not in doc


def _run_scripts(doc: dict):
    """Every (job, step index, script) of a `run:` step: the jobs of a workflow, or the steps of a composite action."""
    groups = [("composite", (doc.get("runs") or {}).get("steps") or [])] if _is_composite_action(doc) else [
        (job_id, (job or {}).get("steps") or []) for job_id, job in (doc.get("jobs") or {}).items()]
    for job_id, steps in groups:
        for i, step in enumerate(steps):
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                yield job_id, i, step["run"]


def lint(doc: dict) -> list[str]:
    findings: list[str] = []
    for job_id, i, script in _run_scripts(doc):
        for text, body in _expressions(script):
            if _tainted(body):
                findings.append(f"script injection: job {job_id!r} step {i} run: uses {text.strip()}")
    if _is_composite_action(doc):
        return findings
    if "pull_request_target" in _triggers(doc):
        findings.append("pull_request_target trigger")
    if "permissions" not in doc:
        findings.append("no top-level permissions block")
    return findings


def _load(text: str) -> dict:
    doc = yaml.safe_load(text)
    assert isinstance(doc, dict)
    return doc


def test_a_workflow_is_discovered():
    assert FILES, "no workflow discovered: the per-file lint below would skip"
    assert ".github/workflows/ci.yml" in FILES


@pytest.mark.parametrize("rel", FILES)
def test_the_workflow_passes_the_security_lint(rel: str):
    assert lint(_load((ROOT / rel).read_text(encoding="utf-8"))) == []


# --- the lint itself --------------------------------------------------------------------------------

CLEAN = (
    "on: [push]\npermissions: {contents: read}\n"
    "jobs:\n  t:\n    runs-on: x\n    steps:\n      - run: echo hi\n"
)


def test_a_clean_workflow_has_no_findings():
    assert lint(_load(CLEAN)) == []


def test_event_data_passed_through_env_is_clean():
    text = CLEAN.replace(
        "      - run: echo hi\n",
        "      - env:\n          TITLE: ${{ github.event.pull_request.title }}\n        run: echo \"$TITLE\"\n",
    )
    assert lint(_load(text)) == []


def test_event_name_and_secrets_in_a_run_line_are_not_flagged():
    text = CLEAN.replace("echo hi", "echo ${{ github.event_name }} ${{ secrets.X }} ${{ github.sha }}")
    assert lint(_load(text)) == []


@pytest.mark.parametrize("expr", [
    "${{ github.event.pull_request.title }}",
    "${{ github.event.issue.body }}",
    "${{ github.head_ref }}",
    "${{github.head_ref}}",
    "${{ github . event . comment.body }}",
    "${{ github.event['pull_request']['title'] }}",
    "${{ format('{0}', github.event.head_commit.message) }}",
    "${{ contains(github.head_ref, 'x') && 'a' || 'b' }}",
])
def test_event_data_in_a_run_script_is_flagged(expr: str):
    text = CLEAN.replace("echo hi", f"echo {expr}")
    assert any(f.startswith("script injection") for f in lint(_load(text)))


def test_a_multiline_run_script_is_scanned_on_every_line():
    text = CLEAN.replace("      - run: echo hi\n",
                         "      - run: |\n          echo one\n          echo ${{ github.head_ref }}\n")
    assert any(f.startswith("script injection") for f in lint(_load(text)))


def test_every_expression_in_one_script_is_checked_not_only_the_first():
    text = CLEAN.replace("echo hi", "echo ${{ github.sha }} ${{ github.head_ref }}")
    assert any(f.startswith("script injection") for f in lint(_load(text)))


def test_a_second_job_and_a_later_step_are_scanned():
    text = CLEAN + "  u:\n    runs-on: x\n    steps:\n      - run: echo a\n      - run: echo ${{ github.head_ref }}\n"
    out = lint(_load(text))
    assert len(out) == 1 and "job 'u' step 1" in out[0]


@pytest.mark.parametrize("on", [
    "on: pull_request_target",
    "on: [push, pull_request_target]",
    "on:\n  pull_request_target:\n    types: [opened]",
])
def test_a_pull_request_target_trigger_is_flagged(on: str):
    text = CLEAN.replace("on: [push]", on)
    assert "pull_request_target trigger" in lint(_load(text))


def test_pull_request_is_not_pull_request_target():
    assert lint(_load(CLEAN.replace("on: [push]", "on:\n  pull_request:\n    branches: [main]"))) == []


def test_a_missing_permissions_block_is_flagged():
    text = CLEAN.replace("permissions: {contents: read}\n", "")
    assert lint(_load(text)) == ["no top-level permissions block"]


def test_an_empty_permissions_block_counts_as_present():
    assert lint(_load(CLEAN.replace("{contents: read}", "{}"))) == []


# --- C-375 (reviewer C-372): the spellings the first version missed, the safe patterns, discovery ----------

@pytest.mark.parametrize("expr", [
    "${{ toJSON(github.event) }}",
    "${{ fromJSON(toJSON(github.event)).number }}",
    "${{ github.event }}",
    "${{ github.event.inputs.name }}",
    "${{ inputs.name }}",
    "${{ inputs['name'] }}",
    "${{ inputs . name }}",
    "${{ format('{0}', inputs.name) }}",
    "${{ GITHUB.HEAD_REF }}",
    "${{ GitHub.Event.Pull_Request.Title }}",
    "${{ INPUTS.Name }}",
    "${{ github['head_ref'] }}",
    '${{ github["event"]["pull_request"]["title"] }}',
    "${{ github [ 'event' ] }}",
    "${{ format('}}', github.head_ref) }}",
    "${{ format('it''s }}', github.event.pull_request.title) }}",
    "${{ format('''}}', github.head_ref) }}",
])
def test_the_spellings_the_first_version_missed_are_flagged(expr: str):
    text = CLEAN.replace("echo hi", f"echo {expr}")
    assert any(f.startswith("script injection") for f in lint(_load(text))), expr


@pytest.mark.parametrize("expr", [
    "${{ github.event_name }}",
    "${{ github.eventful }}",
    "${{ github.head_refx }}",
    "${{ github.sha }}",
    "${{ github.run_id }}",
    "${{ secrets.TOKEN }}",
    "${{ needs.build.outputs.inputs }}",
    "${{ needs.build.outputs.inputs.x }}",
    "${{ steps.x.outputs.inputs['k'] }}",
    "${{ steps.x.outputs.inputs }}",
    "${{ matrix.os }}",
    "${{ env.FOO }}",
    "${{ vars.BAR }}",
    "${{ 'github.event' }}",
    "${{ format('{0}', 'github.head_ref') }}",
    "${{ 'inputs.name' }}",
])
def test_neighbouring_and_quoted_text_is_not_flagged(expr: str):
    text = CLEAN.replace("echo hi", f"echo {expr}")
    assert lint(_load(text)) == [], expr


def test_text_between_two_expressions_is_not_an_expression():
    text = CLEAN.replace("echo hi", "echo ${{ github.sha }} github.head_ref inputs.x ${{ github.run_id }}")
    assert lint(_load(text)) == []


def test_each_of_several_expressions_is_read_separately():
    text = CLEAN.replace("echo hi", "echo ${{ github.sha }} ${{ inputs.a }} ${{ github.run_id }} ${{ github.head_ref }}")
    out = lint(_load(text))
    assert len(out) == 2 and "inputs.a" in out[0] and "github.head_ref" in out[1]


def test_a_multiline_expression_in_a_block_scalar_is_flagged():
    text = CLEAN.replace("      - run: echo hi\n",
                         "      - run: |\n          echo ${{\n            github.event.pull_request.title\n          }}\n")
    assert any(f.startswith("script injection") for f in lint(_load(text)))


def test_an_unterminated_expression_does_not_crash_the_lint():
    assert lint(_load(CLEAN.replace("echo hi", "echo ${{ github.sha"))) == []
    assert any(f.startswith("script injection") for f in lint(_load(CLEAN.replace("echo hi", "echo ${{ github.head_ref"))))


@pytest.mark.parametrize("where", ["with", "if", "name", "job_env", "step_env"])
def test_the_same_expressions_outside_a_run_script_stay_green(where: str):
    expr = "${{ github.event.pull_request.title }} ${{ github.head_ref }} ${{ inputs.x }}"
    steps = {
        "with": "      - uses: actions/checkout@abc\n        with:\n          ref: " + expr + "\n",
        "if": "      - if: ${{ github.event.pull_request.title == 'x' }}\n        run: echo hi\n",
        "name": "      - name: \"" + expr + "\"\n        run: echo hi\n",
        "job_env": "      - run: echo hi\n",
        "step_env": "      - env:\n          TITLE: " + expr + "\n        run: echo \"$TITLE\"\n",
    }[where]
    text = CLEAN.replace("      - run: echo hi\n", steps)
    if where == "job_env":
        text = text.replace("    runs-on: x\n", "    runs-on: x\n    env:\n      TITLE: " + expr + "\n")
    assert lint(_load(text)) == [], where


def test_a_non_string_run_value_is_ignored_not_scanned():
    text = CLEAN.replace("      - run: echo hi\n", "      - run: [github.head_ref, inputs.x]\n")
    assert lint(_load(text)) == []


# --- composite actions ------------------------------------------------------------------------------------

ACTION = (
    "name: a\nruns:\n  using: composite\n  steps:\n    - run: echo hi\n      shell: bash\n"
)


def test_a_clean_composite_action_has_no_findings_and_needs_no_permissions_or_trigger():
    assert lint(_load(ACTION)) == []


def test_an_injection_in_a_composite_action_is_flagged():
    out = lint(_load(ACTION.replace("echo hi", "echo ${{ inputs.name }}")))
    assert len(out) == 1 and out[0].startswith("script injection") and "'composite'" in out[0]


def test_a_node_or_docker_action_is_not_treated_as_composite():
    doc = _load("name: a\nruns:\n  using: node20\n  main: index.js\n")
    assert not _is_composite_action(doc)
    assert lint(doc) == ["no top-level permissions block"]      # read as a workflow: no `on`, no `permissions`


@pytest.mark.parametrize("rel", [
    ".github/workflows/x.yml",
    ".github/workflows/x.yaml",
    ".github/actions/setup/action.yml",
    ".github/actions/setup/action.yaml",
    ".github/actions/a/b/c/action.yml",
])
def test_each_discovery_pattern_finds_its_file(tmp_path: Path, rel: str):
    f = tmp_path / rel
    f.parent.mkdir(parents=True)
    f.write_text("a: 1\n", encoding="utf-8")
    assert _files(tmp_path) == [rel]


def test_files_no_pattern_names_are_not_discovered(tmp_path: Path):
    for rel in (".github/workflows/x.txt", ".github/workflows/sub/y.yml", ".github/actions/setup/other.yml",
                ".github/action.yml", "docs/action.yml", ".github/workflows/action.yml.bak"):
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("a: 1\n", encoding="utf-8")
    assert _files(tmp_path) == []


# --- C-388 (reviewer C-381): the whole context as a value, a dynamic key, the unpinned spellings ----------------

@pytest.mark.parametrize("expr", [
    "${{ toJSON(github) }}",
    "${{ toJson(github) }}",
    "${{ TOJSON(GITHUB) }}",
    "${{ toJSON(inputs) }}",
    "${{ fromJSON(toJSON(github)).event }}",
    "${{ format('{0}', github) }}",
    "${{ format('{0}', inputs) }}",
    "${{ join(github.*, ',') }}",
    "${{ join(inputs.*, ',') }}",
    "${{ github.*.event }}",
    "${{ github . * }}",
    "${{ github[format('{0}','event')] }}",
    "${{ github[ format('{0}','head_ref') ] }}",
    "${{ github [ inputs.key ] }}",
    "${{ GITHUB[format('{0}','event')] }}",       # C-397 (C-395 LOW 3): the dynamic key is case-insensitive
    "${{ github [format('{0}','event')] }}",      # ... and tolerates space before the bracket
    "${{ github[''||'event'] }}",                 # C-397 (C-708 F-C708-1): a literal first, then an operator:
    "${{ github['x' && 'event'] }}",              # the brackets hold more than ONE literal, so the key is dynamic
    "${{ github['sha' || 'event'] }}",
    "${{ github }}",
    "${{ inputs }}",
    "${{ ( github ) }}",
])
def test_the_whole_context_as_a_value_is_flagged(expr: str):
    text = CLEAN.replace("echo hi", f"echo {expr}")
    assert any(f.startswith("script injection") for f in lint(_load(text))), expr


@pytest.mark.parametrize("expr", [
    "${{ github.sha }}",
    "${{ github.event_name }}",
    "${{ github.run_id }}",
    "${{ github.repository }}",
    "${{ github.ref }}",
    "${{ github.base_ref }}",
    "${{ contains(github.ref, 'refs/tags/') }}",
    "${{ format('{0}-{1}', github.sha, github.run_id) }}",
    "${{ secrets.TOKEN }}",
    "${{ needs.github.outputs.x }}",
    "${{ steps.github.outputs.y }}",
    "${{ env.github }}",
    "${{ matrix.inputs_file }}",
    "${{ 'toJSON(github)' }}",
    "${{ format('{0}', 'github') }}",
    "${{ github['sha'] }}",
    "${{ github[\"run_id\"] }}",
    "${{ github[ 'sha' ] }}",                     # C-397 (C-395 F-C395-1): a literal key with a space is not dynamic
    "${{ github [ \"sha\" ] }}",
    "${{ githubx }}",                             # C-397 (C-395 LOW 3): word boundary of the bare-token rule
    "${{ inputs_x }}",
    "${{ myinputs }}",
    "${{ github .sha }}",                         # whitespace before the dot is a neighbour, not the whole context
])
def test_neighbouring_contexts_and_quoted_names_stay_green(expr: str):
    text = CLEAN.replace("echo hi", f"echo {expr}")
    assert lint(_load(text)) == [], expr


@pytest.mark.parametrize("expr", ["${{ github['HEAD_REF'] }}", "${{ GITHUB['Event']['pull_request']['title'] }}",
                                  "${{ github . head_ref }}", "${{ github  .  head_ref }}",
                                  "${{ github . event . pull_request . title }}"])
def test_the_bracket_form_in_upper_case_and_spaced_dotted_forms_are_flagged(expr: str):
    text = CLEAN.replace("echo hi", f"echo {expr}")
    assert any(f.startswith("script injection") for f in lint(_load(text))), expr


def test_permissions_write_all_is_accepted_by_design_at_both_levels():
    top = CLEAN.replace("permissions: {contents: read}", "permissions: write-all")
    assert lint(_load(top)) == []
    job = CLEAN.replace("    runs-on: x\n", "    runs-on: x\n    permissions: write-all\n")
    assert lint(_load(job)) == []


def test_the_docstring_lists_what_is_not_covered():
    doc = __doc__ or ""
    for phrase in ("github.base_ref", "write-all", "env.*", "github-script", "workflow_run", "WHOLE"):
        assert phrase in doc, phrase


# --- mutants of the real workflow: each rule's defect re-introduced must go red ---------------------

def _ci() -> str:
    return (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


def _first_run_line(text: str) -> str:
    m = re.search(r"^\s+(?:- )?run: (?!\|)(?!>)(.+)$", text, re.MULTILINE)
    assert m, "no single-line `run:` step in ci.yml"
    return m.group(0)


def test_mutant_event_data_in_a_run_line_of_ci_goes_red():
    text = _ci()
    line = _first_run_line(text)
    mutated = text.replace(line, line + " ${{ github.event.pull_request.title }}", 1)
    assert mutated != text
    assert any(f.startswith("script injection") for f in lint(_load(mutated)))


def test_mutant_head_ref_in_a_run_line_of_ci_goes_red():
    text = _ci()
    line = _first_run_line(text)
    mutated = text.replace(line, line + " ${{ github.head_ref }}", 1)
    assert any(f.startswith("script injection") for f in lint(_load(mutated)))


def test_mutant_a_pull_request_target_trigger_in_ci_goes_red():
    text = _ci()
    assert "\n  pull_request:" in text
    mutated = text.replace("\n  pull_request:", "\n  pull_request_target:", 1)
    assert "pull_request_target trigger" in lint(_load(mutated))


def test_mutant_removing_the_permissions_block_from_ci_goes_red():
    text = _ci()
    m = re.search(r"^permissions:.*(?:\n[ \t]+.*)*\n", text, re.MULTILINE)
    assert m, "no top-level permissions block in ci.yml"
    mutated = text.replace(m.group(0), "", 1)
    assert mutated != text
    assert "no top-level permissions block" in lint(_load(mutated))
