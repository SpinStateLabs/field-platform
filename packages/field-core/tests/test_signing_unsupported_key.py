"""S8-1: a well-formed public key whose algorithm cryptography does not know (an SPKI with an unknown
OID) made `load_pem_public_key` raise UnsupportedAlgorithm, which is not a ValueError, so it escaped
`verify_event_signature` (documented to return a bool) and `key_fingerprint` (documented to raise
ValueError). Both now go through `load_ed25519_public_key`."""

from __future__ import annotations

import base64

import pytest
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization

from field_core.ledger import GENESIS_HASH, make_event
from field_core.signing import generate_keypair, key_fingerprint, sign_event, verify_event_signature


def _unknown_oid_pem() -> str:
    """SubjectPublicKeyInfo { AlgorithmIdentifier { OID 1.2.3.4 }, BIT STRING (8 bytes) }, PEM-armoured."""
    alg = bytes.fromhex("30050603" + "2a0304")           # SEQ { OID 1.2.3.4 }
    bits = bytes.fromhex("030900") + bytes(range(8))      # BIT STRING, 0 unused bits, 8 bytes
    der = bytes([0x30, len(alg) + len(bits)]) + alg + bits
    b64 = base64.b64encode(der).decode("ascii")
    return f"-----BEGIN PUBLIC KEY-----\n{b64}\n-----END PUBLIC KEY-----\n"


UNKNOWN = _unknown_oid_pem()


def _signed_event(private_pem):
    event = make_event("action", {"x": 1}, prev_hash=GENESIS_HASH, agent_id="a")
    return sign_event(event, private_pem)


def test_the_fixture_really_is_an_unsupported_algorithm_to_cryptography():
    with pytest.raises(UnsupportedAlgorithm):
        serialization.load_pem_public_key(UNKNOWN.encode("ascii"))


def test_verify_event_signature_is_false_not_an_exception_for_an_unknown_algorithm_key():
    private, public = generate_keypair()
    assert verify_event_signature(_signed_event(private), UNKNOWN) is False
    assert verify_event_signature(_signed_event(private).model_dump(), UNKNOWN) is False


def test_key_fingerprint_raises_value_error_for_an_unknown_algorithm_key():
    with pytest.raises(ValueError):
        key_fingerprint(UNKNOWN)


def test_a_signed_event_still_verifies_under_the_real_key():
    private, public = generate_keypair()
    event = _signed_event(private)
    assert verify_event_signature(event, public) is True
    assert verify_event_signature(event, generate_keypair()[1]) is False   # a different key still fails


def test_the_real_fingerprint_is_unchanged_and_other_failures_still_raise():
    _, public = generate_keypair()
    assert len(key_fingerprint(public)) == 64
    for bad in ("not a pem", "", "-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----\n"):
        with pytest.raises(ValueError):
            key_fingerprint(bad)
        assert verify_event_signature(_signed_event(generate_keypair()[0]), bad) is False
