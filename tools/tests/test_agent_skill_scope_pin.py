"""The SSL agent SKILL.md files and their manifests agree on the governed-action strings (scout P-25, tests only).

Each SKILL.md says its `-Action` strings "must match the manifest `delegation.scope` and the minted token; a typo is a
`D.scope` BLOCK". Nothing checked that. This pins, for both agents: the strings in the "Governed actions" table equal the
manifest's `delegation.scope` (both directions), every `-Action "..."` in the text is in scope, the "Never granted" strings
are not in scope, and every `*-Field*` helper the text names is a function in tools/field-rest.ps1. The checker is a pure
function so each rule is proven red on a mutated input."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ["ssl-invoicing-agent", "ssl-timekeeping-agent"]
PS1 = ROOT / "tools" / "field-rest.ps1"
HELPER = re.compile(r"\b(?:Invoke|Send|Get|Test|Write|Protect)-Field\w+")
ACTION = re.compile(r'-Action\s+"([^"]+)"')
FUNCTION = re.compile(r"^function\s+([A-Za-z]+-[A-Za-z]+)", re.MULTILINE)


def _table_actions(skill: str) -> list[str]:
    """The first backticked string in the last cell of each row of the table after '**Governed actions'."""
    lines = skill.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("**Governed actions"))
    out: list[str] = []
    for ln in lines[start + 1:]:
        if not ln.startswith("|"):
            if out:
                break
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        m = re.search(r"`([^`]+)`", cells[-1])
        if m and not cells[-1].startswith("`-Action`") and "-Action" not in cells[-1]:
            out.append(m.group(1))
    return out


def _never_granted(skill: str) -> list[str]:
    line = next(ln for ln in skill.splitlines() if ln.startswith("**Never granted"))
    return re.findall(r"`([^`]+)`", line)


def check(skill: str, manifest: dict, ps1: str) -> list[str]:
    scope = list(manifest["delegation"]["scope"])
    table = _table_actions(skill)
    problems = []
    problems += [f"table string not in scope: {a}" for a in table if a not in scope]
    problems += [f"scope entry missing from the table: {a}" for a in scope if a not in table]
    problems += [f"-Action string not in scope: {a}" for a in ACTION.findall(skill) if a not in scope]
    problems += [f"never-granted string is in scope: {a}" for a in _never_granted(skill) if a in scope]
    defined = set(FUNCTION.findall(ps1))
    problems += [f"helper not defined in field-rest.ps1: {h}" for h in sorted(set(HELPER.findall(skill))) if h not in defined]
    return problems


def _load(agent: str) -> tuple[str, dict]:
    skill = (ROOT / "agents" / agent / "SKILL.md").read_text(encoding="utf-8")
    manifest = yaml.safe_load((ROOT / "manifests" / f"{agent}.yaml").read_text(encoding="utf-8"))
    return skill, manifest


@pytest.mark.parametrize("agent", AGENTS)
def test_the_skill_and_the_manifest_agree(agent):
    skill, manifest = _load(agent)
    assert check(skill, manifest, PS1.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("agent", AGENTS)
def test_the_scan_is_not_blind(agent):
    skill, manifest = _load(agent)
    scope = manifest["delegation"]["scope"]
    assert len(scope) >= 3 and set(_table_actions(skill)) == set(scope)
    assert len(ACTION.findall(skill)) >= 1 and _never_granted(skill)
    assert {"Invoke-FieldCheck", "Send-FieldCheckin", "Send-FieldSpend"} <= set(HELPER.findall(skill))


@pytest.mark.parametrize("agent", AGENTS)
def test_a_typo_in_the_skill_table_is_found(agent):
    skill, manifest = _load(agent)
    first = manifest["delegation"]["scope"][0]
    mutated = skill.replace(f"`{first}`", f"`{first}x`", 1)
    assert mutated != skill
    problems = check(mutated, manifest, PS1.read_text(encoding="utf-8"))
    assert any("table string not in scope" in p for p in problems) and any("missing from the table" in p for p in problems)


@pytest.mark.parametrize("agent", AGENTS)
def test_a_scope_entry_dropped_from_the_manifest_is_found(agent):
    skill, manifest = _load(agent)
    manifest["delegation"]["scope"] = manifest["delegation"]["scope"][1:]
    assert any("table string not in scope" in p for p in check(skill, manifest, PS1.read_text(encoding="utf-8")))


@pytest.mark.parametrize("agent", AGENTS)
def test_a_scope_entry_added_to_the_manifest_is_found(agent):
    skill, manifest = _load(agent)
    manifest["delegation"]["scope"].append("do something new")
    assert any("missing from the table" in p for p in check(skill, manifest, PS1.read_text(encoding="utf-8")))


@pytest.mark.parametrize("agent", AGENTS)
def test_a_never_granted_string_added_to_scope_is_found(agent):
    skill, manifest = _load(agent)
    manifest["delegation"]["scope"].append(_never_granted(skill)[0])
    assert any("never-granted string is in scope" in p for p in check(skill, manifest, PS1.read_text(encoding="utf-8")))


@pytest.mark.parametrize("agent", AGENTS)
def test_an_action_string_with_a_typo_in_the_example_call_is_found(agent):
    skill, manifest = _load(agent)
    first_call = ACTION.findall(skill)[0]
    mutated = skill.replace(f'-Action "{first_call}"', f'-Action "{first_call} "', 1)
    assert any("-Action string not in scope" in p for p in check(mutated, manifest, PS1.read_text(encoding="utf-8")))


@pytest.mark.parametrize("agent", AGENTS)
def test_a_helper_missing_from_field_rest_is_found(agent):
    skill, manifest = _load(agent)
    ps1 = PS1.read_text(encoding="utf-8").replace("function Send-FieldSpend", "function Send-FieldSpendX")
    assert any("Send-FieldSpend" in p for p in check(skill, manifest, ps1))
