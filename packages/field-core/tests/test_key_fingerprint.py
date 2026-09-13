"""key_fingerprint — sha-256 over the RAW 32-byte Ed25519 public key (C0).

The known-answer vector is RFC 8032 section 7.1 TEST 1; the expected digest
was computed with hashlib over the RFC's published public-key bytes, not with
the function under test.
"""

import hashlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, x25519

from field_core.signing import generate_keypair, key_fingerprint

RFC8032_T1_SECRET = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
RFC8032_T1_PUBLIC = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
RFC8032_T1_PUBLIC_PEM = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MCowBQYDK2VwAyEA11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=\n"
    "-----END PUBLIC KEY-----\n"
)
RFC8032_T1_PRIVATE_PEM = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MC4CAQAwBQYDK2VwBCIEIJ1hsZ3v/VpguoRK9JLsLMREScVpezJpGXA7rAMcrn9g\n"
    "-----END PRIVATE KEY-----\n"
)
RFC8032_T1_FINGERPRINT = "21fe31dfa154a261626bf854046fd2271b7bed4b6abe45aa58877ef47f9721b9"


def _public_pem_of(private_pem: str) -> str:
    private = serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)
    return private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def test_known_key_has_stable_fingerprint():
    assert RFC8032_T1_FINGERPRINT == hashlib.sha256(bytes.fromhex(RFC8032_T1_PUBLIC)).hexdigest()
    assert key_fingerprint(RFC8032_T1_PUBLIC_PEM) == RFC8032_T1_FINGERPRINT
    # repeatable
    assert key_fingerprint(RFC8032_T1_PUBLIC_PEM) == key_fingerprint(RFC8032_T1_PUBLIC_PEM)


def test_fingerprint_is_over_raw_key_not_pem_or_der():
    fp = key_fingerprint(RFC8032_T1_PUBLIC_PEM)
    assert len(fp) == 64 and int(fp, 16) >= 0
    assert fp != hashlib.sha256(RFC8032_T1_PUBLIC_PEM.encode("ascii")).hexdigest()
    der = bytes.fromhex("302a300506032b6570032100" + RFC8032_T1_PUBLIC)
    assert fp != hashlib.sha256(der).hexdigest()
    # the PEM with CRLF line endings is the same key, so the same fingerprint
    assert key_fingerprint(RFC8032_T1_PUBLIC_PEM.replace("\n", "\r\n")) == fp


def test_public_half_of_a_private_key_gives_the_same_fingerprint():
    derived = _public_pem_of(RFC8032_T1_PRIVATE_PEM)
    assert key_fingerprint(derived) == RFC8032_T1_FINGERPRINT

    private_pem, public_pem = generate_keypair()
    assert key_fingerprint(_public_pem_of(private_pem)) == key_fingerprint(public_pem)


def test_different_keys_have_different_fingerprints():
    _, pub_a = generate_keypair()
    _, pub_b = generate_keypair()
    assert key_fingerprint(pub_a) != key_fingerprint(pub_b)
    assert key_fingerprint(pub_a) != RFC8032_T1_FINGERPRINT


def test_x25519_key_is_refused_even_though_its_raw_key_is_32_bytes():
    public = x25519.X25519PrivateKey.generate().public_key()
    assert len(public.public_bytes_raw()) == 32
    pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    with pytest.raises(ValueError, match="not Ed25519"):
        key_fingerprint(pem)


def test_ec_key_is_refused():
    public = ec.generate_private_key(ec.SECP256R1()).public_key()
    pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    with pytest.raises(ValueError, match="not Ed25519"):
        key_fingerprint(pem)


def test_private_key_pem_and_garbage_are_refused():
    with pytest.raises(ValueError):
        key_fingerprint(RFC8032_T1_PRIVATE_PEM)
    with pytest.raises(ValueError):
        key_fingerprint("not a pem")
