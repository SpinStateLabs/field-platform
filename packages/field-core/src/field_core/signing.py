"""Ed25519 manifest signing — authenticity for federation crossings.

A counterparty signs the canonical bytes of its manifest with its org
private key; the broker verifies against the public key registered on the
federation contract. Canonicalization = compact sorted-key UTF-8 JSON, so
signature validity is independent of YAML formatting.

Requires the ``cryptography`` package (a field-core dependency).
Key distribution stays out-of-band: the GC receives the counterparty's
public key with the signed contract instrument.

``key_fingerprint`` names an Ed25519 public key (sha-256 over its raw 32
bytes) so a signature record can say which key signed it. A fingerprint
identifies a key; it does not make the key trusted.

Per-event ledger signatures (v1.2 F2, additive): ``sign_event`` /
``verify_event_signature`` sign the bytes ``field_core.ledger.
event_signing_bytes`` gives (the canonical record including its ``hash``),
base64 of the raw 64-byte signature — the same encoding as every other
signature here. ``private_key_fingerprint`` is ``key_fingerprint`` of the
public half of a private key, so a ledger can report which key it signs with
without ever printing key material.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from field_core.ledger import LedgerEvent, event_signing_bytes


def canonical_manifest_bytes(data: dict[str, Any]) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def generate_keypair() -> tuple[str, str]:
    """Return (private_key_pem, public_key_pem)."""
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return private_pem, public_pem


def sign_manifest(data: dict[str, Any], private_key_pem: str) -> str:
    """Sign canonical manifest bytes; returns base64 signature."""
    private = serialization.load_pem_private_key(
        private_key_pem.encode("ascii"), password=None
    )
    if not isinstance(private, Ed25519PrivateKey):
        raise ValueError("private key is not Ed25519")
    signature = private.sign(canonical_manifest_bytes(data))
    return base64.b64encode(signature).decode("ascii")


def verify_manifest(
    data: dict[str, Any], signature_b64: str, public_key_pem: str
) -> bool:
    """True iff signature matches the canonical bytes under the public key."""
    try:
        public = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
        if not isinstance(public, Ed25519PublicKey):
            return False
        public.verify(
            base64.b64decode(signature_b64), canonical_manifest_bytes(data)
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def key_fingerprint(public_key_pem: str) -> str:
    """sha-256 hex over the RAW 32-byte Ed25519 public key.

    Hashes the key itself, not its PEM text or DER wrapper, so the same key
    has the same fingerprint however it was encoded. Raises ``ValueError``
    for anything that is not an Ed25519 public key (including X25519, whose
    raw public key is also 32 bytes).
    """
    public = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
    if not isinstance(public, Ed25519PublicKey):
        raise ValueError("public key is not Ed25519")
    return hashlib.sha256(public.public_bytes_raw()).hexdigest()


# ------------------------------------------------ per-event signatures (F2)


def load_ed25519_private_key(private_key_pem: str) -> Ed25519PrivateKey:
    """The Ed25519 private key in a PEM (the format ``generate_keypair``
    writes). ``ValueError`` for anything else — a message names the failure
    class, never key material."""
    try:
        private = serialization.load_pem_private_key(
            private_key_pem.encode("ascii"), password=None
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"not a PEM private key ({type(exc).__name__})") from None
    except Exception as exc:  # noqa: BLE001 - cryptography's UnsupportedAlgorithm etc.
        raise ValueError(f"not a loadable private key ({type(exc).__name__})") from None
    if not isinstance(private, Ed25519PrivateKey):
        raise ValueError("private key is not Ed25519")
    return private


def private_key_fingerprint(private_key_pem: str) -> str:
    """``key_fingerprint`` of the PUBLIC half of an Ed25519 private key —
    the same value ``keys-admin`` prints for its ``.pub.pem``."""
    public = load_ed25519_private_key(private_key_pem).public_key()
    return hashlib.sha256(public.public_bytes_raw()).hexdigest()


def sign_event(event: LedgerEvent, private_key_pem: str) -> LedgerEvent:
    """A copy of ``event`` carrying ``signature``: base64 of the raw 64-byte
    Ed25519 signature over ``event_signing_bytes`` (the record INCLUDING its
    ``hash``). The hash is not recomputed: hash first, sign second."""
    private = load_ed25519_private_key(private_key_pem)
    raw = private.sign(event_signing_bytes(event))
    return event.model_copy(update={"signature": base64.b64encode(raw).decode("ascii")})


def verify_event_signature(event: LedgerEvent | dict[str, Any], public_key_pem: str) -> bool:
    """True iff ``event.signature`` is a valid Ed25519 signature, under this
    public key, over the event's signing bytes. An event with no signature is
    False (it is not a signed event); so is any malformed signature or key."""
    signature = event.signature if isinstance(event, LedgerEvent) else event.get("signature")
    if not isinstance(signature, str) or not signature:
        return False
    try:
        public = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
        if not isinstance(public, Ed25519PublicKey):
            return False
        public.verify(base64.b64decode(signature, validate=True), event_signing_bytes(event))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
