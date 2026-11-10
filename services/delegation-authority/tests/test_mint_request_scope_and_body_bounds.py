"""S4-7: (1) MintRequest accepted scope [''] or ['  '] and a blank granted_by: with FIELD_DOA_ROSTER unset (the default)
the service minted an active token whose scope could only ever match a blank action. Scope entries are now stripped,
blank ones refused, exact duplicates dropped keeping order, the list capped at 100 entries and each entry at 200
characters; a blank-after-strip granted_by is refused. (2) POST /oauth/introspect read the whole body and decoded all
of it: it now answers 413 over 16 KiB, before decoding, without reading the rest."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import MintRequest, create_app as create_delegation_app
from delegation_authority.clients import LedgerClient, RegistryClient
from delegation_authority.store import TokenStore
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

AGENT_ID = "invoicing-agent"
GRANTOR = "Controller, Spin State Labs"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
MARK = "MADE-UP-MARKER-0123456789"
LIMIT = 16 * 1024


@pytest.fixture()
def spine(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_DOA_ROSTER", raising=False)
    store = TokenStore(tmp_path / "tokens.sqlite3")
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    delegation = TestClient(create_delegation_app(
        store=store, ledger=LedgerClient(client=ledger, base_url="http://t"),
        registry=RegistryClient(client=registry, base_url="http://t")))
    registry.post("/agents", json={"agent_id": AGENT_ID, "name": "Invoice Drafting Copilot",
                                   "owner": GRANTOR, "domain": "finance"})
    return delegation, store


def body(**kw):
    b = {"agent_id": AGENT_ID, "granted_by": GRANTOR, "scope": ["read timesheets"], "ttl_seconds": 3600}
    b.update(kw)
    return b


# ---- (1) the request model -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("scope", [[""], ["  "], ["\t"], ["read timesheets", ""], ["ok", " \n "], [" ", " "]])
def test_a_blank_scope_entry_is_refused_by_the_model_and_mints_nothing(spine, scope):
    delegation, store = spine
    with pytest.raises(ValidationError):
        MintRequest(**body(scope=scope))
    r = delegation.post("/tokens", json=body(scope=scope))
    assert r.status_code == 422, r.text
    assert store.list() == []


@pytest.mark.parametrize("granted_by", ["", " ", "   ", "\t\n"])
def test_a_blank_grantor_is_refused_and_mints_nothing(spine, granted_by):
    delegation, store = spine
    r = delegation.post("/tokens", json=body(granted_by=granted_by))
    assert r.status_code == 422, r.text
    assert store.list() == []


def test_scope_entries_are_stripped_and_exact_duplicates_dropped_in_order():
    m = MintRequest(**body(scope=[" read timesheets ", "draft invoices", "read timesheets", "draft invoices ", "x"]))
    assert m.scope == ["read timesheets", "draft invoices", "x"]


def test_a_scope_with_spaces_inside_an_entry_is_untouched():
    assert MintRequest(**body(scope=["send invoice email"])).scope == ["send invoice email"]


def test_the_scope_list_is_capped_at_100_entries_and_each_entry_at_200_characters():
    assert len(MintRequest(**body(scope=[f"s{i}" for i in range(100)])).scope) == 100
    with pytest.raises(ValidationError):
        MintRequest(**body(scope=[f"s{i}" for i in range(101)]))
    assert MintRequest(**body(scope=["a" * 200])).scope == ["a" * 200]
    with pytest.raises(ValidationError):
        MintRequest(**body(scope=["a" * 201]))


def test_an_empty_scope_is_still_refused():
    with pytest.raises(ValidationError):
        MintRequest(**body(scope=[]))


def test_a_good_mint_still_works_and_stores_the_cleaned_scope(spine):
    delegation, store = spine
    r = delegation.post("/tokens", json=body(scope=[" read timesheets ", "read timesheets", "draft invoices"]))
    assert r.status_code == 201, r.text
    assert r.json()["scope"] == ["read timesheets", "draft invoices"]
    assert [t.scope for t in store.list()] == [["read timesheets", "draft invoices"]]


def test_the_422_for_a_bad_scope_repeats_nothing_it_was_sent(spine):
    delegation, _ = spine
    for scope in ([MARK + " ", " "], [MARK * 50], [MARK + str(i) for i in range(150)]):
        r = delegation.post("/tokens", json=body(scope=scope))
        assert r.status_code == 422 and MARK not in r.text, r.text


# ---- (2) the /oauth/introspect body cap ------------------------------------------------------------------------------


def mint_token(delegation):
    r = delegation.post("/tokens", json=body())
    assert r.status_code == 201, r.text
    return r.json()["token_id"]


def test_a_normal_form_body_still_introspects(spine):
    delegation, _ = spine
    tid = mint_token(delegation)
    r = delegation.post("/oauth/introspect", content=f"token={tid}", headers=FORM)
    assert r.status_code == 200 and r.json()["active"] is True


def test_a_body_exactly_at_the_cap_is_read_and_one_byte_over_is_413(spine):
    delegation, _ = spine
    at_cap = "token=" + "x" * (LIMIT - len("token="))
    assert len(at_cap) == LIMIT
    r = delegation.post("/oauth/introspect", content=at_cap, headers=FORM)
    assert r.status_code == 200 and r.json() == {"active": False}
    r = delegation.post("/oauth/introspect", content=at_cap + "x", headers=FORM)
    assert r.status_code == 413, r.text


def test_a_huge_declared_body_is_413_and_does_not_echo_it(spine):
    delegation, _ = spine
    r = delegation.post("/oauth/introspect", content="token=" + MARK * 200_000, headers=FORM)
    assert r.status_code == 413 and MARK not in r.text


def test_a_chunked_body_with_no_content_length_is_capped_too(spine):
    delegation, _ = spine

    def chunks():
        for _ in range(64):
            yield b"token=" + b"y" * 1000

    r = delegation.post("/oauth/introspect", content=chunks(), headers=FORM)
    assert r.status_code == 413, r.text


def test_an_inactive_answer_is_unchanged_and_an_empty_token_is_still_400(spine):
    delegation, _ = spine
    assert delegation.post("/oauth/introspect", content="token=nope", headers=FORM).json() == {"active": False}
    assert delegation.post("/oauth/introspect", content="token=", headers=FORM).status_code == 400


# ---- the reader itself: a declared oversize body is refused before a byte is read -------------------------------------


class _StubRequest:
    def __init__(self, headers, chunks):
        self.headers = headers
        self._chunks = chunks
        self.read = 0

    async def stream(self):
        for c in self._chunks:
            self.read += 1
            yield c


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_a_declared_oversize_body_is_refused_without_reading_any_of_it():
    from fastapi import HTTPException
    from delegation_authority.api import _read_capped

    req = _StubRequest({"content-length": str(LIMIT + 1)}, [b"x"] * 5)
    with pytest.raises(HTTPException) as exc:
        _run(_read_capped(req, LIMIT))
    assert exc.value.status_code == 413 and req.read == 0


def test_an_undeclared_oversize_body_is_abandoned_at_the_cap_not_read_to_the_end():
    from fastapi import HTTPException
    from delegation_authority.api import _read_capped

    req = _StubRequest({}, [b"y" * 4096] * 100)                      # 400 KiB in 100 chunks, no Content-Length
    with pytest.raises(HTTPException) as exc:
        _run(_read_capped(req, LIMIT))
    assert exc.value.status_code == 413 and req.read == 5            # the 5th chunk crosses 16 KiB; the rest is never read


def test_a_body_within_the_cap_is_returned_whole():
    from delegation_authority.api import _read_capped

    req = _StubRequest({"content-length": "6"}, [b"abc", b"def"])
    assert _run(_read_capped(req, LIMIT)) == b"abcdef"
