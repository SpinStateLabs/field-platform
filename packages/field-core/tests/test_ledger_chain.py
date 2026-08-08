"""Hash-chain tests, including the adversarial tamper case."""

from field_core.ledger import (
    GENESIS_HASH,
    LedgerEvent,
    compute_event_hash,
    make_event,
    verify_chain,
)


def build_chain(n: int) -> list[LedgerEvent]:
    events: list[LedgerEvent] = []
    prev = GENESIS_HASH
    for i in range(n):
        ev = make_event(
            event_type="action",
            payload={"seq": i, "detail": f"step {i}"},
            prev_hash=prev,
            agent_id="agent-under-test",
        )
        events.append(ev)
        prev = ev.hash
    return events


def test_intact_chain_verifies():
    events = build_chain(5)
    result = verify_chain(events)
    assert result.ok
    assert result.length == 5
    assert result.first_break_index is None


def test_empty_chain_is_ok():
    assert verify_chain([]).ok


def test_genesis_must_link_to_zeros():
    events = build_chain(3)
    events[0] = events[0].model_copy(update={"prev_hash": "f" * 64})
    result = verify_chain(events)
    assert not result.ok
    assert result.first_break_index == 0


def test_adversarial_mutate_middle_record_detected():
    """Adversarial case: mutate a middle record's payload; detection at that index."""
    events = build_chain(5)
    tampered = events[2].model_copy(
        update={"payload": {"seq": 2, "detail": "step 2", "amount": 999999}}
    )
    events[2] = tampered
    result = verify_chain(events)
    assert not result.ok
    assert result.first_break_index == 2
    assert "mutated" in result.reason


def test_adversarial_rehash_after_mutation_breaks_next_link():
    """Adversarial case: attacker mutates a record AND recomputes its hash.

    The forged record is self-consistent, so detection moves to the next
    link — event 3's prev_hash no longer matches the forged hash chain.
    """
    events = build_chain(5)
    forged_partial = events[2].model_dump()
    forged_partial["payload"] = {"seq": 2, "detail": "step 2", "amount": 999999}
    del forged_partial["hash"]
    forged = LedgerEvent(**forged_partial, hash=compute_event_hash(forged_partial))
    events[2] = forged
    result = verify_chain(events)
    assert not result.ok
    assert result.first_break_index == 3
    assert "link break" in result.reason


def test_hash_is_deterministic_and_order_insensitive():
    partial = {
        "event_id": "e-1",
        "ts": "2026-08-08T12:00:00+00:00",
        "event_type": "action",
        "agent_id": None,
        "payload": {"b": 2, "a": 1},
        "prev_hash": GENESIS_HASH,
    }
    reordered = {
        "prev_hash": GENESIS_HASH,
        "payload": {"a": 1, "b": 2},
        "agent_id": None,
        "event_type": "action",
        "ts": "2026-08-08T12:00:00+00:00",
        "event_id": "e-1",
    }
    assert compute_event_hash(partial) == compute_event_hash(reordered)
