"""renew_token is a scheduled write against a REAL agent's authority.

If it can revoke a working token, swap in a token that does not work, widen a
scope, touch the API key beside the token, or undo a human's revocation, the
governance estate has been damaged by its own tooling. Every test here drives
the real services over real HTTP (estate_harness.py mounts each service's
create_app() under the prefixes Caddy routes), with the estate's shared secret
ARMED and a DOA roster ARMED, and asserts on the estate's own records (token
state, ledger events) and on the store's bytes, never on the tool's say-so.

The tool is run as a subprocess by the BASE interpreter in isolated mode
(-I): it must work with the standard library alone, as on the GB10.

Failures the real services cannot produce on demand (a 5xx or a lost response
on the mint, a failing ledger append, a failing revoke, a redirect, a process
killed mid-renewal) are injected by a small forwarding proxy in this module;
every request still reaches the real services unless the fault says otherwise.
Disk faults (a store or journal write that fails or lands damaged) are injected
by WRAPPER, which runs the unmodified tool in its own process around a
write_atomic that fails chosen writes.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import http.client
import io
import json
import os
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
TOOL = TOOLS / "renew_token.py"
PROBE = TOOLS / "estate_probe.py"
HARNESS = Path(__file__).with_name("estate_harness.py")
CANARY_MANIFEST = REPO / "manifests" / "canary-gb10.yaml"
sys.path.insert(0, str(TOOLS))

import renew_token  # noqa: E402  (in-process only for the swap unit tests)

PY = getattr(sys, "_base_executable", None) or sys.executable
CANARY = "canary-gb10"
GRANTOR = "Don Hagell, Spin State Labs"
CANARY_SCOPE = ["canary.probe", "canary.read", "canary.throttle", "canary.escalate", "llm.messages"]
#: deliberately NOT sorted and a strict subset: a reordered or widened renewal shows
SUBSET_SCOPE = ["llm.messages", "canary.probe", "canary.read"]
SECRET = "renew-token-test-secret-never-printed"
FAKE_API_KEY = "sk-ant-api03-FAKE-renewal-test-key-must-never-be-printed-0123456789"
DAY = 86400
KEY = "VT_FIELD_TOKEN_ID"

# --- plumbing ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http(method: str, url: str, body: object | None = None, secret: str | None = SECRET) -> tuple[int, object]:
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["x-field-auth"] = secret
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw, status = resp.read(), resp.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(), exc.code
    return status, (json.loads(raw) if raw else None)


_COUNTER = [0]


def _uid(stem: str) -> str:
    _COUNTER[0] += 1
    return f"{stem}-{os.getpid()}-{_COUNTER[0]}"


class FaultProxy:
    """Forwards every request to the harness unless a fault says otherwise, and
    records (method, path, carried x-field-auth) for every request it saw."""

    def __init__(self, upstream_port: int):
        self.upstream_port = upstream_port
        self.faults: dict[str, object] = {}
        self.requests: list[tuple[str, str, bool]] = []
        self.held = threading.Event()
        self.release = threading.Event()
        self.inflight = 0
        self._count = threading.Lock()
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                proxy._serve(self)

            do_POST = do_PATCH = do_GET

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def wait_idle(self, timeout: float = 60) -> None:
        """The harness's SQLite stores answer spurious 404s under concurrent reads
        (tool docstring, NOT_FOUND_READS): a test must not read the estate while a
        held request is still being forwarded."""
        deadline = time.time() + timeout
        while self.inflight and time.time() < deadline:
            time.sleep(0.05)
        assert not self.inflight, "a proxied request never finished"

    def reset(self) -> None:
        self.release.set()
        self.wait_idle()
        self.faults.clear()
        self.requests.clear()
        self.held = threading.Event()
        self.release = threading.Event()

    def _forward(self, h, body, path=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.upstream_port, timeout=60)
        headers = {k: v for k, v in h.headers.items() if k.lower() in ("content-type", "accept", "x-field-auth")}
        conn.request(h.command, path or h.path, body=body, headers=headers)
        resp = conn.getresponse()
        raw, status = resp.read(), resp.status
        conn.close()
        return status, raw

    def _reply(self, h, status: int, raw: bytes) -> None:
        h.send_response(status)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(raw)))
        h.end_headers()
        h.wfile.write(raw)

    def _serve(self, h) -> None:
        with self._count:
            self.inflight += 1
        try:
            self._serve_one(h)
        finally:
            with self._count:
                self.inflight -= 1

    def _serve_one(self, h) -> None:
        n = int(h.headers.get("Content-Length") or 0)
        body = h.rfile.read(n) if n else None
        method, path, f = h.command, h.path, self.faults
        self.requests.append((method, path, "x-field-auth" in h.headers))
        injected = json.dumps({"detail": "injected by the test proxy"}).encode()
        upstream = f"http://127.0.0.1:{self.upstream_port}"
        if method == "POST" and path == "/delegation/tokens":
            if "mint_status" in f:
                return self._reply(h, int(f["mint_status"]), injected)
            req = json.loads(body)
            asked_ttl = req.get("ttl_seconds")
            if f.get("mint_widen"):  # a broken or hostile hop between the tool and the authority
                req["scope"] = req["scope"] + ["canary.throttle"]
            for field in ("granted_by", "agent_id"):  # ...or one that re-attributes the grant
                if f"mint_{field}" in f:
                    req[field] = f[f"mint_{field}"]
            if "mint_ttl" in f:  # ...or one that shortens the lifetime in transit
                req["ttl_seconds"] = int(f["mint_ttl"])
            body = json.dumps(req).encode()
            if f.get("concurrent_mint"):  # an operator mints for the same agent with ANOTHER grant (or the same)
                grant = req if f.get("concurrent_same_grant") else dict(req, scope=["canary.read"])
                status, tok = _http("POST", f"{upstream}/delegation/tokens", grant)
                self.faults["concurrent_id"] = tok["token_id"]
                if f.get("echo_concurrent"):  # ...and the answer to the tool's mint names THAT token
                    f["mint_echo"] = tok["token_id"]
                if f.get("answer_concurrent_row"):  # ...or is THAT token's whole row
                    f["answer_row_of"] = tok["token_id"]
            f["minted"] = True
            if f.get("mint_drop") or f.get("mint_hold"):
                self._forward(h, body)  # the authority DOES mint and persist...
                if f.get("mint_hold"):
                    self.held.set()
                    self.release.wait(120)
                h.close_connection = True
                return  # ...and the response is lost
            status, raw = self._forward(h, body)
            tok = json.loads(raw) if raw else {}
            f["minted_id"] = tok.get("token_id")
            if f.get("revoke_after_mint") and status == 201:  # revoked before the tool reads it back
                assert _http("POST", f"{upstream}/delegation/tokens/{tok['token_id']}/revoke")[0] == 200
            if "mint_echo" in f:  # the answer names another id, or none
                if f["mint_echo"] is None:
                    tok.pop("token_id", None)
                else:
                    tok["token_id"] = f["mint_echo"]
                raw = json.dumps(tok).encode()
            if f.get("mint_answer_ttl") and status == 201:  # the answer hides a lifetime changed in transit
                issued = renew_token.parse_ts(tok["issued_at"])
                tok["expires_at"] = (issued + renew_token.timedelta(seconds=asked_ttl)).isoformat()
                raw = json.dumps(tok).encode()
            if f.get("answer_row_of") and status == 201:  # the WHOLE answer body is another token's row
                row_status, row = _http("GET", f"{upstream}/delegation/tokens/{f['answer_row_of']}")
                assert row_status == 200, row_status
                raw = json.dumps(row).encode()
            return self._reply(h, status, raw)
        if method == "POST" and path == "/ledger/events":
            if "ledger_status" in f:
                return self._reply(h, int(f["ledger_status"]), injected)
            if f.get("ledger_hold") and json.loads(body).get("event_type") == f["ledger_hold"]:
                self.held.set()  # the tool dies with this append in flight; it is never forwarded
                self.release.wait(120)
                h.close_connection = True
                return
        if method == "POST" and path.endswith("/revoke"):
            token = path.split("/")[-2]
            if f.get("revoke_fail") and str(f["revoke_fail"]) in path:
                return self._reply(h, 500, injected)
            if token == f.get("revoke_drop"):  # the authority revokes; the answer is lost
                self._forward(h, body)
                h.close_connection = True
                return
            if token == f.get("revoke_answer_for"):  # a 200 that does not confirm this revoke
                return self._reply(h, 200, json.dumps(f["revoke_answer"]).encode())
        if method == "GET" and path.startswith("/delegation/tokens?"):
            if int(f.get("list_fail", 0)) > 0:
                f["list_fail"] = int(f["list_fail"]) - 1
                return self._reply(h, 500, injected)
            if f.get("minted") and int(f.get("list_fail_after_mint", 0)) > 0:  # a list after the mint fails
                f["list_fail_after_mint"] = int(f["list_fail_after_mint"]) - 1
                return self._reply(h, 500, injected)
            if f.get("list_extra"):  # a list answer that also carries another agent's row
                status, raw = self._forward(h, body)
                rows = json.loads(raw) + [_http("GET", f"{upstream}/delegation/tokens/{f['list_extra']}")[1]]
                return self._reply(h, status, json.dumps(rows).encode())
            if f.get("list_omit"):  # a list answer that misses one row (the store race)
                status, raw = self._forward(h, body)
                rows = [row for row in json.loads(raw) if row.get("token_id") != f["list_omit"]]
                return self._reply(h, status, json.dumps(rows).encode())
        if method == "GET" and path.startswith("/delegation/tokens/"):
            token = path.rsplit("/", 1)[-1]
            if not f.get("minted") and token == f.get("pre_mint_wrong_row_for"):  # the race, before the mint
                path = path.rsplit("/", 1)[0] + "/" + str(f["pre_mint_wrong_row"])
            if f.get("minted") and token == f.get("wrong_row_for"):  # a store race answering another row
                path = path.rsplit("/", 1)[0] + "/" + str(f["wrong_row"])
            if f.get("wrong_row_for_minted") and token == f.get("minted_id"):
                path = path.rsplit("/", 1)[0] + "/" + str(f["wrong_row_for_minted"])
            if f.get("minted_get_fail_after") is not None and token == f.get("minted_id"):
                if int(f["minted_get_fail_after"]) <= 0:
                    return self._reply(h, 500, injected)
                f["minted_get_fail_after"] = int(f["minted_get_fail_after"]) - 1
            if (f.get("minted") and token == f.get("get_500_after_mint_for")) or token == f.get("get_500_for"):
                return self._reply(h, 500, json.dumps(f.get("get_500_body", {"detail": "injected"})).encode())
            if "not_found_except" in f and token != f["not_found_except"]:
                return self._reply(h, 404, injected)
            if f.get("not_found_concurrent") and token == f.get("concurrent_id"):
                return self._reply(h, 404, injected)
            if int(f.get("not_found_first", 0)) > 0:
                f["not_found_first"] = int(f["not_found_first"]) - 1
                return self._reply(h, 404, injected)
            if "hold_get_except" in f and token != f["hold_get_except"] and not self.held.is_set():
                self.held.set()
                self.release.wait(120)
            if "redirect_to" in f:
                h.send_response(307)
                h.send_header("Location", f"{f['redirect_to']}{path}")
                h.send_header("Content-Length", "0")
                h.end_headers()
                return
        status, raw = self._forward(h, body, path)
        self._reply(h, status, raw)


class Sink:
    """Records any request that reaches it (a followed redirect would)."""

    def __init__(self):
        self.seen: list[tuple[str, bool]] = []
        sink = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                sink.seen.append((self.path, "x-field-auth" in self.headers))
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"


class Estate:
    def __init__(self, tmp: Path):
        data = tmp / "data"
        (data / "manifests").mkdir(parents=True)
        self.manifest = data / "manifests" / "canary-gb10.yaml"
        self.manifest.write_bytes(CANARY_MANIFEST.read_bytes())
        self.roster = tmp / "doa-roster.yaml"
        self.arm_roster()
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_")}
        env.update(FIELD_SHARED_SECRET=SECRET, FIELD_DOA_ROSTER=str(self.roster))
        self.proc = subprocess.Popen([sys.executable, str(HARNESS), str(self.port), str(data), "--secret"],
                                     env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 90
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"harness exited early: {self.proc.returncode}")
            try:
                urllib.request.urlopen(f"{self.base}/ledger/health", timeout=2).read()
                break
            except OSError:
                time.sleep(0.3)
        else:
            raise RuntimeError("harness did not come up")
        # The canary is provisioned with the REAL lifecycle CLI, as a gate does -
        # here UNDER the armed roster and the armed secret.
        for prefix, var in (("registry", "FIELD_REGISTRY_URL"), ("ledger", "FIELD_LEDGER_URL"),
                            ("delegation", "FIELD_DELEGATION_URL"), ("governor", "FIELD_GOVERNOR_URL"),
                            ("killswitch", "FIELD_KILLSWITCH_URL")):
            env[var] = f"{self.base}/{prefix}"
        report = tmp / "canary.json"
        subprocess.run(
            [sys.executable, "-m", "lifecycle_manager.cli", "provision",
             "--manifest", str(self.manifest), "--owner", "FIELD canary", "--domain", "canary",
             "--grantor", GRANTOR, "--ttl-days", "1", "--manifest-ref", str(self.manifest), "--out", str(report)],
            env=env, check=True, capture_output=True,
        )
        assert json.loads(report.read_text())["token_id"]
        self.proxy = FaultProxy(self.port)

    def arm_roster(self, grantors: list | None = None, raw: str | None = None) -> None:
        if raw is None:
            rows = grantors if grantors is not None else [
                {"grantor": GRANTOR, "allowed_scope": CANARY_SCOPE, "max_ttl_days": 400,
                 "max_spend_usd": 1, "active": True}]
            raw = json.dumps({"grantors": rows})  # JSON is YAML
        self.roster.write_text(raw, encoding="utf-8")

    def reset(self) -> None:
        self.proxy.reset()
        self.arm_roster()
        status, rec = self.get(f"/registry/agents/{CANARY}")
        assert status == 200
        if rec["status"] != "active":
            assert self.call("PATCH", f"/registry/agents/{CANARY}", {"status": "active"})[0] == 200

    def call(self, method: str, path: str, body: object | None = None) -> tuple[int, object]:
        return _http(method, f"{self.base}{path}", body)

    def get(self, path: str) -> tuple[int, object]:
        return self.call("GET", path)

    def mint(self, ttl_seconds: int, scope: list[str] | None = None, agent: str = CANARY) -> str:
        status, tok = self.call("POST", "/delegation/tokens", {"agent_id": agent, "granted_by": GRANTOR,
                                                               "scope": scope or SUBSET_SCOPE,
                                                               "ttl_seconds": ttl_seconds})
        assert status == 201, (status, tok)
        return tok["token_id"]

    def token(self, token_id: str) -> dict:
        status, tok = self.get(f"/delegation/tokens/{token_id}")
        assert status == 200, status
        return tok

    def token_ids(self, agent: str = CANARY) -> set[str]:
        status, toks = self.get(f"/delegation/tokens?agent_id={agent}")
        assert status == 200
        return {t["token_id"] for t in toks}

    def events(self, event_type: str, agent: str = CANARY) -> list[dict]:
        status, evs = self.get(f"/ledger/events?event_type={event_type}&agent_id={agent}")
        assert status == 200
        return evs

    def register(self) -> str:
        agent = _uid("renewal-subject")
        status, _ = self.call("POST", "/registry/agents", {"agent_id": agent, "name": "renewal test subject",
                                                           "owner": "FIELD canary", "domain": "canary",
                                                           "manifest_ref": str(self.manifest)})
        assert status == 201
        return agent

    def close(self) -> None:
        self.proxy.server.shutdown()
        self.proc.terminate()
        self.proc.wait(timeout=20)


@pytest.fixture(scope="module")
def _estate(tmp_path_factory):
    e = Estate(tmp_path_factory.mktemp("renew-estate"))
    try:
        yield e
    finally:
        e.close()


@pytest.fixture()
def estate(_estate):
    _estate.reset()
    return _estate


# --- one renewal case: a vt-shaped store and the tool -----------------------------------


RECORDER = r'''
import json, os, sys
token, record, rc, echo = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4] == "echo"
with open(record, "w") as fh:
    json.dump({"argv_token": token, "env_token": os.environ.get("RENEW_NEW_TOKEN_ID")}, fh)
print("recorder: verify saw token " + token)
if echo:
    print("recorder: secret is " + os.environ.get("FIELD_SHARED_SECRET", ""))
sys.exit(rc)
'''

INSPECTOR = r'''
import json, os, sys, urllib.request
base, expected = sys.argv[1], json.load(open(sys.argv[2]))
token = os.environ["RENEW_NEW_TOKEN_ID"]
req = urllib.request.Request(base + "/delegation/tokens/" + token,
                             headers={"x-field-auth": os.environ["FIELD_SHARED_SECRET"]})
tok = json.load(urllib.request.urlopen(req, timeout=30))
same = all(tok[k] == expected[k] for k in ("agent_id", "granted_by", "scope"))
print("inspector: agent, grantor and scope list identical to the old token: %s" % same)
sys.exit(0 if same and tok["revoked"] is False else 1)
'''

SLEEPER = r'''
import os, subprocess, sys, time
# a verifier with a child of its own, as a wrapper script or powershell.exe -File has
child = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(600)"])
open(sys.argv[1], "w").write("%d %d" % (os.getpid(), child.pid))
time.sleep(600)
'''

KILLER = r'''
import os, signal
# The renewal is killed while its verification runs: after the swap, before any result.
os.kill(os.getppid(), getattr(signal, "SIGKILL", signal.SIGTERM))
'''

REVOKER = r'''
import json, os, sys, urllib.request
# Someone revokes a token while the verifier runs ("new" = the renewal's new token).
base, which, rc = sys.argv[1], sys.argv[2], int(sys.argv[3])
token = os.environ["RENEW_NEW_TOKEN_ID"] if which == "new" else which
req = urllib.request.Request(base + "/delegation/tokens/" + token + "/revoke", data=b"", method="POST",
                             headers={"x-field-auth": os.environ["FIELD_SHARED_SECRET"]})
print("revoker: revoked=%s" % json.load(urllib.request.urlopen(req, timeout=30))["revoked"])
sys.exit(rc)
'''

OPERATOR = r'''
import sys
# An operator writes another token into the store while the verifier runs.
path, token, rc = sys.argv[1], sys.argv[2], int(sys.argv[3])
lines = open(path, "rb").read().split(b"\n")
lines = [b"VT_FIELD_TOKEN_ID=" + token.encode() if l.startswith(b"VT_FIELD_TOKEN_ID=") else l for l in lines]
open(path, "wb").write(b"\n".join(lines))
print("operator: wrote another token into the store")
sys.exit(rc)
'''

ROLLBACK = r'''
import shutil, sys
# REPAIR-PLAN 6.3's `cp -p secrets.env.bak ~/vt/secrets.env`, which takes no lock, lands mid-verification.
shutil.copyfile(sys.argv[1], sys.argv[2])
print("rollback: the pre-renewal backup was copied over the store")
'''

LOCK_PROBE = r'''
import os, sys
# vt's run.sh (flock -n) or a second renewal trying the locks while the verifier runs.
states = []
for path in sys.argv[3:]:
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        states.append("free")
    except OSError:
        states.append("held")
    finally:
        os.close(fd)
open(sys.argv[2], "w").write(" ".join(states))
print("lockprobe: " + " ".join(states))
'''

#: Runs the tool in its own process with write_atomic failing or damaging chosen
#: writes: the disk faults (ENOSPC, EIO, a sharing violation) no service can inject.
WRAPPER = r'''
import json, os, sys
tools, spec = sys.argv[1], json.loads(sys.argv[2])
sys.path.insert(0, tools)
import renew_token as rt
real, counts = rt.write_atomic, {"store": 0, "journal": 0}
store = os.path.normcase(os.path.abspath(spec["store"]))
def write_atomic(path, data, mode):
    kind = "store" if os.path.normcase(os.path.abspath(path)) == store else "journal"
    counts[kind] += 1
    n = str(counts[kind])
    if n in spec.get(kind + "_fail", []):
        raise OSError(28, "No space left on device (injected)")
    damage = spec.get(kind + "_corrupt", {}).get(n)
    if damage == "byte":  # a byte outside the value
        data = data.replace(b"FIELD_LEDGER_URL", b"FIELD_LEDGER_URM", 1)
    elif damage == "dup":  # the key defined twice: the store no longer parses
        data = data + b"\n" + spec["dup_line"].encode()
    return real(path, data, mode)
rt.write_atomic = write_atomic
raise SystemExit(rt.main(sys.argv[3:]))
'''

HOLDER = r'''
import os, sys, time
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
if os.name == "nt":
    import msvcrt
    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
else:
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
open(sys.argv[2], "w").write("held")
time.sleep(300)
'''


def _q(path: Path | str) -> str:
    return f'"{path}"'


def _env(secret: bool = True) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_")}
    if secret:
        env["FIELD_SHARED_SECRET"] = SECRET
    return env


class Case:
    def __init__(self, e: Estate, tmp: Path):
        self.e, self.tmp = e, tmp
        self.store = tmp / "secrets.env"
        self.lock = tmp / "vt.lock"
        self.lock.write_bytes(b"")
        self.state = tmp / "state"
        self.record = tmp / "verify-record.json"

    # stores ---------------------------------------------------------------------
    def env_store(self, token: str, crlf: bool = False) -> bytes:
        nl = b"\r\n" if crlf else b"\n"
        raw = (b"FIELD_LEDGER_URL=http://127.0.0.1:18080/ledger" + nl + KEY.encode() + b"=" + token.encode() + nl
               + b"ANTHROPIC_API_KEY=" + FAKE_API_KEY.encode() + nl + b"FIELD_SENTINEL_URL=http://127.0.0.1:18080/sentinel")
        self.store.write_bytes(raw)  # last line has no newline: the swap must not add one
        return raw

    def value(self) -> str:
        return renew_token.Store("env-file", str(self.store), KEY).locate(self.store.read_bytes())[2]

    # verify commands ------------------------------------------------------------
    def probe(self, secret_file: Path | None = None) -> str:
        auth = f" --secret-file {_q(secret_file)}" if secret_file else ""
        return f"{_q(PY)} -I {_q(PROBE)} --base {self.e.base}{auth} canary --agent {CANARY} --token {{new_token}}"

    def script(self, name: str, source: str, *args: str) -> str:
        path = self.tmp / f"{name}.py"
        path.write_text(source, encoding="utf-8")
        return " ".join([_q(PY), "-I", _q(path), *args])

    def recorder(self, rc: int, echo: bool = False) -> str:
        return self.script("recorder", RECORDER, "{new_token}", _q(self.record), str(rc), "echo" if echo else "quiet")

    # running --------------------------------------------------------------------
    def argv(self, *extra: str, verify: str | None = None, agent: str = CANARY, store: list[str] | None = None,
             base: str | None = None, lock: bool = True) -> list[str]:
        args = ["--agent", agent, "--base", base or self.e.proxy.base,
                *(store or ["--env-file", str(self.store), "--env-key", KEY]), "--state-dir", str(self.state)]
        if lock:
            args += ["--lock-file", str(self.lock)]
        if verify is not None:
            args += ["--verify-cmd", verify]
        return args + list(extra)

    def run(self, *extra: str, verify: str | None = None, secret: bool = True, timeout: float = 180,
            wrap: dict | None = None, **kw) -> tuple[int, str]:
        tool = [str(TOOL)]
        if wrap is not None:
            wrapper = self.tmp / "wrapper.py"
            wrapper.write_text(WRAPPER, encoding="utf-8")
            tool = [str(wrapper), str(TOOLS), json.dumps(dict(wrap, store=str(self.store)))]
        proc = subprocess.run([PY, "-I", *tool, *self.argv(*extra, verify=verify, **kw)], env=_env(secret),
                              capture_output=True, timeout=timeout)
        out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
        assert SECRET not in out and FAKE_API_KEY not in out, out
        return proc.returncode, out

    def spawn(self, *extra: str, verify: str | None = None, lock: bool = True) -> subprocess.Popen:
        return subprocess.Popen([PY, "-I", str(TOOL), *self.argv(*extra, verify=verify, lock=lock)], env=_env(),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def journal(self, phase: str, old: str, new: str | None = None, known=(), started=None, **fields):
        """A journal as an interrupted run leaves it (fields override for malformed ones)."""
        store = renew_token.Store("env-file", str(self.store), KEY)
        journal = renew_token.Journal(str(self.state), CANARY, store)
        data = {"version": 1, "phase": phase, "agent": CANARY, "store": store.path, "key": KEY, "old_token": old,
                "old_revoked": False, "granted_by": GRANTOR, "scope": SUBSET_SCOPE, "ttl_seconds": DAY,
                "known_tokens": sorted(known), "started_at": (started or renew_token.utcnow()).isoformat(),
                "store_sha256_before": "0" * 64}
        if new is not None:
            data["new_token"] = new
        data.update(fields)
        journal.write(data)
        return journal

    def result(self, out: str) -> str:
        lines = [line for line in out.splitlines() if line.startswith(("result:", "refused:"))]
        assert len(lines) == 1, out
        return lines[0]

    def journals(self) -> list[dict]:
        if not self.state.exists():
            return []
        return [json.loads(p.read_text()) for p in self.state.glob("renew-*.json")]


@pytest.fixture()
def case(estate, tmp_path):
    return Case(estate, tmp_path)


@contextlib.contextmanager
def lock_held(path: Path, tmp: Path):
    ready = tmp / "holder.ready"
    script = tmp / "holder.py"
    script.write_text(HOLDER, encoding="utf-8")
    proc = subprocess.Popen([PY, "-I", str(script), str(path), str(ready)])
    try:
        deadline = time.time() + 30
        while not ready.exists():
            assert proc.poll() is None and time.time() < deadline, "lock holder did not start"
            time.sleep(0.05)
        yield
    finally:
        proc.kill()
        proc.wait(timeout=20)


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _new_since(e: Estate, before: set[str], agent: str = CANARY) -> str:
    fresh = e.token_ids(agent) - before
    assert len(fresh) == 1, fresh
    return fresh.pop()


def _lifetime(tok: dict) -> float:
    return (renew_token.parse_ts(tok["expires_at"]) - renew_token.parse_ts(tok["issued_at"])).total_seconds()


# --- 5: not due ---------------------------------------------------------------------------


def test_not_due_mints_nothing_and_leaves_the_store_untouched(case):
    e, old = case.e, case.e.mint(30 * DAY)
    raw = case.env_store(old)
    before, renewed = e.token_ids(), len(e.events("token.renewed"))
    code, out = case.run(verify=case.recorder(0))
    assert code == 0, out
    assert "not due: 29 days left" in out
    assert case.store.read_bytes() == raw
    assert e.token_ids() == before and e.token(old)["revoked"] is False
    assert len(e.events("token.renewed")) == renewed
    assert not case.record.exists() and case.journals() == []
    assert [m for m, _, _ in e.proxy.requests] == ["GET"]


# --- 6-9: a due token is renewed, proven, and only then is the old one revoked ---------------


def test_due_renews_with_identical_grant_swaps_only_the_value_and_revokes_the_old(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before, renewed = e.token_ids(), len(e.events("token.renewed"))
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    new = _new_since(e, before)
    old_tok, new_tok = e.token(old), e.token(new)
    # the grant is carried forward exactly, never widened or reordered
    assert (new_tok["agent_id"], new_tok["granted_by"], new_tok["scope"]) == (CANARY, GRANTOR, SUBSET_SCOPE)
    assert new_tok["revoked"] is False and old_tok["revoked"] is True
    assert abs(_lifetime(new_tok) - DAY) < 5  # the old token's own 1-day lifetime
    # only the value changed: every other byte, including the API key line and the
    # missing final newline, is identical
    assert case.store.read_bytes() == raw.replace(old.encode(), new.encode())
    assert raw.count(old.encode()) == 1
    events = e.events("token.renewed")
    assert len(events) == renewed + 1
    payload = events[-1]["payload"]
    assert payload == {"old_prefix": old[:8], "new_prefix": new[:8], "expires_at": new_tok["expires_at"],
                       "granted_by": GRANTOR, "scope_count": len(SUBSET_SCOPE)}
    assert case.journals() == []
    # token ids only as prefixes; the API key never read out (asserted in run())
    assert old not in out and new not in out
    assert "[PASS] /check canary.probe ALLOW" in out
    # every request carried the perimeter header
    assert e.proxy.requests and all(auth for _, _, auth in e.proxy.requests)


def test_an_expired_token_is_due_and_renewed(case):
    e, old = case.e, case.e.mint(2)
    case.env_store(old)
    time.sleep(2.5)
    code, out = case.run("--renew-within-days", "0", verify=case.probe())
    assert code == 0, out
    assert "due (expired" in out
    assert e.token(case.value())["revoked"] is False and e.token(old)["revoked"] is True


def test_the_scope_is_never_widened_a_verify_command_that_inspects_the_new_token(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    expected = case.tmp / "expected.json"
    expected.write_text(json.dumps({"agent_id": CANARY, "granted_by": GRANTOR, "scope": SUBSET_SCOPE}))
    code, out = case.run(verify=case.script("inspector", INSPECTOR, e.base, _q(expected), "{new_token}"))
    assert code == 0, out
    assert "scope list identical to the old token: True" in out
    assert e.token(case.value())["scope"] == SUBSET_SCOPE


def test_ttl_is_clamped_to_30_days_and_floored_at_1_day(case):
    e = case.e
    old = e.mint(60 * DAY)
    case.env_store(old)
    code, out = case.run("--renew-within-days", "90", verify=case.probe())
    assert code == 0, out
    assert abs(_lifetime(e.token(case.value())) - 30 * DAY) < 5
    old = e.mint(3600)
    case.env_store(old)
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert abs(_lifetime(e.token(case.value())) - DAY) < 5
    old = e.mint(DAY)
    case.env_store(old)
    code, out = case.run("--ttl-days", "5", verify=case.probe())
    assert code == 0, out
    assert abs(_lifetime(e.token(case.value())) - 5 * DAY) < 5


@pytest.mark.parametrize("ttl", ["31", "0", "-1"])
def test_ttl_days_outside_1_to_30_is_refused_before_anything(case, ttl):
    raw = case.env_store(case.e.mint(DAY))
    code, out = case.run("--ttl-days", ttl, verify=case.probe())
    assert code == 2, out
    assert case.store.read_bytes() == raw and case.e.proxy.requests == []


def test_a_renewal_without_a_verify_command_is_refused(case):
    raw = case.env_store(case.e.mint(DAY))
    code, out = case.run()
    assert code == 2 and "needs --verify-cmd" in out
    assert case.store.read_bytes() == raw and case.e.proxy.requests == []


def test_json_store_swaps_one_member_and_keeps_every_other_byte(case):
    e, old = case.e, case.e.mint(DAY)
    other = "11111111-2222-4333-8444-555555555555"
    doc = ('\ufeff{\n  "ssl-invoicing-agent": "%s",\n  "canary-gb10" : "%s",\n  "anthropic_api_key": "%s",\n'
           '  "nested": {"canary-gb10": "22222222-2222-4333-8444-555555555555"}\n}\n' % (other, old, FAKE_API_KEY))
    path = case.tmp / "tokens-gb10.json"
    raw = doc.encode("utf-8")
    path.write_bytes(raw)
    store = ["--json-file", str(path), "--json-key", CANARY]
    code, out = case.run(verify=case.probe(), store=store)
    assert code == 0, out
    new = renew_token.Store("json-file", str(path), CANARY).locate(path.read_bytes())[2]
    assert new != old and e.token(new)["revoked"] is False and e.token(old)["revoked"] is True
    assert path.read_bytes() == raw.replace(old.encode(), new.encode())


# --- 8: a verification that fails restores everything but the ledger --------------------------


def test_verify_failure_restores_the_store_revokes_only_the_new_token_and_redacts_output(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    code, out = case.run(verify=case.recorder(rc=7, echo=True))
    assert code == 1, out
    new = _new_since(e, before)
    assert case.store.read_bytes() == raw  # byte for byte
    assert e.token(new)["revoked"] is True
    assert e.token(old)["revoked"] is False
    events = e.events("token.renewal_failed")
    assert len(events) == failed + 1
    assert events[-1]["payload"]["reason"] == "verify_failed" and events[-1]["payload"]["verify_rc"] == 7
    assert case.journals() == []
    # the verify command got the new id both ways
    assert json.loads(case.record.read_text()) == {"argv_token": new, "env_token": new}
    # its output is relayed with the secret redacted (run() asserts) and the id shortened
    assert "recorder: verify saw token " + new[:8] + "..." in out and new not in out
    assert "recorder: secret is <redacted>" in out


def test_a_verify_command_that_cannot_start_is_a_failed_verification(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    code, out = case.run(verify=_q(case.tmp / "no-such-verifier.exe") + " {new_token}")
    assert code == 1 and "could not start" in out, out
    new = _new_since(e, before)
    assert case.store.read_bytes() == raw
    assert e.token(new)["revoked"] is True and e.token(old)["revoked"] is False
    assert case.journals() == []


def test_verify_timeout_kills_the_verifiers_whole_tree_and_fails_like_a_non_zero_exit(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    pid_file = case.tmp / "sleeper.pid"
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    started = time.time()
    code, out = case.run("--verify-timeout", "3", verify=case.script("sleeper", SLEEPER, _q(pid_file), "{new_token}"),
                         timeout=90)
    assert code == 1, out
    assert time.time() - started < 60
    new = _new_since(e, before)
    assert case.store.read_bytes() == raw
    assert e.token(new)["revoked"] is True and e.token(old)["revoked"] is False
    payload = e.events("token.renewal_failed")[failed]["payload"]
    assert payload["reason"] == "verify_failed" and payload["timed_out"] is True and payload["verify_rc"] is None
    pids = [int(p) for p in pid_file.read_text().split()]
    deadline = time.time() + 10  # the grandchild too: killing only the direct child would orphan it (taskkill /T)
    while any(_pid_alive(p) for p in pids) and time.time() < deadline:
        time.sleep(0.2)
    survivors = [p for p in pids if _pid_alive(p)]
    for p in survivors:
        subprocess.run(["taskkill", "/F", "/PID", str(p)] if os.name == "nt" else ["kill", "-9", str(p)],
                       capture_output=True)
    assert survivors == [], f"verifier process(es) {survivors} of {pids} survived the timeout"


def test_verify_failure_with_a_failed_revoke_keeps_the_journal_and_the_next_run_revokes_it(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    e.proxy.faults["revoke_fail"] = "/revoke"  # every revoke answers 500
    code, out = case.run(verify=case.recorder(rc=1))
    assert code == 1 and "journal: kept" in out, out
    new = _new_since(e, before)
    assert case.store.read_bytes() == raw and e.token(new)["revoked"] is False
    assert [j["phase"] for j in case.journals()] == ["minted"]
    e.proxy.faults.clear()
    e.proxy.faults["mint_status"] = 409  # the next run cannot renew; it can only reconcile
    case.run(verify=case.recorder(rc=1))
    assert e.token(new)["revoked"] is True, "the run-1 token is still ACTIVE and no journal names it"


def test_restore_never_overwrites_a_token_written_into_the_store_during_verification(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    operators = e.mint(30 * DAY)
    before = e.token_ids()
    code, out = case.run(verify=case.script("operator", OPERATOR, _q(case.store), operators, "1", "{new_token}"))
    assert code == 1, out
    new = _new_since(e, before)
    assert case.value() == operators, "the restore overwrote the operator's token with the old token"
    assert e.token(new)["revoked"] is True and e.token(old)["revoked"] is False
    assert [j["phase"] for j in case.journals()] == ["minted"]  # the old token was not put back
    assert case.result(out) == (f"result: FAILED at verification (rc=1); store holds {operators[:8]} "
                                "(neither the old nor the new token)")


def test_a_failed_restore_never_revokes_the_token_the_store_still_holds(case):
    """ENOSPC, EIO or a sharing violation on the write back: the store still holds the NEW
    token. Revoking it would leave the agent on a revoked token under a log that reads safe."""
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    before = e.token_ids()
    code, out = case.run(verify=case.recorder(rc=1), wrap={"store_fail": ["2"]})  # 1 = the swap, 2 = the restore
    assert code == 1 and "restore: FAILED" in out and "NOT revoked: the store holds it" in out, out
    new = _new_since(e, before)
    assert case.value() == new and e.token(new)["revoked"] is False and e.token(old)["revoked"] is False
    assert case.result(out) == f"result: FAILED at verification (rc=1); store STILL HOLDS {new[:8]} (the new token)"
    payload = e.events("token.renewal_failed")[-1]["payload"]
    assert payload["reason"] == "verify_failed" and payload["restore_failed"] is True
    assert [j["phase"] for j in case.journals()] == ["minted"]
    code, out = case.run(verify=case.probe())  # the next run verifies the token the store holds
    assert code == 0, out
    assert case.value() == new and e.token(new)["revoked"] is False and e.token(old)["revoked"] is True


def test_a_store_rolled_back_during_verification_never_gets_its_token_revoked(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    backup = case.tmp / "secrets.env.bak"
    backup.write_bytes(raw)
    before = e.token_ids()
    code, out = case.run(verify=case.script("rollback", ROLLBACK, _q(backup), _q(case.store), "{new_token}"))
    assert code == 1 and "no longer holds" in out, out
    new = _new_since(e, before)
    assert case.store.read_bytes() == raw and e.token(old)["revoked"] is False, "vt's restored token was revoked"
    assert e.events("token.renewal_failed")[-1]["payload"]["reason"] == "store_changed_during_verify"
    assert [j["phase"] for j in case.journals()] == ["minted"]
    code, out = case.run(verify=case.probe())  # revokes the new token the store never kept, then renews
    assert code == 0, out
    assert e.token(new)["revoked"] is True and e.token(old)["revoked"] is True and case.value() not in (old, new)


@pytest.mark.parametrize("verify_rc", [0, 1])
def test_a_revocation_of_the_new_token_during_verification_is_never_undone(case, verify_rc):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    before, renewed = e.token_ids(), len(e.events("token.renewed"))
    code, out = case.run(verify=case.script("revoker", REVOKER, e.base, "new", str(verify_rc), "{new_token}"))
    assert code == 2 and "Nothing restored and nothing revoked" in out, out
    new = _new_since(e, before)
    assert case.value() == new and e.token(new)["revoked"] is True
    assert e.token(old)["revoked"] is False and len(e.events("token.renewed")) == renewed
    assert [j["phase"] for j in case.journals()] == ["minted"]


@pytest.mark.parametrize("verify_rc", [0, 1])
def test_a_revocation_of_the_old_token_during_verification_revokes_the_new_token_too(case, verify_rc):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    before, renewed = e.token_ids(), len(e.events("token.renewed"))
    code, out = case.run(verify=case.script("revoker", REVOKER, e.base, old, str(verify_rc), "{new_token}"))
    assert code == 2 and "was revoked during the renewal" in out, out
    new = _new_since(e, before)
    assert e.token(new)["revoked"] is True and e.token(old)["revoked"] is True
    assert len(e.events("token.renewed")) == renewed
    assert e.events("token.renewal_failed")[-1]["payload"]["reason"] == "revoked_during_renewal"
    assert case.journals() == []


def test_a_failed_read_of_the_new_token_after_verification_touches_nothing(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    before = e.token_ids()
    e.proxy.faults["minted_get_fail_after"] = 1  # the confirmation reads it; every later read answers 500
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "cannot decide safely" in out, out
    new = _new_since(e, before)
    assert case.value() == new and e.token(new)["revoked"] is False and e.token(old)["revoked"] is False
    assert [j["phase"] for j in case.journals()] == ["minted"]


def test_a_failed_read_of_the_old_token_after_verification_is_never_reported_as_renewed(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    e.proxy.faults["get_500_after_mint_for"] = old
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "cannot decide safely" in out, out
    assert e.token(old)["revoked"] is False and [j["phase"] for j in case.journals()] == ["minted"]
    e.proxy.faults.clear()
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert e.token(old)["revoked"] is True


@pytest.mark.parametrize("answer", ["revoked false", "another token"])
def test_a_revoke_answer_that_does_not_confirm_the_revoke_is_not_counted(case, answer):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    other = e.mint(DAY)
    renewed = len(e.events("token.renewed"))
    body = {"token_id": old, "revoked": False} if answer == "revoked false" else {"token_id": other, "revoked": True}
    e.proxy.faults.update(revoke_answer_for=old, revoke_answer=body)
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "revoke FAILED" in out, out
    assert e.token(old)["revoked"] is False and len(e.events("token.renewed")) == renewed
    assert [j["phase"] for j in case.journals()] == ["verified"]
    e.proxy.faults.clear()
    case.record.unlink()
    code, out = case.run(verify=case.recorder(1))  # verification passed already: it is not run again
    assert code == 0, out
    assert not case.record.exists()
    assert e.token(old)["revoked"] is True and e.token(case.value())["revoked"] is False


def test_a_verification_that_cannot_be_journaled_never_revokes_the_old_token(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    code, out = case.run(verify=case.recorder(0), wrap={"journal_fail": ["3"]})  # intent, minted, VERIFIED
    assert code == 1 and "cannot record the verification" in out, out
    assert e.token(old)["revoked"] is False and e.token(case.value())["revoked"] is False
    assert [j["phase"] for j in case.journals()] == ["minted"]
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert e.token(old)["revoked"] is True


# --- 6: a refused mint changes nothing -------------------------------------------------------


def _assert_mint_refused(case, e, old, raw, agent, code, out, status, failed_before):
    assert code == 1, out
    assert case.store.read_bytes() == raw
    assert e.token(old)["revoked"] is False
    events = e.events("token.renewal_failed", agent)
    assert len(events) == failed_before + 1
    assert events[-1]["payload"]["http_status"] == status
    assert not case.record.exists()


def test_mint_refused_for_a_retired_agent_changes_nothing(case):
    e = case.e
    agent = e.register()
    old = e.mint(DAY, agent=agent)
    raw = case.env_store(old)
    assert e.call("PATCH", f"/registry/agents/{agent}", {"status": "retired"})[0] == 200
    before = e.token_ids(agent)
    code, out = case.run(verify=case.recorder(0), agent=agent)
    _assert_mint_refused(case, e, old, raw, agent, code, out, 409, 0)
    assert e.token_ids(agent) == before
    assert e.events("token.renewal_failed", agent)[-1]["payload"]["reason"] == "mint_refused"
    assert case.journals() == []


def test_mint_refused_when_the_grantor_is_removed_from_the_armed_roster(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    e.arm_roster(grantors=[])
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    code, out = case.run(verify=case.recorder(0))
    _assert_mint_refused(case, e, old, raw, CANARY, code, out, 403, failed)
    assert "HTTP 403 D.grantor" in out
    assert e.events("token.renewal_failed")[-1]["payload"]["clause_id"] == "D.grantor"
    assert e.token_ids() == before


def test_mint_refused_when_the_armed_roster_is_unreadable(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    e.arm_roster(raw="grantors: [unterminated")
    failed = len(e.events("token.renewal_failed"))
    code, out = case.run(verify=case.recorder(0))
    _assert_mint_refused(case, e, old, raw, CANARY, code, out, 503, failed)


def test_a_5xx_mint_changes_nothing_and_keeps_the_intent_for_a_second_sweep(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    e.proxy.faults["mint_status"] = 502
    failed = len(e.events("token.renewal_failed"))
    code, out = case.run(verify=case.recorder(0))
    _assert_mint_refused(case, e, old, raw, CANARY, code, out, 502, failed)
    assert [j["phase"] for j in case.journals()] == ["minting"]


def test_the_orphan_sweep_never_revokes_a_token_that_existed_before_the_mint(case):
    """A token with the SAME grant, minted seconds earlier and not in this store
    (an operator's manual mint, another store's token), is not an orphan."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    bystander = e.mint(DAY)
    e.proxy.faults["mint_status"] = 502  # a 5xx: the tool must sweep for a possible orphan
    code, out = case.run(verify=case.recorder(0))
    assert code == 1, out
    assert "sweep: no orphan token found" in out
    assert e.token(bystander)["revoked"] is False and e.token(old)["revoked"] is False
    assert case.store.read_bytes() == raw


def test_a_mint_that_comes_back_with_another_grant_is_revoked_and_never_swapped(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    e.proxy.faults["mint_widen"] = True
    code, out = case.run(verify=case.recorder(0))
    assert code == 1, out
    widened = _new_since(e, before)
    assert e.token(widened)["scope"] == SUBSET_SCOPE + ["canary.throttle"]
    assert e.token(widened)["revoked"] is True and e.token(old)["revoked"] is False
    assert case.store.read_bytes() == raw and not case.record.exists()
    events = e.events("token.renewal_failed")
    assert len(events) == failed + 1 and events[-1]["payload"]["reason"] == "mint_mismatch"


def test_a_late_recovery_sweep_never_revokes_a_token_minted_outside_the_interrupted_window(case):
    """Hours after an interrupted mint, an operator's same-grant token is not its orphan."""
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    started = renew_token.utcnow() - renew_token.timedelta(hours=20)
    case.journal("minting", old, known=e.token_ids(), started=started)
    operators = e.mint(DAY)  # same grant, not in the snapshot, not in the store - but minted now
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert e.token(operators)["revoked"] is False
    assert "sweep: no orphan token found" in out


def test_the_orphan_sweep_skips_revoked_tokens_and_tokens_of_another_agent(case):
    e, old = case.e, case.e.mint(30 * DAY)
    case.env_store(old)
    case.journal("minting", old, known=e.token_ids())
    revoked = e.mint(DAY)  # same grant, inside the window, not in the snapshot - but already revoked
    assert e.call("POST", f"/delegation/tokens/{revoked}/revoke")[0] == 200
    foreign = e.mint(DAY, agent=e.register())  # same grant, inside the window - another agent's
    e.proxy.faults["list_extra"] = foreign  # the list answer carries that other agent's row
    failed = len(e.events("token.renewal_failed"))
    code, out = case.run(verify=case.recorder(0))
    assert code == 0 and "sweep: no orphan token found" in out and "not due" in out, out
    assert e.token(foreign)["revoked"] is False and len(e.events("token.renewal_failed")) == failed


def test_the_orphan_sweep_never_revokes_the_stores_token_or_the_journals_old_token(case):
    e, started = case.e, renew_token.utcnow()
    stored, journal_old = e.mint(30 * DAY), e.mint(30 * DAY)  # both same grant, inside the window
    case.env_store(stored)
    case.journal("minting", journal_old, known=e.token_ids() - {stored, journal_old}, started=started)
    code, out = case.run(verify=case.recorder(0))
    assert code == 0 and "sweep: no orphan token found" in out, out
    assert e.token(stored)["revoked"] is False and e.token(journal_old)["revoked"] is False


_BAD_JOURNALS = {
    "another store": {"store": "OTHER"},
    "another agent": {"agent": "someone-else"},
    "another key": {"key": "OTHER_TOKEN_ID"},
    "version": {"version": 2},
    # a well-formed new_token: without one the new_token rule would refuse it too and hide this rule
    "phase": {"phase": "swapping", "new_token": "b1b2c3d4-0000-4000-8000-000000000000"},
    "old_token": {"old_token": "not-a-uuid"},
    "minted without new_token": {"phase": "minted"},
    "verified without new_token": {"phase": "verified", "new_token": "not-a-uuid"},
    "old_revoked": {"old_revoked": "no"},
    "granted_by": {"granted_by": 5},
    "scope": {"scope": []},
    "started_at": {"started_at": "yesterday"},
    "digest": {"store_sha256_before": "abc"},
    "known_tokens": {"known_tokens": "all"},
    # a journal may never name, as the token to revoke, a token that existed before its own mint
    "new_token in known_tokens": {"phase": "minted", "new_token": "c1c2c3d4-0000-4000-8000-000000000000",
                                  "known_tokens": ["c1c2c3d4-0000-4000-8000-000000000000"]},
}


@pytest.mark.parametrize("name", sorted(_BAD_JOURNALS))
def test_a_journal_that_is_malformed_or_not_this_stores_is_refused(case, name):
    e, old = case.e, case.e.mint(30 * DAY)
    raw = case.env_store(old)
    fields = dict(_BAD_JOURNALS[name])
    if fields.get("store") == "OTHER":
        fields["store"] = str(case.tmp / "other.env")
    journal = case.journal(fields.pop("phase", "minting"), old, **fields)
    before = e.token_ids()
    code, out = case.run(verify=case.recorder(0))
    assert code == 2 and "is not a valid renewal journal" in out, out
    assert case.store.read_bytes() == raw and e.token_ids() == before and os.path.exists(journal.path)
    assert e.proxy.requests == [] and not case.record.exists()


def test_a_token_the_authority_cannot_find_is_never_counted_as_revoked(case):
    """Undo after a failed confirmation: if the new token cannot be read back, the
    tool must not report it gone. The journal keeps its id and the next run revokes it."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    e.proxy.faults["not_found_except"] = old  # every read of the NEW token answers 404
    code, out = case.run(verify=case.recorder(0))
    assert code == 1, out
    new = _new_since(e, before)
    assert "NOT confirmed revoked" in out
    assert e.token(new)["revoked"] is False  # still active: exactly why the journal must stay
    assert [j.get("new_token") for j in case.journals()] == [new]
    assert case.store.read_bytes() == raw and e.token(old)["revoked"] is False
    e.proxy.faults.clear()
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert e.token(new)["revoked"] is True and e.token(old)["revoked"] is True


def test_a_read_back_of_another_revoked_token_is_not_counted_as_revoking_the_old(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    other = e.mint(DAY)
    assert e.call("POST", f"/delegation/tokens/{other}/revoke")[0] == 200
    # after the mint, every read of the OLD token answers with the other (revoked) row
    e.proxy.faults.update(wrong_row_for=old, wrong_row=other)
    code, out = case.run(verify=case.probe())
    assert code == 1, out
    assert "different token" in out
    assert e.token(old)["revoked"] is False  # still active: the tool must not call it revoked
    assert [j["phase"] for j in case.journals()] == ["minted"]
    e.proxy.faults.clear()
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert e.token(old)["revoked"] is True


def test_a_spurious_404_on_the_current_token_is_re_read_not_refused(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    e.proxy.faults["not_found_first"] = 2  # the authority's store race, twice in a row
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert e.token(old)["revoked"] is True


def test_a_lost_mint_response_revokes_the_orphan_and_the_next_run_renews(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    e.proxy.faults.update(mint_drop=True, concurrent_mint=True)
    failed = len(e.events("token.renewal_failed"))
    code, out = case.run(verify=case.recorder(0))
    assert code == 1, out
    concurrent = e.proxy.faults["concurrent_id"]
    orphan = _new_since(e, before | {concurrent})  # the authority minted it; the tool never saw the id
    assert e.token(orphan)["revoked"] is True
    assert e.token(concurrent)["revoked"] is False  # same agent, same moment, another grant: not ours
    assert len(e.events("token.renewal_failed")) == failed + 1
    assert case.store.read_bytes() == raw and e.token(old)["revoked"] is False
    payload = e.events("token.renewal_failed")[-1]["payload"]
    assert payload["reason"] == "mint_transport_error" and payload["http_status"] is None
    assert [j["phase"] for j in case.journals()] == ["minting"]
    e.proxy.faults.clear()
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert case.value() not in (old, orphan) and e.token(old)["revoked"] is True
    assert case.journals() == []


@pytest.mark.parametrize("echo", ["the old id", "not a uuid", "no id", "a pre-existing same-grant id",
                                  "a pre-existing other-grant id", "a uuid that never existed"])
def test_a_mint_answer_without_a_new_id_revokes_nothing_by_it_and_sweeps_the_real_mint(case, echo):
    """A 201 whose token_id is the store's own token (a broken or hostile hop) must never
    lead to revoking that live token: it is a lost answer, and the token really minted is swept.
    The same holds for any token the agent had before the mint (1.2 swapped in a pre-existing
    same-grant token and revoked an unrelated other-grant one) and for a uuid the authority never
    issued (1.2 kept a journal whose revoke could never be confirmed, so every later run stopped)."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    # the agent's other tokens from BEFORE the mint: an answer may name one, and none may be touched
    same_grant, other_grant = e.mint(3 * DAY), e.mint(30 * DAY, scope=CANARY_SCOPE)
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    e.proxy.faults["mint_echo"] = {"the old id": old, "not a uuid": "not-a-uuid", "no id": None,
                                   "a pre-existing same-grant id": same_grant,
                                   "a pre-existing other-grant id": other_grant,
                                   "a uuid that never existed": "0badc0de-1111-4222-8333-444455556666"}[echo]
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "HTTP 201 without a new token id" in out, out
    really = e.proxy.faults["minted_id"]
    assert e.token_ids() == before | {really}
    assert e.token(old)["revoked"] is False, "the store's live token was revoked by the id a mint answer named"
    assert e.token(really)["revoked"] is True, "the token the authority really minted was left active"
    assert e.token(same_grant)["revoked"] is False and e.token(other_grant)["revoked"] is False, \
        "a token that existed before the mint was revoked"
    assert case.store.read_bytes() == raw and not case.record.exists()
    assert [j["phase"] for j in case.journals()] == ["minting"]
    events = e.events("token.renewal_failed")
    assert len(events) == failed + 1 and events[-1]["payload"]["reason"] == "mint_response_invalid"
    assert case.result(out) == f"result: FAILED at mint; store and old token {old[:8]} untouched"
    e.proxy.faults.clear()
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert e.token(old)["revoked"] is True and case.journals() == []
    assert e.token(same_grant)["revoked"] is False and e.token(other_grant)["revoked"] is False


def test_a_mint_answer_naming_the_current_token_is_lost_even_when_the_token_list_missed_it(case):
    """The snapshot is a list answer, and the store race can drop a row from it. The current token
    is counted in the snapshot regardless: otherwise an answer naming it would be confirmed (it IS
    an active token with this grant and lifetime), swapped over itself, and revoked after verification."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    e.proxy.faults.update(list_omit=old, mint_echo=old)
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "HTTP 201 without a new token id" in out, out
    really = e.proxy.faults["minted_id"]
    assert e.token(old)["revoked"] is False, "the store's live token was revoked by the id a mint answer named"
    assert e.token(really)["revoked"] is True and e.token_ids() == before | {really}
    assert case.store.read_bytes() == raw and not case.record.exists()
    assert [j["phase"] for j in case.journals()] == ["minting"] and old in case.journals()[0]["known_tokens"]


def test_a_mint_answer_naming_a_token_minted_during_the_mint_with_another_grant_sweeps_the_real_mint(case):
    """The answer names a token that did NOT exist before the mint (so the snapshot rule cannot
    catch it) but whose own row carries another grant: an operator's concurrent mint, named by a
    rewritten answer. The confirmation cannot vouch for that id, so the token the mint really
    created is swept too, and the intent is kept for the next run. The named token itself appeared
    during this mint under a grant nobody asked this run for, and is revoked (fail closed)."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    e.proxy.faults.update(concurrent_mint=True, echo_concurrent=True)
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "new token could not be confirmed (scope)" in out, out
    concurrent, really = e.proxy.faults["concurrent_id"], e.proxy.faults["minted_id"]
    assert e.token_ids() == before | {concurrent, really}
    assert e.token(really)["revoked"] is True, "the token the authority really minted was left active"
    assert e.token(concurrent)["revoked"] is True
    assert case.store.read_bytes() == raw and e.token(old)["revoked"] is False and not case.record.exists()
    assert [j["phase"] for j in case.journals()] == ["minting"]
    events = e.events("token.renewal_failed")
    assert len(events) == failed + 1 and events[-1]["payload"]["reason"] == "mint_unconfirmed"
    e.proxy.faults.clear()
    code, out = case.run(verify=case.probe())
    assert code == 0 and "sweep: no orphan token found" in out, out
    assert e.token(old)["revoked"] is True and case.journals() == []


def test_a_mint_answer_naming_a_token_the_authority_cannot_read_back_sweeps_the_real_mint(case):
    """The answer names a token that exists (it is in the token list, so it is not 'never issued')
    but answers 404 on every read: here an operator's same-grant token minted during the mint. The
    id cannot be confirmed to be this mint's, so the tokens are swept and the real mint revoked; the
    named token cannot be confirmed revoked, so the journal keeps naming it for the next run."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    e.proxy.faults.update(concurrent_mint=True, concurrent_same_grant=True, echo_concurrent=True,
                          not_found_concurrent=True)
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "new token could not be confirmed (HTTP 404)" in out, out
    named, really = e.proxy.faults["concurrent_id"], e.proxy.faults["minted_id"]
    assert e.token_ids() == before | {named, really}
    assert e.token(really)["revoked"] is True, "the token the authority really minted was left active"
    assert e.token(named)["revoked"] is False and [j.get("new_token") for j in case.journals()] == [named]
    assert case.store.read_bytes() == raw and e.token(old)["revoked"] is False and not case.record.exists()
    e.proxy.faults.clear()
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert e.token(named)["revoked"] is True and e.token(old)["revoked"] is True and case.journals() == []


def test_a_mint_answer_wholly_replaced_by_a_concurrent_other_grant_row_sweeps_the_real_mint(case):
    """The WHOLE answer body, not just its id, is the row of a token minted for the agent during the
    mint with another grant. The answer itself then shows another grant, so neither the snapshot rule
    nor the confirmation ever sees it. 1.3 revoked the named token and cleared the journal: the token
    the authority really minted stayed active with no journal naming it, also after the next run
    renewed. It is swept before the named token is revoked, and the intent is kept for the next run."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    e.proxy.faults.update(concurrent_mint=True, answer_concurrent_row=True)
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "abandon: mint response differs from the current grant (scope)" in out, out
    concurrent, really = e.proxy.faults["concurrent_id"], e.proxy.faults["minted_id"]
    assert e.token_ids() == before | {concurrent, really}
    assert e.token(really)["revoked"] is True, "the token the authority really minted was left active"
    assert e.token(concurrent)["revoked"] is True
    assert f"sweep: orphan {really[:8]} revoked" in out and f"revoke-new: {concurrent[:8]} revoked" in out, out
    assert case.store.read_bytes() == raw and e.token(old)["revoked"] is False and not case.record.exists()
    assert [j["phase"] for j in case.journals()] == ["minting"]
    events = e.events("token.renewal_failed")
    assert len(events) == failed + 1 and events[-1]["payload"]["reason"] == "mint_mismatch"
    e.proxy.faults.clear()
    code, out = case.run(verify=case.probe())
    assert code == 0 and "sweep: no orphan token found" in out, out
    assert e.token(old)["revoked"] is True and e.token(really)["revoked"] is True and case.journals() == []


def test_a_mint_answer_wholly_replaced_by_another_agents_row_sweeps_the_real_mint_before_refusing(case):
    """The WHOLE answer body is the row of another agent's token. The tool never revokes another agent's
    token (rc 2), and 1.3 refused before any sweep: the token the authority really minted stayed active,
    unswept and unjournaled, and every later run refused on the journal naming the other agent's token.
    The real mint is swept first; that journal still needs a human (runbook 4.2)."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    foreign = e.mint(DAY, agent=e.register())
    before = e.token_ids()
    e.proxy.faults["answer_row_of"] = foreign
    code, out = case.run(verify=case.recorder(0))
    assert code == 2 and "abandon: mint response differs from the current grant (agent_id)" in out, out
    really = e.proxy.faults["minted_id"]
    assert e.token_ids() == before | {really}
    assert e.token(really)["revoked"] is True, "the token the authority really minted was left active"
    lines = out.splitlines()
    swept = lines.index(f"sweep: orphan {really[:8]} revoked")
    refused = [n for n, line in enumerate(lines) if line.startswith("refused:")]
    assert refused == [swept + 1] and f"token {foreign[:8]} does not belong to {CANARY}" in lines[swept + 1], out
    assert e.token(foreign)["revoked"] is False and e.token(old)["revoked"] is False
    assert case.store.read_bytes() == raw and not case.record.exists()
    assert [(j["phase"], j.get("new_token")) for j in case.journals()] == [("minted", foreign)]
    e.proxy.faults.clear()
    code, out = case.run(verify=case.recorder(0))
    assert code == 2 and f"token {foreign[:8]} does not belong to {CANARY}" in out, out
    assert e.token(foreign)["revoked"] is False and e.token(old)["revoked"] is False
    assert case.store.read_bytes() == raw and not case.record.exists()


def test_a_differing_mint_answer_whose_sweep_cannot_list_the_tokens_keeps_the_intent(case):
    """A differing answer's sweep cannot list the agent's tokens, so nothing shows that the token the mint
    really created is gone: the intent is kept, not cleared, and the next run sweeps it."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    e.proxy.faults.update(concurrent_mint=True, answer_concurrent_row=True, list_fail_after_mint=1)
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "sweep: could not list tokens" in out, out
    concurrent, really = e.proxy.faults["concurrent_id"], e.proxy.faults["minted_id"]
    assert e.token(concurrent)["revoked"] is True and e.token(really)["revoked"] is False
    assert case.store.read_bytes() == raw and e.token(old)["revoked"] is False
    assert [j["phase"] for j in case.journals()] == ["minting"]
    e.proxy.faults.clear()
    code, out = case.run(verify=case.probe())
    assert code == 0 and f"sweep: orphan {really[:8]} revoked" in out, out
    assert e.token(really)["revoked"] is True and e.token(old)["revoked"] is True and case.journals() == []


@pytest.mark.parametrize("path", ["the answer", "the confirmation"])
def test_an_untrusted_mint_whose_sweep_and_named_revoke_both_fail_is_swept_by_the_next_run(case, path):
    """The mint answer (its whole body) or the confirmation GET shows another grant, the sweep cannot list the
    tokens, and the revoke of the named token fails too: the run keeps the journal naming that token, and that
    journal does not record the unfinished sweep. 1.4's next run revoked the named token, cleared the journal
    and renewed (rc 0) with the token the authority really minted still active and in no journal. The next run
    sweeps that mint's window after the revoke and before the journal is cleared."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    e.proxy.faults.update(concurrent_mint=True, list_fail_after_mint=1, revoke_fail="/revoke",
                          **{"the answer": {"answer_concurrent_row": True},
                             "the confirmation": {"echo_concurrent": True}}[path])
    code, out = case.run(verify=case.recorder(0))
    abandon = {"the answer": "abandon: mint response differs from the current grant (scope)",
               "the confirmation": "abandon: new token could not be confirmed (scope)"}[path]
    assert code == 1 and abandon in out and "sweep: could not list tokens (HTTP 500)" in out, out
    concurrent, really = e.proxy.faults["concurrent_id"], e.proxy.faults["minted_id"]
    assert f"revoke-new: {concurrent[:8]} revoke FAILED (HTTP 500)" in out and "journal: kept for the next run" in out
    assert e.token_ids() == before | {concurrent, really}
    assert e.token(really)["revoked"] is False and e.token(concurrent)["revoked"] is False
    assert [(j["phase"], j.get("new_token")) for j in case.journals()] == [("minted", concurrent)]
    assert case.store.read_bytes() == raw and e.token(old)["revoked"] is False and not case.record.exists()
    e.proxy.faults.clear()
    failed = len(e.events("token.renewal_failed"))
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert e.token(really)["revoked"] is True, "the token the authority really minted was left active"
    assert e.token(concurrent)["revoked"] is True and e.token(old)["revoked"] is True and case.journals() == []
    lines = out.splitlines()
    revoked = lines.index(f"recovery: {concurrent[:8]} revoked")
    swept = lines.index(f"sweep: orphan {really[:8]} revoked")
    minting = next(n for n, line in enumerate(lines) if line.startswith("mint:"))
    assert revoked < swept < lines.index("journal: cleared") < minting, out
    payload = e.events("token.renewal_failed")[failed]["payload"]
    assert payload["reason"] == "interrupted_before_swap" and payload["orphans_revoked"] == 1, payload


@pytest.mark.parametrize("answer", ["another agent's id", "another agent's row"])
def test_a_mint_answer_naming_another_agents_token_whose_sweep_cannot_list_is_swept_before_the_next_refusal(case,
                                                                                                          answer):
    """The answer names another agent's token (only its id, which the confirmation catches, or its whole row) and
    the sweep cannot list the tokens, so the run refuses (rc 2) with the token the authority really minted unswept.
    1.4's later runs refused on that journal without a sweep, and the real mint stayed active until a human found
    it. The next run sweeps that mint's window, then refuses as before: the journal still needs a human."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    foreign = e.mint(DAY, agent=e.register())
    e.proxy.faults.update({"another agent's id": {"mint_echo": foreign},
                           "another agent's row": {"answer_row_of": foreign}}[answer], list_fail_after_mint=1)
    code, out = case.run(verify=case.recorder(0))
    refusal = f"token {foreign[:8]} does not belong to {CANARY}"
    assert code == 2 and "sweep: could not list tokens (HTTP 500)" in out and refusal in out, out
    really = e.proxy.faults["minted_id"]
    assert e.token(really)["revoked"] is False
    assert [(j["phase"], j.get("new_token")) for j in case.journals()] == [("minted", foreign)]
    e.proxy.faults.clear()
    code, out = case.run(verify=case.recorder(0))
    assert code == 2, out
    lines = out.splitlines()
    swept = lines.index(f"sweep: orphan {really[:8]} revoked")
    refused = [n for n, line in enumerate(lines) if line.startswith("refused:")]
    assert refused == [swept + 1] and refusal in lines[swept + 1], out
    assert e.token(really)["revoked"] is True, "the token the authority really minted was left active"
    assert e.token(foreign)["revoked"] is False and e.token(old)["revoked"] is False
    assert case.store.read_bytes() == raw and not case.record.exists()
    assert [(j["phase"], j.get("new_token")) for j in case.journals()] == [("minted", foreign)]


@pytest.mark.parametrize("started", ["during the mint", "ten minutes before"])
def test_a_recovered_minted_journal_sweeps_only_its_own_mints_window_and_spares_its_snapshot(case, started):
    """The sweep after a minted journal's revoke uses the journal's own snapshot and start time, not the run's: a
    same-grant token the agent had before that mint is never touched, and a journal recovered long after its mint
    does not sweep a same-grant token minted around the recovery."""
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    earlier = e.mint(DAY)  # same grant, in the snapshot
    known = e.token_ids()
    named = e.mint(DAY, scope=CANARY_SCOPE)  # the id an untrusted answer named: another grant
    really = e.mint(DAY)  # same grant, not in the snapshot, in no journal
    back = renew_token.timedelta(seconds={"during the mint": 0, "ten minutes before": 600}[started])
    case.journal("minted", old, new=named, known=known, started=renew_token.utcnow() - back)
    e.proxy.faults["mint_status"] = 409  # the run cannot renew; it can only reconcile
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and f"recovery: {named[:8]} revoked" in out, out
    assert e.token(named)["revoked"] is True and case.journals() == []
    assert e.token(earlier)["revoked"] is False and e.token(old)["revoked"] is False
    if started == "during the mint":
        assert f"sweep: orphan {really[:8]} revoked" in out and e.token(really)["revoked"] is True, out
    else:
        assert "sweep: no orphan token found" in out and e.token(really)["revoked"] is False, out


def test_a_recovered_minted_journal_whose_sweep_cannot_list_the_tokens_is_kept(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    known = e.token_ids()
    named = e.mint(DAY, scope=CANARY_SCOPE)
    really = e.mint(DAY)
    case.journal("minted", old, new=named, known=known)
    e.proxy.faults.update(list_fail=1, mint_status=409)  # the recovery sweep's list
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "sweep: could not list tokens" in out and "recovery: journal kept" in out, out
    assert e.token(named)["revoked"] is True and e.token(really)["revoked"] is False
    assert [(j["phase"], j.get("new_token")) for j in case.journals()] == [("minted", named)]
    e.proxy.faults.clear()
    e.proxy.faults["mint_status"] = 409
    code, out = case.run(verify=case.recorder(0))
    assert f"recovery: {named[:8]} was already revoked" in out and f"sweep: orphan {really[:8]} revoked" in out, out
    assert e.token(really)["revoked"] is True and case.journals() == []


@pytest.mark.parametrize("lifetime", [90, 30 * DAY - 60], ids=["90 seconds", "one minute short"])
def test_a_mint_whose_lifetime_was_changed_in_transit_is_revoked_and_never_swapped(case, lifetime):
    """The authority computes expires_at = issued_at + ttl_seconds and refuses (403), never clamps,
    a TTL over the roster maximum, so a lifetime other than the one asked for is an altered request.
    1.2 swapped in a 90 s token, proved it, and revoked the 30-day one: the agent halted D.expired.
    One minute short pins the tolerance at seconds, not hours."""
    e, old = case.e, case.e.mint(30 * DAY)
    raw = case.env_store(old)
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    e.proxy.faults["mint_ttl"] = lifetime
    code, out = case.run("--renew-within-days", "30", "--ttl-days", "30", verify=case.recorder(0))
    assert code == 1 and "mint response differs from the current grant (lifetime)" in out, out
    new = _new_since(e, before)
    assert _lifetime(e.token(new)) == lifetime and e.token(new)["revoked"] is True
    assert case.store.read_bytes() == raw and e.token(old)["revoked"] is False and not case.record.exists()
    events = e.events("token.renewal_failed")
    assert len(events) == failed + 1 and events[-1]["payload"]["reason"] == "mint_mismatch"
    assert case.journals() == []


def test_a_changed_lifetime_the_mint_answer_hides_is_caught_by_the_confirmation(case):
    e, old = case.e, case.e.mint(30 * DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    e.proxy.faults.update(mint_ttl=90, mint_answer_ttl=True)  # the answer claims the 30 days asked for
    code, out = case.run("--renew-within-days", "30", "--ttl-days", "30", verify=case.recorder(0))
    assert code == 1 and "new token could not be confirmed (lifetime)" in out, out
    new = _new_since(e, before)
    assert _lifetime(e.token(new)) == 90 and e.token(new)["revoked"] is True
    assert case.store.read_bytes() == raw and e.token(old)["revoked"] is False and not case.record.exists()
    assert [j["phase"] for j in case.journals()] == ["minting"]
    e.proxy.faults.clear()
    code, out = case.run("--renew-within-days", "30", "--ttl-days", "30", verify=case.probe())
    assert code == 0, out
    assert _lifetime(e.token(case.value())) == 30 * DAY and e.token(old)["revoked"] is True
    assert case.journals() == []


def test_a_journal_naming_a_token_id_that_was_never_issued_is_swept_not_kept_forever(case):
    """A `minted` journal whose new id the authority never issued (a mint answer that named a
    bogus uuid, then a confirmation that failed): its revoke can never be confirmed, so 1.2 kept
    the journal and stopped every later run, with the token the mint really created still active."""
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    known = e.token_ids()
    orphan = e.mint(DAY)  # what that mint really created: same grant, not in the snapshot, not journaled
    case.journal("minted", old, new="0badc0de-1111-4222-8333-444455556666", known=known)
    failed = len(e.events("token.renewal_failed"))
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert "was never issued; sweeping for the token that mint created" in out
    assert e.token(orphan)["revoked"] is True and e.token(old)["revoked"] is True
    assert e.events("token.renewal_failed")[failed]["payload"]["reason"] == "mint_answer_never_issued"
    assert case.journals() == []


@pytest.mark.parametrize("why", ["it is in the token list", "the token list cannot be read"])
def test_a_journal_token_that_answers_404_is_kept_unless_the_token_list_proves_it_was_never_issued(case, why):
    """The store race answers spurious 404s: a journaled token that 404s on every read but is in
    the agent's token list, or whose absence the list cannot confirm, may still be active. Its
    journal is kept (another grant, so no sweep would ever find it) until its revoke is confirmed."""
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    known = e.token_ids()
    wide = e.mint(DAY, scope=CANARY_SCOPE)
    case.journal("minted", old, new=wide, known=known)
    e.proxy.faults.update(not_found_except=old, mint_status=409)  # every read of it answers 404
    if why == "the token list cannot be read":
        e.proxy.faults["list_fail"] = 1
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "recovery: journal kept" in out, out
    assert "was never issued" not in out and "sweep:" not in out, out
    if why == "the token list cannot be read":
        assert "is not taken as never issued" in out, out
    assert e.token(wide)["revoked"] is False and [j.get("new_token") for j in case.journals()] == [wide]
    e.proxy.faults.clear()
    e.proxy.faults["mint_status"] = 409  # the next run cannot renew; it can only reconcile
    case.run(verify=case.recorder(0))
    assert e.token(wide)["revoked"] is True and case.journals() == []


def test_a_wrong_row_for_the_current_token_never_becomes_the_grant(case):
    """The delegation store's race can answer another row. Read for the CURRENT token, a
    wider same-agent row would be carried forward, and an unrelated token revoked."""
    e = case.e
    old = e.mint(DAY)  # the store's token: 3 scope entries
    wide = e.mint(DAY, scope=CANARY_SCOPE)  # same agent, 5 entries, not in the store
    raw = case.env_store(old)
    before = e.token_ids()
    e.proxy.faults.update(pre_mint_wrong_row_for=old, pre_mint_wrong_row=wide)
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "malformed response" in out, out
    assert e.token_ids() == before and case.store.read_bytes() == raw and not case.state.exists()
    assert e.token(old)["revoked"] is False and e.token(wide)["revoked"] is False


OTHER_GRANTOR = "Mallory, not the grantor of record"


def test_a_mint_re_attributed_to_another_grantor_is_revoked_and_never_swapped(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    row = {"allowed_scope": CANARY_SCOPE, "max_ttl_days": 400, "max_spend_usd": 1, "active": True}
    e.arm_roster(grantors=[dict(row, grantor=GRANTOR), dict(row, grantor=OTHER_GRANTOR)])  # both may mint
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    e.proxy.faults["mint_granted_by"] = OTHER_GRANTOR
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "differs from the current grant (granted_by)" in out, out
    new = _new_since(e, before)
    assert e.token(new)["granted_by"] == OTHER_GRANTOR and e.token(new)["revoked"] is True
    assert case.store.read_bytes() == raw and e.token(old)["revoked"] is False and not case.record.exists()
    events = e.events("token.renewal_failed")
    assert len(events) == failed + 1 and events[-1]["payload"]["reason"] == "mint_mismatch"
    assert case.journals() == []


def test_a_mint_re_attributed_to_another_agent_is_never_swapped(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    other = e.register()
    before = e.token_ids(other)
    e.proxy.faults["mint_agent_id"] = other
    code, out = case.run(verify=case.recorder(0))
    assert code == 2 and f"does not belong to {CANARY}" in out, out  # revoke() will not touch another agent's token
    _new_since(e, before, other)
    assert case.store.read_bytes() == raw and e.token(old)["revoked"] is False and not case.record.exists()


def test_a_confirmation_that_reads_another_row_is_never_swapped(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    bystander = e.mint(DAY)  # same grant and active: a wrong row that passes every other comparison
    e.proxy.faults["wrong_row_for_minted"] = bystander
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "could not be confirmed (token_id)" in out, out
    assert case.store.read_bytes() == raw and not case.record.exists()
    assert e.token(old)["revoked"] is False and e.token(bystander)["revoked"] is False


def test_a_minted_token_revoked_before_its_confirmation_is_never_swapped(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    e.proxy.faults["revoke_after_mint"] = True
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "could not be confirmed (not active)" in out, out
    new = _new_since(e, before)
    assert e.token(new)["revoked"] is True and e.token(old)["revoked"] is False
    assert case.store.read_bytes() == raw and not case.record.exists() and case.journals() == []


def test_no_mint_is_attempted_when_the_agents_tokens_cannot_be_listed_first(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    e.proxy.faults["list_fail"] = 1
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "mint: not attempted" in out, out
    assert e.token_ids() == before and case.store.read_bytes() == raw and not case.state.exists()
    assert ("POST", "/delegation/tokens") not in [(m, p) for m, p, _ in e.proxy.requests]


def test_no_mint_is_attempted_when_the_intent_journal_cannot_be_written(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    code, out = case.run(verify=case.recorder(0), wrap={"journal_fail": ["1"]})
    assert code == 1 and "not minting" in out, out
    assert e.token_ids() == before and case.store.read_bytes() == raw
    assert ("POST", "/delegation/tokens") not in [(m, p) for m, p, _ in e.proxy.requests]


@pytest.mark.parametrize("damage", ["byte", "dup"])
def test_a_swap_whose_restore_also_fails_never_revokes_a_token_the_store_may_hold(case, damage):
    """The swap writes damaged bytes and the write back fails: the store holds the NEW id (or
    cannot be parsed). Revoking the new token then would halt the agent on a token nobody revoked."""
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    before = e.token_ids()
    code, out = case.run(verify=case.recorder(0),
                         wrap={"store_corrupt": {"1": damage}, "store_fail": ["2"], "dup_line": f"{KEY}={old}"})
    assert code == 1 and "RESTORING THE ORIGINAL BYTES ALSO FAILED" in out, out
    new = _new_since(e, before)
    assert e.token(new)["revoked"] is False and e.token(old)["revoked"] is False
    assert [j["phase"] for j in case.journals()] == ["minted"] and not case.record.exists()
    if damage == "byte":
        assert "NOT revoked: the store holds it" in out and case.value() == new
        assert f"store STILL HOLDS {new[:8]}" in case.result(out)
    else:
        assert "NOT revoked: the store cannot be read" in out and "CANNOT BE READ" in case.result(out)


def test_a_response_body_is_never_printed(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    marker = "REFLECTED-request-header-value"
    e.proxy.faults.update(get_500_for=old, get_500_body={"detail": marker})
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "HTTP 500" in out, out
    assert marker not in out and case.store.read_bytes() == raw


# --- 4 and 1: refusals happen before anything is written -----------------------------------------


def test_a_current_token_the_authority_does_not_know_is_refused(case):
    raw = case.env_store("0badc0de-0000-4000-8000-000000000000")
    code, out = case.run(verify=case.recorder(0))
    assert code == 2 and "not known to the delegation authority" in out, out
    assert case.store.read_bytes() == raw and not case.state.exists()


def test_a_verify_command_that_is_not_given_the_new_token_is_refused(case):
    raw = case.env_store(case.e.mint(DAY))
    code, out = case.run(verify=case.script("noop", "print('noop verifier: tested nothing')\n"))
    assert code == 2 and "must pass {new_token}" in out, out
    assert case.store.read_bytes() == raw and case.e.proxy.requests == []


_BAD_ARGS = {
    "renewal window below 0": {"extra": ["--renew-within-days", "-1"]},
    "verify timeout below 1 s": {"extra": ["--verify-timeout", "0.5"]},
    "verify timeout above 1 h": {"extra": ["--verify-timeout", "3601"]},
    "base scheme": {"base": "ftp://127.0.0.1:18080"},
    # no secret: with one, the cleartext rule would refuse a hostless base as well and hide this rule
    "base without a host": {"base": "http://:18080", "secret": False},
    "base with a user": {"base": "http://user@127.0.0.1:18080"},
    "base with a password": {"base": "http://:pw@127.0.0.1:18080"},
    "base with a query": {"base": "http://127.0.0.1:18080/?a=1"},
    "base with a fragment": {"base": "http://127.0.0.1:18080/#f"},
    # the store DOES define `my-key=<uuid>`: only the name rule refuses it
    "env key not a variable name": {"store": ["--env-file", "STORE", "--env-key", "my-key"]},
    "agent id not a registry id": {"agent": "Canary-GB10"},
    "two stores": {"store": ["--env-file", "STORE", "--env-key", KEY, "--json-file", "STORE", "--json-key", CANARY]},
    "a store without its key": {"store": ["--env-file", "STORE"]},
    "unbalanced quotes": {"verify": '"unbalanced {new_token}'},
}


@pytest.mark.parametrize("name", sorted(_BAD_ARGS))
def test_invalid_arguments_are_refused_before_any_request(case, name):
    token = case.e.mint(30 * DAY)
    raw = case.env_store(token) + b"\nmy-key=" + token.encode()
    case.store.write_bytes(raw)
    spec = dict(_BAD_ARGS[name])
    extra = spec.pop("extra", [])
    if "store" in spec:
        spec["store"] = [str(case.store) if part == "STORE" else part for part in spec["store"]]
    verify = spec.pop("verify", case.recorder(0))
    code, out = case.run(*extra, verify=verify, **spec)
    assert code == 2 and "refused:" in out, out
    assert case.store.read_bytes() == raw and case.e.proxy.requests == [] and not case.record.exists()


def test_a_token_of_another_agent_is_refused_and_nothing_is_written(case):
    e = case.e
    agent = e.register()
    foreign = e.mint(DAY, agent=agent)
    raw = case.env_store(foreign)
    mine, theirs = e.token_ids(), e.token_ids(agent)
    failed = len(e.events("token.renewal_failed"))
    code, out = case.run(verify=case.recorder(0))
    assert code == 2, out
    assert "belongs to agent" in out
    assert case.store.read_bytes() == raw
    assert e.token_ids() == mine and e.token_ids(agent) == theirs and e.token(foreign)["revoked"] is False
    assert len(e.events("token.renewal_failed")) == failed and not case.state.exists()
    assert {m for m, _, _ in e.proxy.requests} == {"GET"}


@pytest.mark.parametrize("line", [
    b"VT_FIELD_TOKEN_ID=A1B2C3D4-0000-4000-8000-000000000000",           # upper case
    b'VT_FIELD_TOKEN_ID="a1b2c3d4-0000-4000-8000-000000000000"',         # quoted
    b"VT_FIELD_TOKEN_ID=a1b2c3d4-0000-4000-8000-000000000000\r",         # CRLF file
    b"VT_FIELD_TOKEN_ID=a1b2c3d4-0000-4000-8000-00000000000",            # short
    b"VT_FIELD_TOKEN_ID=",                                               # empty
    b"VT_FIELD_TOKEN_ID=a1b2c3d4-0000-4000-8000-000000000000 # comment",  # trailing text
    b"OTHER_KEY=a1b2c3d4-0000-4000-8000-000000000000",                   # missing
    b"VT_FIELD_TOKEN_ID=a1b2c3d4-0000-4000-8000-000000000000\n"
    b"VT_FIELD_TOKEN_ID=b1b2c3d4-0000-4000-8000-000000000000",           # defined twice
    b"VT_FIELD_TOKEN_ID=a1b2c3d4-0000-4000-8000-000000000000\n"
    b"export VT_FIELD_TOKEN_ID=b1b2c3d4-0000-4000-8000-000000000000",    # shadowed by an export
    b"  VT_FIELD_TOKEN_ID=a1b2c3d4-0000-4000-8000-000000000000",         # only an indented form
])
def test_a_malformed_env_store_value_is_refused_before_any_request(case, line):
    raw = b"ANTHROPIC_API_KEY=" + FAKE_API_KEY.encode() + b"\n" + line + b"\n"
    case.store.write_bytes(raw)
    code, out = case.run(verify=case.recorder(0))
    assert code == 2, out
    assert case.store.read_bytes() == raw and case.e.proxy.requests == [] and not case.state.exists()


@pytest.mark.parametrize("doc", [
    '{"canary-gb10": 12345}',
    '{"canary-gb10": "a1b2c3d4-0000-4000-8000-000000000000", "canary-gb10": "b1b2c3d4-0000-4000-8000-000000000000"}',
    '{"canary-gb10": "\\u00611b2c3d4-0000-4000-8000-000000000000"}',
    '["canary-gb10", "a1b2c3d4-0000-4000-8000-000000000000"]',
    '{"canary-gb10": "a1b2c3d4-0000-4000-8000-000000000000"',
    '{"other": {"canary-gb10": "a1b2c3d4-0000-4000-8000-000000000000"}}',
])
def test_a_malformed_json_store_is_refused_before_any_request(case, doc):
    path = case.tmp / "tokens.json"
    path.write_text(doc, encoding="utf-8")
    code, out = case.run(verify=case.recorder(0), store=["--json-file", str(path), "--json-key", CANARY])
    assert code == 2, out
    assert path.read_text(encoding="utf-8") == doc and case.e.proxy.requests == []


def test_a_symlinked_store_is_refused(case):
    target = case.tmp / "real.env"
    target.write_bytes(KEY.encode() + b"=" + case.e.mint(DAY).encode() + b"\n")
    try:
        os.symlink(target, case.store)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symlinks")
    code, out = case.run(verify=case.recorder(0))
    assert code == 2 and "symlink" in out and case.e.proxy.requests == []


def test_a_revoked_token_is_not_renewed_unless_asked(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    assert e.call("POST", f"/delegation/tokens/{old}/revoke")[0] == 200
    before = e.token_ids()
    code, out = case.run(verify=case.probe())
    assert code == 2 and "REVOKED" in out, out
    assert case.store.read_bytes() == raw and e.token_ids() == before and not case.state.exists()
    code, out = case.run("--renew-revoked", verify=case.probe())
    assert code == 0, out
    assert e.token(case.value())["revoked"] is False


# --- 2: the lock -------------------------------------------------------------------------------------


def test_a_held_lock_skips_visibly_and_writes_nothing(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    with lock_held(case.lock, case.tmp):
        code, out = case.run(verify=case.recorder(0))
    assert code == 3, out
    assert "skipped: lock held" in out
    assert case.store.read_bytes() == raw and e.proxy.requests == [] and not case.state.exists()
    code, out = case.run(verify=case.probe())  # released: the same run now renews
    assert code == 0, out


def test_check_never_writes_even_when_due_and_the_lock_is_held(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    ledger = len(e.events("token.renewed")) + len(e.events("token.renewal_failed"))
    with lock_held(case.lock, case.tmp):
        code, out = case.run("--check", verify=case.recorder(0))
    assert code == 0, out
    assert "check: due" in out
    assert case.store.read_bytes() == raw and e.token_ids() == before and e.token(old)["revoked"] is False
    assert len(e.events("token.renewed")) + len(e.events("token.renewal_failed")) == ledger
    assert {m for m, _, _ in e.proxy.requests} == {"GET"} and not case.state.exists()
    assert not case.record.exists()
    case.env_store(e.mint(30 * DAY))
    code, out = case.run("--check")
    assert code == 0 and "check: not due: 29 days left" in out


def test_the_stores_own_lock_is_taken_even_when_a_lock_file_is_given(case):
    raw = case.env_store(case.e.mint(DAY))
    with lock_held(case.tmp / ".secrets.env.renew-lock", case.tmp):
        code, out = case.run(verify=case.recorder(0))
    assert code == 3 and "skipped: lock held" in out and ".secrets.env.renew-lock" in out, out
    assert case.store.read_bytes() == raw and case.e.proxy.requests == [] and not case.state.exists()


def test_a_hand_run_without_lock_file_is_excluded_by_a_scheduled_run_with_it(case):
    """The cron run passes --lock-file ~/vt/.lock; an operator's hand run may not. The hand run
    must not treat the live run's journal as a crash and revoke its freshly minted token."""
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    before = e.token_ids()
    e.proxy.faults["hold_get_except"] = old  # the scheduled run parks after its mint, locks held
    proc = case.spawn(verify=case.probe())
    try:
        assert e.proxy.held.wait(60), "the scheduled run never reached its confirmation step"
        code, out = case.run(verify=case.probe(), lock=False)
    finally:
        e.proxy.release.set()
    out_a = proc.communicate(timeout=120)[0].decode("utf-8", "replace")
    e.proxy.wait_idle()
    assert code == 3 and "skipped: lock held" in out, out
    assert proc.returncode == 0, out_a
    new = _new_since(e, before)
    assert case.value() == new and e.token(new)["revoked"] is False and e.token(old)["revoked"] is True


def test_both_locks_are_held_for_the_whole_renewal_including_verification(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    state = case.tmp / "lockstate.txt"
    probe = case.script("lockprobe", LOCK_PROBE, "{new_token}", _q(state), _q(case.lock),
                        _q(case.tmp / ".secrets.env.renew-lock"))
    code, out = case.run(verify=probe)
    assert code == 0, out
    assert state.read_text() == "held held", "vt's run.sh or a second renewal could start mid-renewal"


# --- 3: crash recovery ------------------------------------------------------------------------------


def test_crash_after_the_mint_before_the_swap_next_run_revokes_the_orphan(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    e.proxy.faults["hold_get_except"] = old  # hold the confirmation of the NEW token
    proc = case.spawn(verify=case.probe())
    try:
        assert e.proxy.held.wait(60), "the renewal never reached its confirmation step"
        journals = case.journals()
        proc.kill()  # the renewal dies here: minted, journaled, not swapped
        proc.communicate(timeout=30)
    finally:
        e.proxy.release.set()
        e.proxy.wait_idle()
    assert [j["phase"] for j in journals] == ["minted"]
    orphan = journals[0]["new_token"]
    assert case.store.read_bytes() == raw and e.token(orphan)["revoked"] is False
    e.proxy.faults.clear()
    failed = len(e.events("token.renewal_failed"))
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert e.token(orphan)["revoked"] is True
    assert e.events("token.renewal_failed")[failed]["payload"]["reason"] == "interrupted_before_swap"
    assert case.value() not in (old, orphan) and e.token(old)["revoked"] is True
    assert case.journals() == []


def test_crash_during_the_mint_next_run_sweeps_the_orphan_the_lost_response_created(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    e.proxy.faults["mint_hold"] = True
    proc = case.spawn(verify=case.probe())
    try:
        assert e.proxy.held.wait(60)
        proc.kill()
        proc.communicate(timeout=30)
    finally:
        e.proxy.release.set()
        e.proxy.wait_idle()
    orphan = _new_since(e, before)
    assert [j["phase"] for j in case.journals()] == ["minting"]
    assert case.store.read_bytes() == raw and e.token(orphan)["revoked"] is False
    e.proxy.faults.clear()
    failed = len(e.events("token.renewal_failed"))
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert e.token(orphan)["revoked"] is True
    events = e.events("token.renewal_failed")
    assert len(events) == failed + 1 and events[-1]["payload"]["reason"] == "interrupted_during_mint"
    assert case.value() not in (old, orphan) and e.token(old)["revoked"] is True


def test_crash_after_the_swap_before_verification_next_run_verifies_and_revokes_the_old(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    code, out = case.run(verify=case.script("killer", KILLER, "{new_token}"))
    assert code not in (0, 1, 2, 3), out
    new = _new_since(e, before)
    assert case.value() == new and [j["phase"] for j in case.journals()] == ["minted"]
    assert e.token(old)["revoked"] is False and e.token(new)["revoked"] is False
    renewed = len(e.events("token.renewed"))
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert "the renewal did not finish" in out
    assert e.token(old)["revoked"] is True and e.token(new)["revoked"] is False
    assert case.store.read_bytes() == raw.replace(old.encode(), new.encode())
    assert len(e.events("token.renewed")) == renewed + 1 and case.journals() == []
    assert e.token_ids() == before | {new}  # resuming never mints again


def test_a_human_revocation_of_the_swapped_token_after_a_crash_is_never_undone(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    before = e.token_ids()
    case.run(verify=case.script("killer", KILLER, "{new_token}"))
    new = _new_since(e, before)
    assert case.value() == new and [j["phase"] for j in case.journals()] == ["minted"]
    swapped = case.store.read_bytes()
    assert e.call("POST", f"/delegation/tokens/{new}/revoke")[0] == 200  # a human kills vt's delegation
    for _ in range(2):  # the next scheduled runs
        code, out = case.run(verify=case.recorder(0))
        assert code == 2 and "Nothing restored and nothing revoked" in out, out
        assert not case.record.exists(), "a revoked journal token was taken back to verification"
        assert case.store.read_bytes() == swapped and e.token(old)["revoked"] is False
        assert [j["phase"] for j in case.journals()] == ["minted"]
    assert e.token_ids() == before | {new}


def test_an_expired_old_token_is_never_restored_over_the_new_one(case):
    e, old = case.e, case.e.mint(3)
    case.env_store(old)
    time.sleep(3.5)
    before = e.token_ids()
    case.run("--renew-within-days", "0", verify=case.script("killer", KILLER, "{new_token}"))
    new = _new_since(e, before)
    assert case.value() == new
    code, out = case.run(verify=case.recorder(1))  # the resumed verification fails (a transient estate error)
    assert code == 1 and "restore: NOT done" in out, out
    assert case.value() == new and e.token(new)["revoked"] is False, "vt was left with an expired token only"
    assert [j["phase"] for j in case.journals()] == ["minted"]
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert case.value() == new and e.token(new)["revoked"] is False and e.token(old)["revoked"] is True


def test_a_crash_after_the_old_token_was_revoked_is_finished_never_rolled_back(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    before, renewed = e.token_ids(), len(e.events("token.renewed"))
    e.proxy.faults["ledger_hold"] = "token.renewed"  # the renewal dies right after revoking the old token
    proc = case.spawn(verify=case.recorder(0))
    try:
        assert e.proxy.held.wait(60), "the renewal never reached its token.renewed append"
        proc.kill()
        proc.communicate(timeout=30)
    finally:
        e.proxy.release.set()
        e.proxy.wait_idle()
    new = _new_since(e, before)
    assert case.value() == new and e.token(old)["revoked"] is True
    assert [j["phase"] for j in case.journals()] == ["verified"]
    e.proxy.faults.clear()
    case.record.unlink()
    code, out = case.run(verify=case.recorder(1))  # a verifier that would fail now is never run, never rolled back to
    assert code == 0, out
    assert not case.record.exists()
    assert case.value() == new and e.token(new)["revoked"] is False
    assert len(e.events("token.renewed")) == renewed + 1 and case.journals() == []


def test_a_lost_answer_to_the_old_tokens_revoke_is_finished_never_rolled_back(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    renewed = len(e.events("token.renewed"))
    e.proxy.faults["revoke_drop"] = old  # the authority revokes; the answer never arrives
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "transport error" in out, out
    new = case.value()
    assert e.token(old)["revoked"] is True and [j["phase"] for j in case.journals()] == ["verified"]
    e.proxy.faults.clear()
    case.record.unlink()
    code, out = case.run(verify=case.recorder(1))
    assert code == 0 and "was already revoked" in out, out
    assert not case.record.exists() and case.value() == new and e.token(new)["revoked"] is False
    assert len(e.events("token.renewed")) == renewed + 1


def test_a_journal_token_that_expired_before_its_renewal_finished_is_refused(case):
    e, old = case.e, case.e.mint(DAY)
    new = e.mint(2)
    raw = case.env_store(new)  # swapped in by a run that died, then left long enough to expire
    journal = case.journal("minted", old, new=new)
    time.sleep(2.5)
    code, out = case.run(verify=case.recorder(0))
    assert code == 2 and "EXPIRED" in out, out
    assert not case.record.exists() and case.store.read_bytes() == raw and os.path.exists(journal.path)
    assert e.token(old)["revoked"] is False


def test_a_verified_journal_whose_store_was_changed_since_is_refused(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    new = e.mint(DAY)
    journal = case.journal("verified", old, new=new)
    code, out = case.run(verify=case.recorder(0))
    assert code == 2 and "passed verification" in out, out
    assert e.token(new)["revoked"] is False and e.token(old)["revoked"] is False
    assert case.store.read_bytes() == raw and os.path.exists(journal.path) and not case.record.exists()


def test_a_verified_journal_whose_new_token_was_revoked_since_is_refused(case):
    e, old = case.e, case.e.mint(DAY)
    new = e.mint(DAY)
    raw = case.env_store(new)
    journal = case.journal("verified", old, new=new)
    assert e.call("POST", f"/delegation/tokens/{new}/revoke")[0] == 200
    code, out = case.run(verify=case.recorder(0))
    assert code == 2 and "Nothing restored and nothing revoked" in out, out
    assert e.token(old)["revoked"] is False and case.store.read_bytes() == raw and os.path.exists(journal.path)


@pytest.mark.parametrize("fault", ["revoke_fail", "get_500_for"])
def test_a_recovery_revoke_that_fails_keeps_the_journal_until_the_orphan_is_revoked(case, fault):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    orphan = e.mint(DAY)  # minted and journaled, never swapped
    case.journal("minted", old, new=orphan, known=e.token_ids() - {orphan})
    e.proxy.faults.update({fault: orphan, "mint_status": 409})
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "recovery: journal kept" in out, out
    assert e.token(orphan)["revoked"] is False and [j["phase"] for j in case.journals()] == ["minted"]
    e.proxy.faults.clear()
    e.proxy.faults["mint_status"] = 409  # the next run cannot renew; it can only reconcile
    case.run(verify=case.recorder(0))
    assert e.token(orphan)["revoked"] is True, "orphan left ACTIVE with no journal"
    assert case.journals() == []


def test_an_interrupted_mint_whose_sweep_cannot_list_keeps_the_journal(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    known = e.token_ids()
    orphan = e.mint(DAY)  # what a lost mint answer left behind
    case.journal("minting", old, known=known)
    e.proxy.faults["list_fail"] = 2  # the recovery sweep's list, then the pre-mint snapshot
    code, out = case.run(verify=case.recorder(0))
    assert code == 1 and "sweep incomplete; journal kept" in out, out
    assert e.token(orphan)["revoked"] is False and [j["phase"] for j in case.journals()] == ["minting"]
    e.proxy.faults.clear()
    e.proxy.faults["mint_status"] = 409
    case.run(verify=case.recorder(0))
    assert e.token(orphan)["revoked"] is True, "orphan of the interrupted mint left ACTIVE with no journal"


def test_recovery_refuses_a_swapped_journal_token_of_another_agent_before_verifying_it(case):
    e = case.e
    old = e.mint(DAY)
    foreign = e.mint(DAY, agent=e.register())
    raw = case.env_store(foreign)  # the store holds the journal's new token: the resume branch
    journal = case.journal("minted", old, new=foreign)
    code, out = case.run(verify=case.recorder(0))
    assert code == 2 and "belongs to another agent" in out, out
    assert not case.record.exists(), "another agent's token was taken to verification"
    assert case.store.read_bytes() == raw and os.path.exists(journal.path)
    assert e.token(old)["revoked"] is False and e.token(foreign)["revoked"] is False


def test_crash_after_the_swap_then_a_failed_verification_restores_the_old_token(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    code, _ = case.run(verify=case.script("killer", KILLER, "{new_token}"))
    new = _new_since(e, before)
    assert case.value() == new
    failed = len(e.events("token.renewal_failed"))
    code, out = case.run(verify=case.recorder(rc=1))
    assert code == 1, out
    assert case.store.read_bytes() == raw
    assert e.token(new)["revoked"] is True and e.token(old)["revoked"] is False
    events = e.events("token.renewal_failed")
    assert len(events) == failed + 1 and events[-1]["payload"]["reason"] == "verify_failed"
    assert case.journals() == []


def test_a_failed_revoke_of_the_old_token_keeps_the_journal_and_the_next_run_finishes(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    renewed = len(e.events("token.renewed"))
    e.proxy.faults["revoke_fail"] = old
    code, out = case.run(verify=case.probe())
    assert code == 1, out
    new = case.value()
    assert new != old and e.token(old)["revoked"] is False and e.token(new)["revoked"] is False
    assert [j["phase"] for j in case.journals()] == ["verified"]
    assert len(e.events("token.renewed")) == renewed
    e.proxy.faults.clear()
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert e.token(old)["revoked"] is True and case.value() == new
    assert len(e.events("token.renewed")) == renewed + 1


def test_recovery_refuses_to_revoke_a_token_that_belongs_to_another_agent(case):
    e = case.e
    old = e.mint(DAY)
    case.env_store(old)
    agent = e.register()
    foreign = e.mint(DAY, agent=agent)
    journal = case.journal("minted", old, new=foreign)
    code, out = case.run(verify=case.probe())
    assert code == 2, out
    assert e.token(foreign)["revoked"] is False and e.token(old)["revoked"] is False
    assert os.path.exists(journal.path)


def test_the_store_changing_during_a_renewal_is_not_overwritten(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    e.proxy.faults["hold_get_except"] = old
    failed = len(e.events("token.renewal_failed"))
    proc = case.spawn(verify=case.probe())
    try:
        assert e.proxy.held.wait(60)
        changed = raw + b"\nFIELD_GOVERNOR_URL=http://127.0.0.1:18080/governor\n"
        case.store.write_bytes(changed)  # e.g. an operator's setenv.py edit
    finally:
        e.proxy.release.set()
    out, _ = proc.communicate(timeout=120)
    assert proc.returncode == 1, out
    new = _new_since(e, before)
    assert case.store.read_bytes() == changed
    assert e.token(new)["revoked"] is True and e.token(old)["revoked"] is False
    events = e.events("token.renewal_failed")
    assert len(events) == failed + 1 and events[-1]["payload"]["reason"] == "store_changed"


def test_stale_temp_files_from_an_interrupted_swap_are_removed(case):
    case.env_store(case.e.mint(30 * DAY))
    stale = case.tmp / ".secrets.env.renew-tmp-leftover"
    stale.write_bytes(b"a copy of the store would hold the API key")
    code, out = case.run(verify=case.recorder(0))
    assert code == 0, out
    assert not stale.exists() and "removed 1 stale temp file" in out


# --- the swap guard, in process: a write that does not read back is undone ------------------------


def test_swap_readback_mismatch_restores_the_original_bytes(tmp_path, monkeypatch):
    path = tmp_path / "secrets.env"
    old, new = "a1b2c3d4-0000-4000-8000-000000000000", "b1b2c3d4-0000-4000-8000-000000000000"
    raw = f"A=1\n{KEY}={old}\nANTHROPIC_API_KEY={FAKE_API_KEY}\n".encode()
    path.write_bytes(raw)
    store = renew_token.Store("env-file", str(path), KEY)
    start, end, _ = store.locate(raw)
    real, calls = renew_token.write_atomic, []

    def corrupting(p, data, mode):  # the first write damages a byte outside the value
        calls.append(data)
        real(p, data.replace(b"A=1", b"A=2") if len(calls) == 1 else data, mode)

    monkeypatch.setattr(renew_token, "write_atomic", corrupting)
    ok, msg = renew_token.replace_value(store, raw, start, end, new)
    assert ok is False and "original bytes written back" in msg
    assert path.read_bytes() == raw and len(calls) == 2


def test_swap_write_error_leaves_the_original_and_no_temp_file(tmp_path, monkeypatch):
    path = tmp_path / "secrets.env"
    old, new = "a1b2c3d4-0000-4000-8000-000000000000", "b1b2c3d4-0000-4000-8000-000000000000"
    raw = f"{KEY}={old}\n".encode()
    path.write_bytes(raw)
    store = renew_token.Store("env-file", str(path), KEY)
    start, end, _ = store.locate(raw)

    def failing_replace(src, dst):  # e.g. a read-only store on Windows: every replace fails
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(renew_token.os, "replace", failing_replace)
    ok, msg = renew_token.replace_value(store, raw, start, end, new)
    assert ok is False and path.read_bytes() == raw
    assert [p.name for p in tmp_path.iterdir()] == ["secrets.env"]
    # the original was never touched, so this is not the "restore also failed" alarm
    assert "still in place" in msg and "FAILED" not in msg


# --- secrets -----------------------------------------------------------------------------------------


def test_the_secret_file_path_works_and_the_secret_never_appears(case):
    e, old = case.e, case.e.mint(DAY)
    secret_file = case.tmp / "estate-secret"
    secret_file.write_text(SECRET + "\n")
    case.env_store(old)
    code, out = case.run("--secret-file", str(secret_file), verify=case.probe(secret_file), secret=False)
    assert code == 0, out
    assert e.token(old)["revoked"] is True


def test_without_the_secret_the_estate_answers_401_and_nothing_is_written(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    code, out = case.run(verify=case.probe(), secret=False)
    assert code == 1 and "401" in out, out
    assert case.store.read_bytes() == raw and e.token_ids() == before and not case.state.exists()


def test_an_unsafe_secret_is_refused_and_never_printed(case, tmp_path):
    raw = case.env_store(case.e.mint(DAY))
    for bad in (SECRET + "\r", "two words"):
        proc = subprocess.run([PY, "-I", str(TOOL), *case.argv(verify=case.recorder(0))],
                              env=dict(_env(False), FIELD_SHARED_SECRET=bad), capture_output=True, timeout=60)
        assert proc.returncode == 2 and bad.encode() not in proc.stdout + proc.stderr
    # a second line, empty, non-ASCII, and a control character that is not whitespace
    for content in (SECRET + "\nsecond line\n", "", "café-" + SECRET, "bell\x07" + SECRET):
        f = tmp_path / "s"
        f.write_text(content, encoding="utf-8")
        code, out = case.run("--secret-file", str(f), verify=case.recorder(0), secret=False)
        assert code == 2, out
        assert content.strip() == "" or content.strip() not in out
    assert case.store.read_bytes() == raw and case.e.proxy.requests == []


def test_redaction_also_covers_the_escaped_form_of_the_secret():
    """A traceback or a relayed repr() prints a backslash doubled: that form is redacted too."""
    secret = "back\\slash-" + SECRET
    sink = io.StringIO()
    renew_token.Redact(sink, secret).write(f"{secret} {secret!r} {[secret]}\n")
    assert "slash" not in sink.getvalue(), sink.getvalue()


#: Writes one value across the start of the tool's 64 KiB relay window: the window begins `k`
#: characters into the value ("secret" = the inherited FIELD_SHARED_SECRET, otherwise the
#: value itself). k = -10 starts the window exactly at the start of the value's line.
CUTTER = r'''
import os, sys
which, k, window, rc = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
value = (os.environ.get("FIELD_SHARED_SECRET", "") if which == "secret" else which).encode()
lead = b"cut line: "
cut = lead + value + b" TAILMARK\n"
after = b"next line after the cut\n"
rest = window - (len(cut) - len(lead) - k) - len(after)
assert rest > 0
filler = (b"Y" * 99 + b"\n") * (rest // 100) + b"Y" * (rest % 100)
sys.stdout.buffer.write(b"first line\n" + cut + after + filler)
sys.stdout.buffer.flush()
sys.exit(rc)
'''

#: One line of 70 KiB, no line break at all, with the value 10 characters into the window.
GIANT = r'''
import os, sys
window = int(sys.argv[1])
value = os.environ["FIELD_SHARED_SECRET"].encode()
tail = value[10:] + b" TAILMARK" + b"Y" * (window - len(value) + 10 - 9)
sys.stdout.buffer.write(b"Y" * 6000 + value[:10] + tail)
'''

#: Breaks each value across lines the way a console wrap would, at every split point.
WRAPPER_OUTPUT = r'''
import os, sys
secret, new = os.environ["FIELD_SHARED_SECRET"], sys.argv[1]
out = []
for value in (secret, new):
    for j in range(1, len(value)):
        out.append("wrap %d: %s\r\n%s :end" % (j, value[:j], value[j:]))
out.append("\r\n".join(["chunks:"] + [secret[i:i + 6] for i in range(0, len(secret), 6)] + [":end"]))
out.append("prefix alone " + secret[:12] + "\r\nunrelated line")
out.append(secret[-12:] + " suffix alone")
out.append("id " + new + " shortened")
sys.stdout.buffer.write(("\r\n".join(out) + "\r\n").encode())
'''

_RELAY_NEW, _RELAY_OLD = "d174d7e9-9742-4743-809f-ae1ddb5b81ee", "4191cd46-6d0e-4b8a-9c3f-2f6a1e0b7d55"


def _grams(value: str, first: int = 0) -> list[str]:
    return [value[i:i + 8] for i in range(first, len(value) - 7)]


def _relayed(log: str) -> str:
    """The relayed verifier lines joined as one string: a reader of the log can join them too."""
    return "".join(line.split("  verify| ", 1)[1] for line in log.splitlines() if line.startswith("  verify| "))


class _RelayRun:
    """run_verify() in this process, printing through the Redact wrapper main() installs."""

    def __init__(self, tmp: Path, monkeypatch):
        self.tmp, self.sink = tmp, io.StringIO()
        self.renewal = renew_token.Renewal.__new__(renew_token.Renewal)
        self.renewal.a, self.renewal.secret = argparse.Namespace(verify_timeout=60.0), SECRET
        monkeypatch.setattr(sys, "stdout", renew_token.Redact(self.sink, SECRET))
        monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)

    def __call__(self, name: str, source: str, *args: str) -> str:
        script = self.tmp / f"{name}.py"
        script.write_text(source, encoding="utf-8")
        self.renewal.verify_argv = [PY, "-I", str(script), *args]
        self.sink.seek(0)
        self.sink.truncate()
        self.renewal.run_verify(_RELAY_NEW, _RELAY_OLD)
        return self.sink.getvalue()


def test_the_relay_window_never_prints_part_of_the_secret_or_a_token_id_at_any_cut(tmp_path, monkeypatch):
    """E6: the 64 KiB window used to start mid-line, so a secret or a token id straddling
    its start printed from the cut onward, past both the redactor and the id shortening."""
    run, window = _RelayRun(tmp_path, monkeypatch), str(renew_token.VERIFY_OUTPUT_MAX)
    for value, name in ((SECRET, "secret"), (_RELAY_NEW, _RELAY_NEW)):
        forbidden = _grams(value, first=0 if name == "secret" else 1)
        for k in range(1, len(value)):
            log = run("cutter", CUTTER, name, str(k), window, "1")
            leaked = [g for g in forbidden if g in log or g in _relayed(log)]
            assert leaked == [], f"cut {k} characters into the {name[:6]}: printed {leaked}\n{log[:600]}"
            assert "TAILMARK" not in log, f"cut {k}: the line the window cuts must be dropped whole"
            assert "  verify| [earlier output truncated]" in log and "  verify| next line after the cut" in log
    # a window that starts exactly at a line start keeps that line, redacted
    log = run("cutter", CUTTER, "secret", "-10", window, "1")
    assert "  verify| cut line: <redacted> TAILMARK" in log, log[:600]
    # a window with no line break at all shows none of it
    log = run("giant", GIANT, window)
    assert "TAILMARK" not in log and not [g for g in _grams(SECRET) if g in log], log[:600]
    assert "hold no complete line; not shown" in log


def test_a_secret_or_token_id_the_verifier_breaks_across_lines_is_masked_on_both_sides(tmp_path, monkeypatch):
    """PowerShell wraps an error record at the console width: a value split across two (or
    seven) lines is whole in neither, so a redactor that looks at one line at a time misses it."""
    log = _RelayRun(tmp_path, monkeypatch)("wrapper", WRAPPER_OUTPUT, _RELAY_NEW)
    joined = _relayed(log)
    assert [g for g in _grams(SECRET) if g in log or g in joined] == [], log
    assert [g for g in _grams(_RELAY_NEW, first=1) if g in log or g in joined] == [], log
    assert "  verify| prefix alone <redacted>" in log and "  verify| <redacted> suffix alone" in log
    assert "  verify| unrelated line" in log
    # the id's own prefix stays readable, as everywhere else in the log
    assert f"  verify| id {_RELAY_NEW[:8]}... shortened" in log
    assert f"  verify| wrap 20: {_RELAY_NEW[:8]}..." in log


#: Prints isolated fragments, taken from the middle, of the secret and of a full token id: each alone
#: on its own line between markers, so no neighbouring line can complete a longer run.
FRAGMENTS = r'''
import os, sys
secret, new = os.environ["FIELD_SHARED_SECRET"], sys.argv[1]
lines = []
for size in (7, 8, 9, 11):
    lines.append("frag %d %s end" % (size, secret[12:12 + size]))
    lines.append("idfrag %d %s end" % (size, new[10:10 + size]))
sys.stdout.write("\n".join(lines) + "\n")
'''


def test_the_relay_masks_an_isolated_fragment_of_8_characters_and_not_of_7(tmp_path, monkeypatch):
    """Guarantee 9's boundary: a run of 8 or more characters of the secret, or of a token id past its
    prefix, is masked; 7 is the documented limit. The other relay tests only print whole values,
    12-character pieces or cut lines, so a mask threshold of 12 passed all of them."""
    log = _RelayRun(tmp_path, monkeypatch)("fragments", FRAGMENTS, _RELAY_NEW)
    for size in (8, 9, 11):
        assert f"  verify| frag {size} <redacted> end" in log, log
        assert f"  verify| idfrag {size} ... end" in log, log
    assert f"  verify| frag 7 {SECRET[12:19]} end" in log, log
    assert f"  verify| idfrag 7 {_RELAY_NEW[10:17]} end" in log, log


def test_scrub_masks_fragments_of_the_escaped_form_of_the_secret_too():
    secret = "back\\slash-" + SECRET  # repr() and a traceback print the backslash doubled
    escaped = renew_token.secret_forms(secret)[1]
    assert escaped != secret
    lines = renew_token.scrub(["x " + escaped[:12], escaped[12:] + " y"], renew_token.secret_forms(secret), ())
    assert lines == ["x <redacted>", "<redacted> y"], lines


@pytest.mark.parametrize("which", ["secret cut", "new token id cut", "both wrapped"])
def test_a_real_renewal_never_prints_part_of_a_value_its_relay_window_cuts_or_its_verifier_wraps(case, which):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    before = e.token_ids()
    window = str(renew_token.VERIFY_OUTPUT_MAX)
    if which == "both wrapped":
        verify, rc = case.script("wrapper", WRAPPER_OUTPUT, "{new_token}"), 0
    else:
        value, k, rc = ("secret", "5", 1) if which == "secret cut" else ("{new_token}", "8", 0)
        verify = case.script("cutter", CUTTER, value, k, window, str(rc), "{new_token}")
    code, out = case.run(verify=verify)
    new = _new_since(e, before)
    leaked = [g for g in _grams(SECRET) + _grams(new, first=1) if g in out or g in _relayed(out)]
    assert leaked == [], out[-3000:]
    if which == "both wrapped":
        assert "  verify| prefix alone <redacted>" in out and f"  verify| id {new[:8]}... shortened" in out
    else:
        assert "TAILMARK" not in out and "  verify| next line after the cut" in out, out[-2000:]
    if rc == 1:
        assert code == 1 and case.store.read_bytes() == raw and e.token(new)["revoked"] is True, out[-2000:]
    else:
        assert code == 0 and case.value() == new and e.token(old)["revoked"] is True, out[-2000:]


def test_an_environment_proxy_never_receives_a_request(case, monkeypatch):
    """Task Scheduler runs inherit the user's environment: HTTP_PROXY must not carry x-field-auth."""
    e, old = case.e, case.e.mint(30 * DAY)
    case.env_store(old)
    sink = Sink()
    for var in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.setenv(var, sink.base)
    for var in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(var, raising=False)
    code, out = case.run(verify=case.recorder(0))
    sink.server.shutdown()
    assert code == 0 and "not due" in out, out
    assert sink.seen == [], f"the proxy saw {len(sink.seen)} request(s)"


def test_cleartext_to_a_public_host_is_refused_with_a_secret(case):
    raw = case.env_store(case.e.mint(DAY))
    for base in ("http://estate.example.com", "http://8.8.8.8:18080"):
        code, out = case.run(verify=case.recorder(0), base=base)
        assert code == 2 and "cleartext" in out, out
    assert case.store.read_bytes() == raw


def test_a_redirect_is_never_followed(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.env_store(old)
    sink = Sink()
    e.proxy.faults["redirect_to"] = sink.base
    code, out = case.run(verify=case.recorder(0))
    assert code == 1, out
    assert sink.seen == [] and case.store.read_bytes() == raw
    sink.server.shutdown()


def test_a_failed_ledger_append_never_changes_a_successful_renewal(case):
    e, old = case.e, case.e.mint(DAY)
    case.env_store(old)
    renewed = len(e.events("token.renewed"))
    e.proxy.faults["ledger_status"] = 500
    code, out = case.run(verify=case.probe())
    assert code == 0, out
    assert "token.renewed append FAILED" in out
    assert case.value() != old and e.token(old)["revoked"] is True
    assert len(e.events("token.renewed")) == renewed


# --- POSIX-only guards: the GB10's platform (Windows skips these; Linux CI runs them) ----------------

posix = pytest.mark.skipif(os.name == "nt", reason="POSIX-only guard")
_OLD_ID, _NEW_ID = "a1b2c3d4-0000-4000-8000-000000000000", "b1b2c3d4-0000-4000-8000-000000000000"


@posix
def test_posix_lock_excludes_and_is_excluded_by_bash_flock(tmp_path):
    """vt's run.sh takes `flock -n` on ~/vt/.lock (fd 9): the two must exclude each other."""
    lock, store = tmp_path / "vt.lock", tmp_path / "secrets.env"
    lock.write_bytes(b"")
    raw = f"{KEY}={_OLD_ID}\nANTHROPIC_API_KEY={FAKE_API_KEY}\n".encode()
    store.write_bytes(raw)
    # exec: the sleeping process itself holds fd 9, so killing it releases the lock
    holder = subprocess.Popen(["bash", "-c", f'exec 9>"{lock}"; flock -n 9 && echo held && exec sleep 60'],
                              stdout=subprocess.PIPE)
    try:
        assert holder.stdout.readline().strip() == b"held"
        proc = subprocess.run([PY, "-I", str(TOOL), "--agent", CANARY, "--base", "http://127.0.0.1:9",
                               "--env-file", str(store), "--env-key", KEY, "--lock-file", str(lock),
                               "--verify-cmd", "/bin/true {new_token}"], env=_env(False), capture_output=True, text=True,
                              timeout=60)
        assert proc.returncode == 3 and "skipped: lock held" in proc.stdout, proc.stdout
    finally:
        holder.kill()
        holder.wait()
    assert store.read_bytes() == raw
    fd = renew_token.acquire_lock(str(lock))
    assert fd is not None
    try:
        assert subprocess.run(["flock", "-n", str(lock), "true"]).returncode == 1
    finally:
        renew_token.release_lock(fd)
    assert subprocess.run(["flock", "-n", str(lock), "true"]).returncode == 0


@posix
def test_posix_bash_flock_is_excluded_for_the_whole_renewal(tmp_path, monkeypatch):
    """Both locks are held while the renewal runs, not just acquired: `flock -n` (vt's run.sh)
    fails on each of them from inside the locked section."""
    lock, store = tmp_path / "vt.lock", tmp_path / "secrets.env"
    lock.write_bytes(b"")
    store.write_bytes(f"{KEY}={_OLD_ID}\n".encode())
    args = renew_token.parse(["--agent", CANARY, "--base", "http://127.0.0.1:9", "--env-file", str(store),
                              "--env-key", KEY, "--lock-file", str(lock), "--verify-cmd", "/bin/true {new_token}"])
    renewal = renew_token.Renewal(args, None)
    seen = []

    def locked():
        seen.append([subprocess.run(["flock", "-n", str(p), "true"]).returncode
                     for p in (lock, tmp_path / ".secrets.env.renew-lock")])
        return 0

    monkeypatch.setattr(renewal, "locked", locked)
    assert renewal.run() == 0
    assert seen == [[1, 1]], seen
    assert subprocess.run(["flock", "-n", str(lock), "true"]).returncode == 0  # released afterwards


@posix
def test_posix_a_store_owned_by_another_uid_is_refused(tmp_path, monkeypatch):
    """A replaced file would belong to whoever ran the swap: vt (0600) could no longer read it."""
    store = tmp_path / "secrets.env"
    store.write_bytes(f"{KEY}={_OLD_ID}\n".encode())
    monkeypatch.setattr(renew_token.os, "geteuid", lambda: os.stat(store).st_uid + 4242)
    with pytest.raises(renew_token.Refused, match="owned by uid"):
        renew_token.Store("env-file", str(store), KEY).read()


@posix
def test_posix_the_store_mode_is_kept_across_the_atomic_replace(tmp_path):
    for mode in (0o600, 0o640):  # 0640 as well: mkstemp's own 0600 would hide a missing chmod
        path = tmp_path / f"tokens-{mode:o}.json"
        path.write_text('{"%s": "%s"}' % (CANARY, _OLD_ID))
        os.chmod(path, mode)
        store = renew_token.Store("json-file", str(path), CANARY)
        raw = path.read_bytes()
        start, end, _ = store.locate(raw)
        ok, msg = renew_token.replace_value(store, raw, start, end, _NEW_ID)
        assert ok, msg
        assert stat.S_IMODE(os.stat(path).st_mode) == mode
        assert path.read_bytes() == raw.replace(_OLD_ID.encode(), _NEW_ID.encode())


@posix
def test_posix_a_verify_timeout_kills_the_verifiers_whole_process_group(tmp_path):
    renewal = renew_token.Renewal.__new__(renew_token.Renewal)
    renewal.a = argparse.Namespace(verify_timeout=2.0)
    pid_file = tmp_path / "grandchild.pid"
    renewal.verify_argv = ["bash", "-c", f'sleep 300 & echo $! > "{pid_file}"; wait']
    rc, detail = renewal.run_verify(_NEW_ID, _OLD_ID)
    assert rc is None and detail == "timeout"
    pid = int(pid_file.read_text())
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            state = Path(f"/proc/{pid}/stat").read_text().split()[2]
        except OSError:
            break  # gone
        if state == "Z":
            break  # killed, awaiting its reaper
        time.sleep(0.1)
    else:
        pytest.fail(f"the verifier's grandchild {pid} survived the timeout")


# --- the GB10 constraint -----------------------------------------------------------------------------


def test_the_tool_imports_only_the_standard_library():
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert names - {"__future__"} <= set(sys.stdlib_module_names), names - set(sys.stdlib_module_names)
    ast.parse(TOOL.read_text(encoding="utf-8"), feature_version=(3, 12))  # the GB10's python3
