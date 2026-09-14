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

Caller signatures (v1.2 F2b, additive): ``caller_signing_bytes`` /
``sign_caller`` / ``verify_caller_signature`` sign the canonical bytes of
exactly ``{event_type, agent_id, payload, caller_id, caller_ts}`` with a
SERVICE's own key (mounted only into it on the GB10); the ledger verifies
the claim against ``<caller_id>.pub.pem`` in its keyring before the append
and stores it in the event, under its own F2 ``signature``.
``load_ed25519_public_key`` is the public-key twin of
``load_ed25519_private_key`` (a keyring file must be an Ed25519 PUBLIC key).
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

from field_core.ledger import LedgerEvent, _canonical_bytes, event_signing_bytes


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


# ------------------------------------------------ caller signatures (F2b)

#: Exactly the keys a caller signature covers, in one place.
CALLER_SIGNED_KEYS = ("event_type", "agent_id", "payload", "caller_id", "caller_ts")


def load_ed25519_public_key(public_key_pem: str) -> Ed25519PublicKey:
    """The Ed25519 PUBLIC key in a PEM. ``ValueError`` for anything else
    (a private key, an EC/X25519 key, garbage) — the message names the
    failure class, never key material."""
    try:
        public = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"not a PEM public key ({type(exc).__name__})") from None
    except Exception as exc:  # noqa: BLE001 - cryptography's UnsupportedAlgorithm etc.
        raise ValueError(f"not a loadable public key ({type(exc).__name__})") from None
    if not isinstance(public, Ed25519PublicKey):
        raise ValueError("public key is not Ed25519")
    return public


def caller_signing_bytes(
    event_type: str, agent_id: str | None, payload: dict[str, Any], caller_id: str, caller_ts: str
) -> bytes:
    """The bytes a caller signature covers: the canonical (sorted keys,
    compact, UTF-8) JSON of exactly ``CALLER_SIGNED_KEYS``. Neither the
    ledger's ``event_id``/``ts``/``prev_hash``/``hash`` (unknown to the
    caller) nor the ledger's own ``signature`` are in it."""
    return _canonical_bytes({
        "event_type": event_type, "agent_id": agent_id, "payload": payload,
        "caller_id": caller_id, "caller_ts": caller_ts,
    })


def sign_caller(
    private_key: Ed25519PrivateKey | str, *, event_type: str, agent_id: str | None,
    payload: dict[str, Any], caller_id: str, caller_ts: str,
) -> str:
    """base64 of the raw 64-byte Ed25519 signature over ``caller_signing_bytes``.
    ``private_key`` is a loaded key (a client loads its key ONCE) or a PEM."""
    key = private_key if isinstance(private_key, Ed25519PrivateKey) else load_ed25519_private_key(private_key)
    raw = key.sign(caller_signing_bytes(event_type, agent_id, payload, caller_id, caller_ts))
    return base64.b64encode(raw).decode("ascii")


def verify_caller_signature(event: LedgerEvent | dict[str, Any], public_key_pem: str) -> bool:
    """True iff ``event.caller_signature`` is a valid Ed25519 signature, under
    this public key, over the event's caller signing bytes (its ``event_type``,
    ``agent_id``, ``payload``, ``caller_id``, ``caller_ts``). An event with no
    caller signature is False; so is any malformed signature or key."""
    record = event.model_dump() if isinstance(event, LedgerEvent) else dict(event)
    signature = record.get("caller_signature")
    caller_id, caller_ts = record.get("caller_id"), record.get("caller_ts")
    if not isinstance(signature, str) or not signature:
        return False
    if not isinstance(caller_id, str) or not isinstance(caller_ts, str):
        return False
    try:
        public = load_ed25519_public_key(public_key_pem)
        public.verify(
            base64.b64decode(signature, validate=True),
            caller_signing_bytes(record.get("event_type"), record.get("agent_id"),
                                 record.get("payload"), caller_id, caller_ts),
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
