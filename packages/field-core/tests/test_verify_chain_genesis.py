"""verify_chain(events, genesis=...) — C0 helper for chains that do not start
at the beginning of history (a rotated segment, an exported spine).

Every guard here fails if ``verify_chain`` goes back to hard-coding
GENESIS_HASH as the first expected ``prev_hash``.
"""

import inspect

from field_core.ledger import (
    GENESIS_HASH,
    LedgerEvent,
    compute_event_hash,
    make_event,
    verify_chain,
)


def _chain(n: int, start: str, tag: str) -> list[LedgerEvent]:
    events: list[LedgerEvent] = []
    prev = start
    for i in range(n):
        ev = make_event(
            "action",
            {"seq": i, "tag": tag},
            prev_hash=prev,
            agent_id="agent-under-test",
            ts=f"2026-09-12T10:0{i}:00+00:00",
            event_id=f"{tag}-{i}",
        )
        events.append(ev)
        prev = ev.hash
    return events


def _continuation(n: int = 4):
    """A first chain from GENESIS, then a chain whose first prev_hash is its head."""
    first = _chain(3, GENESIS_HASH, "first")
    head = first[-1].hash
    return head, _chain(n, head, "cont")


def test_genesis_parameter_defaults_to_zeros_and_is_positional_compatible():
    sig = inspect.signature(verify_chain)
    params = list(sig.parameters.values())
    assert [p.name for p in params] == ["events", "genesis"]
    assert params[1].default == GENESIS_HASH
    assert GENESIS_HASH == "0" * 64


def test_default_behaviour_identical_intact_and_tampered():
    events = _chain(5, GENESIS_HASH, "d")
    one_arg = verify_chain(events)
    assert one_arg.ok and one_arg.length == 5
    assert one_arg.model_dump() == verify_chain(events, GENESIS_HASH).model_dump()
    assert one_arg.model_dump() == verify_chain(events, genesis=GENESIS_HASH).model_dump()

    tampered = list(events)
    tampered[2] = tampered[2].model_copy(update={"payload": {"seq": 99}})
    default = verify_chain(tampered)
    assert not default.ok and default.first_break_index == 2
    assert "mutated" in default.reason
    assert default.model_dump() == verify_chain(tampered, GENESIS_HASH).model_dump()

    # a generator (what LedgerStore.verify passes) still works with one argument
    assert verify_chain(e for e in events).ok


def test_non_genesis_chain_verifies_with_its_genesis_and_fails_without_it():
    head, cont = _continuation()

    with_genesis = verify_chain(cont, head)
    assert with_genesis.ok
    assert with_genesis.length == 4
    assert with_genesis.first_break_index is None
    assert verify_chain(cont, genesis=head).ok

    without = verify_chain(cont)
    assert not without.ok
    assert without.first_break_index == 0
    assert "link break at index 0" in without.reason
    assert "0" * 12 in without.reason  # it expected the zero genesis


def test_wrong_custom_genesis_breaks_at_index_zero_naming_the_expected_hash():
    head, cont = _continuation()
    wrong = "f" * 64
    result = verify_chain(cont, wrong)
    assert not result.ok
    assert result.first_break_index == 0
    assert result.length == 1
    assert "link break at index 0" in result.reason
    assert wrong[:12] in result.reason
    # and a GENESIS chain does not verify under someone else's genesis
    fresh = _chain(2, GENESIS_HASH, "g")
    assert verify_chain(fresh, head).first_break_index == 0


def test_mutation_under_custom_genesis_reports_that_index_and_reason():
    head, cont = _continuation(5)
    cont[2] = cont[2].model_copy(update={"payload": {"seq": 2, "tag": "edited"}})
    result = verify_chain(cont, head)
    assert not result.ok
    assert result.first_break_index == 2
    assert result.length == 3
    assert "hash mismatch at index 2" in result.reason
    assert "mutated" in result.reason


def test_rehashed_forgery_under_custom_genesis_breaks_the_next_link():
    head, cont = _continuation(5)
    forged_partial = cont[1].model_dump()
    forged_partial.pop("hash")
    forged_partial["payload"] = {"seq": 1, "tag": "forged"}
    cont[1] = LedgerEvent(**forged_partial, hash=compute_event_hash(forged_partial))
    result = verify_chain(cont, head)
    assert not result.ok
    assert result.first_break_index == 2
    assert "link break at index 2" in result.reason


def test_empty_chain_is_ok_under_any_genesis():
    assert verify_chain([], "a" * 64).ok
    assert verify_chain([], "a" * 64).length == 0
