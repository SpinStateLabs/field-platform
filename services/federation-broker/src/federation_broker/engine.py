"""Federation crossing decisions.

A crossing is one governed request from a counterparty org's agent into our
org. The broker trusts nothing about the counterparty except what it can
check:

1. the counterparty presents its FIELD manifest — it must be VALID;
2. that manifest must declare federation with us: ``isolated: false`` and
   our org listed in ``allowed_peers``;
3. we must hold a federation contract for that org (signed out-of-band by
   the GC — a registered record here);
4. the requested scope and data class must be inside the contract.

First failing clause decides; every crossing (either way) is a ledger
event. Deterministic — no LLM.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from field_core.conformance import ConformanceVerdict, Decision
from field_core.validation import validate_manifest_data

HOME_ORG_ENV = "FIELD_ORG_NAME"
DEFAULT_HOME_ORG = "Spin State Labs"


def home_org() -> str:
    return os.environ.get(HOME_ORG_ENV, DEFAULT_HOME_ORG)


class FederationContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
        "every crossing must present a valid manifest signature.",
    )
    active: bool = True


class CrossingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counterparty_org: str = Field(min_length=1)
    counterparty_agent_id: str = Field(min_length=1)
    counterparty_manifest: dict[str, Any]
    manifest_signature: str | None = Field(
        default=None,
        description="Base64 Ed25519 signature over the canonical manifest "
        "bytes. Required when our contract holds the counterparty's key.",
    )
    scope: str = Field(min_length=1, description="The action being requested")
    data_class: str = Field(min_length=1, description="e.g. 'invoice metadata'")
    request_summary: str | None = None


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
        import json

        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM contracts WHERE counterparty_org=? AND active=1",
                (org,),
            ).fetchone()
        if row is None:
            return None
        return FederationContract(
            contract_id=row["contract_id"],
            counterparty_org=row["counterparty_org"],
            allowed_scopes=json.loads(row["allowed_scopes"]),
            allowed_data_classes=json.loads(row["allowed_data_classes"]),
            contract_ref=row["contract_ref"],
            counterparty_pubkey_pem=row["pubkey"],
            active=bool(row["active"]),
        )

    def list(self) -> list[FederationContract]:
        import json

        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM contracts ORDER BY contract_id"
            ).fetchall()
        return [
            FederationContract(
                contract_id=r["contract_id"],
                counterparty_org=r["counterparty_org"],
                allowed_scopes=json.loads(r["allowed_scopes"]),
                allowed_data_classes=json.loads(r["allowed_data_classes"]),
                contract_ref=r["contract_ref"],
                counterparty_pubkey_pem=r["pubkey"],
                active=bool(r["active"]),
            )
            for r in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


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
        verdict = ConformanceVerdict(
            decision=decision,
            agent_id=f"{req.counterparty_org}/{req.counterparty_agent_id}",
            action=req.scope,
            clause_id=clause_id,
            reasons=reasons,
            checked_at=datetime.now(timezone.utc),
            context={"data_class": req.data_class, "direction": "inbound",
                     "home_org": home_org()},
        )
        if self.ledger is not None:
            try:
                self.ledger.append(
                    f"federation.{decision.value.lower()}",
                    payload={
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
        peers = federated.get("allowed_peers") or []
        us = home_org().lower()
        if not any(us in str(p.get("org", "")).lower() for p in peers):
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
        if contract.counterparty_pubkey_pem:
            from field_core.signing import verify_manifest

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

        return self._verdict(
            req, Decision.ALLOW, None,
            [f"crossing within contract {contract.contract_id}"],
        )
