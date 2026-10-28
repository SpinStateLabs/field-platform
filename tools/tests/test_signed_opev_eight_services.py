"""Signed operator events across the eight operator-block services, in process,
against a REAL sealed-ledger that requires caller signatures.

GB10, 2026-10-27, Stage 1 LOG-ONLY (armed 20:06:08Z, rolled back 20:07:58Z):
the ledger runs FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1 with a caller keyring,
and phase_g_check's no-credential, incomplete-credential and bad-credential
probes left ZERO operator.unauthenticated rows: each record was refused 403
(the ledger verifies the caller signature over the payload its Phase G
admission stores, the client had signed the payload before that admission)
and /health dropped_unauthenticated_records stayed 0. CI ran no ledger with
caller signatures required, so nothing here could see it.

For each of registry, delegation, killswitch, governor, fedbroker, lifecycle
(each with its own caller key, with and without an attributing operator
identity of its own), console (C-14: never an identity) and the ledger (its
own in-process append, no caller signature, unaffected): one unauthenticated
guarded write under LOG-ONLY leaves exactly one operator.unauthenticated row
signed by that service, and under ENFORCE one operator.refused row. Every
stored row's caller signature verifies over the STORED payload (the ledger's
verify-callers rule). A ledger that refuses the record still lets the LOG-ONLY
write through, and the loss is counted on /health.

Fake keys only: the Ed25519 pairs are generated per run, the operator keys are
throwaway constants."""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as delegation_app
from delegation_authority.store import TokenStore
from federation_broker.api import create_app as fedbroker_app
from federation_broker.engine import BrokerEngine, ContractStore
from field_core import operator_auth as oa
from field_core.clients import CALLER_ID_ENV, CALLER_KEY_ENV, CallerSigner, LedgerClient
from field_core.signing import generate_keypair, load_ed25519_private_key, verify_caller_signature
from kill_switch.api import create_app as killswitch_app
from lifecycle_manager.api import create_app as lifecycle_app
from ops_console.api import ServiceClient, create_app as console_app
from sealed_ledger.api import create_app as ledger_app
from sealed_ledger.store import CallerPolicy, LedgerStore
from spend_governor.api import create_app as governor_app
from spend_governor.core import GovernorStore

CALLERS = ("registry", "delegation", "killswitch", "governor", "fedbroker", "lifecycle", "console")
KEY_DON = "tkv-don-key-0123456789abcdef"
WRONG = "tkv-wrong-key-0123456789abcdef"
SVC_KEY = {c: f"tkv-svc-{c}-key-0123456789abcdef" for c in CALLERS}

#: (service, method, path, guarded action) for one guarded write per HTTP service.
WRITES = [
    ("registry", "POST", "/agents", "register"),
    ("delegation", "POST", "/tokens", "mint"),
    ("killswitch", "POST", "/revive/canary-gb10", "revive"),
    ("governor", "PUT", "/caps/canary-gb10", "caps"),
    ("fedbroker", "PUT", "/contracts/c1", "federation"),
    ("lifecycle", "POST", "/sweep", "sweep"),
]

PROBES = {   # phase_g_check's three LOG-ONLY probes
    "no_credential": {},
    "incomplete_credential": {oa.HEADER_OPERATOR: "don"},
    "bad_credential": {oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: WRONG},
}


def _row(oid, key, scopes, **kw):
    return {"operator_id": oid, "key_sha256": oa.key_sha256(key), "status": "active",
            "created_at": "2026-10-25", "scopes": scopes, **kw}


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    d = tmp_path_factory.mktemp("callers")
    (d / "keyring").mkdir()
    out = {"dir": d, "keyring": d / "keyring", "pub": {}, "priv_path": {}, "signer": {}}
    for cid in CALLERS:
        priv, pub = generate_keypair()
        (d / "keyring" / f"{cid}.pub.pem").write_text(pub, encoding="ascii")
        (d / f"{cid}.pem").write_text(priv, encoding="ascii")
        out["pub"][cid] = pub
        out["priv_path"][cid] = d / f"{cid}.pem"
        out["signer"][cid] = CallerSigner(cid, load_ed25519_private_key(priv))
    return out


_ENV_NAMES = ("FIELD_OPERATOR_REGISTRY", "FIELD_OPERATOR_REQUIRE", "FIELD_OPERATOR",
              "FIELD_OPERATOR_KEY", "FIELD_OPERATOR_KEY_FILE", "FIELD_SHARED_SECRET",
              CALLER_ID_ENV, CALLER_KEY_ENV, "FIELD_LEDGER_CALLER_KEYRING",
              "FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE", "FIELD_LIFECYCLE_EVERY")


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """Module environment for building the apps (they are built once per
    identity variant: each app build costs seconds of TLS-context setup)."""
    mp = pytest.MonkeyPatch()
    d = tmp_path_factory.mktemp("estate")
    for n in _ENV_NAMES:
        mp.delenv(n, raising=False)
    (d / "data").mkdir()
    (d / "manifests").mkdir()
    mp.setenv("FIELD_DATA_DIR", str(d / "data"))
    mp.setenv("FIELD_MANIFEST_DIR", str(d / "manifests"))
    mp.setenv("FIELD_REGISTRY_URL", "http://127.0.0.1:9/registry")   # dead: guards run first
    ops = d / "operators.json"
    ops.write_text(json.dumps([_row("don", KEY_DON, ["*"])] + [
        _row(f"svc-{c}", SVC_KEY[c], ["ledger_attribute"], event_prefixes=[f"{c}."])
        for c in CALLERS if c != "console"]), encoding="utf-8")
    yield {"dir": d, "ops": ops, "mp": mp}
    mp.undo()


@pytest.fixture(autouse=True)
def _env(base, monkeypatch):
    for n in ("FIELD_OPERATOR_REGISTRY", "FIELD_OPERATOR_REQUIRE"):
        monkeypatch.delenv(n, raising=False)
    yield base["ops"]
    oa.bind(oa.NO_AUTH)


def arm(monkeypatch, ops, mode):
    monkeypatch.setenv("FIELD_OPERATOR_REGISTRY", str(ops))
    if mode == "enforce":
        monkeypatch.setenv("FIELD_OPERATOR_REQUIRE", "1")
    assert oa.mode() == mode


class Estate:
    """One real ledger (caller keyring + FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1)
    and the eight services, each appending through its own signed client. Built
    once per identity variant; ``fresh`` gives every test an empty ledger."""

    def __init__(self, d, keys, mp, *, identity: bool):
        self.dir = d
        self.keys = keys
        self.ledger_app = ledger_app(store=self._store(keys["keyring"]))
        self.ledger = TestClient(self.ledger_app)

        def lc(cid):
            headers = {oa.HEADER_OPERATOR: f"svc-{cid}", oa.HEADER_KEY: SVC_KEY[cid]} if identity else {}
            return LedgerClient(client=TestClient(self.ledger_app, headers=headers),
                                caller=keys["signer"][cid])

        self.apps = {
            "registry": registry_app(store=RegistryStore(d / "agents.json"), ledger=lc("registry")),
            "delegation": delegation_app(store=TokenStore(d / "tokens.json"), ledger=lc("delegation")),
            "killswitch": killswitch_app(ledger=lc("killswitch")),
            "governor": governor_app(store=GovernorStore(d / "governor.json"), ledger=lc("governor")),
            "fedbroker": fedbroker_app(engine=BrokerEngine(store=ContractStore(d / "contracts.json"),
                                                           ledger=lc("fedbroker"))),
            "lifecycle": lifecycle_app(ledger=lc("lifecycle"), every=0),
        }
        # the console reads its caller key from the environment, like on the GB10
        mp.setenv(CALLER_ID_ENV, "console")
        mp.setenv(CALLER_KEY_ENV, str(keys["priv_path"]["console"]))
        self.apps["console"] = console_app(
            ledger=ServiceClient(client=TestClient(self.ledger_app), base_url="http://testserver"))
        mp.delenv(CALLER_ID_ENV)
        mp.delenv(CALLER_KEY_ENV)
        self.clients = {k: TestClient(v) for k, v in self.apps.items()}

    def _store(self, keyring, name="events.jsonl"):
        return LedgerStore(self.dir / name, caller=CallerPolicy(keyring, require_caller_signature=True))

    def fresh(self, tmp_path, keyring=None) -> "Estate":
        """An empty ledger (same keyring, or ``keyring``) behind the same apps."""
        self.dir = tmp_path
        self.ledger_app.state.store = self._store(keyring or self.keys["keyring"])
        for oh in [a.state.operator_health for a in self.apps.values()]:
            oh.refused_count = oh.dropped_records = 0
        return self

    def events(self, event_type):
        r = self.ledger.get("/events", params={"event_type": event_type})
        assert r.status_code == 200
        return r.json()

    def rows(self, event_type, caller_id):
        return [e for e in self.events(event_type) if e.get("caller_id") == caller_id]

    def health(self, svc):
        return self.clients[svc].get("/health").json()


@pytest.fixture(scope="module")
def estates(base, keys):
    built = {}

    def get(identity: bool) -> Estate:
        if identity not in built:
            d = base["dir"] / ("ident" if identity else "plain")
            d.mkdir()
            built[identity] = Estate(d, keys, base["mp"], identity=identity)
        return built[identity]
    return get


def settle(predicate, timeout=5.0):
    """The record append is bounded but asynchronous to the request."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def assert_signed_over_stored(e, keys, cid):
    assert e["caller_id"] == cid and "caller_unsigned" not in e
    assert verify_caller_signature(e, keys["pub"][cid]), f"{cid}: stored row does not verify"


@pytest.fixture(params=[False, True], ids=["identity-less", "attributing-identity"])
def identity(request):
    return request.param


def test_the_ledger_under_test_refuses_an_unsigned_start_type_append(tmp_path, keys, estates):
    """The harness is the GB10's configuration: an unsigned operator.* record
    is refused (if this goes green-for-anything, every test below is moot)."""
    est = estates(False).fresh(tmp_path)
    r = est.ledger.post("/events", json={"event_type": "operator.unauthenticated", "agent_id": None,
                                         "payload": {"action": "revive"}})
    assert r.status_code == 403 and "FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE" in r.text
    h = est.ledger.get("/health").json()
    assert h["require_caller_signature"] is True and h["caller_keys"] == len(CALLERS)


@pytest.mark.parametrize("svc,method,path,action", WRITES, ids=[w[0] for w in WRITES])
def test_log_only_each_probe_leaves_one_signed_unauthenticated_row(
        tmp_path, keys, estates, monkeypatch, _env, identity, svc, method, path, action):
    arm(monkeypatch, _env, "log-only")
    est = estates(identity).fresh(tmp_path)
    before = oa.dropped_unauthenticated_records
    for n, (reason, headers) in enumerate(PROBES.items(), start=1):
        r = est.clients[svc].request(method, path, json={}, headers=headers)
        assert r.status_code not in (401, 403), f"LOG-ONLY refused {svc} {reason}: {r.status_code}"
        assert settle(lambda: len(est.rows("operator.unauthenticated", svc)) == n), \
            f"{svc} {reason}: {len(est.rows('operator.unauthenticated', svc))} rows, want {n}"
    rows = est.rows("operator.unauthenticated", svc)
    assert [e["payload"]["reason"] for e in rows] == list(PROBES)
    for e in rows:
        assert e["payload"]["action"] == action
        assert e["payload"]["self_reported"] is (not identity)
        assert not any(k in e["payload"] for k in oa.RESERVED_KEYS)
        assert_signed_over_stored(e, keys, svc)
    assert len(est.events("operator.unauthenticated")) == 3          # nobody else wrote one
    assert oa.dropped_unauthenticated_records == before
    assert est.health(svc)["dropped_unauthenticated_records"] == before


@pytest.mark.parametrize("svc,method,path,action", WRITES, ids=[w[0] for w in WRITES])
def test_enforce_refusal_leaves_one_signed_refused_row(
        tmp_path, keys, estates, monkeypatch, _env, identity, svc, method, path, action):
    arm(monkeypatch, _env, "enforce")
    est = estates(identity).fresh(tmp_path)
    r = est.clients[svc].request(method, path, json={})
    assert r.status_code == 401
    assert settle(lambda: len(est.rows("operator.refused", svc)) == 1)
    (e,) = est.rows("operator.refused", svc)
    assert e["payload"]["action"] == action and e["payload"]["status"] == 401
    assert e["payload"]["self_reported"] is (not identity)
    assert_signed_over_stored(e, keys, svc)
    assert est.health(svc)["dropped_refused_records"] == 0


def test_console_refusal_is_signed_with_the_consoles_caller_key(tmp_path, keys, estates, monkeypatch, _env):
    arm(monkeypatch, _env, "enforce")
    est = estates(False).fresh(tmp_path)
    r = est.clients["console"].post("/api/agents/canary-gb10/kill", json={"operator": "Don"})
    assert r.status_code == 401
    assert settle(lambda: len(est.rows("operator.refused", "console")) == 1)
    (e,) = est.rows("operator.refused", "console")
    assert e["payload"]["action"] == "kill" and e["agent_id"] == "canary-gb10"
    assert e["payload"]["self_reported"] is True
    assert_signed_over_stored(e, keys, "console")
    assert est.health("console")["dropped_refused_records"] == 0


def test_the_ledgers_own_records_are_in_process_and_unaffected(tmp_path, keys, estates, monkeypatch, _env):
    """The ledger's guards append through its own store (no HTTP, no caller
    policy): still written, still self_reported, never caller-signed."""
    arm(monkeypatch, _env, "log-only")
    est = estates(False).fresh(tmp_path)
    est.ledger.post("/hold", json={})
    rows = est.events("operator.unauthenticated")
    assert len(rows) == 1 and rows[0]["payload"]["action"] == "hold"
    assert rows[0]["payload"]["self_reported"] is True and "caller_id" not in rows[0]
    arm(monkeypatch, _env, "enforce")
    assert est.ledger.post("/hold", json={}).status_code == 401
    assert settle(lambda: len(est.events("operator.refused")) == 1)
    assert "caller_id" not in est.events("operator.refused")[0]


def test_an_attributed_start_type_row_is_signed_with_or_without_ledger_attribute(
        tmp_path, keys, estates, monkeypatch, _env, identity):
    """C-12 / every attributed row: the human's authenticated id merged into a
    start-type event (registry.registered) survives only for a service whose
    ledger_attribute covers the type; either way the row lands signed. Before:
    without the identity the ledger stripped the keys, the signature failed,
    and the registration's audit row was refused 403 (and swallowed)."""
    arm(monkeypatch, _env, "log-only")
    est = estates(identity).fresh(tmp_path)
    r = est.clients["registry"].post("/agents", json={"agent_id": "a1", "name": "a", "owner": "o"},
                                     headers={oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: KEY_DON})
    assert r.status_code == 201
    (e,) = est.rows("registry.registered", "registry")
    assert_signed_over_stored(e, keys, "registry")
    assert (e["payload"].get("operator_id_authenticated") == "don") is identity


def test_log_only_write_still_allowed_when_the_ledger_refuses_the_record(tmp_path, keys, estates, monkeypatch, _env):
    """An empty keyring: every signed record is refused 403. The write is NOT
    refused, the loss is counted on /health, never silent."""
    arm(monkeypatch, _env, "log-only")
    empty = tmp_path / "empty-keyring"
    empty.mkdir()
    est = estates(False).fresh(tmp_path, keyring=empty)
    before = oa.dropped_unauthenticated_records
    r = est.clients["killswitch"].post("/revive/canary-gb10", json={"operator": "x", "reason": "y"})
    assert r.status_code not in (401, 403)
    assert settle(lambda: oa.dropped_unauthenticated_records == before + 1)
    assert est.health("killswitch")["dropped_unauthenticated_records"] == before + 1
    assert est.events("operator.unauthenticated") == []
