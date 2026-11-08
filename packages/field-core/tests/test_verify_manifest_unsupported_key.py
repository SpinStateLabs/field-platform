"""S12-2: verify_manifest returns False, never raises, for a public key it cannot use.

A well-formed SPKI whose algorithm OID cryptography does not know made `load_pem_public_key` raise
UnsupportedAlgorithm (not a ValueError), which escaped verify_manifest. Fixture copied from
test_signing_unsupported_key.py (S8-1)."""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from field_core.signing import generate_keypair, sign_manifest, verify_manifest


def _unknown_oid_pem() -> str:
    alg = bytes.fromhex("30050603" + "2a0304")           # SEQ { OID 1.2.3.4 }
    bits = bytes.fromhex("030900") + bytes(range(8))      # BIT STRING, 0 unused bits, 8 bytes
    der = bytes([0x30, len(alg) + len(bits)]) + alg + bits
    b64 = base64.b64encode(der).decode("ascii")
    return f"-----BEGIN PUBLIC KEY-----\n{b64}\n-----END PUBLIC KEY-----\n"


DATA = {"a": 1}
EC_PUBLIC = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
).decode("ascii")


@pytest.mark.parametrize("pem", [_unknown_oid_pem(), EC_PUBLIC, "garbage text", "caf\u00e9 \u2014 \u00fc"],
                         ids=["unknown-oid", "ec-public", "garbage", "non-ascii"])
def test_an_unusable_public_key_is_false_not_an_exception(pem):
    private, _ = generate_keypair()
    assert verify_manifest(DATA, sign_manifest(DATA, private), pem) is False


def test_a_private_key_pem_is_false():
    private, _ = generate_keypair()
    assert verify_manifest(DATA, sign_manifest(DATA, private), private) is False


def test_a_real_signature_still_verifies():
    private, public = generate_keypair()
    assert verify_manifest(DATA, sign_manifest(DATA, private), public) is True
