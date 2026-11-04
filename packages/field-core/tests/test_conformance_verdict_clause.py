"""S5-6: a ConformanceVerdict's clause_id is consistent with its decision.

BLOCK / ESCALATE cite a registered clause (CLAUSES); ALLOW carries none. The field description always said "required for
BLOCK/ESCALATE"; the model now enforces it. The static scan pins that every in-tree producer (conformance-sentinel and
federation-broker engines) complies, so a later edit that breaks the rule fails here, in field-core's own job, by reading
the two files (no import of the services)."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from field_core.conformance import CLAUSES, ConformanceVerdict, Decision

ROOT = Path(__file__).resolve().parents[3]
ENGINES = [ROOT / "services/conformance-sentinel/src/conformance_sentinel/engine.py",
           ROOT / "services/federation-broker/src/federation_broker/engine.py"]


def make(decision, clause_id=None):
    return ConformanceVerdict(decision=decision, agent_id="a", action="x", clause_id=clause_id)


# ---- the rule ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("decision", [Decision.BLOCK, Decision.ESCALATE])
def test_block_and_escalate_without_a_clause_are_refused(decision):
    with pytest.raises(ValidationError):
        make(decision, None)


@pytest.mark.parametrize("decision", [Decision.BLOCK, Decision.ESCALATE])
@pytest.mark.parametrize("clause", sorted(CLAUSES))
def test_block_and_escalate_with_every_registered_clause_are_accepted(decision, clause):
    assert make(decision, clause).clause_id == clause


@pytest.mark.parametrize("decision", [Decision.BLOCK, Decision.ESCALATE, Decision.ALLOW])
@pytest.mark.parametrize("clause", ["X.unknown", "", "d.scope", "D.scope "])
def test_a_clause_that_is_not_registered_is_refused(decision, clause):
    with pytest.raises(ValidationError):
        make(decision, clause)


@pytest.mark.parametrize("clause", sorted(CLAUSES))
def test_an_allow_carrying_a_clause_is_refused(clause):
    with pytest.raises(ValidationError):
        make(Decision.ALLOW, clause)


def test_a_plain_allow_is_accepted_and_clause_text_is_none():
    v = make(Decision.ALLOW)
    assert v.clause_id is None and v.clause_text() is None and v.allowed


def test_a_valid_verdict_round_trips_through_json():
    v = make(Decision.BLOCK, "D.scope")
    again = ConformanceVerdict.model_validate_json(v.model_dump_json())
    assert again.clause_id == "D.scope" and again.clause_text() == CLAUSES["D.scope"]


def test_the_refusal_names_the_rule_and_the_decision():
    with pytest.raises(ValidationError) as e:
        make(Decision.BLOCK, None)
    assert "BLOCK" in str(e.value) and "clause_id" in str(e.value)


# ---- every in-tree producer complies -------------------------------------------------------------------------------------

def _third_positional(call):
    return call.args[2] if len(call.args) > 2 else None


def _decision_name(node):
    return node.attr if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "Decision" else None


@pytest.mark.parametrize("engine", ENGINES, ids=lambda p: p.parts[-4])
def test_every_in_tree_producer_cites_a_registered_clause_for_block_and_escalate(engine):
    if not engine.exists():
        pytest.skip("service sources are not in this checkout")
    tree = ast.parse(engine.read_text(encoding="utf-8"))
    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", getattr(node.func, "id", ""))
        if name == "ConformanceVerdict":
            kw = {k.arg: k.value for k in node.keywords}
            decision, clause = _decision_name(kw.get("decision")), kw.get("clause_id")
        elif name == "_verdict" and len(node.args) >= 3:
            decision, clause = _decision_name(node.args[1]), node.args[2]
        else:
            continue
        if decision is None:                       # the decision is a variable: covered by the dynamic evidence in the PR
            continue
        checked += 1
        is_none = isinstance(clause, ast.Constant) and clause.value is None
        if decision in ("BLOCK", "ESCALATE"):
            assert not is_none, f"{engine.name}:{node.lineno} {decision} without a clause"
            if isinstance(clause, ast.Constant):
                assert clause.value in CLAUSES, f"{engine.name}:{node.lineno} unregistered clause {clause.value!r}"
        else:
            assert is_none, f"{engine.name}:{node.lineno} ALLOW carrying a clause"
    assert checked >= 3, "the scan found almost nothing: the producers moved"


@pytest.mark.parametrize("engine", ENGINES, ids=lambda p: p.parts[-4])
def test_every_clause_looking_literal_in_the_producers_is_registered(engine):
    if not engine.exists():
        pytest.skip("service sources are not in this checkout")
    tree = ast.parse(engine.read_text(encoding="utf-8"))
    ids = {n.value for n in ast.walk(tree)
           if isinstance(n, ast.Constant) and isinstance(n.value, str) and re.fullmatch(r"[A-Z]\.[a-z_]+", n.value)}
    assert ids, "no clause ids found: the pattern or the file moved"
    assert ids <= set(CLAUSES), sorted(ids - set(CLAUSES))
