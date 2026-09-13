"""The ssl agents' token renewal on Windows: tools/renew_token.py with
tools/ssl-verify-token.ps1 as its --verify-cmd.

The ssl skills present their delegation token through tools/field-rest.ps1,
which reads it from a JSON file (agent_id -> token id) on every hook call. A
renewal is proven only when THAT client presents the new token and the estate
answers. So every renewal here runs the REAL renew_token.py (--json-file) as a
subprocess of the base interpreter (-I), against the REAL services in
estate_harness.py with the shared secret and a DOA roster armed, and
ssl-invoicing-agent provisioned from its real manifest by the real lifecycle
CLI. Its verify command is the REAL verifier under powershell.exe -File,
dot-sourcing the REAL shim. Assertions read the estate's records (token state,
ledger events), the bytes of the token file, what the shim sent, and the log.

Faults the services cannot produce on demand sit in ShimProxy, between the shim
and the estate: a kill-switch route that answers 502, a kill that lands as
verification starts, and a sentinel in log_only mode (a real
conformance-sentinel process started with FIELD_SENTINEL_MODE=log_only, not a
rewritten answer). The tool itself talks to the harness directly.

Nothing here reads C:\\Users\\donal\\.field-local or sends anything to
10.0.0.62: FIELD_TOKENS_FILE, FIELD_SECRET_FILE and FIELD_PROXY_URL always point
into tmp_path and the harness, and the manifest copy's endpoints are rewritten
to a dead local port. The few runs that need FIELD_TOKENS_FILE missing or unset
load a copy of the shim whose path literals point into tmp_path (_decoy_shim).
Skipped where Windows PowerShell does not exist.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("msvcrt", reason="Windows-only: the ssl agents' client is Windows PowerShell")
POWERSHELL = shutil.which("powershell.exe")
pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="needs Windows PowerShell (powershell.exe)")

import yaml  # noqa: E402

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
TOOL = TOOLS / "renew_token.py"
VERIFIER = TOOLS / "ssl-verify-token.ps1"
HARNESS = Path(__file__).with_name("estate_harness.py")
RUNBOOK = REPO / "docs" / "runbooks" / "token-renewal.md"
MANIFEST = REPO / "manifests" / "ssl-invoicing-agent.yaml"
sys.path.insert(0, str(TOOLS))

import renew_token  # noqa: E402  (only to locate the value in the token file)

PY = getattr(sys, "_base_executable", None) or sys.executable
AGENT = "ssl-invoicing-agent"
OTHER_AGENT = "ssl-timekeeping-agent"
OTHER_TOKEN = "5b0e7c1d-3a2f-4e6b-9c8d-1f2e3d4c5b6a"  # the other agent's member: its bytes must survive
GRANTOR = "Don Hagell, Spin State Labs"
SCOPE = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["delegation"]["scope"]
IN_SCOPE = "read timesheets"  # in the manifest, not an escalation trigger
NEVER_GRANTED = "send invoice email"  # absent from the manifest on purpose
PROBE = "token renewal verification: out-of-scope probe"
SECRET = "Zk4w9Qm2Rx7pL3vN8cT1hJ6sB5dF0gYa"  # random: none of its 8-grams occurs in a log by chance
DAY = 86400
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# --- plumbing ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http(method: str, url: str, body: object | None = None) -> tuple[int, object]:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Content-Type": "application/json", "x-field-auth": SECRET})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw, status = resp.read(), resp.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(), exc.code
    return status, (json.loads(raw) if raw else None)


def _wait_up(url: str, proc: subprocess.Popen, what: str) -> None:
    deadline = time.time() + 90
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"{what} exited early: {proc.returncode}")
        try:
            urllib.request.urlopen(urllib.request.Request(url, headers={"x-field-auth": SECRET}), timeout=2).read()
            return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"{what} did not come up")


def _safe_env(env: dict) -> dict:
    """field-rest.ps1 used to fall back to C:\\Users\\donal\\.field-local\\tokens-gb10.json when
    FIELD_TOKENS_FILE named a file that does not exist, and still does when FIELD_TOKENS_FILE is unset.
    Every PowerShell run of the real shim here must therefore name an existing token file in tmp, a secret
    file outside .field-local and a loopback estate, so no regression or mutant of the shim can reach the
    real file. Learned the hard way: a mutant verifier that loaded the real shim, in a test that had not
    written its token file, read the real one."""
    tokens, secret, proxy = env.get("FIELD_TOKENS_FILE"), env.get("FIELD_SECRET_FILE"), env.get("FIELD_PROXY_URL", "")
    assert tokens and Path(tokens).is_file() and ".field-local" not in tokens.lower(), tokens
    assert secret and ".field-local" not in secret.lower(), secret
    assert proxy.startswith("http://127.0.0.1:"), proxy
    return env


def _no_secret(out: str) -> None:
    flat = out.replace("\r", "").replace("\n", "")
    leaked = [SECRET[i:i + 8] for i in range(len(SECRET) - 7) if SECRET[i:i + 8] in flat]
    assert leaked == [], f"part of the secret was printed: {leaked}"


class ShimProxy:
    """Forwards the shim's requests to the harness, records them (with the token id each
    sentinel check presented), and injects the faults a test switches on."""

    def __init__(self, upstream: str):
        self.upstream, self.faults = upstream, {}
        self.requests: list[tuple[str, str]] = []
        self.presented: list[tuple[str, str | None]] = []  # (action, token_id) per sentinel check
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                proxy._serve(self)

            do_POST = do_GET

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def reset(self) -> None:
        self.faults.clear()
        self.requests.clear()
        self.presented.clear()

    def _reply(self, h, status: int, raw: bytes) -> None:
        h.send_response(status)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(raw)))
        h.end_headers()
        h.wfile.write(raw)

    def _serve(self, h) -> None:
        n = int(h.headers.get("Content-Length") or 0)
        body = h.rfile.read(n) if n else None
        method, path, f = h.command, h.path, self.faults
        self.requests.append((method, path))
        if f.pop("kill_on_first", None):  # a human hits the kill switch as verification starts
            status, _ = _http("POST", f"{self.upstream}/killswitch/kill/{AGENT}",
                              {"operator": GRANTOR, "reason": "renewal test: killed during verification"})
            assert status == 200, status
        upstream = self.upstream + path
        if method == "GET" and path.startswith("/killswitch/heartbeat/") and "heartbeat_status" in f:
            return self._reply(h, int(f["heartbeat_status"]), b'{"detail": "injected by the test proxy"}')
        if path.startswith("/sentinel/"):
            if method == "POST" and path == "/sentinel/check":
                req = json.loads(body)
                self.presented.append((req.get("action"), req.get("token_id")))
            if "sentinel_base" in f:  # another sentinel process answers instead
                upstream = f["sentinel_base"] + path[len("/sentinel"):]
        headers = {k: v for k, v in h.headers.items() if k.lower() in ("content-type", "accept", "x-field-auth")}
        req = urllib.request.Request(upstream, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                status, raw = resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        self._reply(h, status, raw)


LOG_ONLY_SENTINEL = r'''
import sys
import uvicorn
from conformance_sentinel.api import create_app
uvicorn.run(create_app(), host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
'''


class SslEstate:
    """armed: the shared secret and the DOA roster on (as after A2 and A3). Unarmed is the
    GB10 today (STATE.md 2026-09-13: nothing armed)."""

    def __init__(self, tmp: Path, armed: bool = True):
        data = tmp / "data"
        self.manifests = data / "manifests"
        self.manifests.mkdir(parents=True)
        self.manifest = self.manifests / f"{AGENT}.yaml"
        # The real manifest. Its kill and revocation endpoints name the GB10 estate, so the
        # copy points them at a dead local port: no test can ever send a packet there.
        self.manifest.write_text(MANIFEST.read_text(encoding="utf-8").replace("http://10.0.0.62:18080",
                                                                               "http://127.0.0.1:9"), encoding="utf-8")
        self.roster = tmp / "doa-roster.yaml"
        self.roster.write_text(json.dumps({"grantors": [{"grantor": GRANTOR, "allowed_scope": SCOPE,
                                                         "max_ttl_days": 400, "max_spend_usd": 5,
                                                         "active": True}]}), encoding="utf-8")
        self.tmp, port = tmp, _free_port()
        self.base = f"http://127.0.0.1:{port}"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_")}
        if armed:
            self.env.update(FIELD_SHARED_SECRET=SECRET, FIELD_DOA_ROSTER=str(self.roster))
        self.proc = subprocess.Popen([sys.executable, str(HARNESS), str(port), str(data)] + (["--secret"] * armed),
                                     env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.sentinel: subprocess.Popen | None = None
        _wait_up(f"{self.base}/ledger/health", self.proc, "harness")
        for prefix, var in (("registry", "FIELD_REGISTRY_URL"), ("ledger", "FIELD_LEDGER_URL"),
                            ("delegation", "FIELD_DELEGATION_URL"), ("governor", "FIELD_GOVERNOR_URL"),
                            ("killswitch", "FIELD_KILLSWITCH_URL")):
            self.env[var] = f"{self.base}/{prefix}"
        report = tmp / "provision.json"
        subprocess.run([sys.executable, "-m", "lifecycle_manager.cli", "provision", "--manifest", str(self.manifest),
                        "--owner", GRANTOR, "--domain", "finance", "--grantor", GRANTOR, "--ttl-days", "1",
                        "--manifest-ref", str(self.manifest), "--out", str(report)],
                       env=self.env, check=True, capture_output=True)
        assert UUID.fullmatch(json.loads(report.read_text())["token_id"])
        self.proxy = ShimProxy(self.base)

    def log_only_sentinel(self) -> str:
        """A second, real conformance-sentinel over the same registry, delegation authority,
        governor, ledger and manifests, in the mode a sentinel starts in by default."""
        if self.sentinel is None:
            port = _free_port()
            script = self.tmp / "log_only_sentinel.py"
            script.write_text(LOG_ONLY_SENTINEL, encoding="utf-8")
            env = dict(self.env, FIELD_SENTINEL_MODE="log_only", FIELD_MANIFEST_DIR=str(self.manifests),
                       FIELD_DATA_DIR=str(self.tmp / "sentinel-data"))
            self.sentinel = subprocess.Popen([sys.executable, str(script), str(port)], env=env,
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.sentinel_base = f"http://127.0.0.1:{port}"
            _wait_up(f"{self.sentinel_base}/health", self.sentinel, "log_only sentinel")
            assert _http("GET", f"{self.sentinel_base}/health")[1]["mode"] == "log_only"
        return self.sentinel_base

    def reset(self) -> None:
        self.proxy.reset()
        status, rec = self.get(f"/registry/agents/{AGENT}")
        assert status == 200
        if rec["status"] != "active":
            assert _http("PATCH", f"{self.base}/registry/agents/{AGENT}", {"status": "active"})[0] == 200

    def get(self, path: str) -> tuple[int, object]:
        return _http("GET", f"{self.base}{path}")

    def mint(self, ttl_seconds: int) -> str:
        status, tok = _http("POST", f"{self.base}/delegation/tokens", {"agent_id": AGENT, "granted_by": GRANTOR,
                                                                        "scope": SCOPE, "ttl_seconds": ttl_seconds})
        assert status == 201, (status, tok)
        return tok["token_id"]

    def token(self, token_id: str) -> dict:
        status, tok = self.get(f"/delegation/tokens/{token_id}")
        assert status == 200, status
        return tok

    def token_ids(self) -> set[str]:
        status, toks = self.get(f"/delegation/tokens?agent_id={AGENT}")
        assert status == 200
        return {t["token_id"] for t in toks}

    def events(self, event_type: str) -> list[dict]:
        status, evs = self.get(f"/ledger/events?event_type={event_type}&agent_id={AGENT}")
        assert status == 200
        return evs

    def close(self) -> None:
        self.proxy.server.shutdown()
        for proc in (self.sentinel, self.proc):
            if proc is not None:
                proc.terminate()
                proc.wait(timeout=20)


@pytest.fixture(scope="module")
def _estate(tmp_path_factory):
    e = SslEstate(tmp_path_factory.mktemp("ssl-renew-estate"))
    try:
        yield e
    finally:
        e.close()


@pytest.fixture()
def estate(_estate):
    _estate.reset()
    return _estate


@pytest.fixture(scope="module")
def unarmed_estate(tmp_path_factory):
    e = SslEstate(tmp_path_factory.mktemp("ssl-renew-unarmed"), armed=False)
    try:
        assert _http("GET", f"{e.base}/killswitch/heartbeat/{AGENT}")[0] == 200
        req = urllib.request.Request(f"{e.base}/delegation/tokens?agent_id={AGENT}")  # no header at all
        assert urllib.request.urlopen(req, timeout=10).status == 200, "this estate must really be unarmed"
        yield e
    finally:
        e.close()


class SslCase:
    def __init__(self, e: SslEstate, tmp: Path):
        self.e, self.tmp = e, tmp
        self.store = tmp / "tokens-gb10.json"
        self.secret_file = tmp / "gb10-estate-secret"
        self.secret_file.write_bytes(SECRET.encode() + b"\r\n")
        self.state = tmp / ".renew-token"

    def tokens_file(self, token: str, path: Path | None = None) -> bytes:
        """As provision_ssl_agents.py writes it: json.dumps(tokens, indent=2)."""
        raw = json.dumps({OTHER_AGENT: OTHER_TOKEN, AGENT: token}, indent=2).encode()
        (path or self.store).write_bytes(raw)
        return raw

    def value(self) -> str:
        return renew_token.Store("json-file", str(self.store), AGENT).locate(self.store.read_bytes())[2]

    def verify_cmd(self, agent: str = AGENT, action: str = IN_SCOPE) -> str:
        return (f'"{POWERSHELL}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{VERIFIER}" '
                f'-Agent {agent} -NewToken {{new_token}} -InScopeAction "{action}"')

    def env(self, tokens_file: Path | None = None, **extra: str) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_")}
        env.update(FIELD_SECRET_FILE=str(self.secret_file), FIELD_TOKENS_FILE=str(tokens_file or self.store),
                   FIELD_PROXY_URL=self.e.proxy.base, **extra)
        return env

    def run(self, verify: str | None = None, env: dict | None = None) -> tuple[int, str]:
        argv = [PY, "-I", str(TOOL), "--agent", AGENT, "--base", self.e.base, "--json-file", str(self.store),
                "--json-key", AGENT, "--secret-file", str(self.secret_file), "--ttl-days", "30",
                "--verify-cmd", verify or self.verify_cmd()]
        proc = subprocess.run(argv, env=_safe_env(env or self.env()), capture_output=True, timeout=300)
        out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
        _no_secret(out)
        return proc.returncode, out

    def verifier(self, *args: str, env: dict | None = None, mode: str = "-File",
                 verifier: Path = VERIFIER) -> tuple[int, str]:
        head = [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"]
        proc = subprocess.run(head + [mode, str(verifier), *args] if mode == "-File" else head + [mode, args[0]],
                              env=_safe_env(env or self.env()), capture_output=True, timeout=120,
                              stdin=subprocess.DEVNULL)
        out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
        _no_secret(out)
        return proc.returncode, out

    def journals(self) -> list[Path]:
        return list(self.state.glob("renew-*.json")) if self.state.exists() else []


@pytest.fixture()
def case(estate, tmp_path):
    return SslCase(estate, tmp_path)


def _new_since(e: SslEstate, before: set[str]) -> str:
    fresh = e.token_ids() - before
    assert len(fresh) == 1, fresh
    return fresh.pop()


def _checks(out: str) -> list[str]:
    """The verifier's PASS/FAIL lines as the tool relayed them."""
    relayed = [line.split("  verify| ", 1)[1].rstrip() for line in out.splitlines() if line.startswith("  verify| ")]
    return [line for line in relayed if line.startswith(("PASS  ", "FAIL  "))]


def _assert_restored(case: SslCase, raw: bytes, old: str, new: str, out: str, failed_before: int,
                     rc: int = 1) -> None:
    """A failed ssl verification: the token file is back byte for byte, the new token is
    revoked, the old one untouched, the failure ledgered and nothing left pending."""
    assert case.store.read_bytes() == raw, out
    assert case.e.token(new)["revoked"] is True and case.e.token(old)["revoked"] is False, out
    events = case.e.events("token.renewal_failed")
    assert len(events) == failed_before + 1, out
    assert (events[-1]["payload"]["reason"], events[-1]["payload"]["verify_rc"]) == ("verify_failed", rc), out
    assert case.journals() == [], out
    assert f"result: FAILED at verification (rc={rc}); store holds {old[:8]} (the old token)" in out, out


# --- a due renewal, proven through the skills' own client ----------------------------------------


def test_a_due_ssl_renewal_is_proven_through_the_shim_and_finished(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.tokens_file(old)
    before, renewed = e.token_ids(), len(e.events("token.renewed"))
    code, out = case.run()
    assert code == 0, out
    new = _new_since(e, before)
    new_tok = e.token(new)
    # the grant is carried forward exactly, for 30 days
    assert (new_tok["agent_id"], new_tok["granted_by"], new_tok["scope"]) == (AGENT, GRANTOR, SCOPE)
    lifetime = (renew_token.parse_ts(new_tok["expires_at"]) - renew_token.parse_ts(new_tok["issued_at"]))
    assert abs(lifetime.total_seconds() - 30 * DAY) < 5
    assert new_tok["revoked"] is False and e.token(old)["revoked"] is True
    # one member's value changed; the other agent's member and every other byte did not
    assert case.store.read_bytes() == raw.replace(old.encode(), new.encode()) and raw.count(old.encode()) == 1
    payload = e.events("token.renewed")[renewed:]
    assert [p["payload"] for p in payload] == [{"old_prefix": old[:8], "new_prefix": new[:8],
                                                "expires_at": new_tok["expires_at"], "granted_by": GRANTOR,
                                                "scope_count": len(SCOPE)}]
    # the verifier ran every check through the shim and each passed
    checks = _checks(out)
    assert len(checks) == 4, out
    assert checks[0] == f"PASS  token file {case.store} holds {new[:8]} for {AGENT} (want {new[:8]})", out
    assert checks[1].startswith(f"PASS  heartbeat: FIELD heartbeat {AGENT} killed=false status=active at="), out
    assert checks[2:] == [f"PASS  in scope: FIELD check {AGENT} '{IN_SCOPE}' -> ALLOW",
                          f"PASS  out of scope: FIELD check {AGENT} '{PROBE}' -> BLOCK D.scope"], out
    assert "  verify| RESULT PASS: 4 of 4 checks" in out and "verify: rc=0" in out
    # ...and the shim really presented the NEW token to the sentinel, both times
    assert e.proxy.presented == [(IN_SCOPE, new), (PROBE, new)]
    assert case.journals() == [] and old not in out and new not in out


# --- a verifier that cannot prove the new token: the old one is put back ---------------------------


def test_a_verifier_that_reads_another_token_file_fails_and_the_old_token_is_restored(case):
    """The Task Scheduler environment resolves the shim's token file somewhere other than
    --json-file: the skills would keep presenting the old token. Checks 2 to 4 pass on that
    old, still-active token; only the token-file check can see it."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.tokens_file(old)
    elsewhere = case.tmp / "the-shims-tokens.json"
    case.tokens_file(old, path=elsewhere)
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    code, out = case.run(env=case.env(tokens_file=elsewhere))
    assert code == 1 and "verify: rc=1" in out, out
    new = _new_since(e, before)
    assert [c for c in _checks(out) if c.startswith("FAIL")] == [
        f"FAIL  token file {elsewhere} holds {old[:8]} for {AGENT} (want {new[:8]})"], out
    assert "  verify| RESULT FAIL: 1 of 4 checks failed" in out
    _assert_restored(case, raw, old, new, out, failed)


def test_an_agent_killed_as_verification_starts_fails_and_the_old_token_is_restored(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.tokens_file(old)
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    e.proxy.faults["kill_on_first"] = True
    code, out = case.run()
    assert code == 1 and "verify: rc=1" in out, out
    new = _new_since(e, before)
    fails = [c for c in _checks(out) if c.startswith("FAIL")]
    assert fails == [f"FAIL  heartbeat: FIELD heartbeat {AGENT} killed=true status=killed -> HALT",
                     f"FAIL  in scope: FIELD check {AGENT} '{IN_SCOPE}' -> BLOCK E.kill_switch",
                     f"FAIL  out of scope: FIELD check {AGENT} '{PROBE}' -> BLOCK E.kill_switch"], out
    _assert_restored(case, raw, old, new, out, failed)


def test_an_in_scope_action_the_manifest_does_not_grant_fails_and_the_old_token_is_restored(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.tokens_file(old)
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    code, out = case.run(verify=case.verify_cmd(action=NEVER_GRANTED))
    assert code == 1 and "verify: rc=1" in out, out
    new = _new_since(e, before)
    assert [c for c in _checks(out) if c.startswith("FAIL")] == [
        f"FAIL  in scope: FIELD check {AGENT} '{NEVER_GRANTED}' -> BLOCK D.scope"], out
    _assert_restored(case, raw, old, new, out, failed)


def test_a_kill_switch_that_does_not_answer_fails_verification(case):
    """Every skill run would HALT at hook 3, whatever the token: not a proven renewal."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.tokens_file(old)
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    e.proxy.faults["heartbeat_status"] = 502
    code, out = case.run()
    assert code == 1 and "verify: rc=1" in out, out
    new = _new_since(e, before)
    fails = [c for c in _checks(out) if c.startswith("FAIL")]
    assert len(fails) == 1 and fails[0].startswith(f"FAIL  heartbeat: FIELD heartbeat {AGENT} UNREACHABLE"), out
    _assert_restored(case, raw, old, new, out, failed)


def test_a_log_only_sentinel_fails_verification(case):
    """A sentinel restarted without FIELD_SENTINEL_MODE=enforce allows everything: the new
    token's in-scope check still reads ALLOW, so only the out-of-scope probe can tell."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.tokens_file(old)
    e.proxy.faults["sentinel_base"] = e.log_only_sentinel()
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    code, out = case.run()
    assert code == 1 and "verify: rc=1" in out, out
    new = _new_since(e, before)
    assert [c for c in _checks(out) if c.startswith("FAIL")] == [
        f"FAIL  out of scope: FIELD check {AGENT} '{PROBE}' -> ALLOW shadow:D.scope"], out
    assert f"PASS  in scope: FIELD check {AGENT} '{IN_SCOPE}' -> ALLOW" in _checks(out)
    _assert_restored(case, raw, old, new, out, failed)


def test_a_log_only_client_posture_fails_verification(case):
    """The shim in log_only returns True on every BLOCK; a skill in that environment would
    never stop, so the verifier does not vouch for it."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.tokens_file(old)
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    code, out = case.run(env=case.env(FIELD_CLIENT_POSTURE="log_only"))
    assert code == 1 and "verify: rc=1" in out, out
    new = _new_since(e, before)
    assert "  verify| FAIL  client posture is 'log_only', not enforce" in out, out
    assert e.proxy.presented == []
    _assert_restored(case, raw, old, new, out, failed)


# --- exit codes: the verifier's, through powershell.exe, as the tool reads them -------------------


def test_a_malformed_agent_in_the_verify_command_exits_2_before_any_call_and_the_tool_restores(case):
    """Get-FieldToken's member lookup ignores case, so SSL-INVOICING-AGENT would read the real
    agent's token: refused before the shim makes a single call. Exit 2 survives -File, and
    the tool treats it as the failed verification it is."""
    e, old = case.e, case.e.mint(DAY)
    raw = case.tokens_file(old)
    before, failed = e.token_ids(), len(e.events("token.renewal_failed"))
    code, out = case.run(verify=case.verify_cmd(agent=AGENT.upper()))
    assert code == 1 and "verify: rc=2" in out, out
    assert "  verify| FAIL  -Agent is not a registry agent id" in out
    assert e.proxy.requests == []
    new = _new_since(e, before)
    _assert_restored(case, raw, old, new, out, failed, rc=2)


def test_a_malformed_new_token_exits_2_before_any_call(case):
    token = case.e.mint(DAY)
    case.tokens_file(token)
    for bad in (token.upper(), "{new_token}", token[:-1] + "g"):
        code, out = case.verifier("-Agent", AGENT, "-NewToken", bad, "-InScopeAction", IN_SCOPE)
        assert code == 2 and "FAIL  -NewToken is not a lowercase uuid (value not shown)" in out, (bad, out)
    assert case.e.proxy.requests == []


def _code_lines(source: str) -> str:
    return "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))


def _decoy_shim(tmp: Path, real_tokens: Path, home: Path) -> Path:
    """A copy of the REAL shim whose only change is its path literals (the rog-command token file
    becomes `real_tokens`, the $HOME default `home`, the default secret file a tmp path), so a run
    whose FIELD_TOKENS_FILE is missing or unset can never reach C:\\Users\\donal\\.field-local."""
    source = (TOOLS / "field-rest.ps1").read_text(encoding="utf-8")
    swaps = {r"C:\Users\donal\.field-local\tokens-gb10.json": str(real_tokens),
             r"C:\Users\donal\.field-local\gb10-estate-secret": str(tmp / "decoy-default-secret"),
             r"Join-Path $HOME '.field-local\tokens-gb10.json'": f"Join-Path '{home}' 'tokens-gb10.json'"}
    for old, new in swaps.items():
        assert old in source, old
        source = source.replace(old, new)
    code = _code_lines(source).lower()
    assert ".field-local" not in code and "$home" not in code, "the decoy still names a real path"
    path = tmp / "decoy-shim" / "field-rest.ps1"
    path.parent.mkdir(exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _verifier_on_decoy(case: SslCase, shim: Path, env: dict, *args: str) -> tuple[int, str]:
    """_safe_env's rule, for the runs that need FIELD_TOKENS_FILE missing or unset: only a decoy shim."""
    assert ".field-local" not in _code_lines(shim.read_text(encoding="utf-8")).lower()
    assert ".field-local" not in _code_lines(VERIFIER.read_text(encoding="utf-8")).lower()
    tokens = env.get("FIELD_TOKENS_FILE")
    assert tokens is None or Path(tokens).is_relative_to(case.tmp), tokens
    assert Path(env["FIELD_SECRET_FILE"]).is_relative_to(case.tmp) and env["FIELD_PROXY_URL"].startswith("http://127.0.0.1:")
    head = [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(VERIFIER)]
    proc = subprocess.run(head + [*args, "-ShimPath", str(shim)], env=env, capture_output=True, timeout=120,
                          stdin=subprocess.DEVNULL)
    out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    _no_secret(out)
    return proc.returncode, out


@pytest.mark.parametrize("shim_reads", ["a FIELD_TOKENS_FILE that does not exist", "another existing file",
                                        "its default (no FIELD_TOKENS_FILE)", "the same file spelled in another case",
                                        "the same file"])
def test_the_verifier_makes_no_call_unless_the_shim_reads_exactly_the_tokens_file(case, shim_reads):
    """-TokensFile is the file the renewal swapped. A shim that resolved its token file anywhere else
    could present another file's token (the real one, before the shim's fallback was removed) to
    FIELD_PROXY_URL: refused before any call, even when that other file holds the same token."""
    e, token = case.e, case.e.mint(DAY)
    case.tokens_file(token)
    real = case.tmp / "decoy-real-tokens.json"  # stands in for the rog-command file the shim falls back to
    case.tokens_file(token, path=real)
    shim = _decoy_shim(case.tmp, real, home=case.tmp / "decoy-home")
    env = case.env()
    if shim_reads == "a FIELD_TOKENS_FILE that does not exist":
        env["FIELD_TOKENS_FILE"] = expected = str(case.tmp / "tokens-typo.json")
    elif shim_reads == "another existing file":
        env["FIELD_TOKENS_FILE"] = expected = str(case.tmp / "another-tokens.json")
        case.tokens_file(token, path=Path(expected))
    elif shim_reads == "its default (no FIELD_TOKENS_FILE)":
        del env["FIELD_TOKENS_FILE"]
        expected = str(real)
    elif shim_reads == "the same file spelled in another case":  # the runbook promises an exact comparison
        env["FIELD_TOKENS_FILE"] = expected = str(case.store).swapcase()
        assert Path(expected).is_file()  # one file on Windows, two spellings
    code, out = _verifier_on_decoy(case, shim, env, "-Agent", AGENT, "-TokensFile", str(case.store),
                                   "-NewToken", token, "-InScopeAction", IN_SCOPE)
    if shim_reads == "the same file":
        assert code == 0 and "RESULT PASS: 4 of 4 checks" in out, out
        assert e.proxy.presented == [(IN_SCOPE, token), (PROBE, token)]
        return
    assert code == 1, out
    assert (f"FAIL  the shim reads its token file from '{expected}', not -TokensFile '{case.store}': "
            "no call made") in out, out
    assert "PASS" not in out and e.proxy.requests == []


def test_the_verifier_refuses_a_tokens_file_that_does_not_exist_before_it_loads_the_shim(case):
    e = case.e
    missing = case.tmp / "never-swapped.json"
    real = case.tmp / "decoy-real-tokens.json"
    case.tokens_file(e.mint(DAY), path=real)
    shim = _decoy_shim(case.tmp, real, home=case.tmp / "decoy-home")
    env = case.env()
    env["FIELD_TOKENS_FILE"] = str(missing)  # the same path: only the existence rule can refuse
    code, out = _verifier_on_decoy(case, shim, env, "-Agent", AGENT, "-TokensFile", str(missing),
                                   "-NewToken", "0f1e2d3c-4b5a-4968-8778-695a4b3c2d1e", "-InScopeAction", IN_SCOPE)
    assert code == 1, out
    assert f"FAIL  -TokensFile '{missing}' is not an existing file: shim not loaded, no call made" in out, out
    assert "FIELD shim loaded" not in out and e.proxy.requests == []


def test_the_verifier_without_its_shim_fails_with_exit_1(case):
    case.tokens_file(case.e.mint(DAY))
    missing = case.tmp / "no-such-dir" / "field-rest.ps1"
    code, out = case.verifier("-Agent", AGENT, "-NewToken", case.value(), "-InScopeAction", IN_SCOPE,
                              "-ShimPath", str(missing))
    assert code == 1 and f"FAIL  shim not found: {missing}" in out, out


FAKE_SHIM = r'''
Write-Output 'FIELD fake shim beside the verifier loaded'
$script:FieldPosture = 'enforce'
$script:FieldTokens = 'fake-tokens.json'
function Get-FieldToken([string]$Agent) { return $env:FAKE_TOKEN }
function Get-FieldHeartbeat { param([string]$Agent) Write-Output "FIELD heartbeat $Agent killed=false status=active at=now"; return $true }
function Invoke-FieldCheck {
    param([string]$Agent, [string]$Action)
    if ($Action -like 'token renewal verification*') { Write-Output "FIELD check $Agent '$Action' -> BLOCK D.scope"; return $false }
    Write-Output "FIELD check $Agent '$Action' -> ALLOW "; return $true
}
'''


def test_the_default_shim_is_the_one_beside_the_verifier_not_a_fixed_path(case, tmp_path):
    """Installed anywhere, the verifier proves the shim installed beside it ($PSScriptRoot)."""
    folder = tmp_path / "installed here"
    folder.mkdir()
    shutil.copyfile(VERIFIER, folder / VERIFIER.name)
    (folder / "field-rest.ps1").write_text(FAKE_SHIM, encoding="utf-8")
    token = "0f1e2d3c-4b5a-4968-8778-695a4b3c2d1e"
    case.tokens_file(token)  # not read by the fake shim; there so that no shim ever falls back to the real file
    code, out = case.verifier("-Agent", AGENT, "-NewToken", token, "-InScopeAction", IN_SCOPE,
                              env=dict(case.env(), FAKE_TOKEN=token), verifier=folder / VERIFIER.name)
    assert code == 0 and "FIELD fake shim beside the verifier loaded" in out and "RESULT PASS: 4 of 4" in out, out
    assert case.e.proxy.requests == []


def test_powershell_file_keeps_the_verifiers_exit_code_and_command_does_not(case):
    """Why the runbook says -File: under -Command a failed verification reads 1, or 0 when any
    statement follows the script, which the tool would take as a proven token."""
    token = case.e.mint(DAY)
    case.tokens_file(token)
    args = ("-Agent", AGENT, "-NewToken", token.upper(), "-InScopeAction", IN_SCOPE)
    assert case.verifier(*args)[0] == 2
    call = f"& '{VERIFIER}' -Agent {AGENT} -NewToken {token.upper()} -InScopeAction '{IN_SCOPE}'"
    assert case.verifier(call, mode="-Command")[0] == 1
    assert case.verifier(call + "; 'the next statement'", mode="-Command")[0] == 0


# --- the runbook's own command, exactly as Task Scheduler will run it ----------------------------

CMD = r"C:\Windows\System32\cmd.exe"
RUNBOOK_PATHS = {  # what the runbook names on rog-command -> what a test may touch instead
    "python": r"C:\Users\donal\AppData\Local\Python\pythoncore-3.14-64\python.exe",
    "tool": r"C:\Users\donal\.field-local\renewal\renew_token.py",
    "store": r"C:\Users\donal\.field-local\tokens-gb10.json",
    "secret": r"C:\Users\donal\.field-local\gb10-estate-secret",
    "repo": r"C:\Users\donal\My Drive\Spin State Labs\Projects\FORCE-FIELD\field-platform",
    "base": "http://10.0.0.62:18080",
}
HOLDER = r'''
import msvcrt, os, sys, time
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
open(sys.argv[2], "w").write("held")
time.sleep(300)
'''


def _runbook_section_5() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    return text[text.index("## 5. Install for the ssl agents"):text.index("## 6. Evidence")]


def _runbook_task_command() -> tuple[str, list[tuple[str, str, str, str]], list[str]]:
    section = _runbook_section_5()
    templates = re.findall(r"^\$template = '(.*)'$", section, flags=re.M)
    assert len(templates) == 1, templates
    rows = re.findall(r"@\{ Agent = '([^']+)'; Action = '([^']+)'; Within = '(\d+)'; At = '(\d\d:\d\d)' \}", section)
    secrets = re.findall(r"^\$secret = '(.*)'$", section, flags=re.M)
    chain = ("$arguments = $template.Replace('{agent}', $t.Agent).Replace('{action}', $t.Action)"
             ".Replace('{within}', $t.Within).Replace('{secret}', $secret)")
    assert section.count(chain) == 2, "the dry run and the registration must build the same arguments"
    return templates[0], rows, secrets


def _task_arguments(row: tuple[str, str, str, str], secret_flag: str, **test_paths: str) -> str:
    template = _runbook_task_command()[0]
    agent, action, within, _ = row
    args = template.replace("{agent}", agent).replace("{action}", action).replace("{within}", within)
    args = args.replace("{secret}", secret_flag)
    log = rf"C:\Users\donal\.field-local\renewal\logs\token-renewal-{agent}.log"
    assert log in args
    args = args.replace(log, test_paths.pop("log"))
    for key in ("tool", "store", "secret", "python", "repo", "base"):  # the log and the tool before the store
        if key in test_paths:
            assert RUNBOOK_PATHS[key] in args, key
            args = args.replace(RUNBOOK_PATHS[key], test_paths[key])
    assert ".field-local" not in args and "10.0.0.62" not in args, "a test must never touch the real paths"
    return args


def _run_task(args: str, env: dict, cwd: Path) -> subprocess.CompletedProcess:
    """CreateProcess with the command line Task Scheduler builds: the program, then -Argument verbatim."""
    return subprocess.run(f'"{CMD}" {args}', env=_safe_env(env), cwd=cwd, capture_output=True, timeout=300)


def _invoicing_row() -> tuple[str, str, str, str]:
    rows = [r for r in _runbook_task_command()[1] if r[0] == AGENT]
    assert len(rows) == 1
    return rows[0]


def test_the_runbook_task_table_names_granted_non_escalating_actions_one_day_apart():
    template, rows, secrets = _runbook_task_command()
    assert [r[0] for r in rows] == [OTHER_AGENT, AGENT]
    for agent, action, within, at in rows:
        manifest = yaml.safe_load((REPO / "manifests" / f"{agent}.yaml").read_text(encoding="utf-8"))
        assert action in manifest["delegation"]["scope"], (agent, action)
        triggers = manifest["enforcement"].get("escalation_triggers") or []
        assert not [t for t in triggers if t.lower() in action.lower() or action.lower() in t.lower()], (agent, action)
        assert PROBE not in manifest["delegation"]["scope"]
    assert sorted(int(r[2]) for r in rows) == [9, 10]  # first due runs one day apart, both before 2026-10-01
    minutes = sorted(int(r[3][:2]) * 60 + int(r[3][3:]) for r in rows)
    assert minutes[1] - minutes[0] >= 15
    assert secrets == ["", ' --secret-file "C:\\Users\\donal\\.field-local\\gb10-estate-secret"']
    for placeholder in ("{agent}", "{action}", "{within}", "{secret}", "{new_token}"):
        assert placeholder in template


def test_the_runbook_task_command_gives_the_verifier_the_json_file_as_its_tokens_file():
    template = _runbook_task_command()[0]
    assert re.findall(r'--json-file "([^"]+)"', template) == [RUNBOOK_PATHS["store"]], template
    assert re.findall(r'-TokensFile \\"(.+?)\\"', template) == [RUNBOOK_PATHS["store"]], template


def test_the_pinned_files_check_out_with_lf_line_endings_whatever_core_autocrlf_says():
    """The runbook's sha256 pins are for LF bytes. rog-command has core.autocrlf=true, so without an
    eol attribute any checkout, stash or fresh clone rewrites these files with CRLF and every pin
    (and the install steps that STOP on them) breaks."""
    git = shutil.which("git")
    names = ["tools/renew_token.py", "tools/ssl-verify-token.ps1", "tools/field-rest.ps1"]
    if git is None or subprocess.run([git, "rev-parse", "--is-inside-work-tree"], cwd=REPO,
                                     capture_output=True).returncode != 0:
        pytest.skip("not a git work tree")
    out = subprocess.run([git, "check-attr", "eol", "--", *names], cwd=REPO, capture_output=True, text=True,
                         check=True).stdout
    assert out.splitlines() == [f"{name}: eol: lf" for name in names], out
    assert [name for name in names if b"\r" in (REPO / name).read_bytes()] == []
    assert "pins are for the files' LF bytes" in RUNBOOK.read_text(encoding="utf-8")


def test_the_runbook_pins_the_files_that_were_tested():
    """Every full sha256 on a runbook line naming one of these files is that file's sha256 now."""
    digests = {name: hashlib.sha256((TOOLS / name).read_bytes()).hexdigest()
               for name in ("renew_token.py", "ssl-verify-token.ps1", "field-rest.ps1")}
    seen = dict.fromkeys(digests, 0)
    for number, line in enumerate(RUNBOOK.read_text(encoding="utf-8").splitlines(), 1):
        named = [name for name in digests if name in line]
        pins = re.findall(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", line)
        if pins and named:
            assert len(named) == 1, f"line {number} names {named} beside a pin: one file per pinned line"
            assert pins == [digests[named[0]]] * len(pins), f"line {number} pins {named[0]} as {pins[0][:12]}..."
            seen[named[0]] += 1
    assert all(seen.values()), seen


def test_the_runbook_task_command_renews_through_cmd_exe_against_todays_unarmed_estate(unarmed_estate, tmp_path):
    e = unarmed_estate
    e.reset()
    case = SslCase(e, tmp_path)
    old = e.mint(DAY)
    raw = case.tokens_file(old)
    log = tmp_path / "renewal" / "logs" / f"token-renewal-{AGENT}.log"
    log.parent.mkdir(parents=True)
    args = _task_arguments(_invoicing_row(), "", log=str(log), tool=str(TOOL), store=str(case.store), python=PY,
                           repo=str(REPO), base=e.base)
    env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_")}
    env.update(FIELD_TOKENS_FILE=str(case.store), FIELD_SECRET_FILE=str(tmp_path / "no-secret-file-before-a2"),
               FIELD_PROXY_URL=e.proxy.base)
    before = e.token_ids()
    proc = _run_task(args, env, tmp_path)
    text = log.read_text(encoding="ascii")
    assert proc.returncode == 0 and proc.stdout == b"" and proc.stderr == b"", (proc, text)
    new = _new_since(e, before)
    assert text.startswith("renew_token 1.5 ") and f"result: renewed {old[:8]} -> {new[:8]}" in text, text
    assert "auth=none" in text and "  verify| RESULT PASS: 4 of 4 checks" in text, text
    assert case.store.read_bytes() == raw.replace(old.encode(), new.encode())
    assert e.token(old)["revoked"] is True and e.token(new)["revoked"] is False
    assert e.proxy.presented == [(IN_SCOPE, new), (PROBE, new)]
    # the other task's renewal holds the store lock: a visible skip, and exit 3 through cmd.exe
    ready = tmp_path / "holder.ready"
    (tmp_path / "holder.py").write_text(HOLDER, encoding="utf-8")
    holder = subprocess.Popen([PY, "-I", str(tmp_path / "holder.py"),
                               str(tmp_path / ".tokens-gb10.json.renew-lock"), str(ready)])
    try:
        deadline = time.time() + 30
        while not ready.exists():
            assert holder.poll() is None and time.time() < deadline, "lock holder did not start"
            time.sleep(0.05)
        proc = _run_task(args, env, tmp_path)
    finally:
        holder.kill()
        holder.wait(timeout=20)
    assert proc.returncode == 3, proc
    assert log.read_text(encoding="ascii").splitlines()[-1].startswith("skipped: lock held ("), log.read_text()


def test_the_runbook_task_command_with_the_a2_secret_renews_against_an_armed_estate(case):
    e, old = case.e, case.e.mint(DAY)
    raw = case.tokens_file(old)
    log = case.tmp / "renewal" / "logs" / f"token-renewal-{AGENT}.log"
    log.parent.mkdir(parents=True)
    a2_secret = _runbook_task_command()[2][1]
    args = _task_arguments(_invoicing_row(), a2_secret, log=str(log), tool=str(TOOL), store=str(case.store),
                           secret=str(case.secret_file), python=PY, repo=str(REPO), base=e.base)
    before = e.token_ids()
    proc = _run_task(args, case.env(), case.tmp)
    text = log.read_text(encoding="ascii")
    _no_secret(text)
    assert proc.returncode == 0, (proc, text)
    new = _new_since(e, before)
    assert "auth=file" in text and f"result: renewed {old[:8]} -> {new[:8]}" in text, text
    assert case.store.read_bytes() == raw.replace(old.encode(), new.encode()) and e.token(old)["revoked"] is True
