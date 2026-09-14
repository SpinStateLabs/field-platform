"""F2b — per-service caller signatures on ledger appends (sealed-ledger).

Done-when (tasks/todo.md Phase F, F2b): a signed caller append is stored and
verifies (``test_signed_caller_append_stored_and_verifies``); an unsigned
append is unchanged when the env is unset and the omitted-when-absent rule
is pinned (``test_unsigned_append_unchanged_when_env_unset_omitted_when_absent``);
unknown caller 403 (``test_unknown_caller_403``); bad signature 403
(``test_bad_signature_403``); stale ``caller_ts`` 403
(``test_stale_caller_ts_403``); caller fields with no keyring 403
(``test_no_keyring_but_caller_fields_403``); REQUIRE: start-type unsigned
403, stop-type 201 ``caller_unsigned: true``
(``test_require_caller_signature_start_type_unsigned_403``,
``test_require_caller_signature_stop_type_unsigned_201_caller_unsigned_true``);
``verify --caller-keyring`` reports and fails correctly
(``test_cli_verify_caller_keyring_reports_and_fails_correctly``). Every
refusal branch has the test that fails when the branch is deleted.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from field_core.clients import CALLER_ID_ENV, CALLER_KEY_ENV, CallerSigner, LedgerClient, LedgerUnreachableError
from field_core.ledger import LedgerEvent, compute_event_hash, make_event
from field_core.signing import (
    generate_keypair,
    load_ed25519_private_key,
    sign_caller,
    sign_event,
    verify_caller_signature,
    verify_event_signature,
)
from ledger_c2_support import KEY_PRIV, KEY_PUB, fill, listing, rotate
from sealed_ledger.api import (
    caller_policy_from_env,
    create_app,
    require_caller_signature_from_env,
)
from sealed_ledger.bundle import verify_bundle
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import (
    CALLER_KEYRING_ENV,
    CALLER_TS_MAX_AGE_S,
    CALLER_TS_MAX_FUTURE_S,
    REQUIRE_CALLER_SIGNATURE_ENV,
    CallerKeyring,
    CallerPolicy,
    CallerRefused,
    LedgerStore,
    SigningConfig,
    load_caller_policy,
    load_signing_config,
    stamp_event,
)

runner = CliRunner()
PRE_F2_KEYS = {"event_id", "ts", "event_type", "agent_id", "payload", "prev_hash", "hash"}
CALLER_FIELDS = {"caller_id", "caller_ts", "caller_signature"}
STOP_TYPES = ["delegation.revoke", "kill.agent", "kill.domain", "lifecycle.decommissioned"]
SENTINEL, KILLSWITCH = "conformance-sentinel", "killswitch"


@pytest.fixture(scope="module")
def callers(tmp_path_factory):
    """Two callers' key pairs (private files outside the keyring, public PEMs
    inside it, as on the GB10), a stranger's pair, and the ledger's own F2
    sign key (a SEPARATE key: it proves the ledger wrote a record)."""
    d = tmp_path_factory.mktemp("caller-keys")
    keyring = d / "callers"
    keyring.mkdir()
    out: dict = {"dir": d, "keyring": keyring}
    for cid in (SENTINEL, KILLSWITCH, "stranger"):
        priv, pub = generate_keypair()
        (d / f"{cid}.pem").write_text(priv, encoding="ascii")
        if cid != "stranger":
            (keyring / f"{cid}.pub.pem").write_text(pub, encoding="ascii")
        out[cid] = {"priv": priv, "pub": pub, "priv_path": d / f"{cid}.pem"}
    lpriv, lpub = generate_keypair()
    (d / "ledger-sign.pem").write_text(lpriv, encoding="ascii")
    (d / "ledger-sign.pub.pem").write_text(lpub, encoding="ascii")
    out["ledger"] = {"priv_path": d / "ledger-sign.pem", "pub_path": d / "ledger-sign.pub.pem", "pub": lpub}
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _claim(callers, cid: str, event_type: str, agent_id, payload: dict, ts: str | None = None,
           priv: str | None = None) -> dict:
    ts = ts or _now()
    sig = sign_caller(priv or callers[cid]["priv"], event_type=event_type, agent_id=agent_id,
                      payload=payload, caller_id=cid, caller_ts=ts)
    return {"caller_id": cid, "caller_ts": ts, "caller_signature": sig}


def _body(event_type: str, agent_id, payload: dict, claim: dict | None = None) -> dict:
    body = {"event_type": event_type, "agent_id": agent_id, "payload": payload}
    if claim:
        body.update(claim)
    return body


def _store(tmp_path: Path, callers, *, keyring: bool = True, require: bool = False,
           ledger_signed: bool = False, name: str = "events.jsonl") -> LedgerStore:
    return LedgerStore(
        tmp_path / name,
        signing=load_signing_config(callers["ledger"]["priv_path"]) if ledger_signed else None,
        caller=CallerPolicy(callers["keyring"] if keyring else None, require_caller_signature=require),
    )


def _lines(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _relink(p: Path, idx: int, mutate) -> None:
    """The attacker without any key: mutate one field of line ``idx``
    (signatures kept), rehash it, recompute every later hash/prev_hash."""
    lines = p.read_text(encoding="utf-8").splitlines()
    recs = [json.loads(x) for x in lines]
    mutate(recs[idx])
    recs[idx]["hash"] = compute_event_hash(recs[idx])
    for k in range(idx + 1, len(recs)):
        recs[k]["prev_hash"] = recs[k - 1]["hash"]
        recs[k]["hash"] = compute_event_hash(recs[k])
    p.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")


def _post(client: TestClient, body: dict):
    return client.post("/events", json=body)


# ----------------------------------------------------------- stored + verifies


def test_signed_caller_append_stored_and_verifies(tmp_path, callers):
    """Store level and served: the claim is stored as three top-level fields,
    INSIDE the hash and under the ledger's own F2 signature; the line adds
    exactly those three keys; GET /events serves it verbatim."""
    s = _store(tmp_path, callers, ledger_signed=True)
    client = TestClient(create_app(store=s))
    payload = {"action": "draft invoices", "amount": 1200}
    claim = _claim(callers, SENTINEL, "conformance.allow", "invoicing-agent", payload)
    r = _post(client, _body("conformance.allow", "invoicing-agent", payload, claim))
    assert r.status_code == 201, r.text
    body = r.json()
    assert {k: body[k] for k in CALLER_FIELDS} == claim
    assert "caller_unsigned" not in body
    ev = LedgerEvent.model_validate(body)
    assert verify_caller_signature(ev, callers[SENTINEL]["pub"])
    assert not verify_caller_signature(ev, callers[KILLSWITCH]["pub"])
    assert compute_event_hash(ev) == ev.hash  # the caller fields are inside the hash
    assert verify_event_signature(ev, callers["ledger"]["pub"])  # and under the ledger's signature
    [rec] = _lines(s.path)
    assert set(rec) == PRE_F2_KEYS | CALLER_FIELDS | {"signature"}
    assert rec == body
    assert client.get("/events").json() == [body]
    assert client.get("/verify").json()["ok"] is True and LedgerStore(s.path).verify().ok
    # the same through the store API (what the served route calls), a second caller
    e2 = s.append_for_caller("kill.agent", {"reason": "x"}, "a",
                             claim=_claim(callers, KILLSWITCH, "kill.agent", "a", {"reason": "x"}))
    assert e2.caller_id == KILLSWITCH and e2.caller_unsigned is None and e2.prev_hash == ev.hash
    assert verify_caller_signature(e2, callers[KILLSWITCH]["pub"])
    # editing the stored caller_id and re-linking: the plain chain is blind,
    # the ledger signature and the caller signature are not
    _relink(s.path, 0, lambda rec: rec.update(caller_id=KILLSWITCH))
    assert LedgerStore(s.path).verify().ok
    forged = LedgerStore(s.path).events()[0]
    assert not verify_event_signature(forged, callers["ledger"]["pub"])
    assert not verify_caller_signature(forged, callers[KILLSWITCH]["pub"])
    assert not verify_caller_signature(forged, callers[SENTINEL]["pub"])


def test_ledger_client_signs_end_to_end_against_the_served_app(tmp_path, callers, monkeypatch):
    """The real caller side (``field_core.clients.LedgerClient`` built from the
    two env vars) against the real served route."""
    s = _store(tmp_path, callers)
    http = TestClient(create_app(store=s))
    monkeypatch.setenv(CALLER_ID_ENV, SENTINEL)
    monkeypatch.setenv(CALLER_KEY_ENV, str(callers[SENTINEL]["priv_path"]))
    out = LedgerClient(client=http, base_url="").append("conformance.allow", {"n": 1}, agent_id="canary")
    assert out["caller_id"] == SENTINEL and verify_caller_signature(out, callers[SENTINEL]["pub"])
    # a client whose key is not in the keyring: 403 => LedgerUnreachableError (fail closed, nothing written)
    monkeypatch.setenv(CALLER_ID_ENV, "stranger")
    monkeypatch.setenv(CALLER_KEY_ENV, str(callers["stranger"]["priv_path"]))
    with pytest.raises(LedgerUnreachableError, match="403"):
        LedgerClient(client=http, base_url="").append("conformance.allow", {"n": 2}, agent_id="canary")
    assert http.get("/health").json()["event_count"] == 1


# ------------------------------------------------------- unsigned unchanged


@pytest.mark.parametrize("keyring", [False, True])
@pytest.mark.parametrize("ledger_signed", [False, True])
def test_unsigned_append_unchanged_when_env_unset_omitted_when_absent(tmp_path, callers, keyring, ledger_signed):
    """A pre-F2b body (no caller fields), REQUIRE off: 201, and the stored line
    carries NONE of the four F2b keys — exactly the pre-F2 keys (plus the
    ledger's own ``signature`` when its key is on). Keyring on or off."""
    s = _store(tmp_path, callers, keyring=keyring, ledger_signed=ledger_signed)
    client = TestClient(create_app(store=s))
    r = _post(client, _body("registry.updated", "a", {"n": 1}))
    assert r.status_code == 201, r.text
    body = r.json()
    assert not (set(body) & (CALLER_FIELDS | {"caller_unsigned"}))
    assert '"caller' not in r.text
    [rec] = _lines(s.path)
    assert set(rec) == PRE_F2_KEYS | ({"signature"} if ledger_signed else set())
    assert '"caller' not in s.path.read_text(encoding="utf-8")
    e = s.append("action", {"n": 2})  # the store's own append: the same
    assert e.caller_id is None and e.caller_unsigned is None
    assert '"caller' not in s.path.read_text(encoding="utf-8")
    assert LedgerStore(s.path).verify().ok


# ---------------------------------------------------------------- refusals


def _refused(client: TestClient, s: LedgerStore, body: dict, *needles: str) -> str:
    before = listing(s.path.parent)
    r = _post(client, body)
    assert r.status_code == 403, r.text
    detail = r.json()["detail"]
    for needle in needles:
        assert needle in detail, (needle, detail)
    assert "BEGIN" not in detail
    assert listing(s.path.parent) == before  # nothing written, not even the lock file
    return detail


def test_unknown_caller_403(tmp_path, callers):
    s = _store(tmp_path, callers)
    client = TestClient(create_app(store=s))
    payload = {"n": 1}
    # no <id>.pub.pem in the keyring (a stranger with a perfectly good key)
    claim = _claim(callers, "stranger", "action", "a", payload, priv=callers["stranger"]["priv"])
    _refused(client, s, _body("action", "a", payload, claim), "unknown caller 'stranger'", "no stranger.pub.pem")
    # an id the name rule refuses never becomes a path: the stranger plants
    # their OWN public key one level up and claims the traversal name, signed
    # with the matching private key — a lookup that built the path would
    # verify it and land the event; the name rule refuses it first
    planted = callers["dir"] / "stranger.pub.pem"
    planted.write_text(callers["stranger"]["pub"], encoding="ascii")
    assert (callers["keyring"] / ".." / "stranger.pub.pem").resolve() == planted.resolve()
    claim = _claim(callers, "../stranger", "action", "a", payload, priv=callers["stranger"]["priv"])
    assert verify_caller_signature({"event_type": "action", "agent_id": "a", "payload": payload, **claim},
                                   callers["stranger"]["pub"])  # the planted key WOULD verify it
    _refused(client, s, _body("action", "a", payload, claim), "unknown caller '../stranger'", "not a valid caller id")
    for bad_id in ("Sentinel", "a/b", "x_y", ""):
        claim = _claim(callers, bad_id, "action", "a", payload, priv=callers["stranger"]["priv"])
        r = _post(client, _body("action", "a", payload, claim))
        assert r.status_code == 403, bad_id
    # a keyring file that is not an Ed25519 PUBLIC key makes that caller unknown (never a 500)
    bad_dir = tmp_path / "bad-keyring"
    bad_dir.mkdir()
    (bad_dir / "governor.pub.pem").write_text(callers["stranger"]["priv"], encoding="ascii")  # a private key
    (bad_dir / "replay.pub.pem").write_text("garbage", encoding="ascii")
    s2 = LedgerStore(tmp_path / "two" / "events.jsonl", caller=CallerPolicy(bad_dir))
    client2 = TestClient(create_app(store=s2))
    for cid in ("governor", "replay"):
        claim = _claim(callers, cid, "action", "a", payload, priv=callers["stranger"]["priv"])
        _refused(client2, s2, _body("action", "a", payload, claim), f"unknown caller '{cid}'", "not an Ed25519 public key")
    assert client.get("/health").json()["event_count"] == 0
    assert client2.get("/health").json()["event_count"] == 0


def test_bad_signature_403(tmp_path, callers):
    s = _store(tmp_path, callers)
    client = TestClient(create_app(store=s))
    payload = {"amount": 1200}
    # a known id signed with somebody else's key
    claim = _claim(callers, SENTINEL, "spend", "fin", payload, priv=callers["stranger"]["priv"])
    _refused(client, s, _body("spend", "fin", payload, claim), "invalid caller signature", SENTINEL)
    # a good claim whose covered fields were changed after signing
    good = _claim(callers, SENTINEL, "spend", "fin", payload)
    _refused(client, s, _body("spend", "fin", {"amount": 12}, good), "invalid caller signature")
    _refused(client, s, _body("spend", "other", payload, good), "invalid caller signature")
    _refused(client, s, _body("spend.other", "fin", payload, good), "invalid caller signature")
    _refused(client, s, _body("spend", "fin", payload, {**good, "caller_id": KILLSWITCH}), "invalid caller signature")
    # malformed signatures
    for sig in ("not base64!", "AAAA", ""):
        r = _post(client, _body("spend", "fin", payload, {**good, "caller_signature": sig}))
        assert r.status_code == 403, sig
    # the untouched claim still lands (the check is not vacuous)
    assert _post(client, _body("spend", "fin", payload, good)).status_code == 201


def test_stale_caller_ts_403(tmp_path, callers):
    """The replay window: older than 300 s or more than 60 s ahead is refused;
    inside it (both edges, naive-as-UTC, a Z suffix) is accepted."""
    s = _store(tmp_path, callers)
    client = TestClient(create_app(store=s))
    payload = {"n": 1}
    now = datetime.now(timezone.utc)

    def at(delta: timedelta, fmt=None) -> str:
        t = now + delta
        return fmt(t) if fmt else t.isoformat()

    stale = _claim(callers, SENTINEL, "action", "a", payload, ts=at(timedelta(seconds=-(CALLER_TS_MAX_AGE_S + 5))))
    _refused(client, s, _body("action", "a", payload, stale), "refused", "replay window")
    ahead = _claim(callers, SENTINEL, "action", "a", payload, ts=at(timedelta(seconds=CALLER_TS_MAX_FUTURE_S + 5)))
    _refused(client, s, _body("action", "a", payload, ahead), "in the future")
    garbage = _claim(callers, SENTINEL, "action", "a", payload, ts="yesterday")
    _refused(client, s, _body("action", "a", payload, garbage), "not an ISO 8601 instant")
    # a replay of a once-valid body after the window: refused (its signature still verifies)
    assert verify_caller_signature({"event_type": "action", "agent_id": "a", "payload": payload, **stale},
                                   callers[SENTINEL]["pub"])
    # inside the window
    for ts in (at(timedelta(seconds=-(CALLER_TS_MAX_AGE_S - 5))),
               at(timedelta(seconds=CALLER_TS_MAX_FUTURE_S - 5)),
               at(timedelta(0), lambda t: t.replace(tzinfo=None).isoformat()),  # naive = UTC
               at(timedelta(0), lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ"))):
        claim = _claim(callers, SENTINEL, "action", "a", payload, ts=ts)
        assert _post(client, _body("action", "a", payload, claim)).status_code == 201, ts
    assert client.get("/health").json()["event_count"] == 4
    # the policy's clock is injectable: the same claim is stale 10 minutes later
    policy = CallerPolicy(callers["keyring"])
    fresh = _claim(callers, SENTINEL, "action", "a", payload)
    assert set(policy.check("action", payload, "a", fresh)) == CALLER_FIELDS
    with pytest.raises(CallerRefused, match="replay window"):
        policy.check("action", payload, "a", fresh, now=now + timedelta(minutes=10))


def test_no_keyring_but_caller_fields_403(tmp_path, callers):
    """Never silently accept an unverifiable claim: with no keyring configured
    a body carrying caller fields is 403 naming the env var, nothing written
    (an unsigned body is still 201: the deployed behaviour)."""
    s = _store(tmp_path, callers, keyring=False)
    client = TestClient(create_app(store=s))
    assert client.get("/health").json()["caller_keyring"] == "off"
    payload = {"n": 1}
    claim = _claim(callers, SENTINEL, "action", "a", payload)
    _refused(client, s, _body("action", "a", payload, claim), "caller keyring not configured", CALLER_KEYRING_ENV)
    assert _post(client, _body("action", "a", payload)).status_code == 201


def test_incomplete_caller_fields_403(tmp_path, callers):
    s = _store(tmp_path, callers)
    client = TestClient(create_app(store=s))
    payload = {"n": 1}
    good = _claim(callers, SENTINEL, "action", "a", payload)
    for drop in (["caller_id"], ["caller_ts"], ["caller_signature"], ["caller_ts", "caller_signature"]):
        partial = {k: v for k, v in good.items() if k not in drop}
        _refused(client, s, _body("action", "a", payload, partial), "incomplete caller fields")
    for blank in CALLER_FIELDS:
        _refused(client, s, _body("action", "a", payload, {**good, blank: ""}), "incomplete caller fields")


# ---------------------------------------------------------------- REQUIRE


def test_require_caller_signature_start_type_unsigned_403(tmp_path, callers):
    """The fail-closed branch (``CallerPolicy.check``): REQUIRE=1 and a
    start-type body with no caller fields is 403 naming the env var, nothing
    written; a signed start-type body lands with NO ``caller_unsigned`` key."""
    s = _store(tmp_path, callers, require=True)
    client = TestClient(create_app(store=s))
    assert client.get("/health").json()["require_caller_signature"] is True
    payload = {"n": 1}
    for event_type in ("registry.updated", "conformance.allow", "delegation.mint", "kill", "lifecycle.decommission"):
        _refused(client, s, _body(event_type, "a", payload), REQUIRE_CALLER_SIGNATURE_ENV, event_type, "stop-type")
    assert not s.path.exists()
    r = _post(client, _body("conformance.allow", "a", payload, _claim(callers, SENTINEL, "conformance.allow", "a", payload)))
    assert r.status_code == 201 and r.json()["caller_id"] == SENTINEL and "caller_unsigned" not in r.json()
    [rec] = _lines(s.path)
    assert set(rec) == PRE_F2_KEYS | CALLER_FIELDS


@pytest.mark.parametrize("event_type", STOP_TYPES)
def test_require_caller_signature_stop_type_unsigned_201_caller_unsigned_true(tmp_path, callers, event_type):
    """The stamping branch: a stop-type body with no caller fields is 201
    with ``caller_unsigned: true`` stamped by the ledger INSIDE the hash (the
    caller sends nothing new; refusing it would keep an agent alive); a
    SIGNED stop-type body is not stamped; with REQUIRE=0 nothing is stamped."""
    s = _store(tmp_path, callers, require=True)
    client = TestClient(create_app(store=s))
    r = _post(client, _body(event_type, "a", {"reason": "F2b"}))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["caller_unsigned"] is True and not (set(body) & CALLER_FIELDS)
    ev = LedgerEvent.model_validate(body)
    assert compute_event_hash(ev) == ev.hash
    [rec] = _lines(s.path)
    assert set(rec) == PRE_F2_KEYS | {"caller_unsigned"} and rec["caller_unsigned"] is True
    assert client.get("/events").json() == [body]
    # a signed stop-type: the claim, no stamp
    claim = _claim(callers, KILLSWITCH, event_type, "a", {"reason": "F2b"})
    r = _post(client, _body(event_type, "a", {"reason": "F2b"}, claim))
    assert r.status_code == 201 and r.json()["caller_id"] == KILLSWITCH and "caller_unsigned" not in r.json()
    assert LedgerStore(s.path).verify().ok
    # removing the stamp from the line is a tamper, not a downgrade
    lines = _lines(s.path)
    del lines[0]["caller_unsigned"]
    s.path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    v = LedgerStore(s.path).verify()
    assert not v.ok and v.first_break_index == 0 and "mutated" in v.reason
    # REQUIRE=0: an unsigned stop-type is exactly a pre-F2b line
    s0 = _store(tmp_path / "off", callers, require=False)
    e = s0.append_for_caller(event_type, {"reason": "x"}, "a", claim=None)
    assert e.caller_unsigned is None and set(_lines(s0.path)[0]) == PRE_F2_KEYS


_FAULTS = ["wrong-key", "unknown-caller", "stale-ts", "incomplete", "no-keyring"]
_FAULT_NEEDLE = {"wrong-key": "invalid caller signature", "unknown-caller": "unknown caller",
                 "stale-ts": "replay window", "incomplete": "incomplete caller fields",
                 "no-keyring": "caller keyring not configured"}


def _bad_claim(callers, fault: str, event_type: str, payload: dict) -> dict:
    """A presented claim that fails verification for exactly one reason
    (``no-keyring``: a perfectly good claim the ledger cannot verify)."""
    if fault == "wrong-key":
        return _claim(callers, KILLSWITCH, event_type, "a", payload, priv=callers["stranger"]["priv"])
    if fault == "unknown-caller":
        return _claim(callers, "stranger", event_type, "a", payload, priv=callers["stranger"]["priv"])
    if fault == "stale-ts":
        return _claim(callers, KILLSWITCH, event_type, "a", payload,
                      ts=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat())
    if fault == "incomplete":
        return {k: v for k, v in _claim(callers, KILLSWITCH, event_type, "a", payload).items() if k != "caller_ts"}
    assert fault == "no-keyring"
    return _claim(callers, KILLSWITCH, event_type, "a", payload)


@pytest.mark.parametrize("fault", _FAULTS)
def test_require_caller_signature_stop_type_with_a_bad_claim_lands_unsigned_never_403(tmp_path, callers, fault, caplog):
    """F2's principle, applied to caller keys: a stop is never refused by a
    caller-key fault. Under REQUIRE=1 a stop-type body that PRESENTS a claim
    which does not verify lands 201 exactly like one that presents none —
    the bad claim DROPPED (none of the three fields stored), ``caller_unsigned:
    true`` stamped inside the hash, the reason logged (no key material) —
    while a start-type body with the same bad claim is 403, nothing written.
    (A perimeter-secret holder can already append that stop-type event with
    no claim at all, so accepting a bad claim as unsigned is no worse.)"""
    caplog.set_level(logging.WARNING, logger="sealed_ledger.store")
    s = _store(tmp_path, callers, keyring=fault != "no-keyring", require=True)
    client = TestClient(create_app(store=s))
    payload = {"reason": "F2b"}
    for n, event_type in enumerate(STOP_TYPES):
        r = _post(client, _body(event_type, "a", payload, _bad_claim(callers, fault, event_type, payload)))
        assert r.status_code == 201, (fault, event_type, r.text)
        body = r.json()
        assert body["caller_unsigned"] is True and not (set(body) & CALLER_FIELDS), (fault, event_type)
        ev = LedgerEvent.model_validate(body)
        assert compute_event_hash(ev) == ev.hash
        rec = _lines(s.path)[n]
        assert set(rec) == PRE_F2_KEYS | {"caller_unsigned"} and rec == body
    assert '"caller_id' not in s.path.read_text(encoding="utf-8")  # the bad claim never reached the disk
    warned = [rec.getMessage() for rec in caplog.records if rec.levelno >= logging.WARNING]
    assert len(warned) == len(STOP_TYPES), warned
    for w in warned:
        assert "landed caller_unsigned" in w and REQUIRE_CALLER_SIGNATURE_ENV in w and _FAULT_NEEDLE[fault] in w
        assert "BEGIN" not in w
    # the same bad claim on a start-type (near-misses included): 403 like any other, nothing more written
    for event_type in ("registry.updated", "conformance.allow", "kill", "lifecycle.decommission"):
        _refused(client, s, _body(event_type, "a", payload, _bad_claim(callers, fault, event_type, payload)),
                 _FAULT_NEEDLE[fault])
    assert client.get("/health").json()["event_count"] == len(STOP_TYPES)
    assert LedgerStore(s.path).verify().ok


@pytest.mark.parametrize("fault", _FAULTS)
def test_require_off_a_bad_claim_on_a_stop_type_is_403_like_any_other(tmp_path, callers, fault):
    """With REQUIRE=0 (the default) an unverifiable claim is never stored and
    never silently downgraded: a stop-type body that presents a bad claim is
    403 naming the fault, nothing written — the operator has not asked for
    fail-safe stops yet."""
    s = _store(tmp_path, callers, keyring=fault != "no-keyring", require=False)
    client = TestClient(create_app(store=s))
    payload = {"reason": "x"}
    for event_type in STOP_TYPES:
        _refused(client, s, _body(event_type, "a", payload, _bad_claim(callers, fault, event_type, payload)),
                 _FAULT_NEEDLE[fault])
    assert not s.path.exists()
    # the policy itself, switch off, raises for the same claim on a stop type
    with pytest.raises(CallerRefused, match=_FAULT_NEEDLE[fault]):
        CallerPolicy(None if fault == "no-keyring" else callers["keyring"]).check(
            "kill.agent", payload, "a", _bad_claim(callers, fault, "kill.agent", payload))


def test_ledger_own_events_are_exempt_from_require_caller_signature(tmp_path, callers, monkeypatch):
    """The ledger's own writes — the offline CLI append, hold placement and
    release, rotation, retention apply — are not served appends: under
    REQUIRE=1 they land with no caller fields and no ``caller_unsigned``
    stamp (the ledger's own F2 signature is what proves the ledger wrote them)."""
    p = tmp_path / "ledger" / "events.jsonl"
    s = LedgerStore(p, signing=load_signing_config(callers["ledger"]["priv_path"]),
                    caller=CallerPolicy(callers["keyring"], require_caller_signature=True))
    fill(s, 3)  # store.append, as the CLI does
    rot = rotate(s, "r1")
    assert rot.rotation_event.caller_unsigned is None and rot.rotation_event.caller_id is None
    s.place_hold(by="GC", reason="litigation")
    s.release_hold(by="GC")
    res = s.archive_closed_segments(older_than_days=0, archive_dir=tmp_path / "archive", operator="ops",
                                    data_dir=tmp_path)
    assert res["archived_segments"] == [1]
    for e in s.events():
        assert e.caller_unsigned is None and e.caller_id is None and e.signature is not None
    assert LedgerStore(p).verify().ok
    # the offline CLI append with the ledger's env (REQUIRE_CALLER=1, keyring on): exit 0, no caller keys
    monkeypatch.setenv(CALLER_KEYRING_ENV, str(callers["keyring"]))
    monkeypatch.setenv(REQUIRE_CALLER_SIGNATURE_ENV, "1")
    monkeypatch.delenv("FIELD_LEDGER_SIGN_KEY", raising=False)
    r = runner.invoke(cli_app, ["append", "registry.updated", "--path", str(p), "--payload", '{"n": 1}'])
    assert r.exit_code == 0, r.output
    line = json.loads(r.stdout.strip())
    assert not (set(line) & (CALLER_FIELDS | {"caller_unsigned"}))
    # while the served route with the same env refuses the same unsigned append
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "served"))
    client = TestClient(create_app())
    assert _post(client, _body("registry.updated", "a", {"n": 1})).status_code == 403


# ------------------------------------------------------------------- health


def test_health_reports_caller_keyring_and_require(tmp_path, callers):
    off = TestClient(create_app(store=_store(tmp_path, callers, keyring=False))).get("/health").json()
    assert off["caller_keyring"] == "off" and off["caller_keys"] == 0 and off["require_caller_signature"] is False
    on = TestClient(create_app(store=_store(tmp_path / "on", callers, require=True))).get("/health").json()
    assert on["caller_keyring"] == "on" and on["caller_keys"] == 2 and on["require_caller_signature"] is True
    for h in (off, on):  # every F2 and pre-F2 field stays
        for key in ("ok", "service", "version", "event_count", "head_hash", "earliest_live_index",
                    "earliest_live_ts", "build_sha", "appendable", "signing", "key_fingerprint",
                    "seal_algorithm", "require_signing"):
            assert key in h, key
        assert "key_error" not in h and "BEGIN" not in json.dumps(h)
    # a configured directory that does not exist: on, 0 keys, never a process exit
    missing = LedgerStore(tmp_path / "m" / "events.jsonl", caller=load_caller_policy(tmp_path / "absent"))
    h = TestClient(create_app(store=missing)).get("/health").json()
    assert h["caller_keyring"] == "on" and h["caller_keys"] == 0
    assert load_caller_policy("  ").keyring is None and load_caller_policy(None).keyring_state == "off"


def test_require_caller_signature_env_parsing(monkeypatch):
    for raw, want in {"1": True, "true": True, "YES": True, " on ": True, "0": False, "": False,
                      "no": False, "2": False, "enabled": False}.items():
        monkeypatch.setenv(REQUIRE_CALLER_SIGNATURE_ENV, raw)
        assert require_caller_signature_from_env() is want, raw
    monkeypatch.delenv(REQUIRE_CALLER_SIGNATURE_ENV)
    assert require_caller_signature_from_env() is False


def test_served_app_builds_the_policy_from_env_and_sees_a_key_imported_after_start(tmp_path, callers, monkeypatch):
    """The served store reads FIELD_LEDGER_CALLER_KEYRING /
    FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE once at start; the keyring FILES
    are read on lookup, so `keys-admin import-public` after the ledger
    started needs no restart."""
    keyring = tmp_path / "keys" / "callers"
    keyring.mkdir(parents=True)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv(CALLER_KEYRING_ENV, str(keyring))
    monkeypatch.setenv(REQUIRE_CALLER_SIGNATURE_ENV, "0")
    monkeypatch.delenv("FIELD_LEDGER_SIGN_KEY", raising=False)
    client = TestClient(create_app())
    h = client.get("/health").json()
    assert h["caller_keyring"] == "on" and h["caller_keys"] == 0 and h["require_caller_signature"] is False
    payload = {"n": 1}
    claim = _claim(callers, SENTINEL, "conformance.allow", "a", payload)
    assert _post(client, _body("conformance.allow", "a", payload, claim)).status_code == 403  # not imported yet
    (keyring / f"{SENTINEL}.pub.pem").write_text(callers[SENTINEL]["pub"], encoding="ascii")
    r = _post(client, _body("conformance.allow", "a", payload, claim))
    assert r.status_code == 201 and r.json()["caller_id"] == SENTINEL
    assert client.get("/health").json()["caller_keys"] == 1
    # the file replaced by another key (rotation of a caller key): the cache follows the file
    (keyring / f"{SENTINEL}.pub.pem").write_text(callers["stranger"]["pub"], encoding="ascii")
    assert _post(client, _body("conformance.allow", "a", payload,
                               _claim(callers, SENTINEL, "conformance.allow", "a", payload))).status_code == 403
    assert caller_policy_from_env().require_caller_signature is False
    monkeypatch.setenv(REQUIRE_CALLER_SIGNATURE_ENV, "1")
    assert caller_policy_from_env().require_caller_signature is True


def test_caller_policy_repr_and_stamp_event_guards(tmp_path, callers):
    policy = CallerPolicy(callers["keyring"], require_caller_signature=True)
    assert "require_caller_signature=True" in repr(policy) and repr(str(callers["keyring"])) in repr(policy)
    ev = make_event("action", {"n": 1})
    assert stamp_event(ev, {}) is ev
    with pytest.raises(ValueError):
        stamp_event(sign_event(ev, callers[SENTINEL]["priv"]), {"caller_unsigned": True})
    ring = CallerKeyring(callers["keyring"])
    assert ring.path_for("../x") is None and ring.path_for(SENTINEL) == callers["keyring"] / f"{SENTINEL}.pub.pem"
    assert CallerKeyring(tmp_path / "absent").count() == 0


# ------------------------------------------------------------ CLI verify


def _verify(*args: str):
    return runner.invoke(cli_app, ["verify", *args])


def _mixed_history(tmp_path: Path, callers, ledger_signed: bool = False) -> LedgerStore:
    """pre-F2b (2 unsigned) -> sentinel x2 -> killswitch -> a stamped stop-type
    (REQUIRE=1, no claim) -> sentinel: 7 events, 4 caller-signed."""
    s = _store(tmp_path, callers, ledger_signed=ledger_signed)
    s.append("action", {"n": 0})
    s.append("action", {"n": 1})
    for n in (2, 3):
        s.append_for_caller("conformance.allow", {"n": n}, "a", claim=_claim(callers, SENTINEL, "conformance.allow", "a", {"n": n}))
    s.append_for_caller("kill.agent", {"n": 4}, "a", claim=_claim(callers, KILLSWITCH, "kill.agent", "a", {"n": 4}))
    s.caller_policy = CallerPolicy(callers["keyring"], require_caller_signature=True)
    s.append_for_caller("delegation.revoke", {"n": 5}, "a", claim=None)
    s.caller_policy = CallerPolicy(callers["keyring"])
    s.append_for_caller("conformance.allow", {"n": 6}, "a", claim=_claim(callers, SENTINEL, "conformance.allow", "a", {"n": 6}))
    return s


SUMMARY = ("caller_signed 4 caller_unsigned 3 per_caller {conformance-sentinel: 3, killswitch: 1} "
           "first_caller_unsigned_after_signed 5")


def test_cli_verify_caller_keyring_reports_and_fails_correctly(tmp_path, callers):
    s = _mixed_history(tmp_path, callers)
    r = _verify("--path", str(s.path), "--caller-keyring", str(callers["keyring"]))
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines() == ["OK — chain intact over 7 events", SUMMARY]
    # without the flag the output is exactly what it was before F2b
    assert _verify("--path", str(s.path)).stdout.splitlines() == ["OK — chain intact over 7 events"]
    # a re-linked edit of a caller-signed event's payload: plain verify passes, the caller check names the index
    forged = tmp_path / "forged"
    forged.mkdir()
    (forged / "events.jsonl").write_bytes(s.path.read_bytes())
    _relink(forged / "events.jsonl", 2, lambda rec: rec["payload"].update(n=99))
    assert LedgerStore(forged / "events.jsonl").verify().ok
    r = _verify("--path", str(forged / "events.jsonl"), "--caller-keyring", str(callers["keyring"]))
    assert r.exit_code == 1, r.output
    assert r.stdout.splitlines()[0] == "OK — chain intact over 7 events"
    assert r.stdout.splitlines()[1].startswith("CALLER SIGNATURE INVALID — index 2:")
    assert "caller_signed " not in r.stdout  # no summary line on a failure
    # the caller id re-attributed to another known caller (signature kept): invalid at that index
    (forged / "events.jsonl").write_bytes(s.path.read_bytes())
    _relink(forged / "events.jsonl", 4, lambda rec: rec.update(caller_id=SENTINEL))
    r = _verify("--path", str(forged / "events.jsonl"), "--caller-keyring", str(callers["keyring"]))
    assert r.exit_code == 1 and "CALLER SIGNATURE INVALID — index 4:" in r.stdout
    # a keyring missing one caller: unknown at the first event that claims it
    partial = tmp_path / "partial-keyring"
    partial.mkdir()
    (partial / f"{SENTINEL}.pub.pem").write_bytes((callers["keyring"] / f"{SENTINEL}.pub.pem").read_bytes())
    r = _verify("--path", str(s.path), "--caller-keyring", str(partial))
    assert r.exit_code == 1, r.output
    assert r.stdout.splitlines()[1].startswith("CALLER UNKNOWN — index 4:") and "killswitch" in r.stdout
    # a keyring holding the WRONG key for a caller: invalid at its first event
    wrong = tmp_path / "wrong-keyring"
    wrong.mkdir()
    (wrong / f"{SENTINEL}.pub.pem").write_text(callers["stranger"]["pub"], encoding="ascii")
    (wrong / f"{KILLSWITCH}.pub.pem").write_bytes((callers["keyring"] / f"{KILLSWITCH}.pub.pem").read_bytes())
    r = _verify("--path", str(s.path), "--caller-keyring", str(wrong))
    assert r.exit_code == 1 and "CALLER SIGNATURE INVALID — index 2:" in r.stdout
    # a keyring file that is not a public key: unknown, never a crash
    (wrong / f"{SENTINEL}.pub.pem").write_text(callers["stranger"]["priv"], encoding="ascii")
    r = _verify("--path", str(s.path), "--caller-keyring", str(wrong))
    assert r.exit_code == 1 and "CALLER UNKNOWN — index 2:" in r.stdout and "BEGIN" not in r.output
    # --caller-keyring must be a directory
    for bad in (callers["keyring"] / f"{SENTINEL}.pub.pem", tmp_path / "absent"):
        r = _verify("--path", str(s.path), "--caller-keyring", str(bad))
        assert r.exit_code == 2 and "--caller-keyring" in r.output and "not a directory" in r.output
    # a chain break is reported first, with no caller summary
    _relink(forged / "events.jsonl", 1, lambda rec: rec["payload"].update(n=42))
    lines = (forged / "events.jsonl").read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[3])
    rec["payload"]["n"] = 7  # mutated without re-linking
    lines[3] = json.dumps(rec)
    (forged / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    r = _verify("--path", str(forged / "events.jsonl"), "--caller-keyring", str(callers["keyring"]))
    assert r.exit_code == 1 and r.stdout.startswith("TAMPERED — ") and "caller_signed" not in r.stdout


def test_cli_verify_caller_keyring_with_event_pubkey_prints_both_lines_in_order(tmp_path, callers):
    s = _mixed_history(tmp_path, callers, ledger_signed=True)
    r = _verify("--path", str(s.path), "--event-pubkey", str(callers["ledger"]["pub_path"]),
                "--caller-keyring", str(callers["keyring"]))
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines() == [
        "OK — chain intact over 7 events",
        "signed 7 unsigned 0 first_unsigned_index none first_signing_failed_index none "
        "first_unsigned_after_signed none",
        SUMMARY,
    ]
    # an attacker without the ledger key who edits a caller field and re-links
    # is caught by the ledger signature FIRST (it covers the caller fields)
    _relink(s.path, 3, lambda rec: rec.update(caller_id=KILLSWITCH))
    r = _verify("--path", str(s.path), "--event-pubkey", str(callers["ledger"]["pub_path"]),
                "--caller-keyring", str(callers["keyring"]))
    assert r.exit_code == 1 and "SIGNATURE INVALID — index 3:" in r.stdout.splitlines()[1]
    assert "CALLER" not in r.stdout
    r = _verify("--path", str(s.path), "--caller-keyring", str(callers["keyring"]))
    assert r.exit_code == 1 and "CALLER SIGNATURE INVALID — index 3:" in r.stdout


def test_cli_verify_caller_keyring_pre_f2b_history_reports_all_unsigned(tmp_path, callers):
    p = tmp_path / "events.jsonl"
    p.write_bytes((Path(__file__).resolve().parent / "fixtures" / "scene4" / "events.jsonl").read_bytes())
    r = _verify("--path", str(p), "--caller-keyring", str(callers["keyring"]))
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines() == [
        "OK — chain intact over 5 events",
        "caller_signed 0 caller_unsigned 5 per_caller {} first_caller_unsigned_after_signed none",
    ]


def test_cli_verify_caller_keyring_across_rotation_closed_archived_and_genesis_modes(tmp_path, callers):
    """Every verify mode checks caller signatures with GLOBAL indices (local
    on --genesis); rotation, hold and retention events are the ledger's own
    (counted caller_unsigned, never failed)."""
    p = tmp_path / "ledger" / "events.jsonl"
    s = _store(tmp_path / "ledger", callers, ledger_signed=True)

    def signed_fill(n: int, cid: str):
        for i in range(n):
            s.append_for_caller("action", {"n": i}, "a", claim=_claim(callers, cid, "action", "a", {"n": i}))

    signed_fill(4, SENTINEL)  # seg 1: global 0..3
    r1 = rotate(s, "r1")  # global 4: the rotation event (the ledger's own)
    signed_fill(3, KILLSWITCH)  # global 5..7
    rotate(s, "r2")  # global 8
    signed_fill(2, SENTINEL)  # global 9..10
    ring = str(callers["keyring"])
    r = _verify("--path", str(p), "--caller-keyring", ring, "--event-pubkey", str(callers["ledger"]["pub_path"]))
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines() == [
        "OK — chain intact over 11 events",
        "(3 segments, 0 archived; 11 events hash-verified)",
        "signed 11 unsigned 0 first_unsigned_index none first_signing_failed_index none "
        "first_unsigned_after_signed none",
        "caller_signed 9 caller_unsigned 2 per_caller {conformance-sentinel: 6, killswitch: 3} "
        "first_caller_unsigned_after_signed 4",
    ]
    # a live closed segment (global indices)
    r = _verify("--path", str(p.with_name("events-2.jsonl")), "--caller-keyring", ring)
    assert r.exit_code == 0 and r.stdout.splitlines()[-1] == (
        "caller_signed 3 caller_unsigned 1 per_caller {killswitch: 3} first_caller_unsigned_after_signed none")
    # --genesis mode: indices local to the file; a forged line inside it is named locally
    r = _verify("--path", str(p.with_name("events-2.jsonl")), "--genesis", r1.head_hash, "--caller-keyring", ring)
    assert r.exit_code == 0 and r.stdout.splitlines()[-1].startswith("caller_signed 3 caller_unsigned 1")
    copy = tmp_path / "copy" / "events-2.jsonl"
    copy.parent.mkdir()
    copy.write_bytes(p.with_name("events-2.jsonl").read_bytes())
    _relink(copy, 2, lambda rec: rec["payload"].update(n=99))
    r = _verify("--path", str(copy), "--genesis", r1.head_hash, "--caller-keyring", ring)
    assert r.exit_code == 1 and "CALLER SIGNATURE INVALID — index 2:" in r.stdout
    # an archived segment from its sidecar (the real retention apply)
    res = s.archive_closed_segments(older_than_days=0, archive_dir=tmp_path / "archive", operator="ops",
                                    data_dir=tmp_path)
    assert res["archived_segments"] == [1, 2]
    r = _verify("--path", str(tmp_path / "archive" / "events-1.jsonl"), "--caller-keyring", ring)
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines()[-1] == (
        "caller_signed 4 caller_unsigned 0 per_caller {conformance-sentinel: 4} first_caller_unsigned_after_signed none")
    # the live walk after archival: rotation event + 2 signed + the retention event
    r = _verify("--path", str(p), "--caller-keyring", ring)
    assert r.exit_code == 0 and r.stdout.splitlines()[-1] == (
        "caller_signed 2 caller_unsigned 2 per_caller {conformance-sentinel: 2} first_caller_unsigned_after_signed 11")


# ---------------------------------------------------------------- export


def test_export_bundle_carries_caller_fields_verbatim_and_verifies(tmp_path, callers):
    s = _mixed_history(tmp_path, callers)
    bundle = Path(s.export(tmp_path / "exports").bundle_dir)
    lines = _lines(bundle / "events.jsonl")
    assert lines == _lines(s.path)
    assert all(set(rec) <= set(LedgerEvent.model_fields) for rec in lines)
    assert [rec.get("caller_id") for rec in lines] == [None, None, SENTINEL, SENTINEL, KILLSWITCH, None, SENTINEL]
    assert lines[5]["caller_unsigned"] is True
    assert verify_bundle(bundle).ok
    r = runner.invoke(cli_app, ["verify-export", str(bundle)])
    assert r.exit_code == 0, r.output


# --------------------------------------------------------------- witness


def test_witness_direction_1_carries_caller_fields_when_a_signer_is_given(tmp_path, callers, monkeypatch):
    """The witness appends anchor.remote through its own httpx client: with a
    ``CallerSigner`` (the CLI builds one from the env) the body gains the
    three caller keys and they verify; without one the body is unchanged."""
    from sealed_ledger import witness as w

    anchor = tmp_path / "ledger-anchor.pem"
    anchor.write_text(KEY_PRIV, encoding="ascii")
    monkeypatch.setenv("FIELD_LEDGER_ANCHOR_KEY", str(anchor))
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    posted: list[dict] = []

    def fly(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"event_count": 42, "head_hash": "ab" * 32})

    def ledger(request: httpx.Request) -> httpx.Response:
        posted.append(json.loads(request.content))
        return httpx.Response(201, json={"hash": "ef" * 32})

    def witness(caller):
        return w.Witness(local_estate="gb10", fly_url="https://fly.test",
                         fly=w.build_fly_client(transport=httpx.MockTransport(fly)),
                         ledger=w.build_ledger_client("http://ledger:8002", transport=httpx.MockTransport(ledger)),
                         observer=w.observer_record("2026-09-14T00:00:00+00:00"), caller=caller)

    assert witness(None).tick().direction1 == "appended"
    assert set(posted[0]) == {"event_type", "payload", "agent_id"}
    signer = CallerSigner("witness", load_ed25519_private_key(callers[KILLSWITCH]["priv"]))
    assert witness(signer).tick().direction1 == "appended"
    body = posted[1]
    assert set(body) == {"event_type", "payload", "agent_id", "caller_id", "caller_ts", "caller_signature"}
    assert body["caller_id"] == "witness" and verify_caller_signature(body, callers[KILLSWITCH]["pub"])
    # and the ledger accepts exactly that body under a keyring holding witness.pub.pem
    ring = tmp_path / "ring"
    ring.mkdir()
    (ring / "witness.pub.pem").write_text(callers[KILLSWITCH]["pub"], encoding="ascii")
    s = LedgerStore(tmp_path / "events.jsonl", caller=CallerPolicy(ring))
    r = TestClient(create_app(store=s)).post("/events", json=body)
    assert r.status_code == 201 and r.json()["caller_id"] == "witness"
    from field_core.signing import verify_manifest  # the anchor itself is still signed by the anchor key

    a = dict(r.json()["payload"])
    assert verify_manifest(a, a.pop("signature"), KEY_PUB)
