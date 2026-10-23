"""Typed actions the deployment agent may be asked to take (or must refuse).

``ActionKind`` values for the in-scope kinds are exactly the ``delegation.scope``
strings of ADR-0079 section 3, so the manifest scope list and the code compare
string for string. The out-of-scope kinds are the ones the ADR lists as
"deliberately absent (so any attempt is a scope BLOCK)" plus one kind per item of
the section 5 refuse list.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field

from . import AGENT_NAME


class ActionKind(str, enum.Enum):
    # ---- in scope (ADR-0079 section 3, delegation.scope) -----------------------
    MINT_FLY_DEPLOY_TOKEN = "mint fly deploy token"
    REVOKE_FLY_DEPLOY_TOKEN = "revoke fly deploy token"
    WRITE_GITHUB_ENV_SECRET = "write github env secret"
    RUN_ESTATE_DEPLOY = "run estate deploy"
    RUN_ESTATE_CANARY = "run estate canary"
    ROTATE_MODEL_KEY_REFERENCE = "rotate model key reference"
    # ---- never granted: R01 delegation authority --------------------------------
    MINT_DELEGATION_TOKEN = "mint delegation token for another agent"
    EDIT_DELEGATION_TOKEN = "edit delegation token"
    WIDEN_DELEGATION_SCOPE = "widen delegation scope"
    EDIT_DOA_ROSTER = "edit doa roster"
    # ---- R02 own governance ------------------------------------------------------
    EDIT_MANIFEST = "edit manifest"
    EDIT_SPEND_CAP = "edit spend cap"
    EDIT_KILL_SWITCH = "edit kill switch configuration"
    DISABLE_KILL_SWITCH = "disable kill switch"
    # ---- R03 secret handling -----------------------------------------------------
    READ_SECRET = "read secret value"
    PRINT_SECRET = "print secret value"
    LOG_SECRET = "log secret value"
    TRANSMIT_SECRET = "transmit secret value"
    ROTATE_ESTATE_SECRET = "rotate estate shared secret"
    # ---- R04 chain-of-trust keys --------------------------------------------------
    ROTATE_LEDGER_KEY = "rotate ledger key"
    ROTATE_ATTEST_KEY = "rotate attest key"
    ROTATE_CALLER_KEY = "rotate caller key"
    # ---- R06 backups, rollback, destructive commands ---------------------------------
    SKIP_BACKUP = "skip backup"
    DELETE_BACKUP = "delete backup"
    SHORTEN_BACKUP = "shorten backup"
    SKIP_ROLLBACK_STEP = "skip rollback step"
    DOCKER_SYSTEM_PRUNE = "docker system prune"
    DOCKER_IMAGE_PRUNE = "docker image prune"
    DOCKER_VOLUME_PRUNE = "docker volume prune"
    FLY_APPS_DESTROY = "fly apps destroy"
    DELETE_VOLUME = "delete volume"
    # ---- R07 --------------------------------------------------------------------
    CREATE_T4_CREDENTIAL = "create credential for t4 tool"
    # ---- R09 / R10 / R11 ----------------------------------------------------------
    OVERRIDE_GATE = "override failed gate"
    GIT_PUSH = "git push"
    GIT_FORCE_PUSH = "git force-push"
    GIT_REWRITE_HISTORY = "git rewrite history"
    TOUCH_PLUGIN_REPO = "touch force-field plugin repo"
    RESTORE_DATA = "restore data"
    REGISTRY_MIGRATION = "registry migration"
    GOVERNOR_MIGRATION = "governor migration"
    AUTO_ROLLBACK = "automatic rollback"
    # ---- free-form (only the command-pattern rules can refuse these by content) -----
    RUN_COMMAND = "run shell command"


#: ADR-0079 section 3 `delegation.scope`: the ceiling no caller may exceed.
ADR_SCOPE: frozenset[str] = frozenset(
    k.value
    for k in (
        ActionKind.MINT_FLY_DEPLOY_TOKEN,
        ActionKind.REVOKE_FLY_DEPLOY_TOKEN,
        ActionKind.WRITE_GITHUB_ENV_SECRET,
        ActionKind.RUN_ESTATE_DEPLOY,
        ActionKind.RUN_ESTATE_CANARY,
        ActionKind.ROTATE_MODEL_KEY_REFERENCE,
    )
)

SECRET_CLASSES = ("estate_secret", "ledger_key", "attest_key", "caller_key", "model_key")
REVOKE_ROLES = ("old", "new_failed", "orphan")


@dataclass(frozen=True)
class Action:
    """One thing the agent is about to do. Facts about the world are inputs.

    The refuse list never trusts a flag to be absent on its own authority: the
    engine fills these from the provider, the journal and the verified release
    record, and every default is the SAFE one (no approval, nothing verified).
    """

    kind: ActionKind
    target: str = ""
    actor: str = AGENT_NAME
    subject_agent: str | None = None  # whom a delegation action is for (may be the actor)
    #: the manifest scope in force (delegation.scope strings). Defaults to the ADR ceiling.
    scope: frozenset[str] = ADR_SCOPE
    # deploy facts
    sha: str | None = None
    verified_release_sha: str | None = None  # set only from a verify_release() success
    estate_killed: bool = False
    journal_pending: bool = False
    # credential facts
    revoke_role: str = "old"  # old | new_failed | orphan (only "old" needs a replacement)
    replacement_verified: bool = False
    credential_revoked_by_human: bool = False
    secret_class: str | None = None
    in_model_context: bool = False
    # approvals and provenance
    human_approval: str | None = None  # id of a human-signed approval record (not verified here)
    gate_override_adr: str | None = None
    one_way_step: bool = False
    one_way_step_ran: bool = False
    from_observed_content: bool = False  # instruction came from a PR, log, issue body, ...
    command: str | None = None
    note: str = field(default="", compare=False)
