"""B-08 (reviewer C-143 / C-149): a security lint over `.github/workflows`.

Three rules, each a way a pull request from a fork turns into code running with the repository's token:
  1. no `${{ github.event.* }}` and no `${{ github.head_ref }}` inside a `run:` script (script
     injection: the expression is pasted into the shell text before the shell parses it; pass it
     through `env:` and read `"$VAR"` instead);
  2. no `pull_request_target` trigger (it runs the base branch's workflow with write access and secrets
     while the PR's contents are checked out or fetched by the job);
  3. a top-level `permissions:` block (without it the job inherits the repository default token scope).
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

# `${{ ... }}` holding github.event.<x> or github.head_ref (whitespace and the dot/bracket form allowed);
# `github.event_name` is not an attacker-controlled value and is not matched.
_EXPR = re.compile(r"\$\{\{(?P<body>.*?)\}\}", re.DOTALL)
_TAINTED = re.compile(r"\bgithub\s*\.\s*(?:event\s*(?:\.|\[)|head_ref\b)")


def _files(root: Path = ROOT) -> list[str]:
    found: set[str] = set()
    for pat in (".github/workflows/*.yml", ".github/workflows/*.yaml"):
        for p in glob.glob(str(root / pat)):
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


def _run_scripts(doc: dict):
    """Every (job, step index, script) of a `run:` step."""
    for job_id, job in (doc.get("jobs") or {}).items():
        for i, step in enumerate((job or {}).get("steps") or []):
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                yield job_id, i, step["run"]


def lint(doc: dict) -> list[str]:
    findings: list[str] = []
    for job_id, i, script in _run_scripts(doc):
        for m in _EXPR.finditer(script):
            if _TAINTED.search(m.group("body")):
                findings.append(f"script injection: job {job_id!r} step {i} run: uses {m.group(0).strip()}")
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
