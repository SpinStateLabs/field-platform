"""field-core: single source of truth for FIELD Platform schemas.

Force Field Protocol — FIELD design-time governance primitives:
manifest models, manifest validation (parity with the shipped
``/field validate`` skill), ledger event + hash-chain primitives,
delegation token model, and conformance verdict model.

Every FIELD Platform service imports these models. No service
redefines schema.
"""

from field_core.conformance import CLAUSES, ConformanceVerdict, Decision
from field_core.delegation import DelegationToken, IntrospectionResult, TokenStatus
from field_core.ledger import (
    GENESIS_HASH,
    ChainVerification,
    LedgerEvent,
    compute_event_hash,
    make_event,
    verify_chain,
)
from field_core.manifest import (
    SCHEMA_VERSION,
    SEAL_ALGORITHMS,
    Agent,
    Delegation,
    Enforcement,
    Federated,
    FieldManifest,
    Identity,
    Ledger,
    RuntimeProtocol,
)
from field_core.validation import (
    ValidationResult,
    ValidationStatus,
    load_manifest,
    validate_manifest_data,
    validate_manifest_file,
)

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "CLAUSES",
    "ChainVerification",
    "ConformanceVerdict",
    "Decision",
    "Delegation",
    "DelegationToken",
    "Enforcement",
    "Federated",
    "FieldManifest",
    "GENESIS_HASH",
    "Identity",
    "IntrospectionResult",
    "Ledger",
    "LedgerEvent",
    "RuntimeProtocol",
    "SCHEMA_VERSION",
    "SEAL_ALGORITHMS",
    "TokenStatus",
    "ValidationResult",
    "ValidationStatus",
    "compute_event_hash",
    "load_manifest",
    "make_event",
    "validate_manifest_data",
    "validate_manifest_file",
    "verify_chain",
]
