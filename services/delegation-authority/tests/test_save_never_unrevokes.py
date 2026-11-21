"""B-S12-15: TokenStore.save never lowers revocation.

save() was INSERT OR REPLACE with revoked taken from the object, so saving a
stale pre-revocation copy overwrote revoked, revocation_id and revoked_at.
Revocation is now monotonic in the store; the first revocation id and time win.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from delegation_authority.store import TokenStore
from field_core.delegation import DelegationToken


@pytest.fixture()
def store(tmp_path):
    return TokenStore(tmp_path / "tokens.sqlite3")


def _token(**kw) -> DelegationToken:
    now = datetime.now(timezone.utc)
    base = dict(agent_id="invoicing-agent", granted_by="grantor", scope=["read timesheets"],
                issued_at=now, expires_at=now + timedelta(hours=1))
    base.update(kw)
    return DelegationToken(**base)


def test_saving_a_stale_live_copy_does_not_unrevoke(store):
    live = store.save(_token())
    revoked = live.revoke().model_copy(update={"revocation_id": "rev-1"})
    won = store.save_revoked(revoked)
    assert won.revoked and won.revocation_id == "rev-1"

    store.save(live)  # the stale pre-revocation object

    after = store.get(live.token_id)
    assert after.revoked is True
    assert after.revocation_id == "rev-1"
    assert after.revoked_at == won.revoked_at


def test_a_second_revoked_save_keeps_the_first_revocation(store):
    live = store.save(_token())
    first = live.revoke().model_copy(update={"revocation_id": "rev-1"})
    store.save_revoked(first)
    second = live.revoke().model_copy(update={"revocation_id": "rev-2"})

    store.save(second)

    after = store.get(live.token_id)
    assert after.revocation_id == "rev-1"
    assert after.revoked_at == first.revoked_at


def test_resaving_a_live_token_still_updates_it(store):
    live = store.save(_token())
    store.save(live.model_copy(update={"scope": ["read timesheets", "draft invoices"]}))
    after = store.get(live.token_id)
    assert after.scope == ["read timesheets", "draft invoices"]
    assert after.revoked is False and after.revocation_id is None


def test_saving_a_revoked_token_for_the_first_time_records_it(store):
    revoked = _token().revoke().model_copy(update={"revocation_id": "rev-9"})
    store.save(revoked)
    after = store.get(revoked.token_id)
    assert after.revoked and after.revocation_id == "rev-9"


def test_ceiling_stays_stamped_once(store):
    live = store.save(_token(max_spend_usd=3.0))
    store.save(live.model_copy(update={"max_spend_usd": 999.0}))
    assert store.get(live.token_id).max_spend_usd == 3.0
