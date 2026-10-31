"""C-553 (reviewer C-521 F-C521-3 and F-C521-4): every contract WRITE leaves a ledger record, and an org name is
validated on write by the same normaliser the store compares by.

* ``federation.contract.<registered|replaced|deactivated|refused>`` with the contract id, the org, active before and
  after, whether a key is present before and after and a 12-digit fingerprint of the PUBLIC key at most (never a key);
  the operator fields come from ``operator_auth.merge_payload`` like every other service's write record;
* four writes (create, move to another org, a second active contract refused, deactivate) are exactly four events,
  and one write is one event;
* a ledger that cannot be reached never undoes or refuses a write (as the crossing records), and says so in the log;
* a blank, over-long, control, format, separator, private-use, unassigned or combining-only org name is refused
  (422) before anything is stored or ledgered, and the refusal never quotes the name; rows stored before the rule
  still list;
* a ledger delivery failure is counted on ``/health`` (``contract_ledger_gaps``), by count only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from federation_broker import engine as engine_module
from federation_broker.api import create_app
from federation_broker.engine import ORG_NAME_MAX, BrokerEngine, ContractStore, validate_org_name

README = Path(engine_module.__file__).resolve().parents[2] / "README.md"
BASE = dict(allowed_scopes=["exchange invoice status"], allowed_data_classes=["invoice metadata"])
CANARY = "CANARYORG-7Q2X"


class RecordingLedger:
    def __init__(self, fail: Exception | None = None):
        self.events: list[tuple[str, dict, str | None]] = []
        self.fail = fail
        self.lock = threading.Lock()

    def append(self, event_type, payload, agent_id=None):
        if self.fail is not None:
            raise self.fail
        with self.lock:
            self.events.append((event_type, payload, agent_id))
        return {}

    def types(self):
        return [e[0] for e in self.events]


def public_pem() -> str:
    key = Ed25519PrivateKey.generate().public_key()
    return key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def body(cid, org="Acme Corp", active=True, **extra):
    return {"contract_id": cid, "counterparty_org": org, "active": active, **BASE, **extra}


@pytest.fixture()
def stack(tmp_path):
    ledger = RecordingLedger()
    engine = BrokerEngine(store=ContractStore(tmp_path / "c.sqlite3"), ledger=ledger)
    client = TestClient(create_app(engine=engine))
    yield client, ledger, engine, tmp_path / "c.sqlite3"
    engine.store.close()


def put(client, cid, **kw):
    return client.put(f"/contracts/{cid}", json=body(cid, **kw))


# -- F-C521-3: four writes, four events ---------------------------------------------------------------------------

def test_four_writes_create_move_refused_second_active_and_deactivate_are_exactly_four_events(stack):
    client, ledger, _engine, _ = stack
    assert put(client, "FED-1", org="Acme Corp").status_code == 200                   # create
    assert put(client, "FED-1", org="Beta Inc").status_code == 200                    # the contract moves to another org
    assert put(client, "FED-2", org="Beta Inc").status_code == 409                    # a second active contract for Beta
    assert put(client, "FED-1", org="Beta Inc", active=False).status_code == 200      # deactivate
    assert ledger.types() == ["federation.contract.registered", "federation.contract.replaced",
                              "federation.contract.refused", "federation.contract.deactivated"]


def test_the_registered_event_names_the_contract_the_org_and_the_state(stack):
    client, ledger, *_ = stack
    put(client, "FED-1", org="Acme Corp")
    (kind, payload, agent), = ledger.events
    assert kind == "federation.contract.registered" and agent is None
    assert payload["contract_id"] == "FED-1" and payload["counterparty_org"] == "Acme Corp"
    assert payload["active_after"] is True and payload["key_present_after"] is False
    assert payload["key_fp_after"] is None
    assert "active_before" not in payload and "org_before" not in payload   # a new id has no 'before'


def test_a_move_records_the_org_it_left_and_active_before_and_after(stack):
    client, ledger, *_ = stack
    put(client, "FED-1", org="Acme Corp")
    put(client, "FED-1", org="Beta Inc")
    _, payload, _ = ledger.events[-1]
    assert payload["org_before"] == "acme corp" and payload["counterparty_org"] == "Beta Inc"
    assert payload["active_before"] is True and payload["active_after"] is True


def test_a_deactivation_is_its_own_kind_and_a_reactivation_is_a_replace(stack):
    client, ledger, *_ = stack
    put(client, "FED-1")
    put(client, "FED-1", active=False)
    put(client, "FED-1", active=True)
    assert ledger.types()[1:] == ["federation.contract.deactivated", "federation.contract.replaced"]
    _, payload, _ = ledger.events[1]
    assert payload["active_before"] is True and payload["active_after"] is False
    _, payload, _ = ledger.events[2]
    assert payload["active_before"] is False and payload["active_after"] is True


def test_the_refused_event_names_the_contract_that_holds_the_org(stack):
    client, ledger, *_ = stack
    put(client, "FED-1", org="Acme Corp")
    assert put(client, "FED-2", org="ACME  corp").status_code == 409       # a spelling variant of the same org
    kind, payload, _ = ledger.events[-1]
    assert kind == "federation.contract.refused"
    assert payload["contract_id"] == "FED-2" and payload["other_contract_id"] == "FED-1"
    assert payload["reason"] == "one_active_contract_per_org" and payload["active_after"] is True


# -- the key is never in an event ---------------------------------------------------------------------------------

def test_a_key_swap_and_a_key_removal_are_recorded_as_a_fingerprint_change_and_never_carry_a_key(stack):
    client, ledger, engine, _ = stack
    k1, k2 = public_pem(), public_pem()
    assert put(client, "FED-1", counterparty_pubkey_pem=k1).status_code == 200
    assert put(client, "FED-1", counterparty_pubkey_pem=k2).status_code == 200       # a key swap under the same id
    assert put(client, "FED-1").status_code == 200                                   # the key removed
    reg, swap, removed = (e[1] for e in ledger.events)
    stored1 = engine_module.canonical_ed25519_public_pem(k1)
    stored2 = engine_module.canonical_ed25519_public_pem(k2)
    fp1, fp2 = (hashlib.sha256(x.encode()).hexdigest()[:12] for x in (stored1, stored2))
    assert reg["key_present_after"] is True and reg["key_fp_after"] == fp1
    assert swap["key_present_before"] is True and swap["key_fp_before"] == fp1 and swap["key_fp_after"] == fp2
    assert swap["key_changed"] is True
    assert removed["key_present_before"] is True and removed["key_present_after"] is False
    assert removed["key_fp_after"] is None and removed["key_changed"] is True
    blob = json.dumps(ledger.events)
    for key in (stored1, stored2, k1, k2):
        assert "PUBLIC KEY" not in blob and key.splitlines()[1] not in blob, "a key reached a ledger payload"


def test_an_unchanged_key_is_recorded_as_not_changed(stack):
    client, ledger, *_ = stack
    k = public_pem()
    put(client, "FED-1", counterparty_pubkey_pem=k)
    put(client, "FED-1", counterparty_pubkey_pem=k)
    assert ledger.events[-1][1]["key_changed"] is False


def test_a_pasted_private_key_is_refused_and_leaves_no_event_and_no_quote(stack):
    client, ledger, *_ = stack
    private = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    r = put(client, "FED-1", counterparty_pubkey_pem=private)
    assert r.status_code == 422 and ledger.events == []
    assert private.splitlines()[1] not in r.text


def test_a_stored_private_key_row_is_never_fingerprinted():
    assert engine_module._key_fingerprint("-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----") is None
    assert engine_module._key_fingerprint(engine_module.WITHHELD_KEY) is None
    assert engine_module._key_fingerprint(None) is None and engine_module._key_fingerprint("  ") is None


# -- one write, one event; concurrent writes ----------------------------------------------------------------------

def test_one_write_is_one_event_and_a_refusal_is_one_event_not_two(stack):
    client, ledger, *_ = stack
    put(client, "FED-1", org="Acme Corp")
    assert len(ledger.events) == 1
    put(client, "FED-2", org="Acme Corp")                       # refused
    assert ledger.types() == ["federation.contract.registered", "federation.contract.refused"]
    put(client, "FED-1", org="Acme Corp")                       # the same text again is a write, so a replace
    assert ledger.types()[-1] == "federation.contract.replaced" and len(ledger.events) == 3


def test_a_422_and_a_path_body_mismatch_write_nothing_and_ledger_nothing(stack):
    client, ledger, *_ = stack
    assert client.put("/contracts/FED-9", json=body("FED-1")).status_code == 422
    assert client.put("/contracts/FED-1", json={"contract_id": "FED-1"}).status_code == 422
    assert ledger.events == [] and client.get("/contracts").json() == []


def test_eight_concurrent_writes_for_one_org_are_one_registered_and_seven_refused_events(stack):
    client, ledger, *_ = stack
    codes: list[int] = []
    barrier = threading.Barrier(8)

    def worker(i):
        barrier.wait()
        codes.append(put(client, f"FED-{i}", org="Acme Corp").status_code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(codes) == [200] + [409] * 7
    assert sorted(ledger.types()) == ["federation.contract.refused"] * 7 + ["federation.contract.registered"]


def test_concurrent_writes_for_different_orgs_are_one_event_each(stack):
    client, ledger, *_ = stack
    barrier = threading.Barrier(6)

    def worker(i):
        barrier.wait()
        assert put(client, f"FED-{i}", org=f"Org {i}").status_code == 200

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(ledger.types()) == ["federation.contract.registered"] * 6
    assert sorted(e[1]["contract_id"] for e in ledger.events) == [f"FED-{i}" for i in range(6)]


def test_the_operator_fields_come_from_the_shared_operator_merge(stack, monkeypatch):
    client, ledger, *_ = stack
    monkeypatch.setattr(engine_module.operator_auth, "merge_payload",
                        lambda p: {**p, "operator_id_authenticated": "op-test"})
    put(client, "FED-1", org="Acme Corp")
    put(client, "FED-2", org="Acme Corp")                                       # refused
    assert [e[1]["operator_id_authenticated"] for e in ledger.events] == ["op-test", "op-test"]


# -- the ledger being down ----------------------------------------------------------------------------------------

def test_an_unreachable_ledger_never_undoes_or_refuses_a_write_and_the_gap_is_logged_by_type_only(tmp_path, caplog):
    ledger = RecordingLedger(fail=RuntimeError(f"ledger at http://10.0.0.9 refused {CANARY}"))
    engine = BrokerEngine(store=ContractStore(tmp_path / "c.sqlite3"), ledger=ledger)
    client = TestClient(create_app(engine=engine))
    with caplog.at_level(logging.WARNING, logger=engine_module.log.name):
        assert put(client, "FED-1", org="Acme Corp").status_code == 200
        assert put(client, "FED-2", org="Acme Corp").status_code == 409          # the refusal still answers 409
    assert [c["contract_id"] for c in client.get("/contracts").json()] == ["FED-1"]   # the write stands
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "federation.contract.registered" in text and "RuntimeError" in text
    assert CANARY not in text and "10.0.0.9" not in text, "the ledger error text reached the log"
    engine.store.close()


def test_a_broker_with_no_ledger_still_writes(tmp_path):
    engine = BrokerEngine(store=ContractStore(tmp_path / "c.sqlite3"), ledger=None)
    client = TestClient(create_app(engine=engine))
    assert put(client, "FED-1").status_code == 200 and put(client, "FED-2").status_code == 409
    engine.store.close()


# -- F-C521-4: org names ------------------------------------------------------------------------------------------

REFUSED = [
    pytest.param("   ", id="three spaces"),
    pytest.param("\u200b", id="one zero-width space"),
    pytest.param("\n", id="one newline"),
    pytest.param("x" * 5000, id="5000 characters"),
    pytest.param("x" * (ORG_NAME_MAX + 1), id="one over the cap"),
    pytest.param("Acme\u200bCorp", id="zero-width inside"),
    pytest.param("Acme\ufeffCorp", id="byte-order mark inside"),
    pytest.param("Acme\u2800Corp", id="braille blank inside"),
    pytest.param("Acme\nCorp", id="newline inside"),
    pytest.param("Acme\tCorp", id="tab inside"),
    pytest.param("Acme\x00Corp", id="NUL inside"),
    pytest.param("\u200b \u2060 \u00ad", id="only invisibles and spaces"),
    pytest.param("Acme\u2028Corp", id="line separator inside (Zl)"),
    pytest.param("Acme\u2029Corp", id="paragraph separator inside (Zp)"),
    pytest.param("Acme\u00a0Corp", id="no-break space inside (Zs)"),
    pytest.param("Acme\u3000Corp", id="ideographic space inside (Zs)"),
    pytest.param("Acme\u2003Corp", id="em space inside (Zs)"),
    pytest.param("Acme\u3164Corp", id="Hangul filler inside"),
    pytest.param("Acme\uffa0Corp", id="halfwidth Hangul filler inside"),
    pytest.param("Acme\u180bCorp", id="Mongolian free variation selector inside"),
    pytest.param("Acme\ue000Corp", id="private use inside (Co)"),
    pytest.param("Acme\U000f0000Corp", id="supplementary private use inside (Co)"),
    pytest.param("Acme\ufffcCorp", id="object replacement character inside"),
    pytest.param("Acme\u0378Corp", id="unassigned code point inside (Cn)"),
    pytest.param("Acme\uffffCorp", id="noncharacter inside (Cn)"),
    pytest.param("\u0301\u0301", id="combining marks only"),
    pytest.param("\u0301 \u0301", id="combining marks and a space only"),
    pytest.param(f"{CANARY}\n{CANARY}", id="a made-up marker with a newline inside"),
    pytest.param(f"{CANARY}\u200b", id="a made-up marker with a zero-width space"),
]


@pytest.mark.parametrize("name", REFUSED)
def test_a_bad_org_name_is_refused_with_422_stores_nothing_ledgers_nothing_and_is_never_quoted(stack, name):
    client, ledger, *_ = stack
    r = put(client, "FED-1", org=name)
    assert r.status_code == 422, r.text
    assert ledger.events == [] and client.get("/contracts").json() == []
    assert name not in r.text and CANARY not in r.text and "x" * 20 not in r.text


def test_an_error_names_the_rule_and_not_the_name(stack):
    client, *_ = stack
    msgs = [put(client, "FED-1", org=o).json()["detail"][0]["msg"]
            for o in ("   ", "x" * 500, "A\nB", "A\u200bB", "A\u2028B", "\u0301\u0301")]
    assert msgs[0].endswith("org name is empty (only whitespace or invisible characters)")
    assert f"longer than {ORG_NAME_MAX} characters" in msgs[1]
    assert "control character" in msgs[2]
    invisible = "invisible, separator, private-use or unassigned character"
    assert invisible in msgs[3] and invisible in msgs[4]
    assert "no letter, digit, punctuation or symbol" in msgs[5]


ACCEPTED = [
    pytest.param("Acme Corp", "Acme Corp", id="plain"),
    pytest.param("x" * ORG_NAME_MAX, "x" * ORG_NAME_MAX, id="exactly at the cap"),
    pytest.param("  Acme Corp \n", "Acme Corp", id="surrounding whitespace is stripped"),
    pytest.param("\u00dcnic\u00f6de Ltd.", "\u00dcnic\u00f6de Ltd.", id="non-ASCII letters and punctuation"),
    pytest.param("\u30a2\u30af\u30e1 \u682a\u5f0f\u4f1a\u793e", "\u30a2\u30af\u30e1 \u682a\u5f0f\u4f1a\u793e", id="Japanese"),
    pytest.param("\u00a0Acme Corp\u3000", "Acme Corp", id="no-break and ideographic space at the ends are stripped"),
    pytest.param("Acme  Corp", "Acme  Corp", id="ASCII spaces inside are kept as written"),
    pytest.param("Acme-Corp & Sons, S.A. (EU)", "Acme-Corp & Sons, S.A. (EU)", id="punctuation and symbols"),
    pytest.param("\u0645\u0624\u0633\u0633\u0629 \u0623\u0643\u0645\u064a", "\u0645\u0624\u0633\u0633\u0629 \u0623\u0643\u0645\u064a", id="Arabic with a combining mark"),
    pytest.param("\u0905\u0915\u094d\u092e\u0940 \u0932\u093f\u092e\u093f\u091f\u0947\u0921", "\u0905\u0915\u094d\u092e\u0940 \u0932\u093f\u092e\u093f\u091f\u0947\u0921", id="Hindi with vowel signs and a virama"),
    pytest.param("A\u0301cme", "A\u0301cme", id="a visible combining accent after a letter"),
    pytest.param("\u0410cme Corp", "\u0410cme Corp", id="a Cyrillic look-alike letter is a different org, kept"),
    pytest.param("1234", "1234", id="digits only"),
    pytest.param("\u2122", "\u2122", id="a symbol only"),
]


@pytest.mark.parametrize("name,stored", ACCEPTED)
def test_a_clean_org_name_is_accepted_and_stored_stripped(stack, name, stored):
    client, ledger, *_ = stack
    r = put(client, "FED-1", org=name)
    assert r.status_code == 200 and r.json()["counterparty_org"] == stored
    assert ledger.events[0][1]["counterparty_org"] == stored


def test_the_name_rule_is_the_normaliser_the_store_compares_by():
    for bad in ("   ", "\u200b", "\u200b \u2060"):
        assert engine_module.normalize_org(bad) == ""          # nothing is left to compare, so it is refused
        with pytest.raises(ValueError):
            validate_org_name(bad)
    assert validate_org_name("  Acme  Corp ") == "Acme  Corp"   # stripped; inner spacing is the normaliser's business
    with pytest.raises(ValueError):
        validate_org_name(None)


def test_every_category_the_rule_names_is_refused_by_category_not_by_a_list_of_examples():
    import sys
    import unicodedata
    seen = {}
    for cp in range(sys.maxunicode + 1):
        cat = unicodedata.category(chr(cp))
        if cat in ("Cs",):
            seen.setdefault(cat, cp)
        elif cat in ("Cc", "Cf", "Co", "Cn", "Zl", "Zp") and cat not in seen:
            seen[cat] = cp
        elif cat == "Zs" and chr(cp) != " " and cat not in seen:
            seen[cat] = cp
    assert set(seen) == {"Cc", "Cf", "Co", "Cn", "Zl", "Zp", "Zs", "Cs"}
    for cat, cp in seen.items():
        with pytest.raises(ValueError):
            validate_org_name(f"Acme{chr(cp)}Corp")                 # one representative per category
    assert validate_org_name("Acme Corp") == "Acme Corp"            # the ASCII space is the one separator a name keeps


def test_a_lone_surrogate_is_refused():
    with pytest.raises(ValueError):
        validate_org_name("Acme" + chr(0xD800) + "Corp")


def test_a_row_stored_before_the_rule_still_lists_and_still_loads(stack):
    client, _ledger, engine, path = stack
    put(client, "FED-1", org="Acme Corp")
    long_name = "L" * 5000
    conn = sqlite3.connect(str(path))
    conn.execute("UPDATE contracts SET counterparty_org=? WHERE contract_id='FED-1'", (long_name,))
    conn.commit()
    conn.close()
    r = client.get("/contracts")
    assert r.status_code == 200 and r.json()[0]["counterparty_org"] == long_name


def test_a_move_away_from_a_legacy_long_name_records_the_org_before_cut_to_the_cap(stack):
    client, ledger, _engine, path = stack
    put(client, "FED-1", org="Acme Corp")
    conn = sqlite3.connect(str(path))
    conn.execute("UPDATE contracts SET counterparty_org=? WHERE contract_id='FED-1'", ("L" * 5000,))
    conn.commit()
    conn.close()
    assert put(client, "FED-1", org="Acme Corp").status_code == 200
    assert len(ledger.events[-1][1]["org_before"]) == ORG_NAME_MAX


# -- the ledger gap is visible on /health ---------------------------------------------------------------------------

def test_health_starts_at_zero_gaps_and_counts_each_failed_delivery_by_count_only(tmp_path, caplog):
    ledger = RecordingLedger()
    engine = BrokerEngine(store=ContractStore(tmp_path / "c.sqlite3"), ledger=ledger)
    client = TestClient(create_app(engine=engine))
    assert client.get("/health").json()["contract_ledger_gaps"] == 0
    put(client, "FED-1", org="Acme Corp")
    assert client.get("/health").json()["contract_ledger_gaps"] == 0           # delivered: no gap
    ledger.fail = RuntimeError(f"ledger at http://10.0.0.9 refused {CANARY}")
    put(client, "FED-2", org="Beta Inc")                                       # a failed registered record
    put(client, "FED-3", org="Beta Inc")                                       # a failed refused record
    health = client.get("/health")
    assert health.json()["contract_ledger_gaps"] == 2
    assert CANARY not in health.text and "10.0.0.9" not in health.text, "the ledger error text reached /health"
    ledger.fail = None
    put(client, "FED-4", org="Gamma Ltd")
    assert client.get("/health").json()["contract_ledger_gaps"] == 2           # delivery works again: no new gap
    engine.store.close()


def test_a_broker_with_no_ledger_counts_no_gap(tmp_path):
    engine = BrokerEngine(store=ContractStore(tmp_path / "c.sqlite3"), ledger=None)
    client = TestClient(create_app(engine=engine))
    put(client, "FED-1")
    assert client.get("/health").json()["contract_ledger_gaps"] == 0
    engine.store.close()


def test_the_gap_counter_is_exact_under_concurrent_failures(tmp_path):
    ledger = RecordingLedger(fail=RuntimeError("down"))
    engine = BrokerEngine(store=ContractStore(tmp_path / "c.sqlite3"), ledger=ledger)
    client = TestClient(create_app(engine=engine))
    barrier = threading.Barrier(8)

    def worker(i):
        barrier.wait()
        assert put(client, f"FED-{i}", org=f"Org {i}").status_code == 200

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert client.get("/health").json()["contract_ledger_gaps"] == 8
    engine.store.close()


# -- the README says what the code does ---------------------------------------------------------------------------

def test_the_readme_states_the_contract_write_events_and_the_name_rule():
    text = README.read_text(encoding="utf-8")
    assert "federation.contract.registered" in text and "replaced" in text and "deactivated" in text
    assert "refused" in text and f"{ORG_NAME_MAX} characters" in text
    assert "never the key" in text
    assert "contract_ledger_gaps" in text
    assert "format, separator, private-use" in text and "unassigned" in text
