"""C-483 (reviewer PR 300, F-PR300-1..4): one active contract per NORMALISED org, atomic across writers, with a loud
warning on a database that already holds duplicates.

* `normalize_org` is the one spelling an org is compared by (NFKC, case-folded, whitespace collapsed); `save`,
  `for_org` and `_lists_org` use it, so a spelling variant is the same org;
* `save` is one `BEGIN IMMEDIATE` transaction and a partial unique index on the normalised key backs it: two stores on
  one file (threads) and eight spawned PROCESSES on one file cannot both win, and an IntegrityError is a 409-shaped
  ContractConflict. The index is what prevents a duplicate; the transaction is what keeps a lock error from surfacing;
* a database that already holds two active rows for one org opens (never refused), logs a warning naming the ids,
  skips the index, still resolves to the lowest contract id (as text) and still refuses a third.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from federation_broker import engine as engine_module
from federation_broker.api import create_app
from federation_broker.engine import (BrokerEngine, ContractConflict, ContractStore, FederationContract, _lists_org,
                                      normalize_org)

DEMO = Path(engine_module.__file__).resolve().parents[2] / "demo.sh"
README = Path(engine_module.__file__).resolve().parents[2] / "README.md"
BASE = dict(allowed_scopes=["exchange invoice status"], allowed_data_classes=["invoice metadata"])


def contract(cid, org="Acme Corp", active=True):
    """C-553: a contract WRITE now refuses a blank, control, zero-width or over-long org name (422), but these tests
    exercise how the STORE compares names, including the spellings a legacy row can still hold, so the model is built
    the way a stored row is (STORED_ROW context, which skips only the new name rule)."""
    return FederationContract.model_validate(
        dict(contract_id=cid, counterparty_org=org, active=active, **BASE), context={engine_module.STORED_ROW: True})


@pytest.fixture()
def store(tmp_path):
    s = ContractStore(tmp_path / "c.sqlite3")
    yield s
    s.close()


def index_exists(path) -> bool:
    c = sqlite3.connect(str(path))
    try:
        return c.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='contracts_one_active_per_org'").fetchone() is not None
    finally:
        c.close()


# ---- the helper -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("a,b", [
    ("Acme Corp", "ACME CORP"),
    ("Acme Corp", "  acme corp  "),
    ("Acme Corp", "Acme    Corp"),
    ("Acme Corp", "Acme\tCorp"),
    ("Acme Corp", "Acme Corp"),                    # no-break space
    ("Acme Corp", "Ａcme Corp"),                    # fullwidth A (NFKC)
    ("Straße AG", "STRASSE AG"),                   # casefold, not lower()
])
def test_spelling_variants_are_one_org(a, b):
    assert normalize_org(a) == normalize_org(b)


@pytest.mark.parametrize("a,b", [("Acme Corp", "Acme Corporation"), ("Acme Corp", "Acme-Corp"), ("Acme Corp", "Acne Corp")])
def test_different_orgs_stay_different(a, b):
    assert normalize_org(a) != normalize_org(b)


def test_a_whitespace_only_name_normalises_to_nothing_and_matches_nothing(store):
    assert normalize_org("  \t ") == ""
    store.save(contract("FED-1", org="Acme Corp"))
    store.save(contract("FED-BLANK", org="   "))           # accepted as before; it can never be looked up
    assert store.for_org("   ") is None
    assert _lists_org([{"org": "Acme Corp"}], "   ") is False


# ---- save, for_org and the peer rule use it -------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_ORG_NAME", "Spin State Labs")
    s = ContractStore(tmp_path / "api.sqlite3")
    yield TestClient(create_app(engine=BrokerEngine(store=s)))
    s.close()


def put(client, cid, org, active=True):
    return client.put(f"/contracts/{cid}", json={"contract_id": cid, "counterparty_org": org, "allowed_scopes": ["s"],
                                                 "allowed_data_classes": ["d"], "active": active})


@pytest.mark.parametrize("variant", ["ACME CORP", " acme  corp ", "Ａcme Corp"])
def test_a_spelling_variant_cannot_hold_a_second_active_contract(client, variant):
    assert put(client, "FED-1", "Acme Corp").status_code == 200
    r = put(client, "FED-2", variant)
    assert r.status_code == 409, r.text
    assert "FED-1" in r.text


def test_the_same_id_may_change_its_spelling(client):
    assert put(client, "FED-1", "Acme Corp").status_code == 200
    assert put(client, "FED-1", "ACME  CORP").status_code == 200


def test_for_org_finds_the_contract_by_any_spelling(store):
    store.save(contract("FED-1", org="Acme Corp"))
    for spelling in ("ACME CORP", " acme   corp", "Ａcme Corp"):
        assert store.for_org(spelling).contract_id == "FED-1"
    assert store.for_org("Acme Corporation") is None


def test_the_peer_rule_compares_normalised_names():
    assert _lists_org([{"org": "ACME   CORP Holdings"}], "acme corp")
    assert not _lists_org([{"org": "Other Co"}], "acme corp")


# ---- atomic across writers: threads, then real processes -------------------------------------------------------------

def test_two_stores_in_two_threads_on_one_file_cannot_both_register_an_active_contract(tmp_path):
    path = tmp_path / "race.sqlite3"
    a, b = ContractStore(path), ContractStore(path)
    try:
        for rnd in range(15):
            for s in (a, b):                                 # start each round with the org free
                for c in s.list():
                    s.save(contract(c.contract_id, org=c.counterparty_org, active=False))
            barrier, results = threading.Barrier(2), {}

            def run(name, s, cid, org):
                barrier.wait()
                try:
                    s.save(contract(cid, org=org))
                    results[name] = "ok"
                except ContractConflict:
                    results[name] = "conflict"

            ts = [threading.Thread(target=run, args=("a", a, f"FED-A{rnd}", "Acme Corp")),
                  threading.Thread(target=run, args=("b", b, f"FED-B{rnd}", "ACME  CORP"))]
            [t.start() for t in ts]
            [t.join() for t in ts]
            assert sorted(results.values()) == ["conflict", "ok"], (rnd, results)
            assert len([c for c in a.list() if c.active]) == 1
    finally:
        a.close()
        b.close()


def test_the_unique_index_exists_and_refuses_a_second_active_row_for_one_key(tmp_path):
    path = tmp_path / "idx.sqlite3"
    ContractStore(path).close()
    assert index_exists(path)
    c = sqlite3.connect(str(path))
    ins = ("INSERT INTO contracts (contract_id, counterparty_org, allowed_scopes, allowed_data_classes, active, org_key) "
           "VALUES (?, 'x', '[]', '[]', ?, 'acme corp')")
    c.execute(ins, ("FED-1", 1))
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(ins, ("FED-2", 1))
    c.execute(ins, ("FED-3", 0))                              # an inactive row is not covered by the index
    c.close()


def test_an_integrity_error_from_the_index_is_a_contract_conflict(store, tmp_path):
    # a row the application check cannot see (its text normalises differently from its key) but the index catches
    with store._lock, store._conn:
        store._conn.execute(
            "INSERT INTO contracts (contract_id, counterparty_org, allowed_scopes, allowed_data_classes, active, org_key) "
            "VALUES ('FED-HIDDEN', 'Something Else', ?, ?, 1, 'acme corp')", (json.dumps(["s"]), json.dumps(["d"])))
    with pytest.raises(ContractConflict, match="one active contract per org"):
        store.save(contract("FED-2", org="Acme Corp"))
    assert [c.contract_id for c in store.list()] == ["FED-HIDDEN"]          # the failed save left nothing behind


# ---- a database from before the rule --------------------------------------------------------------------------------

def old_database(path, rows):
    """rows: (contract_id, org) or (contract_id, org, active)."""
    c = sqlite3.connect(str(path))
    c.executescript("CREATE TABLE contracts (contract_id TEXT PRIMARY KEY, counterparty_org TEXT NOT NULL, "
                    "allowed_scopes TEXT NOT NULL, allowed_data_classes TEXT NOT NULL, contract_ref TEXT, active INTEGER NOT NULL DEFAULT 1);")
    for row in rows:
        cid, org, active = (*row, 1)[:3]
        c.execute("INSERT INTO contracts VALUES (?,?,?,?,NULL,?)", (cid, org, json.dumps(["s"]), json.dumps(["d"]), active))
    c.commit()
    c.close()


def test_a_clean_old_database_is_upgraded_in_place_and_gets_the_index(tmp_path):
    path = tmp_path / "old.sqlite3"
    old_database(path, [("FED-1", "Acme Corp"), ("FED-2", "Other Co")])
    s = ContractStore(path)
    try:
        assert index_exists(path)
        assert s.for_org("ACME CORP").contract_id == "FED-1"
    finally:
        s.close()


def test_a_database_with_duplicate_active_rows_opens_warns_and_skips_the_index(tmp_path, caplog):
    path = tmp_path / "dupes.sqlite3"
    old_database(path, [("FED-B", "Acme Corp"), ("FED-A", "ACME  CORP"), ("FED-C", "Other Co")])
    with caplog.at_level(logging.WARNING, logger="federation_broker.engine"):
        s = ContractStore(path)
    try:
        text = " ".join(r.getMessage() for r in caplog.records)
        assert "FED-A" in text and "FED-B" in text and "NOT created" in text
        assert not index_exists(path)
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="federation_broker.engine"):
            assert s.for_org("acme corp").contract_id == "FED-A"          # the lowest id, as text
        assert "lowest contract id" in " ".join(r.getMessage() for r in caplog.records)
        with pytest.raises(ContractConflict):                                # a third is still refused
            s.save(contract("FED-D", org="Acme Corp"))
    finally:
        s.close()


def test_a_single_active_contract_logs_no_warning(store, caplog):
    store.save(contract("FED-1"))
    with caplog.at_level(logging.WARNING, logger="federation_broker.engine"):
        assert store.for_org("Acme Corp").contract_id == "FED-1"
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


# ---- wording (F-PR300-3, F-PR300-4) ---------------------------------------------------------------------------------

def test_the_readme_says_what_a_legacy_database_resolves_to():
    text = README.read_text(encoding="utf-8")
    assert "lowest contract id" in text and "as text" in text


def test_the_readme_states_the_look_alike_limit_and_the_invisible_character_rule():
    text = " ".join(README.read_text(encoding="utf-8").split())
    assert "NOT merged: look-alike letters (Cyrillic or Greek)" in text
    assert "MERGED (dropped): every Unicode format" in text
    assert "KEPT as part of the name: visible marks" in text
    assert "chosen SUBSET" in text and "U+16FE4" in text
    for word in ("variation selectors", "Hangul fillers", "Khmer inherent vowels", "Braille blank", "grapheme joiner"):
        assert word in text, word


def test_the_demo_does_not_claim_nothing_is_masked():
    text = DEMO.read_text(encoding="utf-8")
    assert "nothing is masked" not in text
    assert "`|| true`" in text and "assertion that follows" in text


# ---- reviewer C-565 -------------------------------------------------------------------------------------------------

def test_begin_immediate_alone_protects_a_database_that_has_no_index(tmp_path, monkeypatch):
    """F-C565-1: on a legacy database holding duplicate active rows the index is skipped, so BEGIN IMMEDIATE is the
    only thing that stops two writers both passing the check. The check is widened (a pause while it reads the legacy
    rows) so that without the transaction both writers get through; with it the second waits and sees the first."""
    path = tmp_path / "legacy.sqlite3"
    old_database(path, [("L-1", "Legacy Org"), ("L-2", "Legacy Org")])
    a, b = ContractStore(path), ContractStore(path)
    assert not index_exists(path)
    real = engine_module.normalize_org

    def slow(org):
        if org == "Legacy Org":
            time.sleep(0.05)                                  # inside save's check, between its SELECT and its INSERT
        return real(org)

    monkeypatch.setattr(engine_module, "normalize_org", slow)
    try:
        for rnd in range(5):
            barrier, results = threading.Barrier(2), {}
            for s_ in (a, b):
                for c in s_.list():
                    if real(c.counterparty_org) == "acme corp":
                        s_.save(contract(c.contract_id, org=c.counterparty_org, active=False))

            def run(name, s_, cid, org):
                barrier.wait()
                try:
                    s_.save(contract(cid, org=org))
                    results[name] = "ok"
                except ContractConflict:
                    results[name] = "conflict"

            ts = [threading.Thread(target=run, args=("a", a, f"FED-A{rnd}", "Acme Corp")),
                  threading.Thread(target=run, args=("b", b, f"FED-B{rnd}", "ACME  CORP"))]
            [t.start() for t in ts]
            [t.join() for t in ts]
            assert sorted(results.values()) == ["conflict", "ok"], (rnd, results)
            assert len([c for c in a.list() if c.active and normalize_org(c.counterparty_org) == "acme corp"]) == 1
    finally:
        a.close()
        b.close()


def test_a_deactivated_contract_resolves_to_nothing_and_blocks_an_inbound_crossing(tmp_path, monkeypatch):
    """F-C565-2: `for_org` is the only place the active flag decides; a deactivated contract must not authorise."""
    from test_federation_broker import COUNTERPARTY, counterparty_manifest
    monkeypatch.setenv("FIELD_ORG_NAME", "Spin State Labs")
    s_ = ContractStore(tmp_path / "off.sqlite3")
    try:
        c = TestClient(create_app(engine=BrokerEngine(store=s_)))
        assert put(c, "FED-OFF", COUNTERPARTY, active=False).status_code == 200
        assert s_.for_org(COUNTERPARTY) is None
        r = c.post("/crossing", json={
            "counterparty_org": COUNTERPARTY, "counterparty_agent_id": "borealis-billing-agent",
            "counterparty_manifest": counterparty_manifest(), "scope": "exchange invoice status",
            "data_class": "invoice metadata"}).json()
        assert r["decision"] == "BLOCK" and "no active federation contract" in r["reasons"][0], r
    finally:
        s_.close()


def test_re_registering_an_id_replaces_its_scopes_classes_and_org(store):
    """F-C565-3: the upsert must update every column; a narrower re-registration must not keep the wider scopes, and
    the old org's key must go (else a new contract for that org would get a 409 although none is active)."""
    store.save(FederationContract(contract_id="FED-1", counterparty_org="Acme", allowed_scopes=["a", "b"],
                                  allowed_data_classes=["x", "y"], contract_ref="old"))
    store.save(FederationContract(contract_id="FED-1", counterparty_org="Beta", allowed_scopes=["a"],
                                  allowed_data_classes=["x"], contract_ref="new"))
    (only,) = store.list()
    assert (only.counterparty_org, only.allowed_scopes, only.allowed_data_classes, only.contract_ref) == \
        ("Beta", ["a"], ["x"], "new")
    assert store.for_org("Acme") is None and store.for_org("beta").contract_id == "FED-1"
    store.save(contract("FED-2", org="Acme"))                  # no stale key: Acme is free again


def test_an_old_database_with_one_inactive_and_one_active_row_of_an_org_gets_the_index(tmp_path):
    """F-C565-4: the documented rotation (deactivate the old contract, register a new id) leaves exactly this."""
    path = tmp_path / "rotated.sqlite3"
    old_database(path, [("FED-OLD", "Acme Corp", 0), ("FED-NEW", "ACME  CORP", 1)])
    s_ = ContractStore(path)
    try:
        assert index_exists(path)
        assert s_.for_org("acme corp").contract_id == "FED-NEW"
    finally:
        s_.close()


CF_CHARS = [("\u200b", "zero-width space"), ("\u00ad", "soft hyphen"), ("\u200e", "left-to-right mark"),
            ("\ufeff", "byte-order mark"), ("\u180e", "Mongolian vowel separator"),
            ("\u200d", "zero-width joiner"), ("\u200c", "zero-width non-joiner")]


@pytest.mark.parametrize("ch,name", CF_CHARS, ids=[n for _, n in CF_CHARS])
def test_an_invisible_format_character_does_not_make_another_org(ch, name, store):
    """F-C565-5: category Cf characters are dropped, so the visually identical names are one org."""
    assert unicodedata.category(ch) == "Cf"
    assert normalize_org(f"Acme{ch} Corp") == normalize_org("Acme Corp") == normalize_org(f"Ac{ch}me Corp{ch}")
    store.save(contract("FED-1", org="Acme Corp"))
    with pytest.raises(ContractConflict):
        store.save(contract("FED-2", org=f"Acme{ch} Corp"))
    assert store.for_org(f"Acme{ch}Corp".replace("Corp", " Corp")).contract_id == "FED-1"


@pytest.mark.parametrize("other,why", [
    ("\u0410cme Corp", "Cyrillic A looks like Latin A"),
    ("Acme Corp.", "a trailing dot is punctuation"),
    ("Acme-Corp", "a hyphen is punctuation"),
    ("\u0391cme Corp", "Greek capital alpha looks like Latin A"),
])
def test_a_look_alike_or_punctuation_variant_is_still_another_org_a_documented_limit(other, why):
    """The limit stated in the README: confusables and punctuation are not merged (an authenticated operator can
    register such a name; the match is exact on what NFKC, case folding and Cf-dropping leave)."""
    assert normalize_org(other) != normalize_org("Acme Corp"), why


def test_the_peer_rule_normalises_the_org_it_is_asked_about():
    """C-565 6a: the needle, not only the peer side, goes through normalize_org."""
    peers = [{"org": "Acme Corp Holdings"}]
    assert _lists_org(peers, "ACME   CORP")
    assert _lists_org(peers, "Acme\u200b Corp")
    assert not _lists_org(peers, "Acme Cor p")


# ---- invisible characters outside Cf (reviewer C-578 F-C578-1, C-583) ---------------------------------------------

NON_CF_INVISIBLES = [
    ("\u034f", "combining grapheme joiner"), ("\ufe00", "variation selector-1"), ("\ufe0f", "variation selector-16"),
    ("\U000e0100", "variation selector-17"), ("\U000e01ef", "variation selector-256"),
    ("\u115f", "Hangul choseong filler"), ("\u1160", "Hangul jungseong filler"), ("\u3164", "Hangul filler"),
    ("\uffa0", "halfwidth Hangul filler"), ("\u17b4", "Khmer vowel inherent aq"), ("\u17b5", "Khmer vowel inherent aa"),
    ("\u2800", "Braille pattern blank"),
    ("\u180b", "Mongolian free variation selector one"), ("\u180c", "Mongolian free variation selector two"),
    ("\u180d", "Mongolian free variation selector three"), ("\u180f", "Mongolian free variation selector four"),
]


@pytest.mark.parametrize("ch,name", NON_CF_INVISIBLES, ids=[n for _, n in NON_CF_INVISIBLES])
def test_an_invisible_character_outside_cf_does_not_make_another_org(ch, name, store):
    assert normalize_org(f"Acme{ch} Corp") == normalize_org("Acme Corp") == normalize_org(f"{ch}Ac{ch}me Corp{ch}")
    store.save(contract("FED-1", org="Acme Corp"))
    with pytest.raises(ContractConflict):
        store.save(contract("FED-2", org=f"Acme{ch} Corp"))
    assert store.for_org(f"Acme{ch} Corp").contract_id == "FED-1"


@pytest.mark.parametrize("ch,why", [
    ("\u20dd", "combining enclosing circle: a visible mark"),
    ("\ufe20", "combining ligature left half: a visible mark in the same block region as the selectors"),
    ("\U000e01f0", "just above the variation selector supplement"),
    ("\u2801", "Braille dot-1: a visible pattern, only the blank is dropped"),
    ("\u1161", "Hangul jungseong A: a real letter next to the fillers"),
    ("\u17b6", "Khmer vowel sign AA: visible, next to the inherent vowels"),
    ("\u034e", "just below the combining grapheme joiner"),
    ("\u1810", "Mongolian digit zero, just above the free variation selectors"),
    ("\u180a", "Mongolian nirugu, just below them"),
    ("\u2065", "reserved default-ignorable code point, left out on purpose (README)"),
    ("\U00016fe4", "Khitan small script filler, left out on purpose (README)"),
])
def test_a_visible_or_neighbouring_character_still_keeps_an_org_distinct(ch, why):
    assert normalize_org(f"Acme{ch} Corp") != normalize_org("Acme Corp"), why


@pytest.mark.parametrize("with_mark,without_mark", [
    ("\u0915\u0947", "\u0915"),                      # Hindi ka + vowel sign E (Mn) vs ka
    ("\u0e17\u0e35\u0e48", "\u0e17\u0e35"),        # Thai tho + vowel sign II + tone mai ek (Mn) vs without the tone mark
    ("\u0e01\u0e47", "\u0e01"),                      # Thai ko + maitaikhu (Mn)
    ("\u1780\u17c1", "\u1780"),                      # Khmer ka + vowel sign E (Mc) vs ka
    ("\u1780\u17d2\u1781", "\u1780\u1781"),        # Khmer ka + coeng (Mn) + kha vs ka kha: the subscript sign is kept
    ("\u0928\u093f", "\u0928"),                      # Hindi na + vowel sign I (Mc) vs na
])
def test_the_combining_marks_of_other_scripts_are_part_of_the_name(with_mark, without_mark):
    for ch in with_mark:
        assert unicodedata.category(ch) in {"Lo", "Mn", "Mc"}
    assert normalize_org(f"{with_mark} Corp") != normalize_org(f"{without_mark} Corp")


# ---- the documented joiner collision (Don, round 3) ----------------------------------------------------------------

@pytest.mark.parametrize("joined,plain", [
    ("\u06a9\u062a\u0627\u0628\u200c\u0647\u0627", "\u06a9\u062a\u0627\u0628\u0647\u0627"),   # Persian kitab+ZWNJ+ha
    ("\u0915\u094d\u200d\u0937", "\u0915\u094d\u0937"),                                          # Hindi conjunct with ZWJ
    ("Acme\u200d Corp", "Acme Corp"),
    ("Acme\u200c Corp", "Acme Corp"),
])
def test_a_joiner_joined_name_is_the_same_org_as_the_plain_name_a_documented_collision(joined, plain, store):
    assert unicodedata.category("\u200d") == "Cf" == unicodedata.category("\u200c")
    assert joined != plain and normalize_org(joined) == normalize_org(plain)
    store.save(contract("FED-1", org=plain))
    with pytest.raises(ContractConflict):                     # the false 409 the README documents
        store.save(contract("FED-2", org=joined))
    assert store.for_org(joined).contract_id == "FED-1"
    assert store.list()[0].counterparty_org == plain          # the stored name is unchanged


def test_the_readme_documents_the_joiner_collision():
    text = " ".join(README.read_text(encoding="utf-8").split())
    assert "the joiner collision" in text and "two DIFFERENT names are ONE org" in text
    assert "false 409" in text and "never a bypass" in text and "keep merging joiners" in text


# ---- spawned processes (reviewer C-864 F-C864-1) ---------------------------------------------------------------------

_WORKER = r"""
import sys, time
from federation_broker import engine
from federation_broker.engine import ContractConflict, ContractStore, FederationContract
path, worker, rounds, t0 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
real = engine.normalize_org
def slow(org):                                              # widens the window between save's check and its insert
    time.sleep(0.01)
    return real(org)
engine.normalize_org = slow
spell = ["Acme {r} Corp", "ACME  {r} CORP", " acme {r} corp ", "Acme\u200b {r} Corp", "\uff21cme {r} Corp",
         "acme\t{r} corp", "ACME {r}  corp", "Acme {r}\u00a0Corp"]
store = ContractStore(path)
out = []
for r in range(rounds):
    time.sleep(max(0.0, t0 + r * 1.0 - time.time()))        # every worker starts round r at the same wall-clock moment
    org = spell[worker % len(spell)].format(r=r)
    try:
        store.save(FederationContract.model_validate(
            dict(contract_id=f"FED-W{worker}-R{r}", counterparty_org=org, allowed_scopes=["s"],
                 allowed_data_classes=["d"]), context={"federation_broker.stored_row": True}))
        out.append("ok")
    except ContractConflict:
        out.append("conflict")
    except Exception as exc:                               # a lock error surfacing is a failure, not a conflict
        out.append("error:" + type(exc).__name__ + ":" + str(exc))
store.close()
print("|".join(out))
"""


@pytest.mark.parametrize("legacy", [False, True], ids=["with the unique index", "legacy database, no index"])
def test_eight_spawned_processes_on_one_file_register_exactly_one_active_contract_per_round(tmp_path, legacy):
    """Eight real processes, one file, a wall-clock barrier per round. With the index it is the backstop; on a database
    that already holds duplicate active rows the index is skipped and BEGIN IMMEDIATE is the only protection."""
    import subprocess
    import sys

    path, workers, rounds = tmp_path / "procs.sqlite3", 8, 5
    if legacy:
        old_database(path, [("L-1", "Legacy Org"), ("L-2", "Legacy Org")])
    ContractStore(path).close()                            # upgrade in place; the index exists only on a clean file
    assert index_exists(path) is (not legacy)
    t0 = time.time() + 6.0                                 # leaves time for 8 interpreters to import and open the file
    procs = [subprocess.Popen([sys.executable, "-c", _WORKER, str(path), str(w), str(rounds), repr(t0)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for w in range(workers)]
    outs = []
    for p in procs:
        out, err = p.communicate(timeout=180)
        assert p.returncode == 0, err
        outs.append(out.strip().split("|"))
    for r in range(rounds):
        results = [o[r] for o in outs]
        assert results.count("ok") == 1, (r, results)
        assert results.count("conflict") == workers - 1, (r, results)    # and no lock error surfaced
    s_ = ContractStore(path)
    try:
        new = [c for c in s_.list() if c.active and not c.contract_id.startswith("L-")]
        assert len(new) == rounds and len({normalize_org(c.counterparty_org) for c in new}) == rounds
    finally:
        s_.close()


def test_the_readme_says_the_index_prevents_duplicates_and_the_transaction_prevents_lock_errors():
    text = " ".join(README.read_text(encoding="utf-8").split())
    assert "the partial unique index is what prevents a duplicate active row" in text
    assert "BEGIN IMMEDIATE` write transaction is what makes the loser a clean 409" in text
