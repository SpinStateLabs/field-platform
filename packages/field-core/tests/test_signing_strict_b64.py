"""Scout S-2-5: `verify_manifest` decoded the signature with `base64.b64decode(sig)` and no `validate=True`, while
`verify_event_signature` and `verify_caller_signature` decode strictly. The default decoder silently drops every character
outside the base64 alphabet, so one signature had many accepted spellings (a newline, a space, a stray `!` or `-`).
Now one spelling is accepted: the exact standard, padded base64 `sign_manifest` produces."""
from __future__ import annotations

import base64
import hashlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from field_core.signing import generate_keypair, sign_manifest, verify_manifest

DATA = {"agent": {"name": "a", "scope": ["x", "y"]}, "n": 1}


@pytest.fixture(scope="module")
def signed():
    private_pem, public_pem = generate_keypair()
    return sign_manifest(DATA, private_pem), public_pem


def test_the_exact_signature_verifies(signed):
    sig, pub = signed
    assert len(sig) == 88 and sig.endswith("==")
    assert verify_manifest(DATA, sig, pub) is True


@pytest.mark.parametrize("spell", [
    lambda s: s[:40] + "\n" + s[40:],          # a newline inside (line-wrapped copy)
    lambda s: s[:40] + "\r\n" + s[40:],
    lambda s: s[:40] + " " + s[40:],           # a space inside
    lambda s: s[:40] + "\t" + s[40:],
    lambda s: s + "\n",                        # trailing newline
    lambda s: "\n" + s,                        # leading newline
    lambda s: " " + s,
    lambda s: s + "!",                         # junk appended
    lambda s: s + "-",
    lambda s: s[:40] + "!" + s[40:],           # junk inserted
    lambda s: s[:40] + "-" + s[40:],
    lambda s: s[:40] + "\x00" + s[40:],
    lambda s: s.rstrip("="),                   # unpadded
    lambda s: s[:-2],                          # truncated padding
])
def test_the_same_signature_in_another_spelling_is_refused(signed, spell):
    sig, pub = signed
    assert spell(sig) != sig
    assert verify_manifest(DATA, spell(sig), pub) is False


def _signed_with_both_url_unsafe_characters() -> tuple[str, str]:
    """A signature of DATA that holds both '+' and '/', with its public key. The keys come from a fixed list of seeds and
    Ed25519 signatures are deterministic, so every run takes the same signature."""
    for n in range(64):
        private = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"strict-b64 test key %d" % n).digest())
        private_pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption()).decode("ascii")
        sig = sign_manifest(DATA, private_pem)
        if "+" in sig and "/" in sig:
            public_pem = private.public_key().public_bytes(serialization.Encoding.PEM,
                                                           serialization.PublicFormat.SubjectPublicKeyInfo)
            return sig, public_pem.decode("ascii")
    raise AssertionError("no seed in the list gives a signature with both '+' and '/'")


def test_a_url_safe_spelling_is_refused():
    sig, pub = _signed_with_both_url_unsafe_characters()
    assert "+" in sig and "/" in sig
    assert verify_manifest(DATA, sig, pub) is True      # the standard spelling of this very signature verifies
    urlsafe = base64.urlsafe_b64encode(base64.b64decode(sig)).decode("ascii")
    assert urlsafe != sig and "-" in urlsafe and "_" in urlsafe
    assert verify_manifest(DATA, urlsafe, pub) is False


def test_acceptance_matches_the_strict_decoder_for_every_single_character_edit(signed):
    """The rule itself: a string verifies exactly when the strict decoder reads it as the real signature bytes."""
    sig, pub = signed
    good = base64.b64decode(sig)
    for i in range(len(sig) + 1):
        for ch in ("\n", " ", "!", "-", "A"):
            for mutant in (sig[:i] + ch + sig[i:], sig[:i] + ch + sig[i + 1:]):
                try:
                    strict = base64.b64decode(mutant, validate=True) == good
                except ValueError:
                    strict = False
                assert verify_manifest(DATA, mutant, pub) is strict, repr(mutant)


def test_garbage_and_non_strings_still_return_false(signed):
    _, pub = signed
    for bad in ("not-base64!!!", "", "====", None, 5, b"abc"):
        assert verify_manifest(DATA, bad, pub) is False
