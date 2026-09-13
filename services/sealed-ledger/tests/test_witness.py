"""X4 — cross-estate witnessing: ``ledger witness run`` and ``ledger verify-witness``.

Every guard below has a test that fails without it:
- a tick against a stub Fly (httpx MockTransport, https) and the REAL ledger app
  served by uvicorn appends exactly one signed ``anchor.remote`` with the spec's fields,
  through the served route with the local perimeter header;
- Fly down / non-200 / a redirect / not a head ⇒ nothing appended;
- no usable key ⇒ nothing appended, nothing sent, and the loop keeps running;
- direction 2 is off by default (one "not live (D5)" line per tick) and on with a
  secret file (Fly receives the POST with that header, body signed);
- neither secret is ever logged, not even a prefix of one cut by the 200-character
  body truncation, and the local secret never goes to Fly;
- verify-witness: every anchor holds ⇒ 0; an edited head_hash ⇒ 1 naming it; a future
  length ⇒ 1; an archived index ⇒ explicit failure; a missing index ⇒ failure; zero
  anchors, or only length-0 anchors ⇒ 1 "nothing witnessed"; a bad signature with
  --pubkey ⇒ 1; duplicate keys refused; across a rotated ledger; --events-url never
  follows a redirect with the secret.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from typer.testing import CliRunner

from field_core.signing import generate_keypair, key_fingerprint, verify_manifest
from ledger_c2_support import KEY_PRIV, fill, rotate, three_segments
from sealed_ledger import witness as w
from sealed_ledger.api import create_app
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import LedgerStore

runner = CliRunner()
FLY = "https://fly.test"
FLY_HEAD = "ab" * 32
LOCAL_SECRET = "local-perimeter-SECRET-5f1e"
FLY_SECRET = "fly-perimeter-SECRET-9a7c"
OBSERVED = "2026-09-13T12:00:00+00:00"
PRIV, PUB = generate_keypair()


# ------------------------------------------------------------------------------ fixtures


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    """The real ledger app on a real socket; each test swaps in its own store."""
    import uvicorn

    app = create_app(store=LedgerStore(tmp_path_factory.mktemp("served") / "events.jsonl"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    yield app, f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(10)


@pytest.fixture()
def env(monkeypatch, tmp_path):
    for name in ("FIELD_LEDGER_URL", "FIELD_SHARED_SECRET", "FIELD_LEDGER_ANCHOR_KEY", w.FLY_SECRET_FILE_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    key = tmp_path / "keys" / "ledger-anchor.pem"
    key.parent.mkdir()
    key.write_text(PRIV, encoding="ascii")
    monkeypatch.setenv("FIELD_LEDGER_ANCHOR_KEY", str(key))
    monkeypatch.setenv("FIELD_SHARED_SECRET", LOCAL_SECRET)
    return monkeypatch


@pytest.fixture()
def local(served, tmp_path):
    app, url = served
    store = LedgerStore(tmp_path / "gb10" / "events.jsonl")
    fill(store, 3)
    app.state.store = store
    return store, url


class StubFly:
    """Fly's open /ledger/health and its perimeter-guarded POST /ledger/events."""

    def __init__(self, health=None, status=200, raise_exc=None, redirect=False, post_status=201):
        self.requests: list[httpx.Request] = []
        self.health = health if health is not None else {"ok": True, "service": "sealed-ledger",
                                                         "event_count": 42, "head_hash": FLY_HEAD}
        self.status, self.raise_exc, self.redirect, self.post_status = status, raise_exc, redirect, post_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_exc is not None:
            raise self.raise_exc
        if request.url.host == "evil.test":
            return httpx.Response(200, json={"event_count": 7, "head_hash": "cd" * 32})
        if request.method == "GET" and request.url.path == "/ledger/health":
            if self.redirect:
                return httpx.Response(302, headers={"location": "https://evil.test/ledger/health"})
            body = self.health if isinstance(self.health, (bytes, str)) else json.dumps(self.health)
            return httpx.Response(self.status, content=body)
        if request.method == "POST" and request.url.path == "/ledger/events":
            if self.post_status != 201:  # an adversarial refusal that echoes what it was sent
                return httpx.Response(self.post_status, text=f"bad x-field-auth {request.headers.get('x-field-auth')}")
            return httpx.Response(201, json={"hash": "ef" * 32})
        return httpx.Response(404)


def _witness(stub: StubFly, ledger_url: str, clock=lambda: OBSERVED) -> w.Witness:
    return w.Witness(local_estate="gb10", fly_url=FLY, fly=w.build_fly_client(transport=httpx.MockTransport(stub)),
                     ledger=w.build_ledger_client(ledger_url), observer=w.observer_record("2026-09-13T11:00:00+00:00"),
                     clock=clock)


def _anchors(store: LedgerStore, estate: str = "fly") -> list:
    return [e for e in store.events(event_type="anchor.remote") if e.payload.get("estate") == estate]


# ------------------------------------------------------------------------------ direction 1


def test_a_tick_appends_exactly_one_signed_anchor_remote_through_the_served_route(env, local, caplog):
    store, url = local
    stub = StubFly()
    caplog.set_level(logging.INFO, logger="sealed_ledger.witness")
    before = store.snapshot().global_length
    outcome = _witness(stub, url).tick()
    assert outcome.direction1 == "appended" and outcome.direction2 == "not-live"
    fresh = LedgerStore(store.path)
    assert fresh.snapshot().global_length == before + 1
    [event] = fresh.events(event_type="anchor.remote")
    p = event.payload
    assert tuple(sorted(p)) == tuple(sorted(w.PAYLOAD_FIELDS))
    assert (p["estate"], p["length"], p["head_hash"], p["observed_at"]) == ("fly", 42, FLY_HEAD, OBSERVED)
    assert p["observer"] == {"role": "witness", "host": socket.gethostname(),
                             "started_at": "2026-09-13T11:00:00+00:00"}
    assert p["key_fingerprint"] == key_fingerprint(PUB)
    assert verify_manifest({k: v for k, v in p.items() if k != "signature"}, p["signature"], PUB)
    assert event.agent_id is None
    # one GET of Fly's open health route, and the local perimeter secret never went to Fly
    assert [(r.method, str(r.url)) for r in stub.requests] == [("GET", f"{FLY}/ledger/health")]
    assert all("x-field-auth" not in r.headers for r in stub.requests)


def test_the_local_append_carries_the_perimeter_header(env, local):
    """The served ledger refuses without x-field-auth; the builder sends the env secret."""
    store, url = local
    env.setenv("FIELD_SHARED_SECRET", "a-different-secret-than-the-client-had")
    witness = _witness(StubFly(), url)  # client built while the env holds that secret
    env.setenv("FIELD_SHARED_SECRET", LOCAL_SECRET)  # server now expects another one
    assert witness.tick().direction1 == "ledger-refused"
    assert _anchors(LedgerStore(store.path)) == []
    assert _witness(StubFly(), url).tick().direction1 == "appended"


@pytest.mark.parametrize("stub", [
    StubFly(raise_exc=httpx.ConnectError("connection refused")),
    StubFly(raise_exc=httpx.ReadTimeout("timed out")),
    StubFly(status=503),
    StubFly(redirect=True),
    StubFly(health=b"<html>maintenance</html>"),
    StubFly(health={"event_count": True, "head_hash": FLY_HEAD}),
    StubFly(health={"event_count": 42, "head_hash": "AB" * 32}),
    StubFly(health={"event_count": -1, "head_hash": FLY_HEAD}),
    StubFly(health='{"event_count": 42, "head_hash": "%s", "head_hash": "%s"}' % ("cd" * 32, FLY_HEAD)),
], ids=["down", "timeout", "503", "redirect", "not-json", "bool-count", "upper-hex", "negative", "dup-key"])
def test_a_failed_fly_read_appends_nothing(env, local, stub, caplog):
    store, url = local
    caplog.set_level(logging.INFO, logger="sealed_ledger.witness")
    before = LedgerStore(store.path).snapshot().global_length
    assert _witness(stub, url).tick().direction1 == "fly-unreadable"
    assert LedgerStore(store.path).snapshot().global_length == before
    assert "nothing appended" in caplog.text
    assert all(r.url.host != "evil.test" for r in stub.requests)  # a redirect is never followed


def test_the_fly_client_never_follows_redirects_and_has_a_timeout():
    import ssl

    client = w.build_fly_client()
    assert client.follow_redirects is False and client.timeout.read == w.HTTP_TIMEOUT_S
    assert "x-field-auth" not in client.headers
    context = client._transport._pool._ssl_context  # httpx 0.28 internals: TLS certificate + hostname checked
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True


def test_fly_url_must_be_https(env, local):
    _, url = local
    for bad in ("http://fly.test", "fly.test", "ftp://fly.test", "https://"):
        with pytest.raises(ValueError):
            w.Witness(local_estate="gb10", fly_url=bad, fly=w.build_fly_client(), ledger=w.build_ledger_client(url),
                      observer=w.observer_record(OBSERVED))
    env.setenv("FIELD_LEDGER_URL", url)
    r = runner.invoke(cli_app, ["witness", "run", "--once", "--estate", "gb10", "--fly-url", "http://fly.test"])
    assert r.exit_code == 2 and "https" in r.output


def _ec_key() -> str:
    return ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()


@pytest.mark.parametrize("key", ["unset", "missing", "garbage", "ec"])
def test_no_usable_key_appends_nothing_sends_nothing_and_the_loop_keeps_running(env, local, tmp_path, key, caplog):
    store, url = local
    key_path = Path(str(tmp_path / "keys" / "ledger-anchor.pem"))
    if key == "unset":
        env.delenv("FIELD_LEDGER_ANCHOR_KEY")
    elif key == "missing":
        key_path.unlink()
    elif key == "garbage":
        key_path.write_text("not a key\n", encoding="ascii")
    else:
        key_path.write_text(_ec_key(), encoding="ascii")
    caplog.set_level(logging.INFO, logger="sealed_ledger.witness")
    stub = StubFly()
    witness = _witness(stub, url)
    before = LedgerStore(store.path).snapshot().global_length
    stop = threading.Event()
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 1:  # the operator fixes the key between ticks: re-read per tick
            key_path.write_text(PRIV, encoding="ascii")
            env.setenv("FIELD_LEDGER_ANCHOR_KEY", str(key_path))
        else:
            stop.set()

    assert w.run_loop(witness.tick, 3600, stop, sleep=fake_sleep) == 2
    assert sleeps == [3600, 3600]
    assert "no usable anchor key" in caplog.text
    fresh = LedgerStore(store.path)
    assert fresh.snapshot().global_length == before + 1  # tick 1 nothing, tick 2 one anchor
    assert len(_anchors(fresh)) == 1
    assert len(stub.requests) == 1  # the keyless tick never contacted Fly


def test_a_raising_tick_does_not_end_the_loop(caplog):
    stop, calls = threading.Event(), []

    def tick():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError(FLY_SECRET)
        stop.set()

    assert w.run_loop(tick, 5, stop, sleep=lambda s: None) == 2
    assert "RuntimeError" in caplog.text and FLY_SECRET not in caplog.text


def test_cli_once_exit_codes(env, local, monkeypatch):
    store, url = local
    env.setenv("FIELD_LEDGER_URL", url)
    stub = StubFly()
    real = w.build_fly_client
    monkeypatch.setattr(w, "build_fly_client", lambda: real(transport=httpx.MockTransport(stub)))
    args = ["witness", "run", "--once", "--estate", "gb10", "--fly-url", FLY]
    assert runner.invoke(cli_app, args).exit_code == 0
    assert len(_anchors(LedgerStore(store.path))) == 1
    stub.raise_exc = httpx.ConnectError("down")
    assert runner.invoke(cli_app, args).exit_code == 1
    assert len(_anchors(LedgerStore(store.path))) == 1
    env.delenv("FIELD_LEDGER_URL")
    assert runner.invoke(cli_app, args).exit_code == 2


# ------------------------------------------------------------------------------ direction 2


def test_direction_2_is_off_by_default_with_one_line_per_tick(env, local, caplog):
    store, url = local
    caplog.set_level(logging.INFO, logger="sealed_ledger.witness")
    stub = StubFly()
    witness = _witness(stub, url)
    stop = threading.Event()
    ticks = w.run_loop(witness.tick, 1, stop, sleep=lambda s: stop.set() if len(stub.requests) >= 2 else None)
    assert ticks == 2
    assert all(r.method == "GET" for r in stub.requests)
    assert caplog.text.count(w.DIRECTION_2_NOT_LIVE) == 2


def test_direction_2_posts_the_local_head_signed_with_the_fly_secret(env, local, tmp_path, caplog):
    store, url = local
    secret_file = tmp_path / "fly-secret"
    secret_file.write_text(FLY_SECRET + "\n", encoding="utf-8")
    env.setenv(w.FLY_SECRET_FILE_ENV, str(secret_file))
    caplog.set_level(logging.INFO, logger="sealed_ledger.witness")
    stub = StubFly()
    outcome = _witness(stub, url).tick()
    assert (outcome.direction1, outcome.direction2) == ("appended", "posted")
    get, post = stub.requests
    assert (get.method, str(get.url)) == ("GET", f"{FLY}/ledger/health") and "x-field-auth" not in get.headers
    assert (post.method, str(post.url)) == ("POST", f"{FLY}/ledger/events")
    assert post.headers["x-field-auth"] == FLY_SECRET  # the Fly secret, never the local one
    body = json.loads(post.content)
    assert body["event_type"] == "anchor.remote" and body["agent_id"] is None
    p = body["payload"]
    snap = LedgerStore(store.path).snapshot()  # the head AFTER direction 1's append
    assert tuple(sorted(p)) == tuple(sorted(w.PAYLOAD_FIELDS))
    assert (p["estate"], p["length"], p["head_hash"]) == ("gb10", snap.global_length, snap.head)
    assert p["key_fingerprint"] == key_fingerprint(PUB)
    assert verify_manifest({k: v for k, v in p.items() if k != "signature"}, p["signature"], PUB)
    assert FLY_SECRET not in caplog.text and LOCAL_SECRET not in caplog.text


@pytest.mark.parametrize("state", ["missing", "empty"])
def test_direction_2_with_an_unusable_secret_file_sends_nothing(env, local, tmp_path, state, caplog):
    _, url = local
    secret_file = tmp_path / "fly-secret"
    if state == "empty":
        secret_file.write_text("\n", encoding="utf-8")
    env.setenv(w.FLY_SECRET_FILE_ENV, str(secret_file))
    stub = StubFly()
    assert _witness(stub, url).tick().direction2 == "secret-unreadable"
    assert [r.method for r in stub.requests] == ["GET"]


def test_secrets_never_reach_the_logs_even_when_a_refusal_echoes_them(env, local, tmp_path, caplog, capsys):
    store, url = local
    secret_file = tmp_path / "fly-secret"
    secret_file.write_text(FLY_SECRET, encoding="utf-8")
    env.setenv(w.FLY_SECRET_FILE_ENV, str(secret_file))
    env.setenv("FIELD_LEDGER_URL", url)
    caplog.set_level(logging.DEBUG)
    stub = StubFly(post_status=401)
    assert _witness(stub, url).tick().direction2 == "refused"
    assert "bad x-field-auth ***" in caplog.text  # the echo is there, redacted
    # and the CLI's own handler (stderr) likewise
    real = w.build_fly_client
    env.setattr(w, "build_fly_client", lambda: real(transport=httpx.MockTransport(stub)))
    r = runner.invoke(cli_app, ["witness", "run", "--once", "--estate", "gb10", "--fly-url", FLY])
    captured = capsys.readouterr()
    text = caplog.text + r.output + captured.out + captured.err
    assert FLY_SECRET not in text and LOCAL_SECRET not in text


def _leaked_prefixes(secret: str, text: str) -> list[str]:
    """Every prefix of ``secret`` of 6+ characters that appears in ``text``."""
    return [secret[:k] for k in range(6, len(secret) + 1) if secret[:k] in text]


@pytest.mark.parametrize("pad", [180, 190, 194])
def test_a_refusal_echo_straddling_the_log_cut_leaks_no_prefix_of_the_fly_secret(env, local, tmp_path, caplog, pad):
    """Redaction runs over the WHOLE body before it is cut to 200 characters: a secret
    starting at ``pad`` crosses the cut, and not even its first 6 characters are logged."""
    _, url = local
    secret_file = tmp_path / "fly-secret"
    secret_file.write_text(FLY_SECRET, encoding="utf-8")
    env.setenv(w.FLY_SECRET_FILE_ENV, str(secret_file))
    caplog.set_level(logging.DEBUG, logger="sealed_ledger.witness")
    assert pad < w.BODY_LOG_CHARS < pad + len(FLY_SECRET)

    class Echo(StubFly):
        def __call__(self, request):
            if request.method == "POST":
                return httpx.Response(401, text="x" * pad + request.headers["x-field-auth"])
            return super().__call__(request)

    assert _witness(Echo(), url).tick().direction2 == "refused"
    assert "x" * pad + "***" in caplog.text  # the echo was logged, redacted
    assert _leaked_prefixes(FLY_SECRET, caplog.text) == []


@pytest.mark.parametrize("pad", [180, 185, 194])
def test_a_refusal_echo_straddling_the_log_cut_leaks_no_prefix_of_the_local_secret(env, caplog, pad):
    caplog.set_level(logging.DEBUG, logger="sealed_ledger.witness")
    assert pad < w.BODY_LOG_CHARS < pad + len(LOCAL_SECRET)

    def ledger_echo(request):
        return httpx.Response(401, text="y" * pad + request.headers.get("x-field-auth", ""))

    witness = w.Witness(local_estate="gb10", fly_url=FLY, fly=w.build_fly_client(transport=httpx.MockTransport(StubFly())),
                        ledger=w.build_ledger_client("http://ledger.test/", transport=httpx.MockTransport(ledger_echo)),
                        observer=w.observer_record(OBSERVED), clock=lambda: OBSERVED)
    assert witness.tick().direction1 == "ledger-refused"
    assert "y" * pad + "***" in caplog.text
    assert _leaked_prefixes(LOCAL_SECRET, caplog.text) == []


def test_no_served_route_signs_anything(tmp_path):
    paths = {getattr(r, "path", "") for r in create_app(store=LedgerStore(tmp_path / "e.jsonl")).routes}
    assert not [p for p in paths if "sign" in p or "witness" in p or "anchor" in p]


# ------------------------------------------------------------------------------ verify-witness


def _event(payload: dict, i: int = 0) -> dict:
    return {"event_id": f"e{i}", "ts": OBSERVED, "event_type": "anchor.remote", "agent_id": None,
            "payload": payload, "prev_hash": "0" * 64, "hash": f"{i:064x}"}


def _anchor_for(snap_length: int, head: str, key: str = PRIV, observed: str = OBSERVED) -> dict:
    return w.sign_anchor({"estate": "fly", "length": snap_length, "head_hash": head, "observed_at": observed,
                          "observer": w.observer_record("2026-09-13T00:00:00+00:00", host="abc123"),
                          "key_fingerprint": w.private_key_fingerprint(key)}, key)


@pytest.fixture()
def fly_ledger(tmp_path, env):
    """The Fly-side LOCAL ledger, rotated once (2 segments), with anchors taken before and
    after the rotation, recorded as GB10 events (a JSON array, as GET /events returns)."""
    p = tmp_path / "fly" / "events.jsonl"
    store = LedgerStore(p)
    fill(store, 4)
    early = store.snapshot()
    anchors = [_anchor_for(2, early.hash_at(1)), _anchor_for(early.global_length, early.head)]
    rotate(store)
    fill(store, 3)
    late = store.snapshot()
    anchors.append(_anchor_for(late.global_length, late.head))
    assert late.verify().segments == 2
    events = [_event(a, i) for i, a in enumerate(anchors)]
    events.insert(1, {**_event({"estate": "gb10", "length": 1, "head_hash": "0" * 64}, 9)})  # another estate
    events.insert(0, {**_event({"estate": "fly"}, 8), "event_type": "action"})  # not an anchor
    pub = tmp_path / "gb10-anchor.pub.pem"
    pub.write_text(PUB, encoding="ascii")
    return p, events, pub


def _verify(p: Path, events, *extra, as_jsonl: bool = False, raw: str | None = None):
    src = p.parent.parent / "gb10-anchor-remote.json"  # never inside the ledger directory
    if raw is not None:
        src.write_text(raw, encoding="utf-8")
    elif as_jsonl:
        src.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    else:
        src.write_text(json.dumps(events), encoding="utf-8")
    return runner.invoke(cli_app, ["verify-witness", "--estate", "fly", "--events-file", str(src),
                                   "--path", str(p), *extra])


def test_every_anchor_holds_across_a_rotated_ledger(fly_ledger):
    p, events, pub = fly_ledger
    r = _verify(p, events, "--pubkey", str(pub))
    assert r.exit_code == 0, r.output
    lines = r.output.strip().splitlines()
    assert [ln.split(" — ")[0] for ln in lines] == ["HOLDS", "HOLDS", "HOLDS", "OK"]
    assert "3 of 3 anchor.remote{estate: fly} hold" in lines[-1] and "3 signature(s) verified" in lines[-1]
    assert _verify(p, events, as_jsonl=True).exit_code == 0


def test_one_edited_head_hash_fails_naming_it(fly_ledger):
    p, events, _ = fly_ledger
    events[3]["payload"]["head_hash"] = "cd" * 32  # anchor 1
    r = _verify(p, events)
    assert r.exit_code == 1
    assert "FAILS — anchor 1 " in r.output and "hash at global index 3 is" in r.output
    assert r.output.count("HOLDS") == 2 and "1 of 3" in r.output


def test_a_length_beyond_the_local_chain_is_a_future_head(fly_ledger):
    p, events, _ = fly_ledger
    events[-1]["payload"]["length"] = 999
    r = _verify(p, events)
    assert r.exit_code == 1 and "witnessed a future head: length 999 > local length" in r.output


@pytest.mark.parametrize("field,value,why", [
    ("length", "4", "malformed: length"),
    ("length", True, "malformed: length"),
    ("length", -1, "malformed: length"),
    ("head_hash", "AB" * 32, "malformed: head_hash"),
    ("head_hash", None, "malformed: head_hash"),
])
def test_a_malformed_anchor_fails_by_name(fly_ledger, field, value, why):
    p, events, _ = fly_ledger
    events[3]["payload"][field] = value
    r = _verify(p, events)
    assert r.exit_code == 1 and f"FAILS — anchor 1 " in r.output and why in r.output


def test_a_zero_length_anchor_holds_only_at_the_genesis_hash(fly_ledger):
    from field_core.ledger import GENESIS_HASH

    p, events, _ = fly_ledger
    events[1]["payload"].update(length=0, head_hash=GENESIS_HASH)
    assert _verify(p, events).exit_code == 0
    events[1]["payload"]["head_hash"] = "cd" * 32
    r = _verify(p, events)
    assert r.exit_code == 1 and "length 0 but head_hash is not the genesis hash" in r.output


def test_length_zero_anchors_alone_are_nothing_witnessed(tmp_path, env):
    """A length-0 anchor at the genesis head holds against ANY chain, so it never counts
    as witnessing: an evidence set of only such anchors exits 1, signed or not."""
    from field_core.ledger import GENESIS_HASH

    p = tmp_path / "unrelated" / "events.jsonl"
    fill(LedgerStore(p), 5)
    r = _verify(p, [_event({"estate": "fly", "length": 0, "head_hash": GENESIS_HASH}, 0)])
    assert r.exit_code == 1 and "WITNESS FAILED — nothing witnessed" in r.output and "length 0" in r.output
    assert "HOLDS — anchor 0 " in r.output  # the anchor itself is not a failure
    pub = tmp_path / "pub.pem"
    pub.write_text(PUB, encoding="ascii")
    r = _verify(p, [_event(_anchor_for(0, GENESIS_HASH), 0), _event(_anchor_for(0, GENESIS_HASH), 1)],
                "--pubkey", str(pub))
    assert r.exit_code == 1 and "nothing witnessed: 2 anchor.remote{estate: fly} hold" in r.output
    # one real anchor alongside makes it a witness again
    snap = LedgerStore(p).snapshot()
    r = _verify(p, [_event(_anchor_for(0, GENESIS_HASH), 0), _event(_anchor_for(5, snap.head), 1)],
                "--pubkey", str(pub))
    assert r.exit_code == 0 and "OK — 2 of 2" in r.output


def test_an_index_missing_from_the_live_chain_fails_even_without_a_verified_length(tmp_path, env):
    """verify_witness() is public and verified_length is optional: a snapshot whose closed
    segment file is absent (the CLI would have refused the chain first) must not hold."""
    s, p, hashes = three_segments(tmp_path / "ledger")
    [seg2] = [x for x in p.parent.iterdir() if x.name == "events-2.jsonl"]
    seg2.unlink()
    snap = LedgerStore(p).snapshot()
    assert snap.hash_at(5) is None  # the precondition: index 5 lives in the absent segment
    anchors = [_event(_anchor_for(6, hashes[5]), 0), _event(_anchor_for(11, hashes[10]), 1)]
    result = w.verify_witness(snap, anchors, "fly")
    assert not result.ok and result.failed == 1
    assert result.lines[0].startswith("FAILS — anchor 0 ")
    assert "global index 5 is missing from the live chain" in result.lines[0]
    assert result.lines[1].startswith("HOLDS — anchor 1 ")


def test_an_anchor_past_the_verified_length_is_never_checked_against_unverified_events(fly_ledger):
    """The CLI verifies the chain, then snapshots it: an append in between is not trusted."""
    p, events, _ = fly_ledger
    snap = LedgerStore(p).snapshot()
    anchors = w.select_anchors(events, "fly")
    assert w.verify_witness(snap, anchors, "fly").ok
    result = w.verify_witness(snap, anchors, "fly", verified_length=snap.global_length - 1)
    assert not result.ok and "witnessed a future head: length 8 > local length 7" in "\n".join(result.lines)
    # the CLI passes what its verify covered: the event "appended after verify" is not trusted
    real_verify = LedgerStore.verify

    def verify_before_the_last_append(self):
        res = real_verify(self)
        return res.model_copy(update={"length": res.length - 1})

    env = pytest.MonkeyPatch()
    try:
        env.setattr(LedgerStore, "verify", verify_before_the_last_append)
        r = _verify(p, events)
    finally:
        env.undo()
    assert r.exit_code == 1 and "witnessed a future head: length 8 > local length 7" in r.output


def test_zero_anchors_is_nothing_witnessed(fly_ledger):
    p, events, _ = fly_ledger
    only_others = [e for e in events if e["event_type"] != "anchor.remote" or e["payload"].get("estate") != "fly"]
    r = _verify(p, only_others)
    assert r.exit_code == 1 and "nothing witnessed" in r.output
    assert _verify(p, []).exit_code == 1


def test_a_bad_signature_with_pubkey_fails(fly_ledger, tmp_path):
    p, events, pub = fly_ledger
    events[1]["payload"]["observed_at"] = "2026-09-13T12:00:01+00:00"  # the head still matches
    assert _verify(p, events).exit_code == 0  # without --pubkey the edit is invisible
    r = _verify(p, events, "--pubkey", str(pub))
    assert r.exit_code == 1 and "FAILS — anchor 0 " in r.output and "signature invalid" in r.output
    # signed by another key that also writes its own fingerprint
    other_priv, _ = generate_keypair()
    events[1]["payload"] = _anchor_for(events[1]["payload"]["length"], events[1]["payload"]["head_hash"],
                                       key=other_priv)
    assert "signature invalid" in _verify(p, events, "--pubkey", str(pub)).output
    # unsigned
    del events[1]["payload"]["signature"]
    r = _verify(p, events, "--pubkey", str(pub))
    assert r.exit_code == 1 and "unsigned, but --pubkey was given" in r.output


def test_a_valid_signature_with_a_wrong_fingerprint_fails(fly_ledger):
    p, events, pub = fly_ledger
    payload = {k: v for k, v in events[1]["payload"].items() if k != "signature"}
    events[1]["payload"] = w.sign_anchor({**payload, "key_fingerprint": "0" * 64}, PRIV)
    r = _verify(p, events, "--pubkey", str(pub))
    assert r.exit_code == 1 and "is not the --pubkey fingerprint" in r.output


def test_duplicate_keys_are_refused(fly_ledger):
    p, events, _ = fly_ledger
    text = json.dumps(events)
    good = events[4]["payload"]["head_hash"]
    decoy = text.replace(f'"head_hash": "{good}"', f'"head_hash": "{"cd" * 32}", "head_hash": "{good}"', 1)
    assert decoy != text
    r = _verify(p, events, raw=decoy)
    assert r.exit_code == 1 and "duplicate JSON key 'head_hash'" in r.output


def test_an_archived_index_is_an_explicit_failure(tmp_path, env):
    data = tmp_path / "data"
    s, p, hashes = three_segments(data / "ledger")
    snap = s.snapshot()
    live = _anchor_for(snap.global_length, snap.head)
    old = _anchor_for(2, hashes[1])
    s.archive_closed_segments(older_than_days=1, archive_dir=data / "ledger-archive", operator="ops",
                              data_dir=data, now=datetime.now(timezone.utc) + timedelta(days=3650))
    r = _verify(p, [_event(old, 0), _event(live, 1)])
    assert r.exit_code == 1
    assert "FAILS — anchor 0 " in r.output and "global index 1 is in archived segment 1" in r.output
    assert "NOT checked against the live chain" in r.output and "HOLDS — anchor 1 " in r.output


def test_a_local_chain_that_does_not_verify_fails_before_any_anchor(fly_ledger):
    p, events, _ = fly_ledger
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    record = json.loads(lines[1])
    record["payload"]["tag"] = "edited"
    lines[1] = json.dumps(record) + "\n"
    p.write_text("".join(lines), encoding="utf-8")
    r = _verify(p, events)
    assert r.exit_code == 1 and "the local chain does not verify" in r.output


def test_verify_witness_over_events_url(fly_ledger, served, env):
    p, events, pub = fly_ledger
    app, url = served
    gb10 = LedgerStore(p.parent.parent / "gb10-src" / "events.jsonl")
    for e in events:
        gb10.append(e["event_type"], e["payload"])
    app.state.store = gb10
    env.delenv("FIELD_SHARED_SECRET")
    r = runner.invoke(cli_app, ["verify-witness", "--estate", "fly", "--events-url", f"{url}/events",
                                "--path", str(p), "--pubkey", str(pub)])
    assert r.exit_code == 0, r.output
    secret = p.parent.parent / "s"
    secret.write_text("x", encoding="utf-8")
    r = runner.invoke(cli_app, ["verify-witness", "--estate", "fly", "--events-url", f"{url}/events",
                                "--secret-file", str(secret), "--path", str(p)])
    assert r.exit_code == 2 and "non-https" in r.output


def test_fetch_events_sends_the_secret_and_asks_for_anchor_remote_only():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=[])

    assert w.fetch_events("https://fly.test/ledger/events", FLY_SECRET, transport=httpx.MockTransport(handler)) == []
    assert seen[0].headers["x-field-auth"] == FLY_SECRET and seen[0].url.params["event_type"] == "anchor.remote"
    with pytest.raises(w.WitnessError):
        w.fetch_events("https://fly.test/ledger/events", None,
                       transport=httpx.MockTransport(lambda r: httpx.Response(401)))


def test_verify_witness_never_follows_a_redirect_carrying_the_secret(fly_ledger, monkeypatch):
    """httpx strips only Authorization on a cross-origin redirect and KEEPS x-field-auth, so
    following one would hand the Fly secret to the redirect target. The target here serves
    anchors that would all hold: following it would also turn a refusal into a pass."""
    p, events, pub = fly_ledger
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "fly.test":
            return httpx.Response(302, headers={"location": "https://evil.test/ledger/events?event_type=anchor.remote"})
        return httpx.Response(200, json=events)

    real = w.fetch_events
    monkeypatch.setattr(w, "fetch_events", lambda url, secret: real(url, secret, transport=httpx.MockTransport(handler)))
    secret = p.parent.parent / "fly-secret"
    secret.write_text(FLY_SECRET + "\n", encoding="utf-8")
    r = runner.invoke(cli_app, ["verify-witness", "--estate", "fly", "--events-url", "https://fly.test/ledger/events",
                                "--secret-file", str(secret), "--path", str(p), "--pubkey", str(pub)])
    assert r.exit_code == 2 and "302" in r.output
    assert [req.url.host for req in seen] == ["fly.test"]  # the redirect target received nothing
    assert seen[0].headers["x-field-auth"] == FLY_SECRET  # the request that WAS sent carried the secret
    assert FLY_SECRET not in r.output


def test_usage_errors_exit_2(fly_ledger):
    p, events, _ = fly_ledger
    assert runner.invoke(cli_app, ["verify-witness", "--estate", "fly", "--path", str(p)]).exit_code == 2
    assert runner.invoke(cli_app, ["verify-witness", "--estate", "fly", "--events-file", "x", "--events-url",
                                   "https://a", "--path", str(p)]).exit_code == 2
    bad = p.parent.parent / "bad.pem"
    bad.write_text(PRIV, encoding="ascii")  # a PRIVATE key is not a --pubkey
    assert _verify(p, events, "--pubkey", str(bad)).exit_code == 2
