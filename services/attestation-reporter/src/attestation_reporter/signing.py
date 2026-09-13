"""Board-pack signature (C4): ``board-pack.json`` is signable with an Ed25519
key under a named signer string (``attest render --signer --sign-key``); a pack
rendered without them is an UNSIGNED DRAFT. What a valid signature proves is
possession of the key it names, not who approved the pack (key custody).

THE BYTES. ``canonical_manifest_bytes(pack.model_dump(mode='json',
exclude={'signature'}))`` — the dump of the pack with ``signed``, ``signer``,
``signed_at`` and ``key_fingerprint`` already set and the ``signature`` KEY
ABSENT (never present as ``None``). So every section title, every metric's
name/value/unit/source_query/status/note/basis, the window, the period,
``generated_at``, the method and the signer fields are all inside the
signature.

VERIFICATION canonicalises the RAW parsed JSON (``json.loads`` of the file,
minus its ``signature`` key) — never a re-validated model, which would drop
an added key or coerce an edited value back into shape. The file is parsed
strictly (``parse_pack_json``): a duplicated key is refused, because
``json.loads`` keeps the LAST occurrence while a human or a first-wins parser
reads the first, and NaN/Infinity are refused as not JSON. The ``signature``
field must be one canonical base64 encoding of 64 bytes, and a valid signature
over an object that is not a ``BoardPack`` is refused. Only
``board-pack.json`` is the signed artefact; the HTML and PDF are renderings.

NOT DOMAIN-SEPARATED. The bytes are the same canonical JSON that
``fedbroker sign --manifest`` signs for any mapping, so a pack-shaped mapping
signed that way with the same key verifies here. Never reuse the pack-signing
key for another FIELD signing verb (README LIMITS).

Key-load failures are ``InvalidSigningKey`` — raised, never a process exit:
the CLI turns them into exit 2 before anything is written. The served pack
never signs (an unattended server cannot be the named human signer; F4).
"""

from __future__ import annotations

import base64
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from field_core.signing import (
    canonical_manifest_bytes,
    key_fingerprint,
    sign_manifest,
    verify_manifest,
)

from attestation_reporter.engine import BoardPack


class InvalidSigningKey(ValueError):
    """The signing key could not be loaded as an Ed25519 private key."""


class PackVerificationError(ValueError):
    """``attest verify`` failed: unsigned, wrong key, or altered after signing."""


def load_signing_key(path: str | Path) -> str:
    """Read an Ed25519 PEM private key. Every failure is ``InvalidSigningKey``;
    messages name the failure, never key material."""
    key_path = Path(path)
    try:
        pem = key_path.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise InvalidSigningKey(
            f"signing key {key_path} is not a readable file ({type(exc).__name__})"
        ) from exc
    signer_public_pem(pem)  # validates: raises InvalidSigningKey
    return pem


def signer_public_pem(private_key_pem: str) -> str:
    try:
        private = serialization.load_pem_private_key(private_key_pem.encode("ascii"), password=None)
    except (TypeError, ValueError, UnicodeEncodeError, UnsupportedAlgorithm) as exc:
        # UnsupportedAlgorithm is NOT a ValueError: a PKCS#8 key under an
        # algorithm OID cryptography does not know would otherwise escape
        raise InvalidSigningKey(
            f"signing key is not an unencrypted PEM private key ({type(exc).__name__})"
        ) from exc
    if not isinstance(private, Ed25519PrivateKey):
        raise InvalidSigningKey("signing key is not Ed25519")
    return private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def signed_bytes(pack: BoardPack) -> bytes:
    """THE signed bytes of a pack (see the module docstring)."""
    return canonical_manifest_bytes(pack.model_dump(mode="json", exclude={"signature"}))


def sign_pack(
    pack: BoardPack, signer: str, private_key_pem: str, now: datetime | None = None
) -> BoardPack:
    """Return a signed copy of an unsigned pack. A blank signer is refused."""
    if not isinstance(signer, str) or not signer.strip():
        raise ValueError("signer must name the human signing the pack (blank refused)")
    if pack.signed:
        raise ValueError("pack is already signed")
    public_pem = signer_public_pem(private_key_pem)
    view = pack.model_copy(update={
        "signed": True,
        "signer": signer,
        "signed_at": (now or datetime.now(timezone.utc)).isoformat(),
        "key_fingerprint": key_fingerprint(public_pem),
    })
    payload = view.model_dump(mode="json", exclude={"signature"})
    signed = view.model_copy(update={"signature": sign_manifest(payload, private_key_pem)})
    # The file a verifier reads is model_dump_json; its raw JSON must
    # canonicalise to exactly the signed bytes, or no written pack verifies.
    raw = json.loads(signed.model_dump_json())
    raw.pop("signature")
    if canonical_manifest_bytes(raw) != canonical_manifest_bytes(payload):
        raise ValueError("pack does not survive a JSON round-trip; refusing to sign")
    BoardPack.model_validate(signed.model_dump(mode="json"))  # a well-formed signed pack
    return signed


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise PackVerificationError(f"not canonical JSON: duplicate key {key!r}")
        seen[key] = value
    return seen


def _no_constant(name: str) -> Any:
    raise PackVerificationError(f"not canonical JSON: {name} is not a JSON number")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise PackVerificationError(f"not canonical JSON: {text} overflows to {value}")
    return value


def parse_pack_json(text: str) -> Any:
    """Parse ``board-pack.json`` for verification — strictly. A repeated key
    (at any depth) or NaN/Infinity is ``PackVerificationError``; text that is
    not JSON at all is ``ValueError`` (``json.JSONDecodeError``)."""
    return json.loads(text, object_pairs_hook=_no_duplicate_keys,
                      parse_constant=_no_constant, parse_float=_finite_float)


def verify_pack(raw: Any, public_key_pem: str) -> dict[str, Any]:
    """Verify the RAW parsed JSON of a pack (parse the file with
    ``parse_pack_json``). Returns the signer facts on success; raises
    ``PackVerificationError`` naming the failure."""
    if not isinstance(raw, dict):
        raise PackVerificationError("not a board pack: the JSON is not an object")
    if raw.get("signed") is not True:
        raise PackVerificationError("UNSIGNED pack (signed: false): nothing to verify")
    signature, fingerprint, signer = raw.get("signature"), raw.get("key_fingerprint"), raw.get("signer")
    if not (isinstance(signature, str) and signature and isinstance(fingerprint, str) and fingerprint):
        raise PackVerificationError("pack says signed but carries no signature or key_fingerprint")
    if not isinstance(signer, str) or not signer.strip():
        raise PackVerificationError("pack says signed but names no signer")
    try:
        supplied = key_fingerprint(public_key_pem)
    except (TypeError, ValueError, UnsupportedAlgorithm) as exc:
        raise PackVerificationError(f"supplied public key is not usable: {exc}") from exc
    if supplied != fingerprint:
        raise PackVerificationError(
            f"wrong key: supplied key fingerprint {supplied[:16]}… but the pack "
            f"was signed by key {fingerprint[:16]}…"
        )
    # The signature string is outside the signed bytes, so it gets exactly one
    # spelling: b64decode alone skips non-alphabet characters.
    try:
        decoded = base64.b64decode(signature, validate=True)
    except ValueError:
        decoded = b""
    if len(decoded) != 64 or base64.b64encode(decoded).decode("ascii") != signature:
        raise PackVerificationError("signature INVALID — not one canonical base64 Ed25519 signature")
    payload = {k: v for k, v in raw.items() if k != "signature"}
    if not verify_manifest(payload, signature, public_key_pem):
        raise PackVerificationError("signature INVALID — board-pack.json was altered after signing")
    try:
        BoardPack.model_validate(raw)
    except ValueError as exc:  # pydantic's ValidationError
        raise PackVerificationError(
            "not a board pack: the signature is valid but the signed object is not a BoardPack "
            f"({type(exc).__name__})"
        ) from exc
    return {"signer": signer, "signed_at": raw.get("signed_at"), "key_fingerprint": fingerprint}
