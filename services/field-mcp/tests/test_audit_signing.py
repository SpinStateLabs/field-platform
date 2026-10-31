"""F-C869-1 (C-902): the intent and outcome rows are signed as a caller of the sealed ledger, so the write process works
on a ledger that requires caller signatures. Proven against the REAL sealed-ledger app (in process) with a keyring and
FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE armed. Mutants: C6 rows unsigned; C7 caller vars read in the read process;
C8 an unusable key silently ignored; C9 only one of the two variables accepted."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import KEY, Stub
from field_core.clients import CallerSigner
from field_core.ledger import LedgerEvent
from field_core.signing import generate_keypair, verify_caller_signature
from field_mcp import audit as au, client as cl
from field_mcp.catalog import SERVICES
from field_mcp.config import Config, ConfigError, ServiceConfig, load
from field_mcp.tools import Dispatcher
from sealed_ledger.api import create_app
from sealed_ledger.store import CallerPolicy, LedgerStore

CALLER = "field-mcp-test"
REGISTER = {"body": {"agent_id": "agent-1", "name": "A", "owner": "o"}, "reason": "signing test"}


@pytest.fixture
def keys(tmp_path):
    priv, pub = generate_keypair()
    ring = tmp_path / "ring"
    ring.mkdir()
    (ring / f"{CALLER}.pub.pem").write_text(pub, encoding="ascii")
    (ring / "other.pub.pem").write_text(generate_keypair()[1], encoding="ascii")
    keyfile = tmp_path / "caller.pem"
    keyfile.write_text(priv, encoding="ascii")
    return {"priv": priv, "pub": pub, "ring": ring, "keyfile": keyfile}


@pytest.fixture
def strict_ledger(tmp_path, keys):
    store = LedgerStore(tmp_path / "events.jsonl", caller=CallerPolicy(keys["ring"], require_caller_signature=True))
    return store, TestClient(create_app(store=store), base_url="http://testserver")


@pytest.fixture
def target():
    t = Stub()
    t.routes[("POST", "/agents")] = (201, {"agent_id": "agent-1"}, {})
    yield t
    t.close()


def env(keys, **extra):
    return {"FFMCP_ENABLE_WRITES": "1", "FFMCP_SEALED_LEDGER_URL": "http://127.0.0.1:1", "FFMCP_CALLER_ID": CALLER,
            "FFMCP_CALLER_KEY_FILE": str(keys["keyfile"]), **extra}


def write_disp(target, ledger_client, signer):
    svcs = {s: ServiceConfig(target.base, KEY) for s in SERVICES}
    svcs["sealed-ledger"] = ServiceConfig("http://testserver", KEY)
    cfg = Config(tier=2, services=svcs, operator="op", operator_key="opk-" + "Q1w2" * 4, caller=signer)
    ups = {s: cl.Upstream(s, c.base, c.key) for s, c in svcs.items()}
    ups["sealed-ledger"] = cl.Upstream("sealed-ledger", "http://testserver", KEY, client=ledger_client)
    return Dispatcher(cfg, ups, au.Audit(ups["sealed-ledger"], "op", "test-client", signer=signer))


def rows(store):
    p = Path(store.path)
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def test_an_unsigned_write_is_refused_by_a_ledger_that_requires_caller_signatures(strict_ledger, target):
    store, client = strict_ledger
    r = write_disp(target, client, None).call("agent_registry_create_agent", REGISTER)
    assert r == {"status": "error", "error": "audit unavailable; no write made"}
    assert not target.requests and rows(store) == []


def test_a_signed_write_is_made_and_both_rows_verify_under_the_callers_key(strict_ledger, target, keys):
    store, client = strict_ledger
    signer = load(2, env(keys)).caller
    r = write_disp(target, client, signer).call("agent_registry_create_agent", REGISTER)
    assert r["status"] == "ok" and r["audit"] == {**r["audit"], "intent": "recorded", "outcome": "recorded"}
    assert len(target.requests) == 1
    stored = rows(store)
    assert [x["event_type"] for x in stored] == ["mcp.write.intent", "mcp.write.outcome"]
    for x in stored:
        assert x["caller_id"] == CALLER and "caller_unsigned" not in x
        assert verify_caller_signature(LedgerEvent.model_validate(x), keys["pub"])
    assert stored[0]["payload"]["reason"] == "signing test"


def test_a_caller_the_keyring_does_not_know_is_refused_and_nothing_is_written(strict_ledger, target, keys):
    store, client = strict_ledger
    _, other_priv = None, generate_keypair()[0]
    from field_core.signing import load_ed25519_private_key
    stranger = CallerSigner("stranger", load_ed25519_private_key(other_priv))
    r = write_disp(target, client, stranger).call("agent_registry_create_agent", REGISTER)
    assert r["error"] == "audit unavailable; no write made" and not target.requests and rows(store) == []


def test_a_wrong_key_for_a_known_caller_id_is_refused(strict_ledger, target, keys):
    store, client = strict_ledger
    from field_core.signing import load_ed25519_private_key
    forged = CallerSigner(CALLER, load_ed25519_private_key(generate_keypair()[0]))
    assert write_disp(target, client, forged).call("agent_registry_create_agent", REGISTER)["status"] == "error"
    assert not target.requests and rows(store) == []


def test_the_private_key_never_reaches_the_ledger_or_the_service(strict_ledger, target, keys):
    store, client = strict_ledger
    write_disp(target, client, load(2, env(keys)).caller).call("agent_registry_create_agent", REGISTER)
    body = "".join(keys["priv"].splitlines()[1:-1])
    blob = Path(store.path).read_text() + "".join(r["body"].decode() for r in target.requests)
    assert body[:40] not in blob and body[40:80] not in blob


def test_config_builds_the_signer_from_the_two_variables_and_hides_it(keys):
    cfg = load(2, env(keys))
    assert isinstance(cfg.caller, CallerSigner) and cfg.caller.caller_id == CALLER
    text = repr(cfg) + str(cfg.__dict__.keys())
    assert "".join(keys["priv"].splitlines()[1:-1])[:40] not in repr(cfg) and "caller.pem" not in text


def test_config_without_the_variables_has_no_signer(keys):
    e = env(keys)
    del e["FFMCP_CALLER_ID"], e["FFMCP_CALLER_KEY_FILE"]
    assert load(2, e).caller is None


@pytest.mark.parametrize("drop", ["FFMCP_CALLER_ID", "FFMCP_CALLER_KEY_FILE"])
def test_only_one_of_the_two_variables_is_a_startup_error(keys, drop):
    e = env(keys)
    del e[drop]
    with pytest.raises(ConfigError, match="FFMCP_CALLER_ID and FFMCP_CALLER_KEY_FILE"):
        load(2, e)


@pytest.mark.parametrize("content", [None, "not a pem", "-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----\n"])
def test_an_unusable_key_file_stops_startup_without_naming_the_path_or_the_cause(keys, tmp_path, content):
    bad = tmp_path / "bad-key-file.pem"
    if content is not None:
        bad.write_text(content)
    with pytest.raises(ConfigError) as e:
        load(2, env(keys, FFMCP_CALLER_KEY_FILE=str(bad)))
    assert "FFMCP_CALLER_KEY_FILE" in str(e.value) and "bad-key-file" not in str(e.value) and "not a pem" not in str(e.value)


class Watched(dict):
    def __init__(self, *a):
        super().__init__(*a)
        self.read = []

    def get(self, k, d=None):
        self.read.append(k)
        return super().get(k, d)


def test_the_read_process_never_reads_the_caller_variables(keys):
    w = Watched({"FFMCP_CALLER_ID": CALLER, "FFMCP_CALLER_KEY_FILE": str(keys["keyfile"])})
    assert load(1, w).caller is None
    assert not ({"FFMCP_CALLER_ID", "FFMCP_CALLER_KEY_FILE"} & set(w.read))
