"""The rotate-then-verify-then-revoke state machine of ADR-0079 section 6, as data.

    planned -> minted -> installed -> verified -> old_revoked -> done
       |          |          |            |            |
       +----------+----------+------------+------------+--> halted   (a human must look)
       +--> rolled_back (planned, minted, installed: the old credential is still the live one)

``done``, ``rolled_back`` and ``halted`` are terminal for a run. ``halted`` stays
pending until a human clears it (journal event ``halt_cleared``): a halted journal
blocks every later run for that target, because a halt means "the agent was about
to do something a human has to decide" (a human revocation, an old credential
that is already invalid, a provider that would not confirm a revoke).

There is no transition out of ``verified`` to ``rolled_back``: once verification
passed, the only way back is forward (revoke the old one) or a halt; the old
credential is never revoked before ``verified``.
"""
from __future__ import annotations

import enum


class State(str, enum.Enum):
    PLANNED = "planned"
    MINTED = "minted"
    INSTALLED = "installed"
    VERIFIED = "verified"
    OLD_REVOKED = "old_revoked"
    DONE = "done"
    ROLLED_BACK = "rolled_back"
    HALTED = "halted"


S = State
TRANSITIONS: dict[State, frozenset[State]] = {
    S.PLANNED: frozenset({S.MINTED, S.ROLLED_BACK, S.HALTED}),
    S.MINTED: frozenset({S.INSTALLED, S.ROLLED_BACK, S.HALTED}),
    S.INSTALLED: frozenset({S.VERIFIED, S.ROLLED_BACK, S.HALTED}),
    S.VERIFIED: frozenset({S.OLD_REVOKED, S.HALTED}),
    S.OLD_REVOKED: frozenset({S.DONE, S.HALTED}),
    S.DONE: frozenset(),
    S.ROLLED_BACK: frozenset(),
    S.HALTED: frozenset(),
}
TERMINAL: frozenset[State] = frozenset(s for s, nxt in TRANSITIONS.items() if not nxt)
#: the happy path, in order: every adjacent pair is one transition with crash points between
HAPPY_PATH: tuple[State, ...] = (
    S.PLANNED, S.MINTED, S.INSTALLED, S.VERIFIED, S.OLD_REVOKED, S.DONE,
)


class IllegalTransition(Exception):
    pass


def check_transition(src: State | None, dst: State) -> None:
    """Raise unless ``src -> dst`` is in the table. ``None`` (no journal) may only enter ``planned``."""
    if src is None:
        if dst is not State.PLANNED:
            raise IllegalTransition(f"a run starts at planned, not {dst.value}")
        return
    if dst not in TRANSITIONS[src]:
        raise IllegalTransition(f"{src.value} -> {dst.value} is not allowed")
