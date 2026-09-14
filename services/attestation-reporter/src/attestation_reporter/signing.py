"""Board-pack signature (C4): ``board-pack.json`` is signable with an Ed25519
key under a named signer string (``attest render --signer --sign-key``); a pack
rendered without them is an UNSIGNED DRAFT. What a valid signature proves is
possession of the key it names, not who approved the pack (key custody).

F4 — served signing with the estate key. When ``FIELD_ATTEST_SIGNER`` and
``FIELD_ATTEST_SIGN_KEY`` are both set and the key loads
(``served_signing_from_env``, once at app start), ``GET /pack`` and
``/pack.html`` serve a pack signed under that name with the provenance
``signed_via: "estate-key"``; the CLI path records ``signed_via: "cli"``.
Either unset ⇒ an unsigned draft; exactly one set, or a key that does not
load ⇒ still an unsigned draft, and ``/health`` names the misconfiguration —
never a process exit, never a signature under a blank name or without a key.
An unattended estate-key signature is the named custodian's STANDING
attestation for served packs, not a per-pack human act: the quarterly pack of
record stays the CLI-signed one (README).

THE BYTES. ``canonical_manifest_bytes(pack.model_dump(mode='json',
exclude={'signature'}))`` — the dump of the pack with ``signed``, ``signer``,
``signed_at``, ``key_fingerprint`` and (F4) ``signed_via`` already set and the
``signature`` KEY ABSENT (never present as ``None``). So every section title,
every metric's name/value/unit/source_query/status/note/basis, the window, the
period, ``generated_at``, the method, the signer fields and the provenance are
all inside the signature. ``signed_via`` is the one field the model OMITS from
its dump when it is None — never written as ``null`` (``BoardPack``'s wrap
serializer) — chosen so that the model dump and the raw file agree in all
three shapes: an UNSIGNED pack has no ``signed_via`` key (the C4 wire shape;
nothing new for older readers); a pack signed BEFORE F4 has no ``signed_via``
key in its file, so its raw JSON canonicalises to exactly the bytes it was
signed over and it still verifies (``attest verify`` reports its provenance as
unrecorded; ``tests/fixtures/pre_f4`` pins one such pack); every pack signed
SINCE F4 carries ``signed_via`` as a real string inside the signed bytes, so
editing it (``estate-key`` → ``cli``), adding it to a pre-F4 pack, or removing
it invalidates the signature. Had ``signed_via`` been dumped as ``null``, the
model dump of a pre-F4 pack would have gained a key its file never had, and
``signed_bytes`` (the model) and ``verify_pack`` (the raw JSON) would have
disagreed on every old pack.

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
key for another FIELD signing verb, and never the ledger anchor key for packs
(README LIMITS).

Key-load failures are ``InvalidSigningKey`` — raised, never a process exit:
the CLI turns them into exit 2 before anything is written, and the served app
turns them into the ``error`` state (``ServedSigning``: unsigned drafts,
named by ``/health``).
"""

from __future__ import annotations

import base64
import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

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


#: F4 environment: the served app signs under this name with this key.
SIGNER_ENV = "FIELD_ATTEST_SIGNER"
SIGN_KEY_ENV = "FIELD_ATTEST_SIGN_KEY"
#: The two provenance values ``signed_via`` may carry (inside the signed bytes).
SIGNED_VIA = ("cli", "estate-key")


@dataclass(frozen=True)
class ServedSigning:
    """The served app's signing state, decided ONCE at app start from the
    environment (``served_signing_from_env``) and reported by ``/health``.

    ``status``: ``on`` — every served pack is signed under ``signer`` with the
    key whose fingerprint is ``key_fingerprint`` (``signed_via: estate-key``);
    ``off`` — both variables unset: unsigned drafts; ``error`` — exactly one
    set, a blank name, or a key that does not load: unsigned drafts, and
    ``key_error`` names why (the failure — never key material, and never the
    configured path: ``/health`` is open, so only the file's name). ``signer`` and
    ``key_fingerprint`` are set only while ``on``; the private PEM is held
    only while ``on`` and kept out of ``repr``."""

    status: Literal["on", "off", "error"]
    signer: str | None = None
    key_fingerprint: str | None = None
    key_error: str | None = None
    private_key_pem: str | None = field(default=None, repr=False)


def served_signing_from_env(env: Mapping[str, str] | None = None) -> ServedSigning:
    """Decide the served signing state from ``FIELD_ATTEST_SIGNER`` and
    ``FIELD_ATTEST_SIGN_KEY``. NEVER raises and never exits: every failure is
    the ``error`` state, so ``create_app`` returns and serves unsigned drafts.
    A blank value counts as unset (compose forwards ``${VAR:-}`` as "")."""
    env = os.environ if env is None else env
    signer = env.get(SIGNER_ENV) or ""
    key_path = (env.get(SIGN_KEY_ENV) or "").strip()
    signer_set, key_set = bool(signer.strip()), bool(key_path)
    if not signer_set and not key_set:
        return ServedSigning(status="off")
    if signer_set and not key_set:  # never sign without a key
        return ServedSigning(status="error", key_error=(
            f"{SIGNER_ENV} is set but {SIGN_KEY_ENV} is not: no key, so served packs stay UNSIGNED"))
    if key_set and not signer_set:  # never sign under a blank name
        return ServedSigning(status="error", key_error=(
            f"{SIGN_KEY_ENV} is set but {SIGNER_ENV} is unset or blank: no signer name, "
            "so served packs stay UNSIGNED"))
    try:
        pem = load_signing_key(key_path)
        fingerprint = key_fingerprint(signer_public_pem(pem))
    except (ValueError, OSError) as exc:  # InvalidSigningKey is a ValueError
        # /health is OPEN: name the key file, never the configured path (its
        # parent is the estate's key layout; on a laptop, a home directory).
        # The CLI keeps the full path in its exit-2 message — that is the
        # operator's own terminal.
        reason = str(exc).replace(str(Path(key_path)), Path(key_path).name or "the configured file")
        return ServedSigning(status="error", key_error=(
            f"{SIGN_KEY_ENV} did not load — {reason}: served packs stay UNSIGNED"))
    return ServedSigning(status="on", signer=signer, key_fingerprint=fingerprint, private_key_pem=pem)


def signed_bytes(pack: BoardPack) -> bytes:
    """THE signed bytes of a pack (see the module docstring)."""
    return canonical_manifest_bytes(pack.model_dump(mode="json", exclude={"signature"}))


def sign_pack(
    pack: BoardPack, signer: str, private_key_pem: str, now: datetime | None = None,
    *, signed_via: str = "cli",
) -> BoardPack:
    """Return a signed copy of an unsigned pack. A blank signer is refused.
    ``signed_via`` records the provenance (F4) inside the signed bytes:
    ``cli`` (the default — ``attest render --signer --sign-key``) or
    ``estate-key`` (the served app under FIELD_ATTEST_SIGNER); anything else
    is refused."""
    if not isinstance(signer, str) or not signer.strip():
        raise ValueError("signer must name the human signing the pack (blank refused)")
    if signed_via not in SIGNED_VIA:
        raise ValueError(f"signed_via must be one of {SIGNED_VIA}, not {signed_via!r}")
    if pack.signed:
        raise ValueError("pack is already signed")
    public_pem = signer_public_pem(private_key_pem)
    view = pack.model_copy(update={
        "signed": True,
        "signer": signer,
        "signed_at": (now or datetime.now(timezone.utc)).isoformat(),
        "key_fingerprint": key_fingerprint(public_pem),
        "signed_via": signed_via,
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
    ``parse_pack_json``). Returns the signer facts on success — ``signer``,
    ``signed_at``, ``key_fingerprint`` and ``signed_via`` (None for a pack
    signed before F4); raises ``PackVerificationError`` naming the failure."""
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
    return {"signer": signer, "signed_at": raw.get("signed_at"), "key_fingerprint": fingerprint,
            "signed_via": raw.get("signed_via")}
