"""S9-2 (the part PR 590 leaves): the three signature verifiers agree on every mangled spelling of a good signature.

PR 590 makes `verify_manifest` decode strictly (`validate=True`), like `verify_event_signature` and `verify_caller_signature`.
Its own tests exercise `verify_manifest` alone. This file puts the three side by side, each with an equivalent fixture, so one
cannot drift from the others again: a good signature verifies; the same signature with a trailing newline, a trailing `!!`, an
inserted space, an inserted newline, a URL-safe spelling, a missing pad or a non-ASCII character does not, in all three."""

import base64

import pytest

from field_core.ledger import make_event
from field_core.signing import (generate_keypair, sign_caller, sign_event, sign_manifest, verify_caller_signature,
                                verify_event_signature, verify_manifest)

DATA = {"agent": {"name": "a", "scope": ["x"]}, "n": 1}
PRIV, PUB = generate_keypair()
OTHER_PRIV, OTHER_PUB = generate_keypair()


def _manifest():
    sig = sign_manifest(DATA, PRIV)
    return sig, lambda s, pub=PUB: verify_manifest(DATA, s, pub)


def _event():
    ev = sign_event(make_event(event_type="action", payload={"n": 1}, agent_id="a1", prev_hash="0" * 64), PRIV)

    def check(s, pub=PUB):
        return verify_event_signature(ev.model_copy(update={"signature": s}), pub)
    return ev.signature, check


def _caller():
    rec = {"event_type": "action", "agent_id": "a1", "payload": {"n": 1}, "caller_id": "svc", "caller_ts": "2026-11-07T00:00:00+00:00"}
    sig = sign_caller(PRIV, **rec)
    return sig, lambda s, pub=PUB: verify_caller_signature({**rec, "caller_signature": s}, pub)


FIXTURES = {"manifest": _manifest, "event": _event, "caller": _caller}


def mangled(sig: str) -> dict[str, str]:
    raw = base64.b64decode(sig)
    return {
        "trailing-newline": sig + "\n",
        "trailing-bangs": sig + "!!",
        "inserted-space": sig[:10] + " " + sig[10:],
        "inserted-newline": sig[:20] + "\n" + sig[20:],
        "leading-space": " " + sig,
        "urlsafe": base64.urlsafe_b64encode(raw).decode("ascii") if base64.urlsafe_b64encode(raw).decode() != sig else sig + "-",
        "no-padding": sig.rstrip("="),
        "non-ascii": sig[:-1] + "é",
        "embedded-nul": sig[:5] + "\x00" + sig[5:],
    }


@pytest.mark.parametrize("name", FIXTURES)
def test_a_good_signature_verifies_and_a_wrong_key_does_not(name):
    sig, check = FIXTURES[name]()
    assert check(sig) is True
    assert check(sig, OTHER_PUB) is False


@pytest.mark.parametrize("name", FIXTURES)
@pytest.mark.parametrize("spelling", list(mangled("A" * 86 + "==")))
def test_every_mangled_spelling_is_refused_by_each_verifier(name, spelling):
    sig, check = FIXTURES[name]()
    assert check(mangled(sig)[spelling]) is False


@pytest.mark.parametrize("spelling", list(mangled("A" * 86 + "==")))
def test_the_three_verifiers_agree_on_each_mangled_spelling(spelling):
    results = {name: build()[1](mangled(build()[0])[spelling]) for name, build in FIXTURES.items()}
    assert len(set(results.values())) == 1, results


@pytest.mark.parametrize("name", FIXTURES)
def test_a_non_string_or_empty_signature_is_false_not_an_exception(name):
    _, check = FIXTURES[name]()
    for bad in ("", None, 5, b"abc", ["x"]):
        assert check(bad) is False
