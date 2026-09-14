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

import os
import sqlite3
import threading
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

    def save(self, contract: FederationContract) -> FederationContract:
        import json

        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO contracts "
                "(contract_id, counterparty_org, allowed_scopes, "
                "allowed_data_classes, contract_ref, pubkey, active) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    contract.contract_id,
                    contract.counterparty_org,
                    json.dumps(contract.allowed_scopes),
                    json.dumps(contract.allowed_data_classes),
                    contract.contract_ref,
                    contract.counterparty_pubkey_pem,
                    int(contract.active),
                ),
            )
        return contract

    def for_org(self, org: str) -> FederationContract | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM contracts WHERE counterparty_org=? AND active=1",
                (org,),
            ).fetchone()
        if row is None:
            return None
        return _contract_from_row(row)

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
    needle = org.lower()
    return any(
        needle in str(p.get("org", "")).lower() for p in peers if isinstance(p, dict)
    )


class BrokerEngine:
    def __init__(self, store: ContractStore, ledger=None):
        self.store = store
        self.ledger = ledger  # LedgerClient-compatible or None

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

        # 4. Signature: when the contract holds the counterparty's key,
        #    the presented manifest must be the one they actually signed.
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
