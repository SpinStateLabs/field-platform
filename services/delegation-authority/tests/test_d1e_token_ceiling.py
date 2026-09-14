"""v1.2 D1e, delegation half: a rostered mint stamps the grantor row's
``max_spend_usd`` on the token, and ``/introspect`` returns it with
``issued_at`` so conformance-sentinel can enforce it as ``E.spend_cap``.

The ceiling lives in a side table (``token_spend_ceilings``), not a new
``tokens`` column: a pre-D1e image writes ``tokens`` with a positional
9-value INSERT, which a 10-column table refuses, so a column would break every
mint AND revoke after an image rollback. ``test_a_pre_d1e_store_*`` pins both
directions with the HEAD statements, verbatim.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from delegation_authority.store import TokenStore
from field_core.delegation import DelegationToken
# Sibling-module import (not ``tests.``): CI also runs this directory from the
# repo root, where only the tests directory itself is on sys.path.
from test_doa_roster import GRANTOR, Spine, write_manifest, write_roster

#: The mint/GET response keys before D1e. A token with no ceiling still
#: answers exactly these, so an older field-agent SDK (``DelegationToken``
#: with extra='forbid') keeps parsing it.
PRE_D1E_TOKEN_KEYS = {"token_id", "agent_id", "granted_by", "scope", "issued_at",
                      "expires_at", "revoked", "revocation_id", "revoked_at"}

#: tokens DDL and the save() INSERT at HEAD 3aa90ff, verbatim.
PRE_D1E_SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
    token_id      TEXT PRIMARY KEY,
    agent_id      TEXT NOT NULL,
    granted_by    TEXT NOT NULL,
    scope         TEXT NOT NULL,           -- JSON array
    issued_at     TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    revoked       INTEGER NOT NULL DEFAULT 0,
    revocation_id TEXT,
    revoked_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_tokens_agent ON tokens (agent_id);
"""
PRE_D1E_INSERT = "INSERT OR REPLACE INTO tokens VALUES (?,?,?,?,?,?,?,?,?)"


@pytest.fixture()
def roster_env(tmp_path, monkeypatch):
    def arm(**row):
        monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path, **row)))
    return arm


def test_a_rostered_mint_stamps_the_rows_max_spend_usd_and_introspect_returns_it(tmp_path, roster_env):
    roster_env(max_spend_usd=12.5)
    spine = Spine(tmp_path, write_manifest(tmp_path))
    r = spine.mint()
    assert r.status_code == 201, r.text
    token = r.json()
    assert token["max_spend_usd"] == 12.5
    assert spine.delegation.get(f"/tokens/{token['token_id']}").json()["max_spend_usd"] == 12.5
    assert [t["max_spend_usd"] for t in spine.delegation.get("/tokens").json()] == [12.5]

    intro = spine.delegation.post("/introspect", json={"token_id": token["token_id"]}).json()
    assert intro["active"] is True and intro["max_spend_usd"] == 12.5
    assert datetime.fromisoformat(intro["issued_at"]) == datetime.fromisoformat(token["issued_at"])
    # the ledger row already carried the roster value (B1); unchanged
    assert spine.mint_events()[-1]["payload"]["doa_row"]["max_spend_usd"] == 12.5


def test_a_zero_ceiling_is_stamped_not_dropped(tmp_path, roster_env):
    roster_env(max_spend_usd=0.0)
    spine = Spine(tmp_path, write_manifest(tmp_path))
    token = spine.mint().json()
    intro = spine.delegation.post("/introspect", json={"token_id": token["token_id"]}).json()
    assert token["max_spend_usd"] == 0.0 and intro["max_spend_usd"] == 0.0


def test_no_ceiling_leaves_the_token_shape_as_it_was(tmp_path, roster_env, monkeypatch):
    """Roster row without max_spend_usd, and the roster unset: no ceiling,
    the token JSON keeps its pre-D1e keys, introspect says null (with issued_at)."""
    roster_env(max_spend_usd=None)
    spine = Spine(tmp_path, write_manifest(tmp_path))
    rostered = spine.mint()
    monkeypatch.delenv("FIELD_DOA_ROSTER")
    unrostered = spine.mint()
    for r in (rostered, unrostered):
        assert r.status_code == 201, r.text
        assert set(r.json()) == PRE_D1E_TOKEN_KEYS
        assert set(spine.delegation.get(f"/tokens/{r.json()['token_id']}").json()) == PRE_D1E_TOKEN_KEYS
        intro = spine.delegation.post("/introspect", json={"token_id": r.json()["token_id"]}).json()
        assert intro["max_spend_usd"] is None and intro["issued_at"] is not None
    unknown = spine.delegation.post("/introspect", json={"token_id": "nope"}).json()
    assert unknown["active"] is False and unknown["max_spend_usd"] is None and unknown["issued_at"] is None


def test_revoke_keeps_the_ceiling_and_a_later_save_cannot_change_it(tmp_path, roster_env):
    roster_env(max_spend_usd=3.0)
    spine = Spine(tmp_path, write_manifest(tmp_path))
    token_id = spine.mint().json()["token_id"]
    revoked = spine.delegation.post(f"/tokens/{token_id}/revoke").json()
    assert revoked["revoked"] is True and revoked["max_spend_usd"] == 3.0
    store = spine.delegation.app.state.store
    for attempt in (None, 999.0):
        returned = store.save(store.get(token_id).model_copy(update={"max_spend_usd": attempt}))
        assert returned.max_spend_usd == 3.0, attempt  # save answers what is stored
        assert store.get(token_id).max_spend_usd == 3.0, attempt


def _token(**kw) -> DelegationToken:
    now = datetime.now(timezone.utc)
    base = dict(agent_id="invoicing-agent", granted_by=GRANTOR, scope=["read timesheets"],
                issued_at=now, expires_at=now + timedelta(hours=1))
    base.update(kw)
    return DelegationToken(**base)


def _pre_d1e_row(token: DelegationToken) -> tuple:
    return (token.token_id, token.agent_id, token.granted_by, json.dumps(token.scope),
            token.issued_at.isoformat(), token.expires_at.isoformat(), int(token.revoked),
            token.revocation_id, token.revoked_at.isoformat() if token.revoked_at else None)


def test_a_pre_d1e_store_opens_and_its_tokens_read_without_a_ceiling(tmp_path):
    path = tmp_path / "tokens.sqlite3"
    legacy = _token()
    conn = sqlite3.connect(path)
    with conn:
        conn.executescript(PRE_D1E_SCHEMA)
        conn.execute(PRE_D1E_INSERT, _pre_d1e_row(legacy))
    conn.close()

    store = TokenStore(path)
    try:
        assert store.get(legacy.token_id).max_spend_usd is None
        stamped = store.save(_token(max_spend_usd=7.0))
        assert [t.max_spend_usd for t in store.list()] == [None, 7.0]
        assert store.get(stamped.token_id).max_spend_usd == 7.0
    finally:
        store.close()


def test_a_pre_d1e_image_can_still_mint_and_revoke_after_d1e_opened_the_file(tmp_path):
    """Image rollback: once this store has opened (and written) the file, the
    HEAD positional INSERT still succeeds for a new mint and for a revoke of a
    stamped token; rolling forward again reads the ceiling back."""
    path = tmp_path / "tokens.sqlite3"
    store = TokenStore(path)
    stamped = store.save(_token(max_spend_usd=2.0))
    store.close()

    conn = sqlite3.connect(path)
    with conn:
        conn.execute(PRE_D1E_INSERT, _pre_d1e_row(_token()))            # old image mints
        conn.execute(PRE_D1E_INSERT, _pre_d1e_row(stamped.revoke()))    # old image revokes
    conn.close()

    store = TokenStore(path)
    try:
        again = store.get(stamped.token_id)
        assert again.revoked is True and again.max_spend_usd == 2.0
        assert len(store.list()) == 2
    finally:
        store.close()
