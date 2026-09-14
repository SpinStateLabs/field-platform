"""F2 — per-event ledger signatures in field-core (additive).

Pins: an unsigned event serialises with NO ``signature`` / ``signing_failed``
key (older ``extra="forbid"`` images keep parsing it); a pre-F2 fixture line
parses unchanged and its stored hash is still what ``compute_event_hash``
gives; a signed line round-trips; the signature covers the hash and is
outside it; ``signing_failed`` is inside the hash; plain ``verify_chain`` is
blind to a re-linked mutation that the signature catches.
"""

from __future__ import annotations

import base64
import json

import pytest

from field_core.ledger import (
    GENESIS_HASH,
    LedgerEvent,
    compute_event_hash,
    event_signing_bytes,
    flag_signing_failed,
    make_event,
    verify_chain,
)
from field_core.manifest import SEAL_ALGORITHMS
from field_core.signing import (
    generate_keypair,
    key_fingerprint,
    private_key_fingerprint,
    sign_event,
    verify_event_signature,
)

#: The first line of services/sealed-ledger/tests/fixtures/scene4/events.jsonl
#: (written 2026-08-10, long before F2), verbatim.
PRE_F2_LINE = (
    '{"event_id":"9feddef0-cb8a-49b9-9502-71c0ce135bea","ts":"2026-08-10T13:59:02.701357+00:00",'
    '"event_type":"conformance.allow","agent_id":"invoicing-agent","payload":{"action":"draft invoices",'
    '"invoice":"INV-001","amount":1200},"prev_hash":"0000000000000000000000000000000000000000000000000000000000000000",'
    '"hash":"626d8e83a92037d6efc26de85f0505684a44d8c078079e46643260adc8fdc9b7"}'
)


@pytest.fixture(scope="module")
def keys():
    private_pem, public_pem = generate_keypair()
    _, other_public = generate_keypair()
    return {"private": private_pem, "public": public_pem, "other_public": other_public}


def _chain(n: int, private_pem: str | None = None) -> list[LedgerEvent]:
    events, prev = [], GENESIS_HASH
    for i in range(n):
        ev = make_event("action", {"seq": i, "amount": 100 + i}, prev_hash=prev, agent_id="a")
        if private_pem is not None:
            ev = sign_event(ev, private_pem)
        events.append(ev)
        prev = ev.hash
    return events


# ------------------------------------------------- additive compat (the rule)


def test_unsigned_event_json_has_no_signature_and_no_signing_failed_key():
    """The additive-compat rule: an unsigned append's line carries neither key,
    in model_dump(), model_dump_json() and the JSON-mode dump."""
    ev = make_event("action", {"n": 1}, agent_id="a")
    assert ev.signature is None and ev.signing_failed is None
    for dumped in (ev.model_dump(), ev.model_dump(mode="json"), json.loads(ev.model_dump_json())):
        assert "signature" not in dumped and "signing_failed" not in dumped
        assert set(dumped) == {"event_id", "ts", "event_type", "agent_id", "payload", "prev_hash", "hash"}


def test_pre_f2_fixture_line_parses_unchanged_and_its_hash_is_unchanged():
    """A line written before F2: parses (extra='forbid' untouched), the stored
    hash is what compute_event_hash still gives, and re-serialising it yields
    exactly the same JSON object (no new keys)."""
    raw = json.loads(PRE_F2_LINE)
    ev = LedgerEvent.model_validate(raw)
    assert compute_event_hash(ev) == raw["hash"] == compute_event_hash(raw)
    assert json.loads(ev.model_dump_json()) == raw
    assert ev.signature is None and ev.signing_failed is None


def test_pre_f2_reader_shape_still_rejects_unknown_keys():
    """extra='forbid' is unchanged: a genuinely unknown key is still refused."""
    raw = json.loads(PRE_F2_LINE)
    with pytest.raises(ValueError):
        LedgerEvent.model_validate({**raw, "witness": "x"})


def test_signed_line_round_trips(keys):
    ev = sign_event(make_event("action", {"n": 1}, agent_id="a"), keys["private"])
    line = ev.model_dump_json()
    back = LedgerEvent.model_validate(json.loads(line))
    assert back == ev and back.signature == ev.signature
    assert "signing_failed" not in json.loads(line)  # a signed event is never flagged
    assert verify_event_signature(back, keys["public"])


# ------------------------------------------------ what the signature covers


def test_signature_is_base64_of_64_raw_bytes_and_outside_the_hash(keys):
    plain = make_event("action", {"n": 1}, agent_id="a")
    signed = sign_event(plain, keys["private"])
    assert len(base64.b64decode(signed.signature, validate=True)) == 64
    # hash first, sign second: signing does not change the hash, and the
    # hash of the signed record ignores the signature
    assert signed.hash == plain.hash == compute_event_hash(signed) == compute_event_hash(plain)
    assert compute_event_hash(signed.model_dump()) == plain.hash


def test_signing_bytes_include_the_hash(keys):
    """The signature binds the hash: the same record with another hash has
    different signing bytes (and so a different signature)."""
    ev = make_event("action", {"n": 1}, agent_id="a")
    other = ev.model_copy(update={"hash": "f" * 64})
    assert event_signing_bytes(ev) != event_signing_bytes(other)
    assert b'"hash":"' + ev.hash.encode() in event_signing_bytes(ev)
    assert b"signature" not in event_signing_bytes(sign_event(ev, keys["private"]))


def test_verify_fails_on_any_mutation_wrong_key_missing_or_malformed_signature(keys):
    ev = sign_event(make_event("action", {"amount": 1200}, agent_id="a"), keys["private"])
    assert verify_event_signature(ev, keys["public"])
    assert not verify_event_signature(ev, keys["other_public"])  # wrong key
    assert not verify_event_signature(ev.model_copy(update={"signature": None}), keys["public"])
    assert not verify_event_signature(ev.model_copy(update={"signature": "not base64!"}), keys["public"])
    assert not verify_event_signature(ev, "-----BEGIN PUBLIC KEY-----\nnope\n-----END PUBLIC KEY-----\n")
    for field, value in (("payload", {"amount": 12}), ("agent_id", "b"), ("event_type", "x"),
                         ("ts", "2020-01-01T00:00:00+00:00"), ("prev_hash", "1" * 64),
                         ("event_id", "other"), ("hash", "f" * 64)):
        mutated = ev.model_copy(update={field: value})
        assert not verify_event_signature(mutated, keys["public"]), field
    # a dict works too (what a CLI reads off disk)
    assert verify_event_signature(json.loads(ev.model_dump_json()), keys["public"])


def test_verify_chain_is_blind_to_a_relinked_mutation_that_the_signature_catches(keys):
    """The attacker without the key: mutate one field of a signed event and
    recompute every later hash. Plain verify_chain passes (pinned); the
    signature at that index fails and every later one still verifies."""
    events = _chain(5, keys["private"])
    forged = events[2].model_dump()
    forged["payload"] = {"seq": 2, "amount": 1}
    forged.pop("hash")
    forged = LedgerEvent(**{**forged, "hash": compute_event_hash(forged)})  # signature kept
    events[2] = forged
    for i in range(3, 5):
        rec = events[i].model_dump(exclude={"hash"})
        rec["prev_hash"] = events[i - 1].hash
        events[i] = LedgerEvent(**rec, hash=compute_event_hash(rec))
    assert verify_chain(events).ok  # the documented blindness of the plain chain
    assert [verify_event_signature(e, keys["public"]) for e in events] == [True, True, False, False, False]
    # (3 and 4 fail too: their prev_hash — under the signature — changed)


# --------------------------------------------------------- signing_failed


def test_flag_signing_failed_is_inside_the_hash_and_omitted_when_none():
    ev = make_event("kill.agent", {"reason": "x"}, agent_id="a")
    flagged = flag_signing_failed(ev)
    assert flagged.signing_failed is True and flagged.signature is None
    assert flagged.hash != ev.hash  # the flag is sealed into the hash
    assert compute_event_hash(flagged) == flagged.hash
    line = json.loads(flagged.model_dump_json())
    assert line["signing_failed"] is True and "signature" not in line
    # stripping the flag from the line breaks the hash (a tamper, not a downgrade)
    stripped = {k: v for k, v in line.items() if k != "signing_failed"}
    assert compute_event_hash(stripped) != flagged.hash
    # a dict that spells the omission as None hashes like the omission
    assert compute_event_hash({**ev.model_dump(), "signing_failed": None}) == ev.hash


def test_flag_signing_failed_refuses_a_signed_event(keys):
    with pytest.raises(ValueError):
        flag_signing_failed(sign_event(make_event("kill.agent"), keys["private"]))


# ----------------------------------------------------------- key helpers


def test_private_key_fingerprint_matches_the_public_key_fingerprint(keys):
    assert private_key_fingerprint(keys["private"]) == key_fingerprint(keys["public"])
    assert len(private_key_fingerprint(keys["private"])) == 64


def test_private_key_helpers_refuse_non_ed25519_and_garbage(keys):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    ec_pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode("ascii")
    ev = make_event("action")
    for bad in (ec_pem, "garbage", keys["public"], ""):
        with pytest.raises(ValueError):
            sign_event(ev, bad)
        with pytest.raises(ValueError):
            private_key_fingerprint(bad)


def test_seal_algorithm_strings_exist_in_field_core():
    """/health reports one of these two; both must be declared algorithms."""
    assert "ed25519-signed-chain" in SEAL_ALGORITHMS and "sha-256-chain" in SEAL_ALGORITHMS
