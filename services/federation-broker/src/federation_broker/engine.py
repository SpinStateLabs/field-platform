"""Federation crossing decisions.

A crossing is one governed request across the org boundary. The broker
DECIDES it; it does not carry the traffic (a crossing-decision service,
not a gateway).

INBOUND (the default) — a counterparty org's agent asks into our org. The
broker trusts nothing about the counterparty except what it can check:

1. the counterparty presents its FIELD manifest — it must be VALID;
2. that manifest must declare federation with us: ``isolated: false`` and
   our org listed in ``allowed_peers``;
3. we must hold a federation contract for that org (signed out-of-band by
   the GC — a registered record here);
4. when that contract holds the counterparty's Ed25519 public key, the
   presented manifest must carry a valid signature under it;
5. the requested scope and data class must be inside the contract.

OUTBOUND — one of OUR agents asks to cross into a counterparty org. The
mirror: OUR manifest VALID → OUR ``isolated: false`` → the counterparty in
OUR ``allowed_peers`` → the same contract, looked up by counterparty org
(one GC instrument covers both directions) → scope and data class inside
it. The signature step is SKIPPED outbound: the contract key is the
counterparty's, so it cannot verify our own manifest.

First failing clause decides; every crossing (either way) is a ledger
event carrying its direction. Deterministic — no LLM.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from field_core import operator_auth
from field_core.conformance import ConformanceVerdict, Decision
from field_core.validation import validate_manifest_data

HOME_ORG_ENV = "FIELD_ORG_NAME"
DEFAULT_HOME_ORG = "Spin State Labs"


def home_org() -> str:
    return os.environ.get(HOME_ORG_ENV, DEFAULT_HOME_ORG)


#: Validation-context key set ONLY by ``ContractStore`` when it rebuilds a
#: contract from its own rows. A row written before the key validator existed
#: may hold an unusable key; it must still LIST (so the operator can see and
#: re-register it), and ``BrokerEngine`` fails its inbound crossings closed.
#: No API path passes a validation context, so request bodies never skip it.
STORED_ROW = "federation_broker.stored_row"

#: PEM armor label of every private-key encoding (PKCS#8, ENCRYPTED, RSA,
#: EC, OPENSSH). Key text carrying it is refused on write and withheld when
#: listing a legacy stored row.
PRIVATE_KEY_MARKER = "PRIVATE KEY"

#: What ``GET /contracts`` shows in place of a legacy stored key that held
#: private-key material. Deliberately not a PEM: ``BrokerEngine`` still finds
#: it unusable and fails that contract's inbound crossings closed.
WITHHELD_KEY = ("<withheld: this stored contract key held private-key material; "
                "re-register the counterparty's public key only>")


def _ed25519_public_pem(pem: object) -> tuple[str | None, str | None]:
    """``(canonical_pem, None)`` when ``pem`` is EXACTLY one Ed25519 public
    key PEM; ``(None, why_not)`` otherwise. The reason never quotes ``pem``."""
    from cryptography.hazmat.primitives import serialization

    from field_core.signing import key_fingerprint

    if not isinstance(pem, str) or not pem.strip():
        return None, ("counterparty public key is empty — omit it (null) for a "
                      "keyless contract")
    if PRIVATE_KEY_MARKER in pem:
        return None, ("counterparty public key text contains private-key "
                      "material — register only the public key")
    try:
        key_fingerprint(pem)  # the loader verify_manifest uses; Ed25519 only
        public = serialization.load_pem_public_key(pem.encode("ascii"))
    except Exception as exc:  # ValueError, UnsupportedAlgorithm, UnicodeError
        return None, ("counterparty public key is not an Ed25519 public key PEM "
                      f"({type(exc).__name__})")
    canonical = public.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")
    # The loader reads only the FIRST PEM block and ignores the rest, so the
    # whole text must BE that key: only whitespace (CRLF, indent, wrapping)
    # may differ from its canonical form. Anything else riding along would
    # be stored and served back by GET /contracts.
    if "".join(pem.split()) != "".join(canonical.split()):
        return None, ("counterparty public key must be exactly one Ed25519 "
                      "public key PEM block, with no other text before or "
                      "after it")
    return canonical, None


def ed25519_public_pem_error(pem: object) -> str | None:
    """``None`` when ``pem`` is exactly one Ed25519 public key in PEM form;
    else why not (never quoting ``pem``).

    Reuses ``field_core.signing.key_fingerprint`` — the same loader the
    crossing-time ``verify_manifest`` uses — so a key accepted here is a key
    the signature step can load. Garbage, a private key, a truncated block,
    an RSA / X25519 key, non-ASCII text, and a valid public block with
    anything else before or after it (a private key appended, a second key,
    a note) are all refused.
    """
    return _ed25519_public_pem(pem)[1]


def canonical_ed25519_public_pem(pem: object) -> str:
    """The canonical SubjectPublicKeyInfo PEM of ``pem``; ``ValueError`` (with
    the reason from ``ed25519_public_pem_error``) unless it is exactly one
    Ed25519 public key PEM."""
    canonical, error = _ed25519_public_pem(pem)
    if error:
        raise ValueError(error)
    return canonical


class FederationContract(BaseModel):
    # hide_input_in_errors: a ValidationError's text must not quote an input
    # that may be a pasted private key (the API's 422 drops ``input`` too).
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    contract_id: str = Field(min_length=1)
    counterparty_org: str = Field(min_length=1)
    allowed_scopes: list[str] = Field(min_length=1)
    allowed_data_classes: list[str] = Field(min_length=1)
    contract_ref: str | None = Field(
        default=None, description="Where the signed instrument lives (GC's record)"
    )
    counterparty_pubkey_pem: str | None = Field(
        default=None,
        description="Counterparty org's Ed25519 public key (PEM). When set, "
        "every INBOUND crossing must present a valid manifest signature. "
        "Validated on write as exactly one Ed25519 public key PEM (422 "
        "otherwise) and stored in canonical form.",
    )
    active: bool = True

    @field_validator("counterparty_org")
    @classmethod
    def _org_name_is_clean(cls, value: str, info: ValidationInfo) -> str:
        if info.context and info.context.get(STORED_ROW):
            return value  # a row stored before this rule lists as stored (never breaks GET /contracts)
        return validate_org_name(value)

    @field_validator("counterparty_pubkey_pem")
    @classmethod
    def _pubkey_is_ed25519(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        if info.context and info.context.get(STORED_ROW):
            # Listed as stored (decide() refuses an unusable key) — except
            # private-key material, which is never served back to a lister.
            return WITHHELD_KEY if PRIVATE_KEY_MARKER in value else value
        return canonical_ed25519_public_pem(value)


Direction = Literal["inbound", "outbound"]

#: Which request fields name which side, per direction. ``counterparty_*``
#: are the inbound names (the other org's agent and the manifest it
#: presents); ``agent_id`` / ``manifest`` are the outbound names (OUR agent
#: and OUR manifest). A field belonging to the other direction is refused.
REQUIRED_NAMES: dict[str, tuple[str, ...]] = {
    "inbound": ("counterparty_agent_id", "counterparty_manifest"),
    "outbound": ("agent_id", "manifest"),
}
REFUSED_NAMES: dict[str, tuple[str, ...]] = {
    "inbound": ("agent_id", "manifest"),
    "outbound": ("counterparty_manifest", "manifest_signature"),
}


class CrossingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: Direction = Field(
        default="inbound",
        description="'inbound': a counterparty's agent asks into our org "
        "(counterparty_agent_id + counterparty_manifest). 'outbound': OUR "
        "agent asks to cross into the counterparty org (agent_id + manifest).",
    )
    counterparty_org: str = Field(min_length=1)
    counterparty_agent_id: str | None = Field(
        default=None, min_length=1,
        description="Inbound: required — the counterparty's agent. Outbound: "
        "optional — the peer agent being called (recorded, not checked).",
    )
    counterparty_manifest: dict[str, Any] | None = Field(
        default=None, description="Inbound only: the manifest the counterparty presents."
    )
    agent_id: str | None = Field(
        default=None, min_length=1, description="Outbound only: OUR agent's id."
    )
    manifest: dict[str, Any] | None = Field(
        default=None, description="Outbound only: OUR agent's manifest."
    )
    manifest_signature: str | None = Field(
        default=None,
        description="Inbound only. Base64 Ed25519 signature over the canonical "
        "manifest bytes. Required when our contract holds the counterparty's "
        "key. Refused outbound — the signature step does not run there.",
    )
    scope: str = Field(min_length=1, description="The action being requested")
    data_class: str = Field(min_length=1, description="e.g. 'invoice metadata'")
    request_summary: str | None = None

    @model_validator(mode="after")
    def _names_match_direction(self) -> "CrossingRequest":
        missing = [n for n in REQUIRED_NAMES[self.direction] if getattr(self, n) is None]
        if missing:
            raise ValueError(
                f"an {self.direction} crossing requires {', '.join(missing)}"
            )
        refused = [n for n in REFUSED_NAMES[self.direction] if getattr(self, n) is not None]
        if refused:
            raise ValueError(
                f"{', '.join(refused)} not accepted on an {self.direction} crossing "
                f"(inbound names: {', '.join(REQUIRED_NAMES['inbound'])}, "
                "manifest_signature; outbound names: "
                f"{', '.join(REQUIRED_NAMES['outbound'])})"
            )
        return self


log = logging.getLogger(__name__)


#: Invisible characters outside Unicode category Cf that still render as nothing or a blank inside a name (reviewer
#: C-578 F-C578-1, C-583): an explicit, documented list, NOT a whole category (category Mn also holds the vowel signs
#: and tone marks of Hindi, Thai and other scripts, which are part of a name and are kept). Inclusive ranges.
#: This is a CHOSEN SUBSET of Unicode's Default_Ignorable_Code_Point set, not all of it: the reserved, unassigned
#: default-ignorable code points (U+2065, U+FFF0-FFF8, most of U+E0000-E0FFF) and U+16FE4 (Khitan small script filler)
#: are left out on purpose (not typeable in real text; reviewer C-684 F-C684-2).
_INVISIBLE_NOT_CF = (
    (0x034F, 0x034F),      # COMBINING GRAPHEME JOINER (Mn)
    (0x180B, 0x180D),      # MONGOLIAN FREE VARIATION SELECTOR 1..3 (Mn; U+180E is Cf)
    (0x180F, 0x180F),      # MONGOLIAN FREE VARIATION SELECTOR 4 (Mn)
    (0xFE00, 0xFE0F),      # VARIATION SELECTOR-1..16 (Mn)
    (0xE0100, 0xE01EF),    # VARIATION SELECTOR-17..256 (Mn)
    (0x115F, 0x1160),      # HANGUL CHOSEONG / JUNGSEONG FILLER (Lo); U+3164 and U+FFA0 become U+1160 under NFKC
    (0x17B4, 0x17B5),      # KHMER VOWEL INHERENT AQ / AA (Mn)
    (0x2800, 0x2800),      # BRAILLE PATTERN BLANK (So)
)


def _invisible(c: str) -> bool:
    cp = ord(c)
    return unicodedata.category(c) == "Cf" or any(lo <= cp <= hi for lo, hi in _INVISIBLE_NOT_CF)


def normalize_org(org: str) -> str:
    """The one spelling an org name is compared by (C-483, reviewer PR 300 F-PR300-1): Unicode NFKC, case-folded,
    surrounding whitespace dropped and inner runs of whitespace collapsed, so 'Acme  Corp', 'ACME CORP' and
    ' acme corp ' are one org. Used by ``ContractStore.save``, ``ContractStore.for_org`` and ``_lists_org``.
    Invisible characters are dropped, so a name that differs only by one is the same org: every Unicode FORMAT
    character (category Cf: zero-width space, soft hyphen, left-to-right mark, byte-order mark, Mongolian vowel
    separator, the joiners; reviewer C-565 F-C565-5, a decision flagged for Don) and the listed invisibles outside
    Cf (``_INVISIBLE_NOT_CF``: combining grapheme joiner, variation selectors, Hangul fillers, Khmer inherent
    vowels, Braille blank; reviewer C-578 F-C578-1). KEPT as part of the name: visible marks (enclosing circle,
    the vowel signs and tone marks of Hindi or Thai names), punctuation, and confusable letters (Cyrillic or Greek
    look-alikes). A name that is only whitespace normalises to the empty string."""
    visible = "".join(c for c in unicodedata.normalize("NFKC", org) if not _invisible(c))
    return " ".join(unicodedata.normalize("NFKC", visible.casefold()).split())


#: The longest org name a contract write accepts (C-553, reviewer C-521 F-C521-4). A name is echoed into verdict
#: reasons, ledger payloads and the console, so it is bounded; legacy rows longer than this still load (STORED_ROW).
ORG_NAME_MAX = 128


def validate_org_name(org: object) -> str:
    """C-553 (reviewer C-521 F-C521-4): the org name a contract WRITE accepts, checked with the same normaliser the
    store compares by. Returns the name with surrounding whitespace stripped; raises ``ValueError`` with fixed text
    (never the name) for: a name that is empty or only whitespace or only invisible characters (``normalize_org``
    leaves nothing), one longer than ``ORG_NAME_MAX`` characters, and one holding a control character (category Cc:
    newline, tab, NUL) or an invisible character (``_invisible``: zero-width space and the other format characters
    and listed invisibles). Visible punctuation, marks and non-Latin letters pass."""
    if not isinstance(org, str):
        raise ValueError("org name must be a string")
    name = org.strip()
    if not normalize_org(name):
        raise ValueError("org name is empty (only whitespace or invisible characters)")
    if len(name) > ORG_NAME_MAX:
        raise ValueError(f"org name is longer than {ORG_NAME_MAX} characters")
    for c in name:
        if unicodedata.category(c) == "Cc":
            raise ValueError("org name holds a control character")
        if _invisible(c):
            raise ValueError("org name holds an invisible or zero-width character")
    return name


_ONE_ACTIVE_INDEX = "contracts_one_active_per_org"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
    contract_id TEXT PRIMARY KEY,
    counterparty_org TEXT NOT NULL,
    allowed_scopes TEXT NOT NULL,
    allowed_data_classes TEXT NOT NULL,
    contract_ref TEXT,
    pubkey TEXT,
    active INTEGER NOT NULL DEFAULT 1
);
"""


def _contract_from_row(row: sqlite3.Row) -> FederationContract:
    """Rebuild a contract from an already-fetched row (no connection use).

    Validated with the ``STORED_ROW`` context: every field check still runs
    except the key-format check, so a row stored before that check existed
    lists instead of breaking ``GET /contracts`` — and its crossings are
    refused by ``BrokerEngine`` (fail closed), never waved through keyless.
    """
    import json

    return FederationContract.model_validate(
        {
            "contract_id": row["contract_id"],
            "counterparty_org": row["counterparty_org"],
            "allowed_scopes": json.loads(row["allowed_scopes"]),
            "allowed_data_classes": json.loads(row["allowed_data_classes"]),
            "contract_ref": row["contract_ref"],
            "counterparty_pubkey_pem": row["pubkey"],
            "active": bool(row["active"]),
        },
        context={STORED_ROW: True},
    )


class ContractConflict(ValueError):
    """A second ACTIVE contract for a counterparty org that already has one (C-461): the API answers 409.
    ``other_id`` is the contract that already holds the org (None when another writer won the race)."""

    def __init__(self, message: str, other_id: str | None = None):
        super().__init__(message)
        self.other_id = other_id


@dataclass(frozen=True)
class ContractWrite:
    """What one ``ContractStore.write`` did (C-553): the stored contract and the row it replaced, read inside the
    same transaction. ``before`` is None for a new contract id, else ``{"org", "active", "pubkey"}``."""

    contract: FederationContract
    before: dict[str, Any] | None


class ContractStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # ONE connection shared by every request thread
        # (check_same_thread=False), so ``_lock`` guards EVERY use of it —
        # reads included, execute through fetch. Unlocked concurrent reads
        # returned "no active contract" for contracted orgs and another
        # org's contract (tests/test_contract_store_concurrency.py). Rows
        # are fetched (materialised) inside the lock and converted after
        # release.
        # Plain Lock, not RLock: no method calls another while holding it.
        # The only unlocked mention of ``_conn`` is the binding below;
        # tests/test_contract_store_lock_coverage.py checks that structurally.
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        with self._lock, self._conn:
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
            try:  # upgrade pre-signing databases in place
                self._conn.execute("ALTER TABLE contracts ADD COLUMN pubkey TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
            self._migrate_org_key()

    def _migrate_org_key(self) -> None:
        """C-483 (reviewer PR 300 F-PR300-2/-3). Called from ``__init__`` while the lock is held. Adds the
        normalised-org column, fills it for older rows, and creates the partial unique index (one ACTIVE contract per
        normalised org) so two processes cannot both win. A database that already holds two active rows for one org
        is NOT refused: the index is skipped, a warning names the ids, and ``save`` still refuses a new duplicate."""
        try:
            self._conn.execute("ALTER TABLE contracts ADD COLUMN org_key TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        for row in self._conn.execute("SELECT contract_id, counterparty_org FROM contracts WHERE org_key IS NULL").fetchall():
            self._conn.execute("UPDATE contracts SET org_key=? WHERE contract_id=?",
                               (normalize_org(row["counterparty_org"]), row["contract_id"]))
        dupes = self._conn.execute(
            "SELECT org_key, group_concat(contract_id) AS ids FROM contracts WHERE active=1 "
            "GROUP BY org_key HAVING count(*) > 1").fetchall()
        if dupes:
            for d in dupes:
                log.warning("federation-broker: more than one active contract for the org %r (%s); for_org resolves "
                            "to the lowest contract id and the one-active-per-org index is NOT created; deactivate "
                            "the extra contracts", d["org_key"], d["ids"])
            return
        self._conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {_ONE_ACTIVE_INDEX} ON contracts(org_key) WHERE active=1")

    def save(self, contract: FederationContract) -> FederationContract:
        return self.write(contract).contract

    def write(self, contract: FederationContract) -> ContractWrite:
        """``save`` that also reports the row it replaced (C-553), read in the SAME write transaction so the
        'before' the ledger records is the one this write actually changed."""
        import json

        key = normalize_org(contract.counterparty_org)
        with self._lock:
            try:
                # BEGIN IMMEDIATE: the check and the insert are one write transaction, so a second process cannot
                # slip a row in between them (C-483, F-PR300-2); the partial unique index is the backstop.
                self._conn.execute("BEGIN IMMEDIATE")
                prior = self._conn.execute(
                    "SELECT counterparty_org, active, pubkey FROM contracts WHERE contract_id=?",
                    (contract.contract_id,)).fetchone()
                before = (None if prior is None else
                          {"org": prior["counterparty_org"], "active": bool(prior["active"]), "pubkey": prior["pubkey"]})
                if contract.active:
                    # C-461 (reviewer C-355 F-C355-2): one active contract per counterparty org, as the README says.
                    # Re-registering the SAME id replaces it; deactivating the old contract first (active: false) is
                    # how an org's contract is changed to a new id. The org is compared by `normalize_org` (C-483).
                    others = self._conn.execute(
                        "SELECT contract_id, counterparty_org FROM contracts WHERE active=1 AND contract_id<>? "
                        "ORDER BY contract_id", (contract.contract_id,)).fetchall()
                    other = next((o for o in others if normalize_org(o["counterparty_org"]) == key), None)
                    if other is not None:
                        raise ContractConflict(
                            f"counterparty org {contract.counterparty_org!r} already has the active contract "
                            f"{other['contract_id']!r}: one active contract per org (deactivate it, or re-register "
                            f"the same contract id)", other_id=other["contract_id"])
                # An upsert on contract_id, NOT `INSERT OR REPLACE`: REPLACE resolves a violation of the one-active
                # index by silently DELETING the other org's active row; here the violation raises instead.
                self._conn.execute(
                    "INSERT INTO contracts "
                    "(contract_id, counterparty_org, allowed_scopes, "
                    "allowed_data_classes, contract_ref, pubkey, active, org_key) "
                    "VALUES (?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(contract_id) DO UPDATE SET counterparty_org=excluded.counterparty_org, "
                    "allowed_scopes=excluded.allowed_scopes, allowed_data_classes=excluded.allowed_data_classes, "
                    "contract_ref=excluded.contract_ref, pubkey=excluded.pubkey, active=excluded.active, "
                    "org_key=excluded.org_key",
                    (
                        contract.contract_id,
                        contract.counterparty_org,
                        json.dumps(contract.allowed_scopes),
                        json.dumps(contract.allowed_data_classes),
                        contract.contract_ref,
                        contract.counterparty_pubkey_pem,
                        int(contract.active),
                        key,
                    ),
                )
                self._conn.commit()
                return ContractWrite(contract=contract, before=before)
            except sqlite3.IntegrityError:
                self._conn.rollback()
                raise ContractConflict(
                    f"counterparty org {contract.counterparty_org!r} already has an active contract: one active "
                    f"contract per org (another writer registered one first)") from None
            except BaseException:
                self._conn.rollback()
                raise

    def for_org(self, org: str) -> FederationContract | None:
        key = normalize_org(org)
        if not key:     # a whitespace-only name names no org
            return None
        with self._lock:
            # ORDER BY: a database that already holds two active rows for an org (written before the one-active
            # rule) resolves to the same row every time, the lowest contract_id, compared as text (C-461). The org
            # is compared by `normalize_org` (C-483); the table is a handful of rows, so it is filtered here.
            rows = self._conn.execute(
                "SELECT * FROM contracts WHERE active=1 ORDER BY contract_id").fetchall()
        hits = [r for r in rows if normalize_org(r["counterparty_org"]) == key]
        if not hits:
            return None
        if len(hits) > 1:
            log.warning("federation-broker: %d active contracts for the org %r (%s); using the lowest contract id %r",
                        len(hits), key, ", ".join(h["contract_id"] for h in hits), hits[0]["contract_id"])
        return _contract_from_row(hits[0])

    def list(self) -> list[FederationContract]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM contracts ORDER BY contract_id"
            ).fetchall()
        return [_contract_from_row(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _lists_org(peers: object, org: str) -> bool:
    """The lenient peer rule, shared by both directions: ``org`` appears
    (case-insensitive substring) in some ``allowed_peers[].org``."""
    if not isinstance(peers, list):
        return False
    needle = normalize_org(org)
    if not needle:      # a whitespace-only name would otherwise be a substring of every peer's org
        return False
    return any(
        needle in normalize_org(str(p.get("org", ""))) for p in peers if isinstance(p, dict)
    )


def _key_fingerprint(pem: object) -> str | None:
    """First 12 hex digits of the SHA-256 of a stored contract PUBLIC key (C-553), or None when there is no key or the
    stored text is private-key material (never fingerprinted, never shown)."""
    if not isinstance(pem, str) or not pem.strip() or PRIVATE_KEY_MARKER in pem or pem == WITHHELD_KEY:
        return None
    return hashlib.sha256(pem.encode("utf-8")).hexdigest()[:12]


class BrokerEngine:
    def __init__(self, store: ContractStore, ledger=None):
        self.store = store
        self.ledger = ledger  # LedgerClient-compatible or None

    def record_contract_write(self, result: ContractWrite) -> str:
        """Ledger one successful contract write (C-553, reviewer C-521 F-C521-3) and return its kind:
        ``registered`` (a new contract id), ``deactivated`` (an active contract written inactive) or ``replaced``
        (any other write under an existing id: a changed org, key or scope, a reactivation, or the same text again).
        Best effort, as every other broker ledger write: a ledger failure never undoes or refuses the write and the
        audit gap is logged (type name only)."""
        c, before = result.contract, result.before
        if before is None:
            kind = "registered"
        elif before["active"] and not c.active:
            kind = "deactivated"
        else:
            kind = "replaced"
        payload: dict[str, Any] = {
            "contract_id": c.contract_id,
            "counterparty_org": c.counterparty_org,
            "active_after": c.active,
            "key_present_after": bool(c.counterparty_pubkey_pem),
            "key_fp_after": _key_fingerprint(c.counterparty_pubkey_pem),
        }
        if before is not None:
            payload.update(
                org_before=normalize_org(before["org"])[:ORG_NAME_MAX],
                active_before=before["active"],
                key_present_before=bool(before["pubkey"]),
                key_fp_before=_key_fingerprint(before["pubkey"]),
                key_changed=(before["pubkey"] or None) != (c.counterparty_pubkey_pem or None),
            )
        self._contract_event(kind, payload)
        return kind

    def record_contract_refusal(self, contract: FederationContract, conflict: ContractConflict) -> None:
        """Ledger a contract write the store REFUSED (a second active contract for the org, C-461), with the id that
        already holds the org (None when another writer won the race)."""
        self._contract_event("refused", {
            "contract_id": contract.contract_id,
            "counterparty_org": contract.counterparty_org,
            "active_after": contract.active,
            "key_present_after": bool(contract.counterparty_pubkey_pem),
            "key_fp_after": _key_fingerprint(contract.counterparty_pubkey_pem),
            "reason": "one_active_contract_per_org",
            "other_contract_id": conflict.other_id,
        })

    def _contract_event(self, kind: str, payload: dict[str, Any]) -> None:
        if self.ledger is None:
            return
        try:
            self.ledger.append(f"federation.contract.{kind}", payload=operator_auth.merge_payload(payload),
                               agent_id=None)
        except Exception as exc:
            log.warning("federation-broker: the federation.contract.%s ledger record was not written (%s); the "
                        "contract write stands", kind, type(exc).__name__)

    def _verdict(
        self,
        req: CrossingRequest,
        decision: Decision,
        clause_id: str | None,
        reasons: list[str],
    ) -> ConformanceVerdict:
        outbound = req.direction == "outbound"
        context: dict[str, Any] = {
            "data_class": req.data_class,
            "direction": req.direction,
            "home_org": home_org(),
            "counterparty_org": req.counterparty_org,
        }
        if outbound and req.counterparty_agent_id:
            context["counterparty_agent_id"] = req.counterparty_agent_id
        verdict = ConformanceVerdict(
            decision=decision,
            # Inbound names the counterparty's agent; outbound names OURS.
            agent_id=(f"{home_org()}/{req.agent_id}" if outbound
                      else f"{req.counterparty_org}/{req.counterparty_agent_id}"),
            action=req.scope,
            clause_id=clause_id,
            reasons=reasons,
            checked_at=datetime.now(timezone.utc),
            context=context,
        )
        if self.ledger is not None:
            try:
                self.ledger.append(
                    f"federation.{decision.value.lower()}",
                    payload={
                        "direction": req.direction,
                        "counterparty_org": req.counterparty_org,
                        "scope": req.scope,
                        "data_class": req.data_class,
                        "clause_id": clause_id,
                        "reasons": reasons,
                    },
                    agent_id=verdict.agent_id,
                )
            except Exception:
                pass  # crossing verdicts stand; the audit gap is visible
        return verdict

    def decide(self, req: CrossingRequest) -> ConformanceVerdict:
        if req.direction == "outbound":
            return self._decide_outbound(req)
        return self._decide_inbound(req)

    def _outside_contract(
        self, req: CrossingRequest, contract: FederationContract
    ) -> ConformanceVerdict | None:
        """Scope and data class must be inside the contract (both directions)."""
        if req.scope not in contract.allowed_scopes:
            return self._verdict(
                req, Decision.BLOCK, "F.peer",
                [f"scope '{req.scope}' not in contract {contract.contract_id} "
                 f"allowed_scopes {contract.allowed_scopes}"],
            )
        if req.data_class not in contract.allowed_data_classes:
            return self._verdict(
                req, Decision.BLOCK, "F.peer",
                [f"data class '{req.data_class}' not in contract "
                 f"{contract.contract_id} allowed_data_classes "
                 f"{contract.allowed_data_classes}"],
            )
        return None

    def _decide_inbound(self, req: CrossingRequest) -> ConformanceVerdict:
        # 1. Counterparty manifest must be VALID.
        validation = validate_manifest_data(req.counterparty_manifest)
        if not validation.ok:
            return self._verdict(
                req, Decision.BLOCK, "I.manifest",
                [f"counterparty manifest INVALID: {validation.critical_gaps[:2]}"],
            )

        # 2. It must declare federation with us.
        federated = req.counterparty_manifest.get("federated") or {}
        if federated.get("isolated") is not False:
            return self._verdict(
                req, Decision.BLOCK, "F.isolated",
                ["counterparty manifest declares isolated: true — it does not "
                 "federate with anyone"],
            )
        if not _lists_org(federated.get("allowed_peers") or [], home_org()):
            return self._verdict(
                req, Decision.BLOCK, "F.peer",
                [f"counterparty manifest does not list {home_org()} as an "
                 "allowed peer"],
            )

        # 3. We must hold an active contract for that org.
        contract = self.store.for_org(req.counterparty_org)
        if contract is None:
            return self._verdict(
                req, Decision.BLOCK, "F.peer",
                [f"no active federation contract with '{req.counterparty_org}'"],
            )

        # 4. Signature. An INBOUND crossing needs a contract key (Don D-19, C-175): without one the presented
        #    manifest is whatever the caller says, so a keyless contract is valid only OUTBOUND. With the key,
        #    the presented manifest must be the one the counterparty actually signed.
        if contract.counterparty_pubkey_pem is None:
            return self._verdict(
                req, Decision.BLOCK, "F.peer",
                [f"contract {contract.contract_id} holds no counterparty key: inbound crossings "
                 "require a contract key (re-register it: fedbroker add-contract --pubkey)"],
            )
        if contract.counterparty_pubkey_pem is not None:
            from field_core.signing import verify_manifest

            key_error = ed25519_public_pem_error(contract.counterparty_pubkey_pem)
            if key_error:  # a row stored before write-time key validation
                return self._verdict(
                    req, Decision.BLOCK, "F.peer",
                    [f"contract {contract.contract_id} holds an unusable key: "
                     f"{key_error} — re-register it (fedbroker add-contract "
                     "--pubkey)"],
                )
            if not req.manifest_signature:
                return self._verdict(
                    req, Decision.BLOCK, "F.peer",
                    [f"contract {contract.contract_id} requires a signed "
                     "manifest but no signature was presented"],
                )
            if not verify_manifest(
                req.counterparty_manifest,
                req.manifest_signature,
                contract.counterparty_pubkey_pem,
            ):
                return self._verdict(
                    req, Decision.BLOCK, "F.peer",
                    ["manifest signature invalid — the presented manifest is "
                     "not the one the counterparty signed"],
                )

        # 5. Scope and data class must be inside the contract.
        blocked = self._outside_contract(req, contract)
        if blocked is not None:
            return blocked

        return self._verdict(
            req, Decision.ALLOW, None,
            [f"crossing within contract {contract.contract_id}"],
        )

    def _decide_outbound(self, req: CrossingRequest) -> ConformanceVerdict:
        ours = req.manifest
        # 1. OUR manifest must be VALID — before any of it is believed.
        validation = validate_manifest_data(ours)
        if not validation.ok:
            return self._verdict(
                req, Decision.BLOCK, "I.manifest",
                [f"our manifest INVALID: {validation.critical_gaps[:2]}"],
            )

        # 2. OUR manifest must federate at all.
        federated = ours.get("federated")
        if not isinstance(federated, dict) or federated.get("isolated") is not False:
            return self._verdict(
                req, Decision.BLOCK, "F.isolated",
                [f"our manifest for '{req.agent_id}' does not declare "
                 "isolated: false — it does not federate with anyone"],
            )

        # 3. The counterparty must be one of OUR allowed peers.
        if not _lists_org(federated.get("allowed_peers") or [], req.counterparty_org):
            return self._verdict(
                req, Decision.BLOCK, "F.peer",
                [f"our manifest for '{req.agent_id}' does not list "
                 f"'{req.counterparty_org}' as an allowed peer"],
            )

        # 4. The same contract, by counterparty org: one GC instrument covers
        #    both directions.
        contract = self.store.for_org(req.counterparty_org)
        if contract is None:
            return self._verdict(
                req, Decision.BLOCK, "F.peer",
                [f"no active federation contract with '{req.counterparty_org}'"],
            )

        # (The signature step is SKIPPED outbound: the contract key is the
        #  counterparty's and cannot verify our own manifest.)

        # 5. Scope and data class must be inside the contract.
        blocked = self._outside_contract(req, contract)
        if blocked is not None:
            return blocked

        reasons = [f"outbound crossing within contract {contract.contract_id}"]
        if contract.counterparty_pubkey_pem is not None:
            reasons.append(
                "signature step skipped outbound: the contract key is the "
                "counterparty's and cannot verify our own manifest"
            )
        return self._verdict(req, Decision.ALLOW, None, reasons)
