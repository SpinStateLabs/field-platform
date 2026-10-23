"""The ``Provider`` protocol and the in-memory FAKE used by the tests.

There is NO real provider here. The Fly / GitHub / GB10 adapters are out of scope
for the skeleton (ADR-0079 section 9 lists the prerequisites that must land
first); ``RealProviderNotImplemented`` is the placeholder and every method raises
``NotImplementedError`` with a pointer to the ADR.

Credential values travel as ``SecretValue`` and are only ``reveal()``-ed by the
rotator when it stages/backs up a value in a 0600 file and by the provider
adapter itself. Ids (``cred_id``) are short opaque handles and are what the
journal records.
"""
from __future__ import annotations

import secrets as _secrets
from dataclasses import dataclass, replace
from typing import Protocol, runtime_checkable

from .secrets_guard import SecretValue

ADR_POINTER = (
    "no real provider exists in the skeleton: Fly, GitHub and GB10 adapters are out of scope "
    "(harness repo adr/ADR-0079-*.md sections 4, 6 and 9)"
)


@dataclass(frozen=True)
class MintResult:
    cred_id: str
    secret: SecretValue


@dataclass(frozen=True)
class CredInfo:
    cred_id: str
    target: str
    state: str  # "active" | "revoked" | "expired"
    revoked_by: str | None = None  # the actor that revoked it ("human" or the agent name)
    ttl_days: int | None = None
    label: str | None = None  # the stamp the minting run put on it (None: not minted by this agent)


@runtime_checkable
class Provider(Protocol):
    """What the rotator needs from a credential provider plus its consumer."""

    def current(self, target: str) -> str:
        """Id of the credential the consumer is configured with now."""

    def list_credentials(self, target: str) -> list[str]:
        """Ids of every credential the provider holds for the target (any state)."""

    def mint(self, target: str, ttl_days: int, label: str) -> MintResult:
        """Create a credential with the requested lifetime, stamped with ``label`` (the provider's
        name/label/metadata field). ``describe`` must return the label so a sweep can tell this agent's
        own credentials from anyone else's."""

    def describe(self, cred_id: str) -> CredInfo:
        """Fresh read of one credential (target, state, who revoked it, lifetime)."""

    def read_installed(self, target: str) -> bytes:
        """The bytes the consumer holds now (needed for the byte-identical backup)."""

    def install(self, target: str, value: bytes) -> None:
        """Write the consumer's copy atomically."""

    def verify(self, target: str, secret: SecretValue) -> bool:
        """Exercise the consumer WITH this credential in the request. True only if it worked."""

    def revoke(self, cred_id: str, by: str) -> None:
        """Revoke (idempotent). The rotator re-reads with ``describe`` to confirm."""


class RealProviderNotImplemented:
    """Placeholder for the Fly / GitHub / GB10 adapters. Every call raises."""

    def _no(self, *a: object, **k: object) -> object:
        raise NotImplementedError(ADR_POINTER)

    current = list_credentials = mint = describe = read_installed = install = verify = revoke = _no  # type: ignore[assignment]


class FakeProvider:
    """In-memory provider + consumer with fault knobs. Deterministic apart from secret values."""

    def __init__(self, agent: str = "ssl-deployment-agent") -> None:
        self.agent = agent
        self.creds: dict[str, CredInfo] = {}
        self.secrets: dict[str, SecretValue] = {}
        self.installed: dict[str, bytes] = {}
        self.configured: dict[str, str] = {}  # target -> cred id the consumer is configured with
        self.minted_secrets: list[SecretValue] = []  # every value ever minted (tests scan journals for them)
        self.calls: list[tuple[str, str]] = []
        self._n = 0
        # fault knobs
        self.verify_result: bool | None = None  # force verify's answer
        self.verifier_ignores_secret = False  # a broken verifier that always says yes
        self.mint_ttl_override: int | None = None  # provider returns a different lifetime than asked
        self.install_error: Exception | None = None
        self.revoke_noop = False  # provider silently does not revoke (confirmation must catch it)
        self.revoke_errors = 0  # the next N revoke calls raise (message deliberately secret-shaped)
        self.describe_error: Exception | None = None
        self.prefix_only_verifier = False  # a verifier that only looks at the credential's prefix
        self.on_verify: list = []  # callables run inside verify (e.g. a human revoking mid-verify)

    # ---- test helpers ---------------------------------------------------------
    def seed(self, target: str, ttl_days: int = 30) -> str:
        """Create the pre-existing credential the consumer already holds."""
        res = self._mint(target, ttl_days)
        self.installed[target] = res.secret.reveal().encode()
        self.configured[target] = res.cred_id
        return res.cred_id

    def human_revoke(self, cred_id: str) -> None:
        c = self.creds[cred_id]
        self.creds[cred_id] = replace(c, state="revoked", revoked_by="human")

    def expire(self, cred_id: str) -> None:
        c = self.creds[cred_id]
        self.creds[cred_id] = replace(c, state="expired", revoked_by=None)

    def active_ids(self, target: str) -> list[str]:
        return [i for i, c in self.creds.items() if c.target == target and c.state == "active"]

    # ---- Provider -------------------------------------------------------------
    def human_mint(self, target: str, ttl_days: int = 30) -> str:
        """A credential somebody else created for the target (no stamp)."""
        return self._mint(target, ttl_days).cred_id

    def _mint(self, target: str, ttl_days: int, label: str | None = None) -> MintResult:
        self._n += 1
        cid = f"fk-{self._n:04d}"
        secret = SecretValue("fakesecret-" + _secrets.token_hex(24))
        self.creds[cid] = CredInfo(cid, target, "active", None, ttl_days, label)
        self.secrets[cid] = secret
        self.minted_secrets.append(secret)
        return MintResult(cid, secret)

    def current(self, target: str) -> str:
        return self.configured[target]

    def list_credentials(self, target: str) -> list[str]:
        return [i for i, c in self.creds.items() if c.target == target]

    def mint(self, target: str, ttl_days: int, label: str) -> MintResult:
        self.calls.append(("mint", target))
        res = self._mint(target, ttl_days, label)
        if self.mint_ttl_override is not None:
            self.creds[res.cred_id] = replace(self.creds[res.cred_id], ttl_days=self.mint_ttl_override)
        return res

    def describe(self, cred_id: str) -> CredInfo:
        if self.describe_error is not None:
            raise self.describe_error
        return self.creds[cred_id]

    def read_installed(self, target: str) -> bytes:
        return self.installed[target]

    def install(self, target: str, value: bytes) -> None:
        self.calls.append(("install", target))
        if self.install_error is not None:
            raise self.install_error
        self.installed[target] = bytes(value)
        for cid, sec in self.secrets.items():
            if self.creds[cid].target == target and sec.reveal().encode() == value:
                self.configured[target] = cid

    def verify(self, target: str, secret: SecretValue) -> bool:
        self.calls.append(("verify", target))
        for hook in list(self.on_verify):
            hook()
        if self.verifier_ignores_secret:
            return True
        if self.prefix_only_verifier:
            return secret.reveal()[:8] == "fakesecr"
        if self.verify_result is not None:
            return self.verify_result
        if self.installed.get(target) != secret.reveal().encode():
            return False
        for cid, sec in self.secrets.items():
            if sec == secret:
                return self.creds[cid].state == "active" and self.creds[cid].target == target
        return False

    def revoke(self, cred_id: str, by: str) -> None:
        self.calls.append(("revoke", cred_id))
        if self.revoke_errors > 0:
            self.revoke_errors -= 1
            raise RuntimeError("provider rejected token fo1_" + "Z" * 30)
        if self.revoke_noop:
            return
        c = self.creds[cred_id]
        if c.state == "revoked":
            return
        self.creds[cred_id] = replace(c, state="revoked", revoked_by=by)
