"""Mutant survivors found by a hand-built AST mutation sweep (Lane R).

Each test pins a behaviour whose removal no existing test caught.
"""

from datetime import datetime, timedelta, timezone

import pytest
from field_core.delegation import DelegationToken

from delegation_authority.doa import DoaRosterError, load_roster
from delegation_authority.store import TokenStore

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _tok(agent="a-1", hours=1):
    return DelegationToken(
        agent_id=agent, granted_by="Grantor Person", scope=["read x"],
        issued_at=T0, expires_at=T0 + timedelta(hours=hours),
    )


def test_active_tokens_for_honours_an_explicit_now(tmp_path):
    """store.py active_tokens_for: a caller-supplied `now` decides activity,
    not the wall clock. Token lives 2026-01-01 00:00-01:00; the wall clock is
    long past that, so only the explicit `now` can make it active."""
    store = TokenStore(tmp_path / "t.db")
    tok = store.save(_tok())
    inside = store.active_tokens_for("a-1", now=T0 + timedelta(minutes=30))
    assert [t.token_id for t in inside] == [tok.token_id]
    after = store.active_tokens_for("a-1", now=T0 + timedelta(hours=2))
    assert after == []


def test_empty_roster_is_refused_as_empty_not_as_wrong_shape(tmp_path):
    """doa.py load_roster: an empty file says 'is empty' (a distinct, operator
    readable refusal), not the generic mapping-shape message."""
    p = tmp_path / "roster.yaml"
    p.write_text("", encoding="utf-8")
    with pytest.raises(DoaRosterError) as ei:
        load_roster(p)
    assert "is empty" in str(ei.value)
    assert "must be a mapping" not in str(ei.value)
