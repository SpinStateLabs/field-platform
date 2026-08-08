"""Ed25519 manifest signing — authenticity for federation crossings.

A counterparty signs the canonical bytes of its manifest with its org
private key; the broker verifies against the public key registered on the
federation contract. Canonicalization = compact sorted-key UTF-8 JSON, so
signature validity is independent of YAML formatting.

Requires the ``cryptography`` package (a field-core dependency).
Key distribution stays out-of-band: the GC receives the counterparty's
public key with the signed contract instrument.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


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
