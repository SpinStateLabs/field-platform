"""Phase G C-13: DOA roster rows with job ids as grantors; the jobs mint as themselves.

Design v0.4 section 2.2.1 (+ amendment P22) and 9.5 C-13 (RT1-4). A job identity
holds `mint, revoke` (renewal) or `register, caps, mint, revoke` (self-agent
provisioning) and NO `mint_for_others`, so under ENFORCE the delegation
authority accepts a mint from it only with `granted_by` equal to its own id
(operator_auth.check_granted_by). With the DOA roster armed, that id must then
be a roster row whose allowed_scope covers the agent's scope.

These tests run the REAL services (estate_harness.py) with the shared secret
armed, the DOA roster armed with a copy of manifests/doa-roster.example.yaml,
VERBATIM (the job rows were folded into it from the former companion
doa-roster.jobs.example.yaml, R2-04, so the rows the example ships are the rows
that are proven), and the operator
registry armed in ENFORCE with the job rows of design 2.2.1. They assert on the
estate's own records (token rows, ledger events) and on what crossed the wire.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

import harness_wait  # tools/tests is on sys.path

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
TOOL = TOOLS / "renew_token.py"
HARNESS = Path(__file__).with_name("estate_harness.py")
ROSTER = REPO / "manifests" / "doa-roster.example.yaml"
#: the former companion file; its rows now live in ROSTER (R2-04)
JOBS_ROSTER = REPO / "manifests" / "doa-roster.jobs.example.yaml"
PY = getattr(sys, "_base_executable", None) or sys.executable

SECRET = "c13-test-perimeter-secret-never-printed"
#: throwaway test keys generated for this file; only their sha256 goes in the registry
KEYS = {
    "don": "test-c13-don-key-NEVER-PRINT-0123456789",
    "job-provision-gb10": "test-c13-provision-key-NEVER-PRINT-01234",
    "job-renewal-gb10": "test-c13-renewal-gb10-key-NEVER-PRINT-0123",
    "job-renewal-rog": "test-c13-RR-key-NEVER-PRINT-0123456789zzzz",
}
SCOPES = {  # design 2.2.1 (v0.4) + P22: no job row holds mint_for_others
    # C-805: the verifier's full set (kill, revive, revoke + mint) under a non-verifier id is refused at load; this
    # fixture never revives, so don stops one scope short (the explicit list keeps the old register behaviour)
    "don": ["kill", "drill", "attest", "mint", "mint_for_others", "revoke", "register", "caps", "escalation"],
    "job-provision-gb10": ["register", "caps", "mint", "revoke"],
    "job-renewal-gb10": ["mint", "revoke"],
    "job-renewal-rog": ["mint", "revoke"],
}
DON = "Don Hagell, Spin State Labs"
SSL = ("ssl-timekeeping-agent", "ssl-invoicing-agent")
SELF_AGENTS = ("conformance-sentinel", "force-gateway", "compliance-crosswalk")
DAY = 86400


def _manifest(agent: str) -> dict:
    return yaml.safe_load((REPO / "manifests" / f"{agent}.yaml").read_text(encoding="utf-8"))


def _union(agents) -> list[str]:
    out: list[str] = []
    for a in agents:
        for s in _manifest(a)["delegation"]["scope"]:
            if s not in out:
                out.append(s)
    return out


# -- the roster rows (static) ------------------------------------------------------------


def _merged() -> str:
    """The estate's roster: the example, verbatim (the job rows are folded into it)."""
    return ROSTER.read_text(encoding="utf-8")


def _rows(tmp_path) -> dict[str, dict]:
    from delegation_authority.doa import load_roster

    assert [r.grantor for r in load_roster(ROSTER).grantors
            if r.grantor.startswith("job-")] == ["job-provision-gb10", "job-renewal-rog"]
    merged = tmp_path / "merged.yaml"
    merged.write_text(_merged(), encoding="utf-8")
    grantors = [r.grantor for r in load_roster(merged).grantors]
    assert len(grantors) == len(set(grantors)), grantors  # find() takes the first: no duplicates
    return {r.grantor: r.model_dump() for r in load_roster(merged).grantors}


def test_the_job_roster_loads_merges_and_carries_exactly_the_job_scopes(tmp_path):
    rows = _rows(tmp_path)
    assert rows["Don Hagell, Spin State Labs"]["max_ttl_days"] == 30  # the example's row is unchanged
    assert rows["job-provision-gb10"]["allowed_scope"] == _union(SELF_AGENTS)
    assert rows["job-renewal-rog"]["allowed_scope"] == _union(SSL)
    for job in ("job-provision-gb10", "job-renewal-rog"):
        assert rows[job]["max_ttl_days"] == 31 and rows[job]["active"] is True, rows[job]
        assert rows[job]["max_spend_usd"] is None
    # job-renewal-gb10 renews volatility-trader, whose manifest is not in this repository:
    # the example names the row in a comment and does not invent its scopes.
    assert "job-renewal-gb10" not in rows
    text = ROSTER.read_text(encoding="utf-8")
    assert "# - grantor: job-renewal-gb10" in text and "volatility-trader" in text
    assert not JOBS_ROSTER.exists()  # one file holds the rows: no companion to drift from it


# -- a real estate, ENFORCE, roster armed with the example --------------------------------


def _http(method: str, url: str, body=None, headers: dict | None = None):
    h = {"Content-Type": "application/json", "x-field-auth": SECRET, **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw, status = resp.read(), resp.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(), exc.code
    return status, (json.loads(raw) if raw else None)


class Recording:
    """Forwards to the harness; records (method, path, carried x-field-operator, carried key)."""

    def __init__(self, upstream: int):
        self.seen: list[tuple[str, str, str | None, bool]] = []
        rec = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _fwd(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else None
                rec.seen.append((self.command, self.path.split("?")[0], self.headers.get("x-field-operator"),
                                 bool(self.headers.get("x-field-operator-key"))))
                conn = http.client.HTTPConnection("127.0.0.1", upstream, timeout=60)
                hdrs = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "connection")}
                conn.request(self.command, self.path, body=body, headers=hdrs)
                resp = conn.getresponse()
                raw = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.getheader("Content-Type") or "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                conn.close()

            do_GET = do_POST = do_PUT = do_PATCH = _fwd

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"


@harness_wait.kills_proc_on_init_failure
class JobEstate:
    def __init__(self, tmp: Path):
        data = tmp / "data"
        (data / "manifests").mkdir(parents=True)
        for agent in SSL + SELF_AGENTS:
            shutil.copy(REPO / "manifests" / f"{agent}.yaml", data / "manifests" / f"{agent}.yaml")
        self.manifests = data / "manifests"
        self.roster = tmp / "doa-roster.yaml"
        self.roster.write_text(_merged(), encoding="utf-8")
        self.ops = tmp / "operators.json"
        self.ops.write_text(json.dumps([
            {"operator_id": oid, "key_sha256": hashlib.sha256(key.encode()).hexdigest(), "status": "active",
             "created_at": "2026-10-26T00:00:00+00:00", "scopes": SCOPES[oid],
             "names": ["Don Hagell", DON] if oid == "don" else []}
            for oid, key in KEYS.items()]), encoding="utf-8")
        self.key_files = {}
        for oid, key in KEYS.items():
            p = tmp / f"{oid}.key"
            p.write_text(key + "\n", encoding="utf-8")
            self.key_files[oid] = p
        sock = __import__("socket").socket()
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        sock.close()
        self.base = f"http://127.0.0.1:{self.port}"
        env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_")}
        env.update(FIELD_SHARED_SECRET=SECRET, FIELD_DOA_ROSTER=str(self.roster))
        self.env = env
        wait = harness_wait.harness_wait(90)
        self.proc = subprocess.Popen([sys.executable, str(HARNESS), str(self.port), str(data), "--secret"],
                                     env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + wait
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
        self.proxy = Recording(self.port)

    def arm(self, mode: str) -> None:
        env = {"FIELD_OPERATOR_REGISTRY": None, "FIELD_OPERATOR_REQUIRE": None}
        if mode != "off":
            env["FIELD_OPERATOR_REGISTRY"] = str(self.ops)
        if mode == "enforce":
            env["FIELD_OPERATOR_REQUIRE"] = "1"
        status, _ = _http("POST", f"{self.base}/__operator", {"env": env})
        assert status == 200

    def cli_env(self) -> dict[str, str]:
        env = dict(self.env)
        for prefix, var in (("registry", "FIELD_REGISTRY_URL"), ("ledger", "FIELD_LEDGER_URL"),
                            ("delegation", "FIELD_DELEGATION_URL"), ("governor", "FIELD_GOVERNOR_URL"),
                            ("killswitch", "FIELD_KILLSWITCH_URL")):
            env[var] = f"{self.proxy.base}/{prefix}"
        env.pop("FIELD_DOA_ROSTER", None)
        return env

    def provision(self, agent: str, *extra: str, out: Path) -> subprocess.CompletedProcess:
        ref = str(self.manifests / f"{agent}.yaml")
        return subprocess.run(
            [sys.executable, "-m", "lifecycle_manager.cli", "provision", "--manifest", ref,
             "--owner", DON, "--domain", "platform" if agent in SELF_AGENTS else "finance",
             "--ttl-days", "1", "--manifest-ref", ref, "--out", str(out), *extra],
            env=self.cli_env(), capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180)

    def token(self, token_id: str) -> dict:
        status, tok = _http("GET", f"{self.base}/delegation/tokens/{token_id}")
        assert status == 200, status
        return tok

    def events(self, event_type: str, agent: str) -> list[dict]:
        status, evs = _http("GET", f"{self.base}/ledger/events?event_type={event_type}&agent_id={agent}")
        assert status == 200
        return evs

    def close(self) -> None:
        self.proxy.server.shutdown()
        self.proc.terminate()
        self.proc.wait(timeout=20)


@pytest.fixture(scope="module")
def est(tmp_path_factory):
    e = JobEstate(tmp_path_factory.mktemp("c13"))
    try:
        e.arm("off")
        # ssl-timekeeping-agent provisioned as today (mode off, grantor = Don's display name, a roster row)
        out = tmp_path_factory.mktemp("c13-setup") / "ssl.json"
        proc = e.provision("ssl-timekeeping-agent", "--grantor", DON, out=out)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        e.arm("enforce")
        yield e
    finally:
        e.arm("off")
        e.close()


def _assert_no_key(text: str) -> None:
    for key in KEYS.values():
        assert key not in text, "an operator key was printed"
    assert SECRET not in text


def test_provision_as_job_provision_gb10_mints_granted_by_its_own_id_under_enforce(est, tmp_path):
    est.proxy.seen.clear()
    out = tmp_path / "cs.json"
    proc = est.provision("conformance-sentinel", "--operator-id", "job-provision-gb10",
                         "--operator-key-file", str(est.key_files["job-provision-gb10"]), out=out)
    _assert_no_key(proc.stdout + proc.stderr)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(out.read_text())
    tok = est.token(report["token_id"])
    assert tok["granted_by"] == "job-provision-gb10"
    assert tok["scope"] == _manifest("conformance-sentinel")["delegation"]["scope"]
    mint = [e for e in est.events("delegation.mint", "conformance-sentinel")
            if e["payload"].get("token_id") == report["token_id"]]
    assert len(mint) == 1 and mint[0]["payload"]["doa_row"]["grantor"] == "job-provision-gb10", mint
    # the pair crossed the wire only on guarded writes
    keyed = {(m, p) for m, p, op, key in est.proxy.seen if op or key}
    assert keyed and all(op == "job-provision-gb10" for m, p, op, key in est.proxy.seen if op)
    assert keyed <= {("POST", "/registry/agents"), ("PUT", "/governor/caps/conformance-sentinel"),
                     ("PUT", "/governor/rate-limits/conformance-sentinel"), ("POST", "/delegation/tokens")}
    assert ("POST", "/delegation/tokens") in keyed and ("POST", "/registry/agents") in keyed
    assert not any(op or key for m, p, op, key in est.proxy.seen if m == "GET" or p.endswith("/events"))


def test_provision_as_a_job_naming_another_grantor_is_refused_under_enforce(est, tmp_path):
    """Why the default matters: the job row has no mint_for_others, so a display-name
    grantor is refused at the mint (403), and nothing is minted."""
    proc = est.provision("force-gateway", "--grantor", "Founder & CTO, Spin State Labs", "--operator-id",
                         "job-provision-gb10", "--operator-key-file", str(est.key_files["job-provision-gb10"]),
                         out=tmp_path / "fg.json")
    _assert_no_key(proc.stdout + proc.stderr)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    report = json.loads((tmp_path / "fg.json").read_text())
    mint = [s for s in report["steps"] if s["step"] == "mint"]
    assert mint and mint[0]["outcome"] == "failed" and mint[0]["http_status"] == 403, report["steps"]


VERIFY = "import sys; sys.exit(0 if len(sys.argv) > 1 and len(sys.argv[1]) == 36 else 5)\n"


def _renew(est: JobEstate, tmp: Path, store: Path, *op: str) -> tuple[int, str]:
    verifier = tmp / "verify.py"
    verifier.write_text(VERIFY, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_")}
    env["FIELD_SHARED_SECRET"] = SECRET
    proc = subprocess.run(
        [PY, "-I", str(TOOL), "--agent", "ssl-timekeeping-agent", "--base", est.proxy.base,
         "--json-file", str(store), "--json-key", "ssl-timekeeping-agent", "--state-dir", str(tmp / "state"),
         "--renew-within-days", "7", "--verify-cmd", f'"{PY}" -I "{verifier}" {{new_token}}', *op],
        env=env, capture_output=True, timeout=240)
    out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    _assert_no_key(out)
    return proc.returncode, out


def _don_token(est: JobEstate) -> str:
    """A 1-day token for the ssl agent, minted by don (display-name grantor, mint_for_others)."""
    status, tok = _http("POST", f"{est.base}/delegation/tokens",
                        {"agent_id": "ssl-timekeeping-agent", "granted_by": DON,
                         "scope": _manifest("ssl-timekeeping-agent")["delegation"]["scope"], "ttl_seconds": DAY},
                        headers={"x-field-operator": "don", "x-field-operator-key": KEYS["don"]})
    assert status == 201, (status, tok)
    return tok["token_id"]


def test_renewal_as_job_renewal_rog_mints_as_itself_and_records_the_one_time_grantor_change(est, tmp_path):
    old = _don_token(est)
    store = tmp_path / "tokens-gb10.json"
    store.write_text(json.dumps({"ssl-timekeeping-agent": old}, indent=2), encoding="utf-8")
    est.proxy.seen.clear()
    renewed_before = len(est.events("token.renewed", "ssl-timekeeping-agent"))
    code, out = _renew(est, tmp_path, store, "--operator-id", "job-renewal-rog", "--operator-key-file",
                       str(est.key_files["job-renewal-rog"]))
    assert code == 0, out
    assert f"grant: granted_by {DON!r} -> 'job-renewal-rog'" in out, out
    new = json.loads(store.read_text())["ssl-timekeeping-agent"]
    new_tok, old_tok = est.token(new), est.token(old)
    assert new_tok["granted_by"] == "job-renewal-rog"
    assert new_tok["scope"] == old_tok["scope"]
    assert old_tok["revoked"] is True and new_tok["revoked"] is False
    events = est.events("token.renewed", "ssl-timekeeping-agent")
    assert len(events) == renewed_before + 1
    payload = events[-1]["payload"]
    assert payload["granted_by"] == "job-renewal-rog" and payload["granted_by_changed_from"] == DON, payload
    keyed = [(m, p) for m, p, op, key in est.proxy.seen if op or key]
    assert keyed == [("POST", "/delegation/tokens"), ("POST", f"/delegation/tokens/{old}/revoke")], est.proxy.seen
    assert all(op == "job-renewal-rog" for m, p, op, key in est.proxy.seen if op)

    # the next renewal carries the job grantor forward: no change recorded again
    status, _ = _http("POST", f"{est.base}/delegation/tokens/{new}/revoke",
                      headers={"x-field-operator": "don", "x-field-operator-key": KEYS["don"]})
    assert status == 200
    code, out = _renew(est, tmp_path, store, "--renew-revoked", "--operator-id", "job-renewal-rog",
                       "--operator-key-file", str(est.key_files["job-renewal-rog"]))
    assert code == 0, out
    assert "grant: granted_by" not in out
    payload = est.events("token.renewed", "ssl-timekeeping-agent")[-1]["payload"]
    assert payload["granted_by"] == "job-renewal-rog" and "granted_by_changed_from" not in payload, payload


def test_renewal_without_an_identity_is_refused_under_enforce_and_changes_nothing(est, tmp_path):
    old = _don_token(est)
    store = tmp_path / "tokens-gb10.json"
    raw = json.dumps({"ssl-timekeeping-agent": old}, indent=2).encode()
    store.write_bytes(raw)
    code, out = _renew(est, tmp_path, store)
    assert code == 1, out
    assert "mint: FAILED (HTTP 401" in out, out
    assert store.read_bytes() == raw and est.token(old)["revoked"] is False


def test_renewal_as_a_job_outside_its_roster_scope_is_refused_by_the_doa_gate(est, tmp_path):
    """job-renewal-gb10 has no row in the example (volatility-trader's scopes are not in
    this repository), so the armed roster refuses its mint: D.grantor, nothing changed."""
    old = _don_token(est)
    store = tmp_path / "tokens-gb10.json"
    raw = json.dumps({"ssl-timekeeping-agent": old}, indent=2).encode()
    store.write_bytes(raw)
    code, out = _renew(est, tmp_path, store, "--operator-id", "job-renewal-gb10", "--operator-key-file",
                       str(est.key_files["job-renewal-gb10"]))
    assert code == 1, out
    assert "mint: FAILED (HTTP 403" in out and "D.grantor" in out, out
    assert store.read_bytes() == raw and est.token(old)["revoked"] is False


LEAKY = ("import sys\n"
         "key = open(sys.argv[1], encoding='utf-8').read().strip()\n"
         "print('verifier saw', key[:16])\n"
         "print(key[16:])\n"
         "sys.exit(5)\n")


def test_a_verifier_that_prints_the_operator_key_in_pieces_is_masked_in_the_relay(est, tmp_path):
    """The relayed verify output is masked for the operator key as for the secret, also when the
    verifier breaks it across lines (the stream redactor alone matches only the whole key)."""
    old = _don_token(est)
    store = tmp_path / "tokens-gb10.json"
    store.write_text(json.dumps({"ssl-timekeeping-agent": old}, indent=2), encoding="utf-8")
    leak = tmp_path / "leak.py"
    leak.write_text(LEAKY, encoding="utf-8")
    keyfile = est.key_files["job-renewal-rog"]
    env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_")}
    env["FIELD_SHARED_SECRET"] = SECRET
    proc = subprocess.run(
        [PY, "-I", str(TOOL), "--agent", "ssl-timekeeping-agent", "--base", est.proxy.base,
         "--json-file", str(store), "--json-key", "ssl-timekeeping-agent", "--state-dir", str(tmp_path / "state"),
         "--verify-cmd", f'"{PY}" -I "{leak}" "{keyfile}" {{new_token}}',
         "--operator-id", "job-renewal-rog", "--operator-key-file", str(keyfile)],
        env=env, capture_output=True, timeout=240)
    out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    assert proc.returncode == 1, out
    assert "verify| verifier saw <redacted>" in out, out
    key = KEYS["job-renewal-rog"]
    for i in range(len(key) - 8 + 1):
        assert key[i:i + 8] not in out, f"8 characters of the operator key at {i} reached the log"
    assert est.token(old)["revoked"] is False



@pytest.mark.parametrize("identity,agent", [("job-provision-gb10", "compliance-crosswalk"),
                                            ("don", "ssl-timekeeping-agent")])
def test_re_provision_of_a_registered_agent_stops_at_the_register_step_with_403_under_enforce(est, tmp_path,
                                                                                                identity, agent):
    """PG0-CLI-R1-01, pinned rather than accidental, as narrowed by P29. Re-provisioning a
    registered agent with a DIFFERENT owner gets 409 from the registry, and the engine then
    PATCHes owner and manifest_ref. That needs registry_edit, which only don-admin holds (design
    v0.4 2.2.1, RT1-9), so as the job (on a self-agent it provisioned, whose manifest lists no
    authorized operators) or as don (on the ssl agent, whose list names don's alias) the run
    stops at the register step with 403: nothing capped, nothing minted, the registry row
    unchanged. Each pair is one the PATCH would accept with registry_edit added (the mutant in
    the review-round-1 report), so the 403 is the scope, not a missing identity or the agent's
    operator list. An UNCHANGED re-provision sends no PATCH at all (P29): next test."""
    key = ["--operator-id", identity, "--operator-key-file", str(est.key_files[identity])]
    if _http("GET", f"{est.base}/registry/agents/{agent}")[0] == 404:
        first = est.provision(agent, *key, out=tmp_path / "first.json")  # a first provision works
        assert first.returncode == 0, first.stdout + first.stderr
    status, before = _http("GET", f"{est.base}/registry/agents/{agent}")
    assert status == 200, status
    est.proxy.seen.clear()
    out = tmp_path / "re.json"
    # a real edit: the owner changes (click keeps the last --owner given)
    proc = est.provision(agent, *key, "--owner", "Someone Else, Spin State Labs", out=out)
    _assert_no_key(proc.stdout + proc.stderr)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    report = json.loads(out.read_text())
    steps = {s["step"]: s for s in report["steps"]}
    assert steps["register"]["outcome"] == "failed" and steps["register"]["http_status"] == 403, report["steps"]
    assert "PATCH refused" in steps["register"]["detail"], steps["register"]
    assert not any(s in steps for s in ("cap", "rate_limits", "mint")), report["steps"]
    assert report.get("token_id") is None
    assert ("PATCH", f"/registry/agents/{agent}", identity, True) in est.proxy.seen, est.proxy.seen
    assert not any(m == "PUT" or p == "/delegation/tokens" for m, p, _, _ in est.proxy.seen), est.proxy.seen
    status, after = _http("GET", f"{est.base}/registry/agents/{agent}")
    assert status == 200 and after == before, (before, after)



@pytest.mark.parametrize("identity,agent", [("job-provision-gb10", "compliance-crosswalk"),
                                            ("don", "ssl-timekeeping-agent")])
def test_a_re_provision_that_CHANGES_the_owner_still_stops_at_the_register_step_with_403(est, tmp_path,
                                                                                         identity, agent):
    """P29 keeps the PG0-CLI-R1-01 gate on a real edit. Re-provisioning a registered agent with a
    different owner still sends the PATCH, which needs registry_edit (only don-admin, design v0.4
    2.2.1, RT1-9), so as the job or as don the run stops at the register step with 403: nothing
    capped, nothing minted, the registry row unchanged. (The test above re-provisions with the
    SAME owner; under P29 that sends no PATCH, see 'Needs ruling' in the P29 PR.)"""
    key = ["--operator-id", identity, "--operator-key-file", str(est.key_files[identity])]
    if _http("GET", f"{est.base}/registry/agents/{agent}")[0] == 404:
        first = est.provision(agent, *key, out=tmp_path / "first.json")  # a first provision works
        assert first.returncode == 0, first.stdout + first.stderr
    status, before = _http("GET", f"{est.base}/registry/agents/{agent}")
    assert status == 200, status
    est.proxy.seen.clear()
    out = tmp_path / "re.json"
    # a real edit: the owner changes (click keeps the last --owner given)
    proc = est.provision(agent, *key, "--owner", "Someone Else, Spin State Labs", out=out)
    _assert_no_key(proc.stdout + proc.stderr)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    report = json.loads(out.read_text())
    steps = {s["step"]: s for s in report["steps"]}
    assert steps["register"]["outcome"] == "failed" and steps["register"]["http_status"] == 403, report["steps"]
    assert "PATCH refused" in steps["register"]["detail"], steps["register"]
    assert not any(s in steps for s in ("cap", "rate_limits", "mint")), report["steps"]
    assert report.get("token_id") is None
    assert ("PATCH", f"/registry/agents/{agent}", identity, True) in est.proxy.seen, est.proxy.seen
    assert not any(m == "PUT" or p == "/delegation/tokens" for m, p, _, _ in est.proxy.seen), est.proxy.seen
    status, after = _http("GET", f"{est.base}/registry/agents/{agent}")
    assert status == 200 and after == before, (before, after)


@pytest.mark.parametrize("identity,agent", [("job-provision-gb10", "compliance-crosswalk"),
                                            ("don", "ssl-timekeeping-agent")])
def test_an_unchanged_re_provision_sends_no_registry_patch_under_enforce(est, tmp_path, identity, agent):
    """P29: owner and manifest_ref already equal the stored values, so the engine sends no PATCH
    and registry_edit is not needed. The register step passes (registry_outcome 'unchanged') and
    the row is untouched. As job-provision-gb10 on its self-agent the whole re-provision (the
    Fly/GB10 renewal path) then completes and mints."""
    key = ["--operator-id", identity, "--operator-key-file", str(est.key_files[identity])]
    if _http("GET", f"{est.base}/registry/agents/{agent}")[0] == 404:
        first = est.provision(agent, *key, out=tmp_path / "first.json")
        assert first.returncode == 0, first.stdout + first.stderr
    status, before = _http("GET", f"{est.base}/registry/agents/{agent}")
    assert status == 200, status
    est.proxy.seen.clear()
    out = tmp_path / "re.json"
    proc = est.provision(agent, *key, out=out)
    _assert_no_key(proc.stdout + proc.stderr)
    report = json.loads(out.read_text())
    steps = {s["step"]: s for s in report["steps"]}
    assert steps["register"]["outcome"] == "ok" and report["registry_outcome"] == "unchanged", report["steps"]
    assert not any(m == "PATCH" for m, _, _, _ in est.proxy.seen), est.proxy.seen
    status, after = _http("GET", f"{est.base}/registry/agents/{agent}")
    assert status == 200 and after == before, (before, after)
    if identity == "job-provision-gb10":
        assert proc.returncode == 0 and report.get("token_id"), proc.stdout + proc.stderr


def test_don_re_provisions_an_ssl_agent_end_to_end_under_enforce_with_the_manifest_principal(est, tmp_path):
    """Review L3 (P29): the test above pins only don's register step. provision_ssl_agents.py
    passes the manifest's identity.principal (Don's display name, an alias of the don row and a
    DOA roster row) as --grantor, so an unchanged re-provision as don sends no PATCH, re-caps,
    and mints with granted_by = that name. Without --grantor the CLI mints as 'don', which is
    not a roster row (403 D.grantor at the mint; not this path)."""
    agent = "ssl-timekeeping-agent"
    key = ["--operator-id", "don", "--operator-key-file", str(est.key_files["don"])]
    status, before = _http("GET", f"{est.base}/registry/agents/{agent}")
    assert status == 200, status  # provisioned by the module fixture
    est.proxy.seen.clear()
    out = tmp_path / "re.json"
    proc = est.provision(agent, *key, "--grantor", DON, out=out)
    _assert_no_key(proc.stdout + proc.stderr)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(out.read_text())
    assert report["ok"] is True and report["registry_outcome"] == "unchanged", report["steps"]
    assert {s["step"]: s["outcome"] for s in report["steps"]}.get("mint") == "ok", report["steps"]
    assert not any(m == "PATCH" for m, _, _, _ in est.proxy.seen), est.proxy.seen
    assert ("POST", "/delegation/tokens", "don", True) in est.proxy.seen, est.proxy.seen
    assert est.token(report["token_id"])["granted_by"] == DON
    status, after = _http("GET", f"{est.base}/registry/agents/{agent}")
    assert status == 200 and after == before, (before, after)


def test_a_roster_regenerated_with_job_rows_keeps_a_job_mint_passing_the_doa_gate_under_enforce(est, tmp_path):
    """R2-04. tools/generate_doa_roster.py rosters only what the registry, the manifests and
    live tokens name, and none of them names a job id. Regenerated from this estate's own
    registry with --job-rows manifests/doa-roster.example.yaml, the roster carries the job
    rows, and job-renewal-rog's mint (granted_by its own id, under ENFORCE) passes the DOA
    gate. The same regeneration WITHOUT --job-rows, armed the same way, refuses that mint
    403 D.grantor: the negative control that makes the pass mean the carried row."""
    agent = "ssl-timekeeping-agent"
    status, agents = _http("GET", f"{est.base}/registry/agents")
    assert status == 200 and any(a["agent_id"] == agent for a in agents), agents
    registry = tmp_path / "agents.json"
    registry.write_text(json.dumps(agents), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_")}

    def regenerate(*extra: str) -> bytes:
        out = tmp_path / "generated" / "doa-roster.yaml"
        proc = subprocess.run([sys.executable, str(TOOLS / "generate_doa_roster.py"), "--registry", str(registry),
                               "--manifests", str(est.manifests), "--out", str(out), *extra],
                              env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=120)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        return out.read_bytes()

    def mint():
        return _http("POST", f"{est.base}/delegation/tokens",
                     {"agent_id": agent, "granted_by": "job-renewal-rog",
                      "scope": _manifest(agent)["delegation"]["scope"], "ttl_seconds": DAY},
                     headers={"x-field-operator": "job-renewal-rog", "x-field-operator-key": KEYS["job-renewal-rog"]})

    original = est.roster.read_bytes()
    try:
        est.roster.write_bytes(regenerate("--job-rows", str(ROSTER)))
        status, tok = mint()
        assert status == 201, (status, tok)
        assert tok["granted_by"] == "job-renewal-rog"
        mint_events = [e for e in est.events("delegation.mint", agent)
                       if e["payload"].get("token_id") == tok["token_id"]]
        assert len(mint_events) == 1, mint_events
        doa_row = mint_events[0]["payload"]["doa_row"]
        assert doa_row["grantor"] == "job-renewal-rog" and doa_row["max_ttl_days"] == 31, doa_row
        status, _ = _http("POST", f"{est.base}/delegation/tokens/{tok['token_id']}/revoke",
                          headers={"x-field-operator": "job-renewal-rog",
                                   "x-field-operator-key": KEYS["job-renewal-rog"]})
        assert status == 200

        est.roster.write_bytes(regenerate())
        status, body = mint()
        assert status == 403 and "D.grantor" in json.dumps(body), (status, body)
    finally:
        est.roster.write_bytes(original)
