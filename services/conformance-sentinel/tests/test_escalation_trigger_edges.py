"""S6-14: step 7's trigger rule is a substring match in BOTH directions, so two edges are pinned as DECIDED behaviour.

(1) An empty or single-space declared trigger is a substring of every action: every otherwise-allowed action
ESCALATEs E.escalation_trigger. This is kept (fail closed: a manifest authoring slip raises human reviews, it never
lets an action through unreviewed) and named here so a change is a decision, not an accident; the manifest schema
allows it (escalation_triggers items have no minLength).
(2) The reverse leg: an action that is a substring of a trigger (a one-word action inside a longer trigger) matches too."""

import pytest
import yaml


def _set_triggers(stack, triggers):
    data = yaml.safe_load(stack.manifest_path.read_text(encoding="utf-8"))
    data["enforcement"]["escalation_triggers"] = triggers
    stack.manifest_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


@pytest.mark.parametrize("blank", ["", " "])
def test_a_blank_trigger_escalates_an_otherwise_allowed_action(stack, blank):
    _set_triggers(stack, [blank])
    stack.set_cap()
    token = stack.mint_token()
    verdict = stack.check("draft invoices", token_id=token)
    assert verdict["decision"] == "ESCALATE"
    assert verdict["clause_id"] == "E.escalation_trigger"


def test_a_longer_run_of_spaces_is_not_a_substring_of_a_one_space_action_so_it_does_not_match(stack):
    # a correction to the scout card: only the empty string and a single space match every multi-word action
    _set_triggers(stack, ["   "])
    stack.set_cap()
    token = stack.mint_token()
    assert stack.check("draft invoices", token_id=token)["decision"] == "ALLOW"


def test_the_same_action_is_allowed_when_no_trigger_matches(stack):
    _set_triggers(stack, ["wire transfer"])
    stack.set_cap()
    token = stack.mint_token()
    assert stack.check("draft invoices", token_id=token)["decision"] == "ALLOW"


def test_the_reverse_leg_an_action_inside_a_longer_trigger_escalates(stack):
    _set_triggers(stack, ["draft invoices and send them"])
    stack.set_cap()
    token = stack.mint_token()
    verdict = stack.check("draft invoices", token_id=token)
    assert verdict["decision"] == "ESCALATE" and verdict["clause_id"] == "E.escalation_trigger"
