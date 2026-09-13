"""X1a - tools/field-rest.ps1 reads the perimeter secret from a file.

The shim is what both ssl skills dot-source on rog-command. When the GB10 arms
FIELD_SHARED_SECRET (arming step A2) every call without `x-field-auth` is a 401,
which the shim reads as UNREACHABLE = HALT. So this test runs the REAL script
in the REAL Windows PowerShell against:

* estate_harness.py started with --secret (every service's real create_app
  behind the real authn middleware): the file-sourced header is what turns a
  HALT into `killed=false`;
* a local capture server that records the request headers, so "no header was
  sent" and "the header is the trimmed value" are observed, not inferred.

Every run asserts that no secret value appears in anything PowerShell printed,
including under `Set-PSDebug -Trace 2` and against an upstream that reflects the
header into every field it returns.
Tests never touch C:\\Users\\donal\\.field-local: FIELD_SECRET_FILE always
points into tmp_path. Skipped where powershell.exe does not exist.
"""

from __future__ import annotations

import http.server
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
from pathlib import Path

import pytest

msvcrt = pytest.importorskip("msvcrt", reason="Windows-only: needs Windows PowerShell")
POWERSHELL = shutil.which("powershell.exe") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="needs Windows PowerShell (powershell.exe)")

TOOLS = Path(__file__).resolve().parents[1]
SHIM = TOOLS / "field-rest.ps1"
HARNESS = Path(__file__).with_name("estate_harness.py")
SECRET = "field-rest-file-secret-4c1e9a7b-never-printed"
ENV_SECRET = "field-rest-env-secret-0d2b6f3e-never-printed"
AGENT = "ps1-secret-agent"
ENV_KEYS = ("FIELD_SHARED_SECRET", "FIELD_SECRET_FILE", "FIELD_PROXY_URL",
            "FIELD_TOKENS_FILE", "FIELD_CLIENT_POSTURE")


# --- plumbing ----------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


UNSET = "unset"


def _code_lines(source: str) -> str:
    return "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))


def _safe_env(env: dict[str, str], shim: Path, tmp_path: Path) -> dict[str, str]:
    """Every PowerShell run must be unable to reach C:\\Users\\donal\\.field-local. The real shim
    names that directory in code, and before 1.3's fix it silently replaced a FIELD_TOKENS_FILE that
    did not exist with the real token file there (a real ssl token was once sent to a local harness
    that way). So a run of the real shim names an EXISTING token file inside tmp_path; only a copy
    whose code names no .field-local path and no $HOME (decoy_shim) may run with it missing or unset."""
    tokens, secret, proxy = env.get("FIELD_TOKENS_FILE"), env.get("FIELD_SECRET_FILE", ""), env["FIELD_PROXY_URL"]
    assert proxy.startswith("http://127.0.0.1:"), proxy
    assert ".field-local" not in secret.lower() and Path(secret).is_relative_to(tmp_path), secret
    code = _code_lines(shim.read_text(encoding="utf-8")).lower()
    if ".field-local" in code or "$home" in code:
        assert tokens and Path(tokens).is_file() and Path(tokens).is_relative_to(tmp_path), tokens
    else:
        assert tokens is None or Path(tokens).is_relative_to(tmp_path), tokens
    return env


def decoy_shim(tmp_path: Path, real_tokens: Path, home: Path) -> Path:
    """A copy of the REAL shim whose only change is its path literals: the rog-command token file
    becomes `real_tokens`, the $HOME default becomes `home`, the default secret file a tmp path.
    Every line of logic is the shim's own, so a fallback in it shows up here, against files the
    test owns, instead of against the real .field-local."""
    source = SHIM.read_text(encoding="utf-8")
    swaps = {r"C:\Users\donal\.field-local\tokens-gb10.json": str(real_tokens),
             r"C:\Users\donal\.field-local\gb10-estate-secret": str(tmp_path / "decoy-default-secret"),
             r"Join-Path $HOME '.field-local\tokens-gb10.json'": f"Join-Path '{home}' 'tokens-gb10.json'"}
    for old, new in swaps.items():
        assert old in source, old
        source = source.replace(old, new)
    code = _code_lines(source).lower()
    assert ".field-local" not in code and "$home" not in code, "the decoy still names a real path"
    path = tmp_path / "decoy-field-rest.ps1"
    path.write_text(source, encoding="utf-8")
    return path


def run_shim(tmp_path: Path, proxy: str, commands: str, *, secret_file: Path | None,
             env_secret: str | None = None, forbidden: tuple[str, ...] = (),
             prelude: str = "", shim: Path = SHIM, tokens_file: Path | str | None = None) -> str:
    """Dot-source the shim in a fresh powershell.exe and run `commands`.

    FIELD_SHARED_SECRET is UNSET unless env_secret is given; FIELD_SECRET_FILE
    always points inside tmp_path (a path that does not exist when
    secret_file is None). FIELD_TOKENS_FILE is tmp_path/tokens.json, written
    as {} when the test did not write it (see _safe_env); a decoy_shim run may
    name another tmp path, or UNSET. Returns stdout+stderr, after asserting
    that no value in `forbidden` (plus both test secrets) was printed."""
    env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    env["FIELD_PROXY_URL"] = proxy
    env["FIELD_SECRET_FILE"] = str(secret_file if secret_file is not None else tmp_path / "absent-secret")
    if tokens_file is None:
        tokens_file = tmp_path / "tokens.json"
        if not tokens_file.exists():
            tokens_file.write_text("{}", encoding="utf-8")
    if tokens_file != UNSET:
        env["FIELD_TOKENS_FILE"] = str(tokens_file)
    if env_secret is not None:
        env["FIELD_SHARED_SECRET"] = env_secret
    script = prelude + ". '" + str(shim).replace("'", "''") + "'; " + commands
    proc = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        env=_safe_env(env, shim, tmp_path), capture_output=True, timeout=120,
    )
    out = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
    # The console wraps long lines, and Set-PSDebug truncates a traced value
    # with "..." — so a leak can be split across lines or be only a PREFIX of
    # the secret. Check the unwrapped text, and every 16-character fragment.
    flat = out.replace("\r", "").replace("\n", "")
    for value in (SECRET, ENV_SECRET, *forbidden):
        assert value not in out and value not in flat, "a secret value was printed"
    for value in (SECRET, ENV_SECRET):
        for i in range(len(value) - 15):
            assert value[i:i + 16] not in flat, f"part of a secret value was printed: {value[i:i + 16]!r}"
    return out


class Capture:
    """Records the headers of every request; answers like a live heartbeat."""

    def __init__(self) -> None:
        self.requests: list[dict[str, str]] = []
        self.body: dict | None = None  # None = a live, not-killed heartbeat
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _answer(self):
                outer.requests.append({k.lower(): v for k, v in self.headers.items()})
                body = json.dumps(outer.body or {"agent_id": AGENT, "killed": False, "status": "active",
                                                 "checked_at": "2026-09-12T00:00:00+00:00"}).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = _answer

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def only_request(self) -> dict[str, str]:
        assert len(self.requests) == 1, self.requests
        return self.requests[0]


@pytest.fixture()
def capture():
    c = Capture()
    try:
        yield c
    finally:
        c.server.shutdown()
        c.server.server_close()


@pytest.fixture(scope="module")
def perimeter_estate(tmp_path_factory):
    """estate_harness.py --secret: every data route needs x-field-auth. One
    registered, active agent, registered WITH the header (so the estate's own
    perimeter is proven to accept it before the shim is involved)."""
    data = tmp_path_factory.mktemp("estate") / "data"
    (data / "manifests").mkdir(parents=True)
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ)
    env["FIELD_SHARED_SECRET"] = SECRET
    proc = subprocess.Popen([sys.executable, str(HARNESS), str(port), str(data), "--secret"],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 90
        while True:
            if proc.poll() is not None:
                raise RuntimeError(f"harness exited early: {proc.returncode}")
            try:
                urllib.request.urlopen(f"{base}/ledger/health", timeout=2).read()
                break
            except OSError:
                if time.time() > deadline:
                    raise RuntimeError("harness did not come up")
                time.sleep(0.3)

        def call(method, path, body=None, secret=None):
            headers = {"content-type": "application/json"}
            if secret:
                headers["x-field-auth"] = secret
            req = urllib.request.Request(f"{base}{path}", method=method, headers=headers,
                                         data=json.dumps(body).encode() if body is not None else None)
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    return r.status
            except urllib.error.HTTPError as exc:
                return exc.code

        assert call("POST", "/registry/agents", {"agent_id": AGENT, "name": AGENT, "owner": "FIELD canary",
                                                 "domain": "canary"}, SECRET) == 201
        # the perimeter is really on: the same read without the header is refused
        assert call("GET", f"/killswitch/heartbeat/{AGENT}") == 401
        assert call("GET", f"/killswitch/heartbeat/{AGENT}", secret=SECRET) == 200
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=30)


def write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


# --- against a perimeter estate (the brief's three cases) ----------------------------


def test_with_the_secret_file_the_heartbeat_reads_killed_false(tmp_path, perimeter_estate):
    secret_file = write(tmp_path / "gb10-estate-secret", SECRET.encode() + b"\r\n")
    out = run_shim(tmp_path, perimeter_estate, f"Get-FieldHeartbeat -Agent {AGENT}", secret_file=secret_file)
    assert "auth=file" in out
    assert f"FIELD heartbeat {AGENT} killed=false status=active" in out
    assert "UNREACHABLE" not in out and "HALT" not in out


def test_without_the_secret_file_the_heartbeat_halts_on_401(tmp_path, perimeter_estate):
    out = run_shim(tmp_path, perimeter_estate, f"Get-FieldHeartbeat -Agent {AGENT}", secret_file=None)
    assert "auth=none" in out
    assert "malformed" not in out and "unreadable" not in out  # absent is not an error
    assert f"FIELD heartbeat {AGENT} UNREACHABLE" in out
    assert "(401)" in out  # the perimeter refused it, not a dead port
    assert "HALT" in out


MALFORMED = {
    "interior-space": SECRET[:20] + " " + SECRET[20:],
    "interior-crlf": SECRET[:20] + "\r\n" + SECRET[20:],
    "tab": SECRET[:20] + "\t" + SECRET[20:],
    "control-char": SECRET[:20] + "\x07" + SECRET[20:],
    "non-ascii": SECRET[:20] + "\u00e9" + SECRET[20:],
    # U+212A KELVIN SIGN case-folds to "k": `-match` (case-insensitive) would
    # accept it into [\x21-\x7E]; only `-cmatch` refuses it.
    "kelvin-sign": SECRET[:20] + "\u212a" + SECRET[20:],
}


@pytest.mark.parametrize("kind", sorted(MALFORMED))
def test_a_malformed_secret_file_is_never_sent_and_never_printed(tmp_path, perimeter_estate, capture, kind):
    value = MALFORMED[kind]
    halves = (SECRET[:20], SECRET[20:])
    secret_file = write(tmp_path / "gb10-estate-secret", value.encode("utf-8") + b"\n")

    out = run_shim(tmp_path, perimeter_estate, f"Get-FieldHeartbeat -Agent {AGENT}",
                   secret_file=secret_file, forbidden=(value, *halves))
    malformed_lines = [ln for ln in out.splitlines() if "is malformed" in ln]
    assert len(malformed_lines) == 1, out
    assert "auth=file-malformed" in out
    assert "(401)" in out and "HALT" in out

    out = run_shim(tmp_path, capture.base, f"Get-FieldHeartbeat -Agent {AGENT}",
                   secret_file=secret_file, forbidden=(value, *halves))
    assert "x-field-auth" not in capture.only_request()


# --- what exactly is sent (capture server) ----------------------------------------------


def test_the_header_is_the_trimmed_file_value(tmp_path, capture):
    secret_file = write(tmp_path / "s", b"  " + SECRET.encode() + b" \r\n\r\n")
    out = run_shim(tmp_path, capture.base, f"Get-FieldHeartbeat -Agent {AGENT}", secret_file=secret_file)
    assert capture.only_request()["x-field-auth"] == SECRET
    assert "killed=false" in out


def test_the_environment_secret_wins_over_the_file(tmp_path, capture):
    secret_file = write(tmp_path / "s", SECRET.encode())
    out = run_shim(tmp_path, capture.base, f"Get-FieldHeartbeat -Agent {AGENT}",
                   secret_file=secret_file, env_secret=ENV_SECRET)
    assert capture.only_request()["x-field-auth"] == ENV_SECRET
    assert "auth=env" in out


def test_a_malformed_environment_secret_is_refused_without_falling_back_to_the_file(tmp_path, capture):
    """A trailing newline is the CRLF-.env failure the estate probe found. The
    regex must anchor with \\z: `$` would accept "value\\n". And an explicit env
    value that is refused must not be silently replaced by a different secret."""
    secret_file = write(tmp_path / "s", SECRET.encode())
    bad = ENV_SECRET + "\n"
    out = run_shim(tmp_path, capture.base, f"Get-FieldHeartbeat -Agent {AGENT}",
                   secret_file=secret_file, env_secret=bad, forbidden=(bad,))
    assert "FIELD_SHARED_SECRET is malformed" in out
    assert "auth=env-malformed" in out
    assert "x-field-auth" not in capture.only_request()


@pytest.mark.parametrize("content", [b"", b"   \r\n\t\n"], ids=["empty", "whitespace-only"])
def test_an_empty_secret_file_is_no_header_and_not_an_error(tmp_path, capture, content):
    secret_file = write(tmp_path / "s", content)
    out = run_shim(tmp_path, capture.base, f"Get-FieldHeartbeat -Agent {AGENT}", secret_file=secret_file)
    assert "auth=none" in out
    assert "malformed" not in out and "unreadable" not in out
    assert "x-field-auth" not in capture.only_request()


def test_an_unreadable_secret_file_is_no_header_and_says_so(tmp_path, capture):
    """A byte-range lock makes the read fail while the file still exists."""
    secret_file = write(tmp_path / "s", SECRET.encode() + b"\n")
    fd = os.open(secret_file, os.O_RDWR)
    msvcrt.locking(fd, msvcrt.LK_NBLCK, 4096)
    try:
        out = run_shim(tmp_path, capture.base, f"Get-FieldHeartbeat -Agent {AGENT}", secret_file=secret_file)
    finally:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 4096)
        os.close(fd)
    assert "is unreadable" in out
    assert "auth=file-unreadable" in out
    assert "x-field-auth" not in capture.only_request()


def test_every_hook_sends_the_file_secret(tmp_path, capture):
    """All four hooks build their headers the same way."""
    secret_file = write(tmp_path / "s", SECRET.encode())
    (tmp_path / "tokens.json").write_text(json.dumps({AGENT: "tok-1"}), encoding="utf-8")
    run_shim(tmp_path, capture.base,
             f"Get-FieldHeartbeat -Agent {AGENT}; Send-FieldCheckin -Agent {AGENT}; "
             f"Invoke-FieldCheck -Agent {AGENT} -Action 'canary.probe'; Send-FieldSpend -Agent {AGENT}",
             secret_file=secret_file)
    assert len(capture.requests) == 4
    assert [r.get("x-field-auth") for r in capture.requests] == [SECRET] * 4


# --- the token file ----------------------------------------------------------------------------


DECOY_TOKEN = "d3c0d3c0-0000-4000-8000-00000000d3c0"


@pytest.mark.parametrize("named", ["a missing file", "a missing directory"])
def test_a_tokens_file_the_environment_names_is_never_replaced_by_another_file(tmp_path, capture, named):
    """FIELD_TOKENS_FILE naming a file that does not exist used to be replaced, silently, by the
    rog-command token file (here a decoy the test owns), whose token then went to FIELD_PROXY_URL.
    A set FIELD_TOKENS_FILE is the only file: missing means NO TOKEN and no sentinel call."""
    real = tmp_path / "decoy-real-tokens.json"
    real.write_text(json.dumps({AGENT: DECOY_TOKEN}), encoding="utf-8")
    shim = decoy_shim(tmp_path, real_tokens=real, home=tmp_path / "decoy-home")
    missing = tmp_path / ("tokens-typo.json" if named == "a missing file" else "no-such-dir/tokens.json")
    out = run_shim(tmp_path, capture.base, f"Invoke-FieldCheck -Agent {AGENT} -Action 'canary.probe'",
                   secret_file=None, shim=shim, tokens_file=missing, forbidden=(DECOY_TOKEN,))
    assert f"tokens={missing} " in out, out
    assert f"FIELD check {AGENT} 'canary.probe' NO TOKEN ({missing}) -> BLOCK" in out, out
    assert capture.requests == []


def test_without_tokens_file_in_the_environment_the_default_and_its_fallback_are_kept(tmp_path, capture):
    """Unchanged behaviour when FIELD_TOKENS_FILE is unset: the $HOME default, else the rog-command file."""
    real = tmp_path / "decoy-real-tokens.json"
    real.write_text(json.dumps({AGENT: DECOY_TOKEN}), encoding="utf-8")
    home = tmp_path / "decoy-home"
    home.mkdir()
    shim = decoy_shim(tmp_path, real_tokens=real, home=home)
    out = run_shim(tmp_path, capture.base, f"Get-FieldToken {AGENT}", secret_file=None, shim=shim,
                   tokens_file=UNSET)
    assert f"tokens={real} " in out and DECOY_TOKEN in out, out
    (home / "tokens-gb10.json").write_text(json.dumps({AGENT: "home-token"}), encoding="utf-8")
    out = run_shim(tmp_path, capture.base, f"Get-FieldToken {AGENT}", secret_file=None, shim=shim,
                   tokens_file=UNSET)
    assert f"tokens={home / 'tokens-gb10.json'} " in out and "home-token" in out, out


# --- redaction -----------------------------------------------------------------------------


def test_protect_field_text_redacts_the_secret(tmp_path, capture):
    """The secret is assembled inside PowerShell, never on a command line."""
    secret_file = write(tmp_path / "s", SECRET.encode())
    out = run_shim(tmp_path, capture.base,
                   "Protect-FieldText ('upstream said: ' + (Get-FieldSecretState).Value + ' (reflected)')",
                   secret_file=secret_file)
    assert "upstream said: <redacted> (reflected)" in out


HOOKS = ("Get-FieldHeartbeat", "Send-FieldCheckin", "Invoke-FieldCheck", "Send-FieldSpend")


def _hook_bodies(source: str) -> dict[str, str]:
    bodies = {}
    for name in HOOKS:
        m = re.search(r"^function " + name + r" \{\n(.*?)^\}\n", source, flags=re.S | re.M)
        assert m, name
        bodies[name] = m.group(1)
    return bodies


def test_every_line_a_hook_prints_goes_through_the_redactor():
    """Source guard, extended beyond exception messages: a hook prints ONLY via
    Write-FieldLine with the request's own secret state, and builds its header
    from that same state (never a second read). Server-returned fields and
    exception messages are both inside those lines."""
    source = SHIM.read_text(encoding="utf-8")
    bodies = _hook_bodies(source)
    for name, body in bodies.items():
        assert "Write-Output" not in body, name
        assert "Write-Host" not in body and "Write-Information" not in body, name
        lines = re.findall(r"Write-FieldLine (\S+) ", body)
        assert lines and set(lines) == {"$ctx.Auth"}, (name, lines)
        assert body.count("Get-FieldHeaders $ctx.Auth") == 1, name
        assert "Get-FieldHeaders)" not in body, name
        assert "$ctx = @{ Auth = (Get-FieldSecretState) }" in body, name
        # the value and the responses never sit in a named variable
        assert not re.search(r"^\s*\$(r|v|s|clause|raw|value)\s*=", body, flags=re.M), name
        # nor is anything printed IMPLICITLY: a statement that is a bare
        # interpolating string (or a bare variable / member read) is pipeline
        # output PowerShell prints without passing the redactor. Single-quoted
        # literals cannot carry a server field (switch labels use them).
        assert not re.search(r'^\s*@?"', body, flags=re.M), name
        assert not re.search(r"^\s*\$[\w:.()]+\s*$", body, flags=re.M), name
    assert sum(len(re.findall(r"\$_\.Exception\.Message", b)) for b in bodies.values()) >= 4


class Reflector:
    """A hostile or buggy upstream: echoes the x-field-auth value it receives
    into every field the shim prints. `on_request` runs before it answers.

    mode "default": GET heartbeat alive, POST heartbeat killed, a verdict with
    a clause_id, a spend state. mode "inverse": the OTHER print branches — GET
    killed, POST alive (last_seen), a shadow verdict (context.would_be). mode
    "text": a 200 whose body is not JSON (the secret reflected in plain text)."""

    def __init__(self) -> None:
        self.headers: list[str | None] = []
        self.on_request = None
        self.mode = "default"
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _answer(self):
                echo = self.headers.get("x-field-auth")
                outer.headers.append(echo)
                if outer.on_request is not None:
                    outer.on_request()
                length = int(self.headers.get("content-length") or 0)
                if length:
                    self.rfile.read(length)
                echo = echo or "no-header"
                if outer.mode == "text":
                    data = ("t-" + echo).encode()
                    self.send_response(200)
                    self.send_header("content-type", "text/plain")
                    self.send_header("content-length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if self.path.startswith("/killswitch/heartbeat/"):
                    killed = (self.command == "POST") != (outer.mode == "inverse")
                    body = {"killed": killed, "status": "s-" + echo, "checked_at": "c-" + echo,
                            "last_seen": "l-" + echo}
                elif self.path == "/sentinel/check" and outer.mode == "inverse":
                    body = {"decision": "d-" + echo, "clause_id": None,
                            "context": {"would_be": {"clause_id": "w-" + echo}}}
                elif self.path == "/sentinel/check":
                    body = {"decision": "d-" + echo, "clause_id": "k-" + echo}
                else:
                    # a real state prints the line; a reflected state is refused
                    # as MALFORMED before anything from the reply is printed
                    state = "t-" + echo if outer.mode == "inverse" else "OK"
                    body = {"state": state, "spent_cents": "p-" + echo,
                            "limit_cents": "m-" + echo, "detail": "e-" + echo}
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = _answer

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture()
def reflector():
    r = Reflector()
    try:
        yield r
    finally:
        r.server.shutdown()
        r.server.server_close()


ALL_HOOKS = (f"Get-FieldHeartbeat -Agent {AGENT}; Send-FieldCheckin -Agent {AGENT}; "
             f"Invoke-FieldCheck -Agent {AGENT} -Action 'canary.probe'; Send-FieldSpend -Agent {AGENT}")


def test_a_reflected_secret_in_server_fields_is_redacted_in_every_hook_line(tmp_path, reflector):
    secret_file = write(tmp_path / "s", SECRET.encode())
    (tmp_path / "tokens.json").write_text(json.dumps({AGENT: "tok-1"}), encoding="utf-8")
    out = run_shim(tmp_path, reflector.base, ALL_HOOKS, secret_file=secret_file)  # asserts SECRET absent
    assert reflector.headers == [SECRET] * 4  # the upstream really had it to reflect
    lines = [ln for ln in out.splitlines() if ln.startswith("FIELD ") and "shim loaded" not in ln]
    assert len(lines) == 4, out
    assert "status=s-<redacted> at=c-<redacted>" in lines[0]
    assert "killed=true status=s-<redacted> -> HALT" in lines[1]
    assert "-> d-<redacted> k-<redacted>" in lines[2]
    assert "-> OK spent=p-<redacted>c of m-<redacted>c e-<redacted>" in lines[3]


def test_a_reflected_secret_in_the_other_print_branches_is_redacted(tmp_path, reflector):
    """The branches the default reflector never reaches: GET killed, POST alive
    with last_seen, and a shadow verdict. A hook line printed implicitly (a bare
    string) instead of via Write-FieldLine leaks here and nowhere else."""
    reflector.mode = "inverse"
    secret_file = write(tmp_path / "s", SECRET.encode())
    (tmp_path / "tokens.json").write_text(json.dumps({AGENT: "tok-1"}), encoding="utf-8")
    out = run_shim(tmp_path, reflector.base, ALL_HOOKS, secret_file=secret_file)  # asserts SECRET absent
    assert reflector.headers == [SECRET] * 4
    lines = [ln for ln in out.splitlines() if ln.startswith("FIELD ") and "shim loaded" not in ln]
    assert len(lines) == 4, out
    assert "heartbeat" in lines[0] and "killed=true status=s-<redacted> -> HALT" in lines[0]
    assert "checkin" in lines[1] and "killed=false status=s-<redacted> last_seen=l-<redacted>" in lines[1]
    assert "-> d-<redacted> shadow:w-<redacted>" in lines[2]
    assert lines[3] == f"FIELD spend {AGENT} MALFORMED reply (no OK/ESCALATE/BLOCK state) -> unmetered = STOP"


RETURNS = "; ".join(
    f"$o = @({hook}); $o[0..($o.Count - 2)]; 'RET ' + $o[-1]"
    for hook in (f"Get-FieldHeartbeat -Agent {AGENT}", f"Send-FieldCheckin -Agent {AGENT}",
                 f"Invoke-FieldCheck -Agent {AGENT} -Action 'canary.probe'", f"Send-FieldSpend -Agent {AGENT}")
)


def test_a_200_reply_that_is_not_json_fails_closed_in_every_hook(tmp_path, reflector):
    """An HTML login page or a text body answered with 200 used to read as
    `killed=false` (heartbeat, checkin returned True) and as not-BLOCK (spend
    returned True): fail-open. Under enforce every hook must return False, and
    the reflected secret in that body must not be printed."""
    reflector.mode = "text"
    secret_file = write(tmp_path / "s", SECRET.encode())
    (tmp_path / "tokens.json").write_text(json.dumps({AGENT: "tok-1"}), encoding="utf-8")
    out = run_shim(tmp_path, reflector.base, RETURNS, secret_file=secret_file)  # asserts SECRET absent
    assert reflector.headers == [SECRET] * 4
    assert [ln for ln in out.splitlines() if ln.startswith("RET ")] == ["RET False"] * 4, out
    assert f"FIELD heartbeat {AGENT} MALFORMED reply" in out
    assert f"FIELD checkin {AGENT} MALFORMED reply" in out
    assert f"FIELD spend {AGENT} MALFORMED reply" in out
    assert "killed=false" not in out


def test_a_json_heartbeat_without_a_boolean_killed_fails_closed(tmp_path, capture):
    """A JSON body with no `killed` field is not a verdict: `$null` is falsy, so
    without the guard it read as `killed=false` and the hook returned True."""
    capture.body = {"agent_id": AGENT, "status": "active", "checked_at": "2026-09-12T00:00:00+00:00"}
    secret_file = write(tmp_path / "s", SECRET.encode())
    out = run_shim(tmp_path, capture.base, RETURNS.split("; $o = @(Invoke-FieldCheck")[0],
                   secret_file=secret_file)
    assert [ln for ln in out.splitlines() if ln.startswith("RET ")] == ["RET False"] * 2, out


def test_redaction_uses_the_secret_the_request_was_sent_with(tmp_path, reflector):
    """The secret file is rotated WHILE the request is in flight. A redactor that
    re-read the file would look for the NEW value and print the reflected OLD
    one; the hook must redact with the state it built its header from."""
    rotated = "field-rest-rotated-secret-9e8d7c6b-never-printed"
    secret_file = write(tmp_path / "s", SECRET.encode())
    reflector.on_request = lambda: secret_file.write_bytes(rotated.encode())
    out = run_shim(tmp_path, reflector.base, f"Get-FieldHeartbeat -Agent {AGENT}",
                   secret_file=secret_file, forbidden=(rotated,))  # asserts SECRET absent
    assert reflector.headers == [SECRET]
    assert "status=s-<redacted> at=c-<redacted>" in out


@pytest.mark.parametrize("source", ["file", "env"])
@pytest.mark.parametrize("upstream", ["honest", "reflecting", "unreachable"])
def test_set_psdebug_trace_2_prints_no_secret(tmp_path, capture, reflector, upstream, source):
    """`Set-PSDebug -Trace 2` prints "! SET $name = value" for every variable
    assignment. The secret (and any response that could carry it back) must
    never sit in a named variable: file read, header build, redaction, the
    load-time state line and every hook, on the success and the error path."""
    if source == "file":
        secret_file, env_secret, sent = write(tmp_path / "s", SECRET.encode() + b"\r\n"), None, SECRET
    else:  # the env half: FIELD_SHARED_SECRET wins and must not sit in a variable either
        secret_file, env_secret, sent = None, ENV_SECRET, ENV_SECRET
    (tmp_path / "tokens.json").write_text(json.dumps({AGENT: "tok-1"}), encoding="utf-8")
    proxy = {"honest": capture.base, "reflecting": reflector.base,
             "unreachable": f"http://127.0.0.1:{_free_port()}"}[upstream]
    out = run_shim(tmp_path, proxy, ALL_HOOKS, secret_file=secret_file, env_secret=env_secret,
                   prelude="Set-PSDebug -Trace 2; ")  # asserts BOTH secrets absent
    assert "DEBUG:" in out and "! SET $" in out  # tracing really was on
    assert f"auth={source}" in out
    if upstream == "honest":
        assert [r.get("x-field-auth") for r in capture.requests] == [sent] * 4
    elif upstream == "reflecting":
        assert reflector.headers == [sent] * 4
        assert "<redacted>" in out
    else:
        failed = [ln for ln in out.splitlines()
                  if ln.startswith("FIELD ") and ("UNREACHABLE" in ln or "FAILED" in ln)]
        assert len(failed) == 4, out  # every hook took its error path
