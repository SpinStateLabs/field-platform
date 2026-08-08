"""Ed25519 manifest signing tests."""

from field_core.signing import (
    canonical_manifest_bytes,
    generate_keypair,
    sign_manifest,
    verify_manifest,
)
from field_core.templates_api import template_data


def test_sign_verify_roundtrip():
    private_pem, public_pem = generate_keypair()
    data = template_data("default")
    signature = sign_manifest(data, private_pem)
    assert verify_manifest(data, signature, public_pem)


def test_canonicalization_is_format_independent():
    a = {"b": 2, "a": {"y": 1, "x": [1, 2]}}
    b = {"a": {"x": [1, 2], "y": 1}, "b": 2}
    assert canonical_manifest_bytes(a) == canonical_manifest_bytes(b)


def test_adversarial_any_field_change_breaks_signature():
    private_pem, public_pem = generate_keypair()
    data = template_data("default")
    signature = sign_manifest(data, private_pem)
    data["delegation"]["scope"].append("transfer funds")
    assert not verify_manifest(data, signature, public_pem)


def test_adversarial_wrong_key_fails():
    private_pem, _ = generate_keypair()
    _, other_public = generate_keypair()
    data = template_data("default")
    assert not verify_manifest(data, sign_manifest(data, private_pem), other_public)


def test_garbage_signature_returns_false_not_crash():
    _, public_pem = generate_keypair()
    assert not verify_manifest({"a": 1}, "not-base64!!!", public_pem)
    assert not verify_manifest({"a": 1}, "", public_pem)
