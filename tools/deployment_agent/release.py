"""Release-record verifier SKELETON (ADR-0079 section 4.6).

A release record names the exact full 40-hex SHA, image digests, a hash of each
stage's result, the digest of ``gate_pass.json`` and carries a signature. The
signature is checked by an INJECTED ``SignatureVerifier``; this module does no
cryptography and holds no key. The default verifier refuses everything
(fail-closed) with a pointer to the ADR, so nothing can pass by accident until a
real verifier (GitHub artifact attestation or equivalent, unverified feature set)
is supplied by a later change.

What is checked here, deterministically:
  * the record's ``sha`` is exactly 40 lowercase hex characters and equals the SHA
    the caller asks to deploy (a short SHA is refused on either side);
  * ``signature`` is a non-empty string and the injected verifier accepts
    (canonical payload bytes, signature);
  * ``image_digests``, ``stage_results`` and ``gate_pass_digest`` are present and
    shaped (sha256:<64 hex> / 64 hex), and every required stage has a hash;
  * an ADR override (``adr_override``) is only valid with a ``override_approval``
    naming a human approver and carrying its own signature, also checked by the
    injected verifier (refuse-list item 9).
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .secrets_guard import SHA40

#: (payload bytes, signature) -> True only if the signature is valid for the payload
SignatureVerifier = Callable[[bytes, str], bool]

REQUIRED_STAGES = ("lint", "unit", "e2e", "redteam", "evals")
_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
_DIGEST = re.compile(r"\Asha256:[0-9a-f]{64}\Z")


class ReleaseRecordError(ValueError):
    """The record is malformed, names the wrong SHA, or its signature is not accepted."""


def refuse_all_verifier(payload: bytes, signature: str) -> bool:
    raise NotImplementedError(
        "no signature verifier is wired in: signature cryptography is out of scope for the skeleton "
        "(ADR-0079 section 4.6; GitHub attestation feature set unverified)"
    )


@dataclass(frozen=True)
class VerifiedRelease:
    sha: str
    gate_pass_digest: str
    adr_override: str | None
    override_approver: str | None


def canonical_payload(record: Mapping[str, Any], drop: tuple[str, ...] = ("signature",)) -> bytes:
    body = {k: v for k, v in record.items() if k not in drop}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def require_full_sha(value: object, what: str = "sha") -> str:
    if not isinstance(value, str) or not SHA40.match(value):
        raise ReleaseRecordError(f"{what} must be the exact full 40-hex lowercase SHA (short or malformed refused)")
    return value


def verify_release(
    record: Mapping[str, Any],
    expected_sha: str,
    verifier: SignatureVerifier = refuse_all_verifier,
) -> VerifiedRelease:
    """Return a VerifiedRelease or raise ReleaseRecordError. Never returns on a doubt."""
    expected = require_full_sha(expected_sha, "expected sha")
    if not isinstance(record, Mapping):
        raise ReleaseRecordError("record must be a mapping")
    sha = require_full_sha(record.get("sha"), "record sha")
    if sha != expected:
        raise ReleaseRecordError("record names a different SHA than the one to deploy")

    digests = record.get("image_digests")
    if not isinstance(digests, Mapping) or not digests or not all(
        isinstance(k, str) and isinstance(v, str) and _DIGEST.match(v) for k, v in digests.items()
    ):
        raise ReleaseRecordError("image_digests must map image name to sha256:<64 hex>")
    stages = record.get("stage_results")
    if not isinstance(stages, Mapping) or any(
        not (isinstance(stages.get(s), str) and _HEX64.match(stages[s])) for s in REQUIRED_STAGES
    ):
        raise ReleaseRecordError(f"stage_results must hold a 64-hex hash for each of {', '.join(REQUIRED_STAGES)}")
    gate = record.get("gate_pass_digest")
    if not isinstance(gate, str) or not _HEX64.match(gate):
        raise ReleaseRecordError("gate_pass_digest must be 64 hex")

    signature = record.get("signature")
    if not isinstance(signature, str) or not signature.strip():
        raise ReleaseRecordError("record has no signature")
    if not _accepts(verifier, canonical_payload(record), signature):
        raise ReleaseRecordError("signature not accepted by the verifier")

    override = record.get("adr_override")
    approver = None
    if override is not None:
        approval = record.get("override_approval")
        if (
            not isinstance(override, str) or not override.strip()
            or not isinstance(approval, Mapping)
            or not isinstance(approval.get("approver"), str) or not approval["approver"].strip()
            or not isinstance(approval.get("signature"), str) or not approval["signature"].strip()
        ):
            raise ReleaseRecordError("an ADR override needs a human-signed override_approval")
        body = {"sha": sha, "adr_override": override, "approver": approval["approver"]}
        if not _accepts(verifier, canonical_payload(body, drop=()), approval["signature"]):
            raise ReleaseRecordError("override approval signature not accepted by the verifier")
        approver = approval["approver"]
    return VerifiedRelease(sha, gate, override if isinstance(override, str) else None, approver)


def _accepts(verifier: SignatureVerifier, payload: bytes, signature: str) -> bool:
    try:
        return verifier(payload, signature) is True
    except NotImplementedError:
        raise
    except Exception as exc:  # a verifier that blows up never counts as a pass
        raise ReleaseRecordError(f"verifier failed: {type(exc).__name__}") from None
