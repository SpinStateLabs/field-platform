"""estate_kill_watcher carries an estate kill to a governed Claude Code session (harness ADR-0072).

If it drops a kill, undoes a human's halt, trusts a wrong answer, follows a redirect with the secret, or
prints the secret, an estate kill silently fails to stop a session. Every behaviour test drives the REAL
kill-switch + registry over real HTTP (estate_harness.py mounts each service's create_app() under the
prefixes Caddy routes) and asserts on the files the Claude Code gate reads, never on the tool's say-so.
The tool runs as a subprocess by the BASE interpreter in isolated mode (-I): standard library only.

The other half of the chain, the gate denying E1 while the sentinel exists and when the stamp is stale,
is tested in the Force-Field repo (plugins/field/hooks/test/run_estate_kill.sh).
"""

from __future__ import annotations

import json
import os
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

import harness_wait  # tools/tests is on sys.path (pytest rootdir/prepend import mode)

TOOLS = Path(__file__).resolve().parents[1]
TOOL = TOOLS / "estate_kill_watcher.py"
HARNESS = Path(__file__).with_name("estate_harness.py")
PY = getattr(sys, "_base_executable", None) or sys.executable
SECRET = "kill-watcher-test-secret-never-printed"
MARKER = "field-estate-kill-watcher v1"
_N = [0]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http(method, url, body=None, secret=None):
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["x-field-auth"] = secret
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw, status = resp.read(), resp.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(), exc.code
    return status, (json.loads(raw) if raw else None)


@harness_wait.kills_proc_on_init_failure
class Estate:
    def __init__(self, tmp_path: Path, secret: bool):
        data = tmp_path / "data"
        (data / "manifests").mkdir(parents=True)
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.secret = SECRET if secret else None
        env = dict(os.environ)
        env.pop("FIELD_SHARED_SECRET", None)
        argv = [sys.executable, str(HARNESS), str(self.port), str(data)]
        if secret:
            argv.append("--secret")
            env["FIELD_SHARED_SECRET"] = SECRET
        wait = harness_wait.harness_wait(60)
        self.proc = subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + wait
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"harness exited early: {self.proc.returncode}")
            try:
                urllib.request.urlopen(f"{self.base}/ledger/health", timeout=2).read()
                return
            except OSError:
                time.sleep(0.3)
        raise RuntimeError("harness did not come up")

    def agent(self) -> str:
        _N[0] += 1
        agent_id = f"watch-{_N[0]}"
        status, _ = _http("POST", f"{self.base}/registry/agents",
                          {"agent_id": agent_id, "name": agent_id, "owner": "kill watcher test", "domain": "canary"},
                          self.secret)
        assert status == 201, status
        return agent_id

    def kill(self, agent_id: str) -> None:
        status, body = _http("POST", f"{self.base}/killswitch/kill/{agent_id}",
                             {"operator": "test operator", "reason": "estate kill test"}, self.secret)
        assert status == 200, (status, body)

    def revive(self, agent_id: str) -> None:
        status, body = _http("POST", f"{self.base}/killswitch/revive/{agent_id}",
                             {"operator": "test operator", "reason": "estate revive test"}, self.secret)
        assert status == 200, (status, body)

    def close(self) -> None:
        self.proc.terminate()
        self.proc.wait(timeout=20)


@pytest.fixture(scope="module")
def estate(tmp_path_factory):
    saved = os.environ.pop("FIELD_SHARED_SECRET", None)
    e = Estate(tmp_path_factory.mktemp("open"), secret=False)
    try:
        yield e
    finally:
        e.close()
        if saved is not None:
            os.environ["FIELD_SHARED_SECRET"] = saved


@pytest.fixture(scope="module")
def secret_estate(tmp_path_factory):
    e = Estate(tmp_path_factory.mktemp("secret"), secret=True)
    try:
        yield e
    finally:
        e.close()


def run(args, secret=None, timeout=60):
    env = {k: v for k, v in os.environ.items() if k != "FIELD_SHARED_SECRET"}
    if secret:
        env["FIELD_SHARED_SECRET"] = secret
    p = subprocess.run([PY, "-I", str(TOOL), *args], capture_output=True, text=True, env=env, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


def once(e, agent, sentinel, *extra, secret=None):
    return run(["--agent", agent, "--base", e.base, "--sentinel", str(sentinel), "--once", *extra],
               secret=secret if secret is not None else e.secret)


# --- the estate drives the sentinel -------------------------------------------------


def test_kill_creates_the_sentinel_and_revive_removes_it(estate, tmp_path):
    a, s = estate.agent(), tmp_path / "state" / "ESTATE_KILL"
    code, out = once(estate, a, s)
    assert code == 0, out
    assert not s.exists(), "an alive agent has no sentinel"
    assert (tmp_path / "state" / "ESTATE_KILL.alive").exists(), "the stamp is written on a successful poll"
    estate.kill(a)
    code, out = once(estate, a, s)
    assert code == 0, out
    assert s.read_text().splitlines()[0] == MARKER
    assert json.loads(s.read_text().splitlines()[1])["agent_id"] == a
    estate.revive(a)
    code, out = once(estate, a, s)
    assert code == 0, out
    assert not s.exists(), "a revive on the estate removes the file the watcher wrote"
    assert (tmp_path / "state" / "ESTATE_KILL.alive").exists()


def test_an_unregistered_agent_is_killed_fail_closed(estate, tmp_path):
    """The kill-switch tells an unknown agent to halt; so does the watcher."""
    s = tmp_path / "ESTATE_KILL"
    code, out = once(estate, "never-registered", s)
    assert code == 0, out
    assert s.exists()


def test_a_human_made_sentinel_survives_an_alive_poll(estate, tmp_path):
    a, s = estate.agent(), tmp_path / "ESTATE_KILL"
    s.write_text("halted by hand\n")
    code, out = once(estate, a, s)
    assert code == 0 and "not the watcher's" in out, out
    assert s.read_text() == "halted by hand\n"


def test_a_killed_agent_with_an_existing_sentinel_is_left_as_is(estate, tmp_path):
    a, s = estate.agent(), tmp_path / "ESTATE_KILL"
    estate.kill(a)
    s.write_text("halted by hand\n")
    code, out = once(estate, a, s)
    assert code == 0 and "already present" in out, out
    assert s.read_text() == "halted by hand\n"


def test_no_answer_keeps_the_kill_and_does_not_refresh_the_stamp(estate, tmp_path):
    """An outage must never drop a kill, and must not make a dead estate look alive."""
    a, s = estate.agent(), tmp_path / "ESTATE_KILL"
    estate.kill(a)
    assert once(estate, a, s)[0] == 0 and s.exists()
    stamp = tmp_path / "ESTATE_KILL.alive"
    old = time.time() - 600
    os.utime(stamp, (old, old))
    code, out = run(["--agent", a, "--base", f"http://127.0.0.1:{_free_port()}", "--sentinel", str(s), "--once"])
    assert code == 3, out
    assert s.exists(), "the sentinel is untouched by an outage"
    assert abs(stamp.stat().st_mtime - old) < 2, "the stamp is not refreshed without an answer"
    assert once(estate, a, s)[0] == 0
    assert stamp.stat().st_mtime > old + 500, "the stamp is refreshed by the next good poll"


def test_the_watcher_follows_the_estate_within_the_poll_interval(estate, tmp_path):
    a, s = estate.agent(), tmp_path / "ESTATE_KILL"
    proc = subprocess.Popen(
        [PY, "-I", str(TOOL), "--agent", a, "--base", estate.base, "--sentinel", str(s), "--interval", "0.3"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        def wait(cond, what, limit=15.0):
            t0 = time.time()
            while time.time() - t0 < limit:
                if cond():
                    return time.time() - t0
                time.sleep(0.05)
            raise AssertionError(f"{what} did not happen within {limit} s")

        wait(lambda: (tmp_path / "ESTATE_KILL.alive").exists(), "first stamp")
        assert not s.exists()
        estate.kill(a)
        took = wait(s.exists, "sentinel after an estate kill")
        assert took < 5.0, f"propagation took {took:.1f} s for a 0.3 s interval"
        estate.revive(a)
        wait(lambda: not s.exists(), "sentinel removal after a revive")
        assert proc.poll() is None, "poll errors and state changes never end the loop"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


# --- the answer is trusted only when it is well-formed --------------------------------


class Stub:
    """A one-route HTTP server that answers GET /killswitch/heartbeat/<agent> with a canned reply."""

    def __init__(self, reply):
        outer = self
        self.hits: list[dict] = []
        self.reply = reply

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.hits.append({"path": self.path, "auth": self.headers.get("x-field-auth")})
                status, headers, body = outer.reply(self.path)
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()


def _json(obj, status=200):
    return lambda path: (status, {"Content-Type": "application/json"}, json.dumps(obj).encode())


@pytest.mark.parametrize("reply", [
    _json({"agent_id": "someone-else", "status": "active", "killed": False}),   # another agent's answer
    _json({"agent_id": "a1", "status": "active", "killed": "no"}),              # killed is not a boolean
    _json({"agent_id": "a1", "status": "active"}),                              # no killed at all
    _json({"agent_id": "a1", "killed": False}, status=500),                     # an error status
    _json({"agent_id": "a1", "killed": False}, status=404),
    _json(["a1"]),                                                              # not an object
    lambda path: (200, {"Content-Type": "text/html"}, b"<html>ok</html>"),     # not JSON
    lambda path: (200, {}, b""),                                                # empty
])
def test_a_malformed_or_foreign_answer_changes_nothing(reply, tmp_path):
    stub = Stub(reply)
    try:
        s = tmp_path / "ESTATE_KILL"
        s.write_text(f"{MARKER}\n{{}}\n")  # a watcher-written sentinel: a bad "alive" answer must not remove it
        code, out = run(["--agent", "a1", "--base", stub.base, "--sentinel", str(s), "--once"])
        assert code == 3, out
        assert s.exists(), "a bad answer must not read as a revive"
        assert not (tmp_path / "ESTATE_KILL.alive").exists(), "a bad answer must not refresh the stamp"
    finally:
        stub.close()


def test_a_redirect_is_not_followed_and_the_secret_does_not_travel(tmp_path):
    target = Stub(_json({"agent_id": "a1", "status": "active", "killed": False}))
    redirector = Stub(lambda path: (302, {"Location": f"{target.base}/killswitch/heartbeat/a1"}, b""))
    try:
        s = tmp_path / "ESTATE_KILL"
        code, out = run(["--agent", "a1", "--base", redirector.base, "--sentinel", str(s), "--once"], secret=SECRET)
        assert code == 3, out
        assert target.hits == [], "the redirect target was contacted: the secret would have travelled"
        assert SECRET not in out
    finally:
        redirector.close()
        target.close()


def test_the_request_is_a_get_on_the_heartbeat_with_the_secret_header(tmp_path):
    stub = Stub(_json({"agent_id": "a1", "status": "active", "killed": False}))
    try:
        code, out = run(["--agent", "a1", "--base", stub.base, "--sentinel", str(tmp_path / "K"), "--once"], secret=SECRET)
        assert code == 0, out
        assert stub.hits == [{"path": "/killswitch/heartbeat/a1", "auth": SECRET}]
        code, out = run(["--agent", "a1", "--base", stub.base, "--sentinel", str(tmp_path / "K"), "--once",
                         "--kill-prefix", "/"], secret=None)
        assert code == 0 and stub.hits[-1] == {"path": "/heartbeat/a1", "auth": None}
    finally:
        stub.close()


def test_the_secret_is_required_and_never_printed(secret_estate, tmp_path):
    a, s = secret_estate.agent(), tmp_path / "ESTATE_KILL"
    secret_estate.kill(a)
    code, out = run(["--agent", a, "--base", secret_estate.base, "--sentinel", str(s), "--once"], secret=None)
    assert code == 3 and "401" in out and not s.exists(), out   # no secret: no answer, the kill is NOT applied from a 401
    code, out = once(secret_estate, a, s)
    assert code == 0 and s.exists(), out
    assert SECRET not in out
    sf = tmp_path / "secret.txt"
    sf.write_text(SECRET + "\n")
    s.unlink()
    code, out = run(["--agent", a, "--base", secret_estate.base, "--sentinel", str(s), "--once", "--secret-file", str(sf)])
    assert code == 0 and s.exists() and SECRET not in out, out


# --- refusals ---------------------------------------------------------------------------


@pytest.mark.parametrize("extra,why", [
    (["--agent", "bad id!"], "agent"),
    (["--agent", "a1", "--interval", "0"], "interval"),
    (["--agent", "a1", "--interval", "10", "--max-age-s", "20"], "twice"),
    (["--agent", "a1", "--interval", "10", "--max-age-s", "25"], "twice"),   # 25 = 2 * 10 + the default 5 s timeout: not enough
    (["--agent", "a1", "--interval", "10", "--max-age-s", "26"], None),      # 26 > 2 * 10 + 5 is accepted
    (["--agent", "a1", "--interval", "nan"], "interval"),
    (["--agent", "a1", "--timeout", "inf"], "timeout"),
])
def test_refusals_and_the_interval_rule(extra, why, tmp_path):
    code, out = run(["--base", "http://127.0.0.1:1", "--sentinel", str(tmp_path / "K"), "--once", *extra])
    if why is None:
        assert code == 3, out   # accepted; the closed port simply gives no answer
    else:
        assert code == 2 and why in out, out


def test_a_non_http_base_and_a_missing_sentinel_are_refused(tmp_path):
    code, out = run(["--agent", "a1", "--base", "ftp://x", "--sentinel", str(tmp_path / "K"), "--once"])
    assert code == 2 and "http" in out, out
    code, out = run(["--agent", "a1", "--base", "http://127.0.0.1:1", "--once"])
    assert code == 2 and "--sentinel" in out, out


def test_a_sentinel_path_that_is_a_directory_is_refused(estate, tmp_path):
    a = estate.agent()
    estate.kill(a)
    d = tmp_path / "ESTATE_KILL"
    d.mkdir()
    code, out = once(estate, a, d)
    assert code == 2 and "not a regular file" in out, out


def test_the_manifest_names_the_sentinel_and_must_agree(estate, tmp_path):
    yaml = pytest.importorskip("yaml")
    a = estate.agent()
    mdir = tmp_path / "proj"
    mdir.mkdir()
    (mdir / "field-manifest.yaml").write_text(yaml.safe_dump(
        {"enforcement": {"kill_switch": {"endpoint": "http://x/kill", "method": "HTTP POST",
                                         "local_sentinel": "state/ESTATE_KILL", "sentinel_max_age_s": 30}}}))
    estate.kill(a)
    code, out = run(["--agent", a, "--base", estate.base, "--manifest", str(mdir / "field-manifest.yaml"), "--once"])
    assert code == 0, out
    assert (mdir / "state" / "ESTATE_KILL").exists(), "relative local_sentinel resolves against the manifest directory"
    assert (mdir / "state" / "ESTATE_KILL.alive").exists()
    code, out = run(["--agent", a, "--base", estate.base, "--manifest", str(mdir / "field-manifest.yaml"),
                     "--sentinel", str(tmp_path / "other"), "--once"])
    assert code == 2 and "disagrees" in out, out
    code, out = run(["--agent", a, "--base", estate.base, "--manifest", str(mdir / "field-manifest.yaml"),
                     "--interval", "20", "--once"])
    assert code == 2 and "twice" in out, out   # 30 is not more than 2 * 20
    (mdir / "field-manifest.yaml").write_text(yaml.safe_dump({"enforcement": {"kill_switch": {"endpoint": "x", "method": "y"}}}))
    code, out = run(["--agent", a, "--base", estate.base, "--manifest", str(mdir / "field-manifest.yaml"), "--once"])
    assert code == 2 and "local_sentinel" in out, out


# --- review findings: runtime failures never crash or end the watcher --------------------------------------------


def test_a_sentinel_that_cannot_be_written_is_exit_3_not_a_crash(estate, tmp_path):
    a = estate.agent()
    estate.kill(a)
    blocker = tmp_path / "file"
    blocker.write_text("x")
    code, out = once(estate, a, blocker / "ESTATE_KILL")
    assert code == 3 and "Traceback" not in out and "could not change the sentinel" in out, out


def test_the_loop_survives_a_sentinel_it_cannot_use_and_recovers(estate, tmp_path):
    a, s = estate.agent(), tmp_path / "ESTATE_KILL"
    estate.kill(a)
    s.mkdir()   # in the way: a runtime refusal in --once, a retry in the loop
    proc = subprocess.Popen([PY, "-I", str(TOOL), "--agent", a, "--base", estate.base, "--sentinel", str(s),
                             "--interval", "0.3"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(1.5)
        assert proc.poll() is None, "a runtime refusal ended the loop: later kills would no longer propagate"
        assert not (tmp_path / "ESTATE_KILL.alive").exists(), "no stamp while the kill cannot be applied"
        s.rmdir()
        t0 = time.time()
        while time.time() - t0 < 10 and not s.is_file():
            time.sleep(0.1)
        assert s.is_file(), "the watcher did not recover once the path was usable"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_timeout_is_a_total_deadline_not_per_read(tmp_path):
    """A server dripping one byte every 0.4 s must not hold a poll for ~65 000 x the timeout."""
    class Drip(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "100000")
            self.end_headers()
            try:
                for _ in range(200):
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(0.4)
            except OSError:
                pass

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Drip)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        t0 = time.time()
        code, out = run(["--agent", "a1", "--base", f"http://127.0.0.1:{srv.server_address[1]}",
                         "--sentinel", str(tmp_path / "K"), "--once", "--timeout", "1"])
        took = time.time() - t0
        assert code == 3, out
        assert took < 4.0, f"a 1 s timeout held the poll for {took:.1f} s"
    finally:
        srv.shutdown()


def test_only_http_200_is_an_answer(tmp_path):
    stub = Stub(_json({"agent_id": "a1", "status": "active", "killed": False}, status=201))
    try:
        code, out = run(["--agent", "a1", "--base", stub.base, "--sentinel", str(tmp_path / "K"), "--once"])
        assert code == 3 and "HTTP 201" in out, out
    finally:
        stub.close()


def test_a_symlink_at_the_sentinel_path_is_refused_and_its_target_untouched(estate, tmp_path):
    a = estate.agent()
    estate.kill(a)
    target = tmp_path / "precious.txt"
    target.write_text("keep")
    link = tmp_path / "ESTATE_KILL"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    code, out = once(estate, a, link)
    assert code == 2 and "not a regular file" in out, out
    assert target.read_text() == "keep" and link.is_symlink()


def test_the_environment_proxy_is_never_used(tmp_path):
    real = Stub(_json({"agent_id": "a1", "status": "active", "killed": False}))
    proxy = Stub(_json({"agent_id": "a1", "status": "active", "killed": True}))
    try:
        env = {k: v for k, v in os.environ.items() if k != "FIELD_SHARED_SECRET"}
        env.update({"HTTP_PROXY": proxy.base, "http_proxy": proxy.base, "ALL_PROXY": proxy.base, "NO_PROXY": ""})
        p = subprocess.run([PY, "-I", str(TOOL), "--agent", "a1", "--base", real.base, "--sentinel",
                            str(tmp_path / "K"), "--once"], capture_output=True, text=True, env=env, timeout=60)
        assert p.returncode == 0, p.stdout + p.stderr
        assert proxy.hits == [] and len(real.hits) == 1 and not (tmp_path / "K").exists()
    finally:
        real.close()
        proxy.close()


def test_a_transport_error_does_not_print_the_secret(tmp_path):
    code, out = run(["--agent", "a1", "--base", f"http://127.0.0.1:{_free_port()}", "--sentinel", str(tmp_path / "K"),
                     "--once"], secret=SECRET)
    assert code == 3 and "transport error" in out and SECRET not in out, out


def test_server_text_cannot_inject_log_lines(tmp_path):
    stub = Stub(_json({"agent_id": "a1", "status": "active\n2026-01-01T00:00:00Z FAKE: alive: sentinel removed", "killed": False}))
    try:
        code, out = run(["--agent", "a1", "--base", stub.base, "--sentinel", str(tmp_path / "K"), "--once"])
        assert code == 0, out
        assert len([ln for ln in out.splitlines() if ln.strip()]) == 1, out
    finally:
        stub.close()


def test_a_bare_name_the_gate_would_reject_is_refused(tmp_path):
    code, out = run(["--agent", "a1", "--base", "http://127.0.0.1:1", "--sentinel", "KILL", "--once"])
    assert code == 2 and "file path" in out, out
