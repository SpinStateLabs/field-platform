"""The ADR-0079 section 5 refuse list: every item is a test that must BLOCK.

Three layers:

1. ``CASES`` - for each rule R01-R15, one or more actions that must be refused BY
   THAT RULE (the reason starts with its id), and ``CONTROLS`` - legitimate actions
   that must pass. A case that merely says "refused by something" would let a
   deleted rule hide behind the catch-all scope rules, so the id is asserted.
2. Every ``ActionKind`` outside the ADR scope is refused with the default scope, and
   a widened scope does not widen anything (the agent cannot grant itself scope).
3. A mutant check: for each rule, a scratch copy of the package is made with that
   rule removed from ``RULES``; at least one case of that rule must go red against
   the mutant (and the unmutated copy must stay green, so the harness itself is
   proven sensitive).
"""
from __future__ import annotations

import importlib
import importlib.util
import re
import shutil
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from deployment_agent import refuse as refuse_mod  # noqa: E402
from deployment_agent.actions import ADR_SCOPE, Action, ActionKind  # noqa: E402

SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER = "fedcba9876543210fedcba9876543210fedcba98"
WIDE = ADR_SCOPE | {"mint delegation token for another agent"}


# (rule id, case name, builder(A, K) -> Action). Builders take the Action and ActionKind classes
# so the mutant check can run the same cases against a scratch copy of the package.
CASES = [
    ("R01", "mint a delegation token for another agent", lambda A, K: A(K.MINT_DELEGATION_TOKEN, subject_agent="ssl-invoicing-agent")),
    ("R01", "mint a delegation token for itself", lambda A, K: A(K.MINT_DELEGATION_TOKEN, subject_agent="ssl-deployment-agent")),
    ("R01", "widen a delegation scope", lambda A, K: A(K.WIDEN_DELEGATION_SCOPE)),
    ("R01", "edit a delegation token", lambda A, K: A(K.EDIT_DELEGATION_TOKEN, subject_agent="canary-gb10")),
    ("R01", "edit the DOA roster", lambda A, K: A(K.EDIT_DOA_ROSTER)),
    ("R02", "edit its own manifest", lambda A, K: A(K.EDIT_MANIFEST)),
    ("R02", "edit its own spend cap", lambda A, K: A(K.EDIT_SPEND_CAP)),
    ("R02", "edit its own kill-switch configuration", lambda A, K: A(K.EDIT_KILL_SWITCH)),
    ("R02", "disable the kill switch", lambda A, K: A(K.DISABLE_KILL_SWITCH)),
    ("R03", "read an estate secret", lambda A, K: A(K.READ_SECRET, secret_class="estate_secret")),
    ("R03", "print a model key", lambda A, K: A(K.PRINT_SECRET, secret_class="model_key")),
    ("R03", "log a ledger key", lambda A, K: A(K.LOG_SECRET, secret_class="ledger_key")),
    ("R03", "transmit a caller key", lambda A, K: A(K.TRANSMIT_SECRET, secret_class="caller_key")),
    ("R03", "put a model key in model context", lambda A, K: A(K.ROTATE_MODEL_KEY_REFERENCE, secret_class="model_key", in_model_context=True)),
    ("R03", "touch an estate shared secret in any way", lambda A, K: A(K.WRITE_GITHUB_ENV_SECRET, secret_class="estate_secret")),
    ("R03", "rotate an estate shared secret", lambda A, K: A(K.ROTATE_ESTATE_SECRET, secret_class="estate_secret")),
    ("R03", "an unknown secret class is treated as a secret", lambda A, K: A(K.READ_SECRET, secret_class="mystery_key")),
    ("R03", "print a secret even with no secret_class", lambda A, K: A(K.PRINT_SECRET)),
    ("R03", "read a secret even with no secret_class", lambda A, K: A(K.READ_SECRET)),
    ("R03", "log a secret even with no secret_class", lambda A, K: A(K.LOG_SECRET)),
    ("R03", "transmit a secret even with no secret_class", lambda A, K: A(K.TRANSMIT_SECRET)),
    ("R04", "rotate the ledger key", lambda A, K: A(K.ROTATE_LEDGER_KEY)),
    ("R04", "rotate the attest key", lambda A, K: A(K.ROTATE_ATTEST_KEY)),
    ("R04", "rotate a caller key", lambda A, K: A(K.ROTATE_CALLER_KEY)),
    ("R04", "touch an attest key through an in-scope action", lambda A, K: A(K.WRITE_GITHUB_ENV_SECRET, secret_class="attest_key")),
    ("R05", "deploy a SHA with no release record", lambda A, K: A(K.RUN_ESTATE_DEPLOY, sha=SHA)),
    ("R05", "deploy a short SHA", lambda A, K: A(K.RUN_ESTATE_DEPLOY, sha=SHA[:7], verified_release_sha=SHA[:7])),
    ("R05", "deploy with no SHA", lambda A, K: A(K.RUN_ESTATE_DEPLOY)),
    ("R05", "release record is for another SHA", lambda A, K: A(K.RUN_ESTATE_DEPLOY, sha=SHA, verified_release_sha=OTHER)),
    ("R05", "estate killed state unknown (None)", lambda A, K: A(K.RUN_ESTATE_DEPLOY, sha=SHA, verified_release_sha=SHA, journal_pending=False)),
    ("R05", "journal pending state unknown (None)", lambda A, K: A(K.RUN_ESTATE_DEPLOY, sha=SHA, verified_release_sha=SHA, estate_killed=False)),
    ("R05", "estate_killed given as a truthy non-bool", lambda A, K: A(K.RUN_ESTATE_DEPLOY, sha=SHA, verified_release_sha=SHA, estate_killed="no", journal_pending=False)),
    ("R05", "deploy while the estate is killed", lambda A, K: A(K.RUN_ESTATE_DEPLOY, sha=SHA, verified_release_sha=SHA, estate_killed=True)),
    ("R05", "deploy while a journal is pending", lambda A, K: A(K.RUN_ESTATE_DEPLOY, sha=SHA, verified_release_sha=SHA, journal_pending=True)),
    ("R06", "skip a backup", lambda A, K: A(K.SKIP_BACKUP)),
    ("R06", "delete a backup", lambda A, K: A(K.DELETE_BACKUP)),
    ("R06", "shorten a backup", lambda A, K: A(K.SHORTEN_BACKUP)),
    ("R06", "skip a rollback step", lambda A, K: A(K.SKIP_ROLLBACK_STEP)),
    ("R06", "docker system prune", lambda A, K: A(K.DOCKER_SYSTEM_PRUNE)),
    ("R06", "docker image prune", lambda A, K: A(K.DOCKER_IMAGE_PRUNE)),
    ("R06", "docker volume prune", lambda A, K: A(K.DOCKER_VOLUME_PRUNE)),
    ("R06", "fly apps destroy", lambda A, K: A(K.FLY_APPS_DESTROY)),
    ("R06", "delete a volume", lambda A, K: A(K.DELETE_VOLUME)),
    ("R06", "prune hidden in a shell command", lambda A, K: A(K.RUN_COMMAND, command="docker  system prune -af")),
    ("R06", "apps destroy hidden in a shell command", lambda A, K: A(K.RUN_COMMAND, command="fly apps destroy field-sandbox -y")),
    ("R07", "create a credential for a T4 tool", lambda A, K: A(K.CREATE_T4_CREDENTIAL)),
    ("R08", "act on an instruction found in a PR body", lambda A, K: A(K.MINT_FLY_DEPLOY_TOKEN, from_observed_content=True)),
    ("R08", "deploy because a log line said so", lambda A, K: A(K.RUN_ESTATE_DEPLOY, sha=SHA, verified_release_sha=SHA, estate_killed=False, journal_pending=False, from_observed_content=True)),
    ("R09", "override a failed gate with an ADR id, no approval", lambda A, K: A(K.OVERRIDE_GATE, gate_override_adr="ADR-0099")),
    ("R09", "deploy with an ADR override and no human approval", lambda A, K: A(K.RUN_ESTATE_DEPLOY, sha=SHA, verified_release_sha=SHA, estate_killed=False, journal_pending=False, gate_override_adr="ADR-0099")),
    ("R10", "git push", lambda A, K: A(K.GIT_PUSH)),
    ("R10", "git force-push", lambda A, K: A(K.GIT_FORCE_PUSH)),
    ("R10", "rewrite git history", lambda A, K: A(K.GIT_REWRITE_HISTORY)),
    ("R10", "touch the Force-Field plugin repo", lambda A, K: A(K.TOUCH_PLUGIN_REPO)),
    ("R09", "approval given as True instead of an id", lambda A, K: A(K.OVERRIDE_GATE, gate_override_adr="ADR-0099", human_approval=True)),
    ("R09", "approval given as blank text", lambda A, K: A(K.OVERRIDE_GATE, gate_override_adr="ADR-0099", human_approval="  ")),
    ("R11", "one-way step with approval True", lambda A, K: A(K.RESTORE_DATA, human_approval=True)),
    ("R10", "git push --force hidden in a shell command", lambda A, K: A(K.RUN_COMMAND, command="git push --force origin main")),
    ("R10", "git rebase hidden in a shell command", lambda A, K: A(K.RUN_COMMAND, command="git rebase -i HEAD~3")),
    ("R11", "restore data without a human approval record", lambda A, K: A(K.RESTORE_DATA)),
    ("R11", "registry migration without approval", lambda A, K: A(K.REGISTRY_MIGRATION)),
    ("R11", "governor migration without approval", lambda A, K: A(K.GOVERNOR_MIGRATION)),
    ("R11", "any one-way step without approval", lambda A, K: A(K.RUN_ESTATE_DEPLOY, sha=SHA, verified_release_sha=SHA, estate_killed=False, journal_pending=False, one_way_step=True)),
    ("R11", "auto-rollback after a one-way step, even with an approval", lambda A, K: A(K.AUTO_ROLLBACK, one_way_step_ran=True, human_approval="appr-1")),
    ("R12", "install over a credential a human revoked", lambda A, K: A(K.WRITE_GITHUB_ENV_SECRET, credential_revoked_by_human=True)),
    ("R12", "mint a replacement for a credential a human revoked", lambda A, K: A(K.MINT_FLY_DEPLOY_TOKEN, credential_revoked_by_human=True)),
    ("R13", "revoke the old credential with no verified replacement", lambda A, K: A(K.REVOKE_FLY_DEPLOY_TOKEN)),
    ("R13", "replacement_verified given as a truthy non-bool", lambda A, K: A(K.REVOKE_FLY_DEPLOY_TOKEN, replacement_verified="yes")),
    ("R13", "revoke with an unknown role", lambda A, K: A(K.REVOKE_FLY_DEPLOY_TOKEN, revoke_role="whatever", replacement_verified=True)),
    ("R14", "an action whose scope was widened past the ADR ceiling", lambda A, K: A(K.MINT_FLY_DEPLOY_TOKEN, scope=frozenset(A.__dataclass_fields__["scope"].default) | {"mint delegation token for another agent"})),
    ("R15", "an in-scope kind the manifest does not grant", lambda A, K: A(K.MINT_FLY_DEPLOY_TOKEN, scope=frozenset(A.__dataclass_fields__["scope"].default) - {"mint fly deploy token"})),
    ("R15", "a free-form command outside scope", lambda A, K: A(K.RUN_COMMAND, command="ls")),
    ("R15", "an approved one-way step is still outside scope", lambda A, K: A(K.RESTORE_DATA, human_approval="appr-1")),
]

CONTROLS = [
    ("mint", lambda A, K: A(K.MINT_FLY_DEPLOY_TOKEN, target="fly-app-a")),
    ("write the environment secret", lambda A, K: A(K.WRITE_GITHUB_ENV_SECRET, target="fly-app-a")),
    ("revoke the old credential after verification", lambda A, K: A(K.REVOKE_FLY_DEPLOY_TOKEN, replacement_verified=True)),
    ("revoke a failed new credential (rollback)", lambda A, K: A(K.REVOKE_FLY_DEPLOY_TOKEN, revoke_role="new_failed")),
    ("revoke an orphan (sweep)", lambda A, K: A(K.REVOKE_FLY_DEPLOY_TOKEN, revoke_role="orphan")),
    ("deploy a SHA with a verified release record", lambda A, K: A(K.RUN_ESTATE_DEPLOY, sha=SHA, verified_release_sha=SHA, estate_killed=False, journal_pending=False)),
    ("deploy with a human-approved ADR override", lambda A, K: A(K.RUN_ESTATE_DEPLOY, sha=SHA, verified_release_sha=SHA, estate_killed=False, journal_pending=False, gate_override_adr="ADR-0099", human_approval="appr-1")),
    ("run the canary", lambda A, K: A(K.RUN_ESTATE_CANARY)),
    ("rotate the model key reference", lambda A, K: A(K.ROTATE_MODEL_KEY_REFERENCE, secret_class=None)),
]


def _apply(refuse_module, actions_module, builder):
    return refuse_module.refuse_rule_id(builder(actions_module.Action, actions_module.ActionKind))


@pytest.mark.parametrize("rule_id,name,builder", CASES, ids=[f"{r}-{n}" for r, n, _ in CASES])
def test_refuse_list_item_blocks_with_its_own_rule(rule_id, name, builder):
    action = builder(Action, ActionKind)
    reason = refuse_mod.refuse(action)
    assert reason is not None, f"{name}: not refused"
    assert reason.startswith(rule_id + ":"), f"{name}: refused by the wrong rule: {reason}"


@pytest.mark.parametrize("name,builder", CONTROLS, ids=[n for n, _ in CONTROLS])
def test_legitimate_actions_are_not_refused(name, builder):
    assert refuse_mod.refuse(builder(Action, ActionKind)) is None


def test_every_rule_in_the_table_has_a_case_and_every_case_names_a_rule():
    ids = {f.__name__[:3].upper() for f in refuse_mod.RULES}
    assert ids == {r for r, _, _ in CASES}
    assert len(ids) == len(refuse_mod.RULES) == 15


def test_adr_section_5_items_1_to_12_are_all_covered():
    assert {f"R{n:02d}" for n in range(1, 13)} <= {r for r, _, _ in CASES}


@pytest.mark.parametrize("kind", [k for k in ActionKind if k.value not in ADR_SCOPE], ids=lambda k: k.name)
def test_every_out_of_scope_kind_is_refused_by_default(kind):
    assert refuse_mod.refuse(Action(kind)) is not None


def test_widening_the_scope_on_an_action_widens_nothing():
    for kind in ActionKind:
        if kind.value in ADR_SCOPE:
            continue
        wide = ADR_SCOPE | {kind.value}
        reason = refuse_mod.refuse(Action(kind, scope=frozenset(wide)))
        assert reason is not None, kind
        assert reason.split(":")[0] in {f"R{n:02d}" for n in range(1, 15)}  # something specific or R14, never silence


def test_reason_strings_carry_no_secret_looking_text():
    from deployment_agent.secrets_guard import looks_like_secret

    for _, _, builder in CASES:
        reason = refuse_mod.refuse(builder(Action, ActionKind))
        assert reason and not looks_like_secret(reason), reason


def test_refuse_is_pure_and_repeatable():
    a = Action(ActionKind.RUN_ESTATE_DEPLOY, sha=SHA)
    assert refuse_mod.refuse(a) == refuse_mod.refuse(a)


ALIAS_R06 = [
    "flyctl destroy field-sandbox", "fly destroy field-sandbox -y", "fly vol delete vol_abc", "fly volume delete vol_abc",
    "fly volumes destroy vol_abc", "fly machine destroy abc", "flyctl apps destroy x",
    "docker -H tcp://10.0.0.62:2375 system prune -af", "docker network prune -f", "docker buildx prune -af",
    "docker volume rm field-keys", "docker builder prune", "docker --context prod image prune -a",
    '"docker" "system" "prune"', "docker 'volume' 'prune'",
]
ALIAS_R10 = [
    "git -C . push", "git -c user.name=x push origin main", 'git "push" --force', "git --git-dir=.git push",
    "git -C /repo -c k=v rebase main", "git filter-repo --path x",
]


@pytest.mark.parametrize("cmd", ALIAS_R06)
def test_destructive_command_aliases_are_refused_by_r06(cmd):
    assert refuse_mod.refuse(Action(ActionKind.RUN_COMMAND, command=cmd)).startswith("R06")


@pytest.mark.parametrize("cmd", ALIAS_R10)
def test_git_command_aliases_are_refused_by_r10(cmd):
    assert refuse_mod.refuse(Action(ActionKind.RUN_COMMAND, command=cmd)).startswith("R10")


def test_a_malformed_action_is_refused_not_raised():
    for bad in (
        Action("mint fly deploy token"),  # a str, not an ActionKind
        Action(None),
        Action(ActionKind.MINT_FLY_DEPLOY_TOKEN, scope=["mint fly deploy token"]),
        Action(ActionKind.MINT_FLY_DEPLOY_TOKEN, scope=set(ADR_SCOPE)),
        Action(ActionKind.MINT_FLY_DEPLOY_TOKEN, scope=None),
    ):
        reason = refuse_mod.refuse(bad)
        assert reason is not None and reason.startswith("R00")
    assert refuse_mod.refuse("not an action").startswith("R00")


def test_unknown_deploy_facts_refuse_and_known_false_facts_pass():
    base = dict(sha=SHA, verified_release_sha=SHA)
    assert refuse_mod.refuse(Action(ActionKind.RUN_ESTATE_DEPLOY, **base)).startswith("R05")
    assert refuse_mod.refuse(Action(ActionKind.RUN_ESTATE_DEPLOY, estate_killed=False, journal_pending=False, **base)) is None


# ---- mutant check ---------------------------------------------------------------------------------------


def _load_package(src: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, src / "__init__.py", submodule_search_locations=[str(src)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return importlib.import_module(name + ".refuse"), importlib.import_module(name + ".actions")


def _unload(name: str) -> None:
    for key in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        del sys.modules[key]


def _make_copy(tmp_path: Path, tag: str, drop_rule: str | None) -> Path:
    dst = tmp_path / tag / f"da_{tag}"
    shutil.copytree(TOOLS / "deployment_agent", dst, ignore=shutil.ignore_patterns("__pycache__"))
    if drop_rule is not None:
        text = (dst / "refuse.py").read_text(encoding="utf-8")
        pattern = re.compile(rf"^    {drop_rule.lower()}_\w+,\n", re.MULTILINE)
        mutated, n = pattern.subn("", text)
        assert n == 1, f"could not remove {drop_rule} from RULES"
        (dst / "refuse.py").write_text(mutated, encoding="utf-8")
    return dst


def _mismatches(tmp_path: Path, tag: str, drop_rule: str | None) -> dict[str, list[str]]:
    """For each rule, the case names the (possibly mutated) copy does NOT refuse with that rule."""
    src = _make_copy(tmp_path, tag, drop_rule)
    name = src.name
    try:
        refuse_module, actions_module = _load_package(src, name)
        assert (len(refuse_module.RULES) == 15) == (drop_rule is None)
        out: dict[str, list[str]] = {}
        for rule, case, builder in CASES:
            if _apply(refuse_module, actions_module, builder) != rule:
                out.setdefault(rule, []).append(case)
        return out
    finally:
        _unload(name)


def test_mutant_harness_is_green_on_an_unmutated_copy(tmp_path):
    assert _mismatches(tmp_path, "clean", None) == {}


@pytest.mark.parametrize("rule", [f"R{n:02d}" for n in range(1, 16)])
def test_removing_one_rule_turns_a_test_red(tmp_path, rule):
    red = _mismatches(tmp_path, "mut" + rule.lower(), rule)
    assert rule in red, f"mutant without {rule} survived: no case of {rule} noticed"
