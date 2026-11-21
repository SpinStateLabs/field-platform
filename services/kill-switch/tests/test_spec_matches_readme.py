"""S11-15: SPEC.md and README.md agree on three statements that SPEC had left behind.

1. A domain kill's route is 200 only while at least one agent was halted or already killed; when every attempted
   (non-retired) agent errored it answers 502 with the report as the `detail` (C-19), a domain with no registered
   agent is 404.
2. "No operator authentication/authorization (recorded, not verified)" predates Phase G: with an operator mode armed
   the guarded routes check the operator's key and scope and the manifest's `authorized_operators`.
3. "No auto-kill policies (... may add an opt-in flag)" predates lifecycle-manager's `sweep --auto-kill-orphans`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SERVICE = Path(__file__).resolve().parents[1]
SPEC = " ".join((SERVICE / "SPEC.md").read_text(encoding="utf-8").split())
README = " ".join((SERVICE / "README.md").read_text(encoding="utf-8").split())

DOMAIN_502 = ("when every attempted (non-retired) agent errored it answers **502** with the report as the `detail` "
              "(C-19), and a domain with no registered agent is 404")


def test_the_domain_kill_502_sentence_is_the_same_in_spec_and_readme():
    assert DOMAIN_502 in README, "the README no longer carries the reference sentence: update this test with it"
    assert DOMAIN_502 in SPEC


def test_the_spec_no_longer_says_the_domain_route_always_stays_200():
    assert not re.search(r"recorded, not raised, and the route stays 200\b(?!\s+while)", SPEC)
    assert "the route stays 200 while at least one agent was halted or already killed" in SPEC


@pytest.mark.parametrize("stale", [
    "No operator authentication/authorization (recorded, not verified).",
    "No auto-kill policies (lifecycle-manager, Phase 4, may add an opt-in flag).",
])
def test_the_pre_phase_g_non_goals_are_gone(stale):
    assert stale not in SPEC


def test_the_operator_statement_matches_the_readmes_armed_and_unarmed_wording():
    assert "FIELD_OPERATOR_REQUIRE" in SPEC and "authorized_operators" in SPEC
    assert "recorded, not verified" in SPEC            # still true while no operator mode is armed
    assert "recorded outside this repository" in SPEC   # whether an estate arms it is not asserted here
    assert "Enforced in code when `FIELD_OPERATOR_REQUIRE=1`" in README   # the reference this one agrees with


def test_the_auto_kill_statement_names_the_opt_in_flag_and_who_owns_it():
    assert "--auto-kill-orphans" in SPEC and "lifecycle-manager" in SPEC
    assert "never a default" in SPEC
