"""F2b — caller signatures in field-core (additive) and the caller side of
``LedgerClient.append``.

Pins: an unsigned event serialises with NO ``caller_id`` / ``caller_ts`` /
``caller_signature`` / ``caller_unsigned`` key (the additive-compat rule; a
pre-F2 line parses with its hash unchanged); ``caller_signing_bytes`` covers
exactly five keys, canonically; sign/verify round-trips and every covered
field mutation fails while the ledger-only fields do not matter; the caller
fields are INSIDE the hash and under the ledger's F2 signature; the client
body is exactly the pre-F2b body when the env is unset, gains the three
caller keys when both vars are set (key loaded once per client), and is
UNSIGNED with one warning per process — never an exception — when the key
is configured but cannot be loaded.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

import field_core.clients as clients
from field_core.clients import CALLER_ID_ENV, CALLER_KEY_ENV, CallerSigner, LedgerClient
from field_core.ledger import LedgerEvent, compute_event_hash, make_event, verify_chain
from field_core.signing import (
    CALLER_SIGNED_KEYS,
    caller_signing_bytes,
    generate_keypair,
    load_ed25519_private_key,
    load_ed25519_public_key,
    sign_caller,
    sign_event,
    verify_caller_signature,
    verify_event_signature,
)

PRE_F2_KEYS = {"event_id", "ts", "event_type", "agent_id", "payload", "prev_hash", "hash"}
CALLER_KEYS = {"caller_id", "caller_ts", "caller_signature", "caller_unsigned"}
#: The first line of services/sealed-ledger/tests/fixtures/scene4/events.jsonl
#: (written 2026-08-10, long before F2/F2b), verbatim.
PRE_F2_LINE = (
    '{"event_id":"9feddef0-cb8a-49b9-9502-71c0ce135bea","ts":"2026-08-10T13:59:02.701357+00:00",'
    '"event_type":"conformance.allow","agent_id":"invoicing-agent","payload":{"action":"draft invoices",'
    '"invoice":"INV-001","amount":1200},"prev_hash":"0000000000000000000000000000000000000000000000000000000000000000",'
    '"hash":"626d8e83a92037d6efc26de85f0505684a44d8c078079e46643260adc8fdc9b7"}'
)
CID = "conformance-sentinel"


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    d = tmp_path_factory.mktemp("caller-keys")
    private_pem, public_pem = generate_keypair()
    _, other_public = generate_keypair()
    priv = d / f"{CID}.pem"
    priv.write_text(private_pem, encoding="ascii")
    return {"private": private_pem, "public": public_pem, "other_public": other_public, "priv_path": priv}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamped(event: LedgerEvent, **fields) -> LedgerEvent:
    """An event with extra fields sealed INSIDE its hash (what the ledger's
    ``stamp_event`` does)."""
    record = event.model_dump(exclude={"hash", "signature"})
    record.update(fields)
    return LedgerEvent(**record, hash=compute_event_hash(record))


# ------------------------------------------------- additive compat (the rule)


def test_unsigned_event_json_has_no_caller_keys():
    """The additive-compat rule for F2b: an event appended without caller
    fields carries none of the four keys in model_dump(), model_dump_json()
    and the JSON-mode dump — exactly the seven pre-F2 keys."""
    ev = make_event("action", {"n": 1}, agent_id="a")
    assert ev.caller_id is None and ev.caller_ts is None
    assert ev.caller_signature is None and ev.caller_unsigned is None
    for dumped in (ev.model_dump(), ev.model_dump(mode="json"), json.loads(ev.model_dump_json())):
        assert not (set(dumped) & CALLER_KEYS)
        assert set(dumped) == PRE_F2_KEYS


def test_pre_f2_fixture_line_parses_unchanged_and_its_hash_is_unchanged():
    raw = json.loads(PRE_F2_LINE)
    ev = LedgerEvent.model_validate(raw)
    assert compute_event_hash(ev) == raw["hash"] == compute_event_hash(raw)
    assert json.loads(ev.model_dump_json()) == raw
    # a dict spelling the omission as None hashes like the omission
    assert compute_event_hash({**raw, "caller_id": None, "caller_ts": None,
                               "caller_signature": None, "caller_unsigned": None}) == raw["hash"]
    with pytest.raises(ValueError):  # extra='forbid' is unchanged
        LedgerEvent.model_validate({**raw, "caller_pubkey": "x"})


def test_caller_stamped_line_round_trips_with_exactly_the_three_keys_added(keys):
    ev = make_event("conformance.allow", {"action": "x"}, agent_id="a")
    ts = _ts()
    sig = sign_caller(keys["private"], event_type=ev.event_type, agent_id=ev.agent_id,
                      payload=ev.payload, caller_id=CID, caller_ts=ts)
    stamped = _stamped(ev, caller_id=CID, caller_ts=ts, caller_signature=sig)
    line = json.loads(stamped.model_dump_json())
    assert set(line) == PRE_F2_KEYS | {"caller_id", "caller_ts", "caller_signature"}
    assert "caller_unsigned" not in line
    back = LedgerEvent.model_validate(line)
    assert back == stamped and verify_caller_signature(back, keys["public"])
    assert verify_caller_signature(line, keys["public"])  # a dict off disk works too


# ------------------------------------------------ what the signature covers


def test_caller_signing_bytes_cover_exactly_five_keys_canonically():
    b = caller_signing_bytes("t", "a", {"z": 1, "y": [1, 2]}, CID, "2026-09-14T00:00:00+00:00")
    assert b == b'{"agent_id":"a","caller_id":"conformance-sentinel","caller_ts":"2026-09-14T00:00:00+00:00",' \
                b'"event_type":"t","payload":{"y":[1,2],"z":1}}'
    assert set(json.loads(b)) == set(CALLER_SIGNED_KEYS)
    # key order in the payload does not matter; every covered value does
    assert caller_signing_bytes("t", "a", {"y": [1, 2], "z": 1}, CID, "2026-09-14T00:00:00+00:00") == b
    assert caller_signing_bytes("t", None, {}, CID, "x") != caller_signing_bytes("t", "", {}, CID, "x")
    for changed in (("t2", "a", {"z": 1, "y": [1, 2]}, CID, "2026-09-14T00:00:00+00:00"),
                    ("t", "b", {"z": 1, "y": [1, 2]}, CID, "2026-09-14T00:00:00+00:00"),
                    ("t", "a", {"z": 2, "y": [1, 2]}, CID, "2026-09-14T00:00:00+00:00"),
                    ("t", "a", {"z": 1, "y": [1, 2]}, "killswitch", "2026-09-14T00:00:00+00:00"),
                    ("t", "a", {"z": 1, "y": [1, 2]}, CID, "2026-09-14T00:00:01+00:00")):
        assert caller_signing_bytes(*changed) != b


def test_sign_caller_round_trips_with_a_pem_or_a_loaded_key_and_every_covered_mutation_fails(keys):
    ts = _ts()
    kw = dict(event_type="spend", agent_id="fin", payload={"amount": 1200}, caller_id=CID, caller_ts=ts)
    sig = sign_caller(keys["private"], **kw)
    assert sig == sign_caller(load_ed25519_private_key(keys["private"]), **kw)
    assert len(base64.b64decode(sig, validate=True)) == 64
    ev = _stamped(make_event("spend", {"amount": 1200}, agent_id="fin"),
                  caller_id=CID, caller_ts=ts, caller_signature=sig)
    assert verify_caller_signature(ev, keys["public"])
    assert not verify_caller_signature(ev, keys["other_public"])  # wrong key
    for field, value in (("payload", {"amount": 12}), ("agent_id", "b"), ("event_type", "x"),
                         ("caller_id", "killswitch"), ("caller_ts", "2020-01-01T00:00:00+00:00")):
        assert not verify_caller_signature(ev.model_copy(update={field: value}), keys["public"]), field
    # the ledger-only fields are NOT under the caller signature (the caller never knows them)
    for field, value in (("event_id", "other"), ("ts", "2020-01-01T00:00:00+00:00"),
                         ("prev_hash", "1" * 64), ("hash", "f" * 64), ("signature", "AAAA")):
        assert verify_caller_signature(ev.model_copy(update={field: value}), keys["public"]), field
    # no signature, a malformed one, an incomplete claim, a bad key: never True
    assert not verify_caller_signature(ev.model_copy(update={"caller_signature": None}), keys["public"])
    assert not verify_caller_signature(ev.model_copy(update={"caller_signature": "not base64!"}), keys["public"])
    assert not verify_caller_signature(ev.model_copy(update={"caller_id": None}), keys["public"])
    assert not verify_caller_signature(ev.model_copy(update={"caller_ts": None}), keys["public"])
    assert not verify_caller_signature(ev, "-----BEGIN PUBLIC KEY-----\nnope\n-----END PUBLIC KEY-----\n")
    assert not verify_caller_signature(ev, keys["private"])  # a private PEM is not a public key
    assert not verify_caller_signature(make_event("spend"), keys["public"])  # no claim at all


def test_caller_fields_are_inside_the_hash_and_under_the_ledger_signature(keys):
    """Hash first, ledger-sign second: the caller fields change the hash, and
    the ledger's F2 ``signature`` (over the hashed record) covers them, so an
    attacker without the ledger key who edits ``caller_id`` and re-links is
    caught by ``verify --event-pubkey`` as well as by the caller check."""
    ledger_priv, ledger_pub = generate_keypair()
    plain = make_event("action", {"n": 1}, agent_id="a")
    ts = _ts()
    sig = sign_caller(keys["private"], event_type="action", agent_id="a", payload={"n": 1},
                      caller_id=CID, caller_ts=ts)
    stamped = _stamped(plain, caller_id=CID, caller_ts=ts, caller_signature=sig)
    assert stamped.hash != plain.hash and compute_event_hash(stamped) == stamped.hash
    for field, value in (("caller_id", "killswitch"), ("caller_ts", "x"), ("caller_signature", "AAAA")):
        assert compute_event_hash(stamped.model_copy(update={field: value})) != stamped.hash, field
    # stripping the three keys off the line is a chain break, not a downgrade
    line = json.loads(stamped.model_dump_json())
    stripped = {k: v for k, v in line.items() if k not in CALLER_KEYS}
    assert compute_event_hash(stripped) != stamped.hash
    assert not verify_chain([LedgerEvent.model_validate(stripped)]).ok
    # the ledger's own signature covers them
    signed = sign_event(stamped, ledger_priv)
    assert verify_event_signature(signed, ledger_pub) and verify_caller_signature(signed, keys["public"])
    forged = signed.model_dump()
    forged["caller_id"] = "killswitch"
    forged.pop("hash")
    forged = LedgerEvent(**{**forged, "hash": compute_event_hash(forged)})  # re-linked, signature kept
    assert verify_chain([forged]).ok  # the plain chain is blind to it
    assert not verify_event_signature(forged, ledger_pub)  # the ledger signature is not
    assert not verify_caller_signature(forged, keys["public"])  # nor the caller's
    # caller_unsigned is inside the hash too
    flagged = _stamped(plain, caller_unsigned=True)
    assert flagged.hash != plain.hash and json.loads(flagged.model_dump_json())["caller_unsigned"] is True
    assert compute_event_hash({**plain.model_dump(), "caller_unsigned": None}) == plain.hash


def test_load_ed25519_public_key_refuses_private_ec_and_garbage(keys):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    ec_pub = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
    assert load_ed25519_public_key(keys["public"]).public_bytes_raw()
    for bad in (keys["private"], ec_pub, "garbage", "", "-----BEGIN PUBLIC KEY-----\nnope\n-----END PUBLIC KEY-----\n"):
        with pytest.raises(ValueError) as exc_info:
            load_ed25519_public_key(bad)
        assert "BEGIN" not in str(exc_info.value)


# --------------------------------------------------------------- the client


class _Resp:
    status_code = 201
    text = ""

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class _Http:
    """Captures every POST body (the JSON the wire would carry)."""

    def __init__(self):
        self.bodies: list[dict] = []

    def post(self, url, **kwargs):
        body = kwargs["json"]
        json.dumps(body)  # what httpx does: the body must be JSON-encodable
        self.bodies.append(body)
        return _Resp({"ok": True, **body})

    def get(self, url, **kwargs):  # pragma: no cover - not used here
        raise AssertionError

    def patch(self, url, **kwargs):  # pragma: no cover - not used here
        raise AssertionError


@pytest.fixture()
def clean_env(monkeypatch):
    monkeypatch.delenv(CALLER_ID_ENV, raising=False)
    monkeypatch.delenv(CALLER_KEY_ENV, raising=False)
    monkeypatch.setattr(clients, "_caller_key_warned", False)  # "one per process" starts fresh
    return monkeypatch


def _warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.name == "field_core.clients" and r.levelno >= logging.WARNING]


def test_append_body_is_exactly_the_pre_f2b_body_when_the_env_is_unset(clean_env, caplog):
    caplog.set_level(logging.WARNING, logger="field_core.clients")
    http = _Http()
    out = LedgerClient(client=http, base_url="http://t").append("action", {"n": 1}, agent_id="a")
    assert http.bodies == [{"event_type": "action", "payload": {"n": 1}, "agent_id": "a"}]
    assert out["ok"] is True
    assert _warnings(caplog) == []


def test_append_signs_when_both_vars_are_set_and_loads_the_key_once_per_client(clean_env, keys, caplog, tmp_path):
    caplog.set_level(logging.WARNING, logger="field_core.clients")
    key = tmp_path / "k.pem"
    key.write_text(keys["private"], encoding="ascii")
    clean_env.setenv(CALLER_ID_ENV, CID)
    clean_env.setenv(CALLER_KEY_ENV, str(key))
    http = _Http()
    client = LedgerClient(client=http, base_url="http://t")
    key.unlink()  # loaded at construction: appends must not read it again
    before = datetime.now(timezone.utc)
    client.append("conformance.allow", {"action": "x", "n": 1}, agent_id="canary")
    client.append("kill.agent", {"reason": "y"}, agent_id=None)
    assert len(http.bodies) == 2
    for body, (event_type, payload, agent_id) in zip(
            http.bodies, [("conformance.allow", {"action": "x", "n": 1}, "canary"), ("kill.agent", {"reason": "y"}, None)]):
        assert set(body) == {"event_type", "payload", "agent_id", "caller_id", "caller_ts", "caller_signature"}
        assert body["event_type"] == event_type and body["payload"] == payload and body["agent_id"] == agent_id
        assert body["caller_id"] == CID
        ts = datetime.fromisoformat(body["caller_ts"])
        assert ts.tzinfo is not None and ts.utcoffset() == timedelta(0)
        assert before - timedelta(seconds=1) <= ts <= datetime.now(timezone.utc) + timedelta(seconds=1)
        assert verify_caller_signature(body, keys["public"])
        assert not verify_caller_signature(body, keys["other_public"])
        assert "caller_unsigned" not in body
    assert _warnings(caplog) == []
    # a NEW client with the key gone: unsigned, one warning (the load is per client)
    unsigned = _Http()
    LedgerClient(client=unsigned, base_url="http://t").append("action", {}, agent_id="a")
    assert unsigned.bodies == [{"event_type": "action", "payload": {}, "agent_id": "a"}]
    assert len(_warnings(caplog)) == 1 and CALLER_KEY_ENV in _warnings(caplog)[0]


@pytest.mark.parametrize("state", ["missing-file", "directory", "garbage", "public-key", "not-ed25519", "non-ascii"])
def test_key_configured_but_unloadable_appends_unsigned_with_one_warning_per_process_and_never_raises(
        clean_env, keys, caplog, tmp_path, state):
    """The never-raise branch (``CallerSigner.from_env``): the caller must
    still be able to revoke and kill; the ledger's REQUIRE switch is the
    enforcement point. Exactly ONE warning across two clients and three
    appends, naming the env var and the failure class, never key material."""
    caplog.set_level(logging.WARNING, logger="field_core.clients")
    d = tmp_path / "keys"
    d.mkdir()
    path = {"missing-file": d / "absent.pem", "directory": d, "garbage": d / "garbage.pem",
            "public-key": d / "pub.pem", "not-ed25519": d / "ec.pem", "non-ascii": d / "utf.pem"}[state]
    if state == "garbage":
        path.write_bytes(b"-----BEGIN PRIVATE KEY-----\nnot a key\n-----END PRIVATE KEY-----\n")
    if state == "public-key":
        path.write_text(keys["public"], encoding="ascii")
    if state == "non-ascii":
        path.write_bytes("clé\n".encode("utf-8"))
    if state == "not-ed25519":
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        path.write_bytes(ec.generate_private_key(ec.SECP256R1()).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    clean_env.setenv(CALLER_ID_ENV, CID)
    clean_env.setenv(CALLER_KEY_ENV, str(path))
    http = _Http()
    a, b = LedgerClient(client=http, base_url="http://t"), LedgerClient(client=http, base_url="http://t")
    assert a._caller is None and b._caller is None
    assert a.append("registry.updated", {"n": 1}, agent_id="x")["ok"] is True
    assert a.append("kill.agent", {"reason": "r"}, agent_id="x")["ok"] is True  # the kill still goes out
    assert b.append("delegation.revoke", {}, agent_id="x")["ok"] is True
    assert all(set(body) == {"event_type", "payload", "agent_id"} for body in http.bodies)
    warned = _warnings(caplog)
    assert len(warned) == 1, warned
    assert CALLER_KEY_ENV in warned[0] and "appending unsigned" in warned[0]
    assert "BEGIN" not in warned[0] and "not a key" not in warned[0]
    assert keys["private"].strip().splitlines()[1][:16] not in warned[0]


@pytest.mark.parametrize("only", [CALLER_ID_ENV, CALLER_KEY_ENV])
def test_only_one_of_the_two_vars_set_appends_unsigned_with_one_warning(clean_env, keys, caplog, only):
    caplog.set_level(logging.WARNING, logger="field_core.clients")
    clean_env.setenv(only, CID if only == CALLER_ID_ENV else str(keys["priv_path"]))
    http = _Http()
    LedgerClient(client=http, base_url="http://t").append("action", {}, agent_id="a")
    LedgerClient(client=http, base_url="http://t").append("action", {}, agent_id="a")
    assert all(set(body) == {"event_type", "payload", "agent_id"} for body in http.bodies)
    warned = _warnings(caplog)
    assert len(warned) == 1 and "BOTH" in warned[0] and CALLER_ID_ENV in warned[0] and CALLER_KEY_ENV in warned[0]


def test_an_uncanonicalisable_payload_is_sent_unsigned_with_a_warning_not_an_exception_here(clean_env, keys, caplog):
    caplog.set_level(logging.WARNING, logger="field_core.clients")
    signer = CallerSigner(CID, load_ed25519_private_key(keys["private"]))
    client = LedgerClient(client=_Http(), base_url="http://t", caller=signer)
    body = client.append_body("action", {"when": datetime(2026, 9, 14)}, "a")  # datetime: not JSON
    assert set(body) == {"event_type", "payload", "agent_id"}
    assert len(_warnings(caplog)) == 1 and "payload not canonicalisable" in _warnings(caplog)[0]


def test_caller_signer_repr_never_shows_key_material(keys):
    signer = CallerSigner(CID, load_ed25519_private_key(keys["private"]))
    secret_fragment = keys["private"].strip().splitlines()[1][:16]
    for text in (repr(signer), str(signer), f"{signer}"):
        assert CID in text and "BEGIN" not in text and secret_fragment not in text
    fields = signer.fields("action", "a", {"n": 1})
    assert set(fields) == {"caller_id", "caller_ts", "caller_signature"}
    assert verify_caller_signature({"event_type": "action", "agent_id": "a", "payload": {"n": 1}, **fields},
                                   keys["public"])
