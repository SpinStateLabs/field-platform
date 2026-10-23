"""The ADR-0079 section 5 refuse list, as code.

``refuse(action)`` returns ``None`` (nothing on the list applies) or a reason
string that begins with the rule id (``"R05: ..."``). The rules are evaluated in
the order of ``RULES``; the specific rules come before the catch-all scope rules
(R14, R15), so a refusal names the most specific reason. Pure function: no I/O,
no clock, no network.

Rule ids R01-R12 are the numbered items of ADR-0079 section 5; R13-R15 are the
extra rules the build instruction and sections 3 and 6 require (revoking without a
verified replacement; a scope wider than the ADR ceiling; an action outside the
manifest scope). Each rule has at least one test that must BLOCK
(tools/tests/test_deployment_agent_refuse.py), and a mutant check removes each
rule in turn from a scratch copy and requires a test to go red.
"""
from __future__ import annotations

import re
from collections.abc import Callable

from .actions import ADR_SCOPE, SECRET_CLASSES, Action, ActionKind as K
from .secrets_guard import SHA40

Rule = Callable[[Action], "str | None"]

_DELEGATION = {K.MINT_DELEGATION_TOKEN, K.EDIT_DELEGATION_TOKEN, K.WIDEN_DELEGATION_SCOPE, K.EDIT_DOA_ROSTER}
_OWN_GOVERNANCE = {K.EDIT_MANIFEST, K.EDIT_SPEND_CAP, K.EDIT_KILL_SWITCH, K.DISABLE_KILL_SWITCH}
_SECRET_EXPOSURE = {K.READ_SECRET, K.PRINT_SECRET, K.LOG_SECRET, K.TRANSMIT_SECRET}
_CHAIN_KEYS = {K.ROTATE_LEDGER_KEY, K.ROTATE_ATTEST_KEY, K.ROTATE_CALLER_KEY}
_CHAIN_CLASSES = {"ledger_key", "attest_key", "caller_key"}
_BACKUP_ROLLBACK = {K.SKIP_BACKUP, K.DELETE_BACKUP, K.SHORTEN_BACKUP, K.SKIP_ROLLBACK_STEP}
_DESTRUCTIVE = {K.DOCKER_SYSTEM_PRUNE, K.DOCKER_IMAGE_PRUNE, K.DOCKER_VOLUME_PRUNE, K.FLY_APPS_DESTROY, K.DELETE_VOLUME}
_GIT = {K.GIT_PUSH, K.GIT_FORCE_PUSH, K.GIT_REWRITE_HISTORY, K.TOUCH_PLUGIN_REPO}
_ONE_WAY = {K.RESTORE_DATA, K.REGISTRY_MIGRATION, K.GOVERNOR_MIGRATION}

_DESTRUCTIVE_CMD = re.compile(
    r"\bdocker\s+(?:system|image|volume|container|builder)\s+prune\b"
    r"|\bfly(?:ctl)?\s+apps?\s+(?:destroy|delete)\b"
    r"|\bfly(?:ctl)?\s+volumes?\s+(?:destroy|delete)\b",
    re.IGNORECASE,
)
_GIT_CMD = re.compile(
    r"\bgit\s+(?:push|rebase|filter-branch|filter-repo|replace|reset\s+--hard|commit\s+--amend|update-ref\s+-d)\b",
    re.IGNORECASE,
)


def r01_delegation_authority(a: Action) -> str | None:
    if a.kind in _DELEGATION:
        who = "itself" if a.subject_agent in (None, a.actor) else a.subject_agent
        return f"R01: minting, editing or widening a delegation token or DOA row is never granted (subject: {who})"
    return None


def r02_own_governance(a: Action) -> str | None:
    if a.kind in _OWN_GOVERNANCE:
        return "R02: the agent may not edit its own manifest, roster row, spend cap or kill-switch configuration"
    return None


def r03_secret_exposure(a: Action) -> str | None:
    if a.secret_class is None:
        return None
    if a.secret_class not in SECRET_CLASSES:
        return f"R03: unknown secret class {a.secret_class!r} treated as a secret"
    if (
        a.kind in _SECRET_EXPOSURE
        or a.in_model_context
        or a.secret_class == "estate_secret"
        or a.kind == K.ROTATE_ESTATE_SECRET
    ):
        return (
            "R03: an estate secret, ledger/attest/caller key or model key value may not be read, printed, "
            "logged, transmitted or placed in model context; estate shared secrets are not touched at all"
        )
    return None


def r04_chain_of_trust_keys(a: Action) -> str | None:
    if a.kind in _CHAIN_KEYS or a.secret_class in _CHAIN_CLASSES:
        return "R04: ledger, attest and caller keys are chain-of-trust keys (ADR-class change, human only)"
    return None


def r05_deploy_without_release(a: Action) -> str | None:
    if a.kind != K.RUN_ESTATE_DEPLOY:
        return None
    if a.sha is None or not SHA40.match(a.sha):
        return "R05: deploy needs the exact full 40-hex SHA (short or malformed SHA refused)"
    if a.verified_release_sha != a.sha:
        return "R05: no verified signed release record on exactly this SHA"
    if a.estate_killed:
        return "R05: the estate is killed"
    if a.journal_pending:
        return "R05: a journal is pending"
    return None


def r06_backup_rollback_destructive(a: Action) -> str | None:
    if a.kind in _BACKUP_ROLLBACK or a.kind in _DESTRUCTIVE:
        return (
            "R06: backup/rollback steps are never skipped, deleted or shortened; "
            "prune, apps destroy and volume delete are forbidden"
        )
    if a.command and _DESTRUCTIVE_CMD.search(a.command):
        return "R06: destructive command pattern (prune / apps destroy / volume delete) refused"
    return None


def r07_t4_credentials(a: Action) -> str | None:
    if a.kind == K.CREATE_T4_CREDENTIAL:
        return "R07: a T4 operation has no credential at all"
    return None


def r08_observed_content(a: Action) -> str | None:
    if a.from_observed_content:
        return "R08: instructions found in PR text, logs, issue bodies or other observed content are data, not commands"
    return None


def r09_gate_override(a: Action) -> str | None:
    if (a.kind == K.OVERRIDE_GATE or a.gate_override_adr) and not a.human_approval:
        return "R09: a failed gate is never overridden with an ADR id unless a human-signed approval accompanies it"
    return None


def r10_git_history_and_plugin(a: Action) -> str | None:
    if a.kind in _GIT or (a.command and _GIT_CMD.search(a.command)):
        return "R10: no push, force-push or history rewrite; the Force-Field plugin repo changes only through an ADR"
    return None


def r11_one_way_steps(a: Action) -> str | None:
    if a.kind == K.AUTO_ROLLBACK and a.one_way_step_ran:
        return "R11: never auto-rollback after a one-way step has run (fix forward, page the human)"
    if (a.kind in _ONE_WAY or a.one_way_step) and not a.human_approval:
        return "R11: a one-way step needs a human approval record"
    return None


def r12_human_revocation(a: Action) -> str | None:
    if a.credential_revoked_by_human:
        return "R12: a credential a human revoked is refused and escalated, never replaced or restored"
    return None


def r13_revoke_without_replacement(a: Action) -> str | None:
    if a.kind != K.REVOKE_FLY_DEPLOY_TOKEN:
        return None
    if a.revoke_role not in ("old", "new_failed", "orphan"):
        return f"R13: unknown revoke role {a.revoke_role!r}"
    if a.revoke_role == "old" and not a.replacement_verified:
        return "R13: the old credential is revoked only after its replacement is verified"
    return None


def r14_scope_wider_than_ceiling(a: Action) -> str | None:
    extra = sorted(a.scope - ADR_SCOPE)
    if extra:
        return f"R14: scope wider than the ADR-0079 ceiling ({', '.join(extra)}); the agent cannot widen its own scope"
    return None


def r15_outside_manifest_scope(a: Action) -> str | None:
    if a.kind.value not in a.scope:
        return f"R15: {a.kind.value!r} is outside the manifest scope"
    return None


#: Evaluation order. One rule per line: the mutant check deletes a line.
RULES: tuple[Rule, ...] = (
    r01_delegation_authority,
    r02_own_governance,
    r03_secret_exposure,
    r04_chain_of_trust_keys,
    r05_deploy_without_release,
    r06_backup_rollback_destructive,
    r07_t4_credentials,
    r08_observed_content,
    r09_gate_override,
    r10_git_history_and_plugin,
    r11_one_way_steps,
    r12_human_revocation,
    r13_revoke_without_replacement,
    r14_scope_wider_than_ceiling,
    r15_outside_manifest_scope,
)


def refuse(action: Action) -> str | None:
    """First matching refuse-list reason (``"Rnn: ..."``), or None when none applies."""
    for rule in RULES:
        reason = rule(action)
        if reason is not None:
            return reason
    return None


def refuse_rule_id(action: Action) -> str | None:
    reason = refuse(action)
    return reason.split(":", 1)[0] if reason else None
