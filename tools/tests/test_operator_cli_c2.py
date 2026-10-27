"""Phase G C-2: --operator-id / --operator-key-file on the tools and the service CLIs.

Design v0.4 section 2.5 and 9.5 (C-2, RT1-10, RT4-13). Three properties, each
asserted against what actually crosses the wire (a recording HTTP server), not
the tool's say-so:

1. every tool and guarded CLI verb accepts --operator-id and --operator-key-file
   and says so in --help (Stage 0 exit line: `--help | grep -- --operator-key-file`);
2. the key comes from the file, stripped, and is never printed, never accepted
   on argv, and a broken file named on the command line refuses (exit 2) before
   anything is sent;
3. the operator pair is sent ONLY on an explicit allowlist of guarded
   method + path pairs: never on a read, a heartbeat, a sentinel check, a ledger
   append, or a route whose method differs. The allowlists are checked against
   the services' own api.py: every entry is a guarded route, and no unguarded
   route matches any entry.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import estate_probe  # noqa: E402
import renew_token  # noqa: E402

PY = sys.executable
OP_ID = "test-operator"
#: a throwaway test value (never a real key); asserted absent from every output
OP_KEY = "test-op-key-NEVER-PRINT-c2-0123456789abcdef"
ENV_KEY = "test-env-op-key-NEVER-PRINT-c2-fedcba987654"
FILE_ENV_KEY = "test-file-env-op-key-NEVER-PRINT-c2-aaaabbbb"
OPERATOR_VARS = ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY", "FIELD_OPERATOR_KEY_FILE")

#: service source dir -> the Caddy prefix the estates route it under
SERVICE_PREFIX = {
    "agent-registry": "registry", "sealed-ledger": "ledger", "delegation-authority": "delegation",
    "kill-switch": "killswitch", "spend-governor": "governor", "lifecycle-manager": "lifecycle",
    "federation-broker": "federation", "conformance-sentinel": "sentinel",
}


# -- the services' own routes ------------------------------------------------------------

_ROUTE = re.compile(r'@app\.(get|post|put|patch|delete)\(\s*"([^"]+)"', re.S)


def api_routes() -> dict[str, list[tuple[str, str, bool]]]:
    """prefix -> [(METHOD, template, guarded)] read from each service's api.py.
    A route is guarded when its handler takes Depends(guard_*) or calls
    operator_auth.authorize_sync (the registry PATCH)."""
    out: dict[str, list[tuple[str, str, bool]]] = {}
    for svc, prefix in SERVICE_PREFIX.items():
        src = next((REPO / "services" / svc / "src").glob("*/api.py")).read_text(encoding="utf-8")
        hits = list(_ROUTE.finditer(src))
        rows = []
        for i, m in enumerate(hits):
            body = src[m.end(): hits[i + 1].start() if i + 1 < len(hits) else len(src)]
            guarded = "Depends(guard_" in body or "operator_auth.authorize_sync(" in body
            rows.append((m.group(1).upper(), m.group(2), guarded))
        out[prefix] = rows
    return out


def sample(template: str) -> str:
    return re.sub(r"\{[^}]+\}", "sample-id-1", template)


ROUTES = api_routes()


def test_the_route_scan_sees_the_guarded_routes_it_must():
    guarded = {(p, m, t) for p, rows in ROUTES.items() for m, t, g in rows if g}
    for row in [("killswitch", "POST", "/kill/{agent_id}"), ("killswitch", "POST", "/kill/domain/{domain}"),
                ("delegation", "POST", "/tokens"), ("delegation", "POST", "/tokens/{token_id}/revoke"),
                ("registry", "PATCH", "/agents/{agent_id}"), ("registry", "POST", "/agents"),
                ("governor", "PUT", "/caps/{agent_id}"), ("lifecycle", "POST", "/sweep")]:
        assert row in guarded, row
    assert ("delegation", "GET", "/tokens/{token_id}", False) not in guarded
    assert ("killswitch", "POST", "/heartbeat/{agent_id}") not in guarded


def _check_allowlist(name: str, routes, matches) -> None:
    """Every allowlist entry hits at least one guarded route; no unguarded route
    (any method) matches any entry. ``matches(prefix, method, path)``."""
    used = set()
    for prefix, rows in ROUTES.items():
        for method, template, guarded in rows:
            path = sample(template)
            for i, (m, rx) in enumerate(routes(prefix)):
                if m == method and rx.fullmatch(path):
                    assert guarded, f"{name}: allowlist entry {m} {rx.pattern} matches UNGUARDED {method} " \
                                    f"/{prefix}{template}"
                    used.add((prefix, i))
            if not guarded:
                assert not matches(prefix, method, path), f"{name}: sends the pair on {method} /{prefix}{template}"
    every = {(p, i) for p in ROUTES for i, _ in enumerate(routes(p))}
    assert every <= used, f"{name}: allowlist entries that are no guarded route: {sorted(every - used)}"


def _split_proxy_routes(table):
    """A proxy-root tool's allowlist (paths carry the service prefix) as per-prefix tables."""
    def routes(prefix):
        out = []
        for m, rx in table:
            head = rx.pattern.lstrip("/").split("/", 1)[0]
            if head == prefix:
                out.append((m, re.compile(rx.pattern[len(prefix) + 1:])))
        return out
    return routes


@pytest.mark.parametrize("tool", [estate_probe, renew_token])
def test_proxy_root_tool_allowlist_is_exactly_guarded_routes(tool):
    _check_allowlist(tool.__name__, _split_proxy_routes(tool.GUARDED_ROUTES),
                     lambda p, m, path: tool.is_guarded(m, f"/{p}{path}"))


def _calls(src: str, receiver: str) -> list[tuple[str, str]]:
    pat = re.compile(receiver + r'\.call\(\s*"(POST|PUT|PATCH|DELETE)",\s*f?"([^"?]+)')
    return [(m, re.sub(r"\{[^}]+\}", "sample-id-1", p)) for m, p in pat.findall(src)]


@pytest.mark.parametrize("tool,receiver", [(estate_probe, r"estate"), (renew_token, r"self\.api")])
def test_every_write_the_tool_sends_to_a_guarded_route_carries_the_pair_and_no_other(tool, receiver):
    src = Path(tool.__file__).read_text(encoding="utf-8")
    calls = _calls(src, receiver)
    assert calls, "no call sites found"
    guarded_samples = {(m, f"/{p}{sample(t)}") for p, rows in ROUTES.items() for m, t, g in rows if g}
    for method, path in calls:
        assert tool.is_guarded(method, path) == ((method, path) in guarded_samples), (method, path)


# -- a recording server ------------------------------------------------------------------


class Recorder:
    """Records (method, path, x-field-operator, x-field-operator-key, x-field-auth)."""

    def __init__(self, answer=None):
        self.seen: list[tuple[str, str, str | None, str | None, str | None]] = []
        self.answer = answer or (lambda method, path: (200, {}))
        rec = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _serve(self):
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
                rec.seen.append((self.command, self.path.split("?")[0], self.headers.get("x-field-operator"),
                                 self.headers.get("x-field-operator-key"), self.headers.get("x-field-auth")))
                status, body = rec.answer(self.command, self.path)
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _serve

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def carried(self) -> dict[tuple[str, str], tuple[str | None, str | None]]:
        return {(m, p): (op, key) for m, p, op, key, _ in self.seen}

    def close(self):
        self.server.shutdown()


@pytest.fixture
def rec():
    r = Recorder()
    yield r
    r.close()


@pytest.fixture
def clean_env(monkeypatch):
    for k in OPERATOR_VARS + ("FIELD_SHARED_SECRET",):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


@pytest.fixture
def key_file(tmp_path):
    p = tmp_path / "op.key"
    p.write_text(OP_KEY + "\r\n", encoding="utf-8")  # stripped: a CRLF line end is not part of the key
    return p


# -- 1. --help names the flags --------------------------------------------------------


@pytest.mark.parametrize("tool", ["estate_probe.py", "renew_token.py", "provision_ssl_agents.py"])
def test_tool_help_names_operator_id_and_operator_key_file(tool):
    env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_")}
    proc = subprocess.run([PY, str(TOOLS / tool), "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "--operator-key-file" in proc.stdout and "--operator-id" in proc.stdout, proc.stdout


def _cli_help(module: str, *verb: str) -> str:
    """The verb's --help as plain text. CI sets FORCE_COLOR/GITHUB_ACTIONS, and rich then
    styles option names with ANSI codes that split "--operator-key-file": colour is
    turned off and any escape sequence left is stripped."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("FIELD_") and k not in ("FORCE_COLOR", "PY_COLORS", "CLICOLOR_FORCE", "GITHUB_ACTIONS")}
    env.update(COLUMNS="200", NO_COLOR="1", TERM="dumb")
    proc = subprocess.run([PY, "-m", module, *verb, "--help"], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", proc.stdout)


@pytest.mark.parametrize("module,verb", [
    ("lifecycle_manager.cli", "provision"), ("lifecycle_manager.cli", "decommission"),
    ("lifecycle_manager.cli", "sweep"),
    ("kill_switch.cli", "agent"), ("kill_switch.cli", "domain"), ("kill_switch.cli", "drill"),
    ("kill_switch.cli", "revive"),
    ("delegation_authority.cli", "mint"), ("delegation_authority.cli", "revoke"),
])
def test_guarded_cli_verbs_help_names_operator_key_file(module, verb):
    out = _cli_help(module, verb)
    assert "--operator-key-file" in out and "--operator-id" in out, out


@pytest.mark.parametrize("tool,argv", [
    ("estate_probe.py", ["--operator-key", "a-value", "registry"]),
    ("renew_token.py", ["--agent", "a", "--env-file", "x", "--env-key", "K", "--check", "--operator-key", "a-value"]),
    ("provision_ssl_agents.py", ["--operator-key", "a-value"]),
])
def test_a_key_on_argv_is_not_an_option_not_even_as_an_abbreviation(tool, argv, rec):
    """No --operator-key option exists, and argparse abbreviations are off, so
    "--operator-key VALUE" is never read as --operator-key-file VALUE."""
    base = [] if tool == "provision_ssl_agents.py" else ["--base", rec.base]
    proc = subprocess.run([PY, str(TOOLS / tool), *base, *argv], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120,
                          env={**{k: v for k, v in os.environ.items() if not k.startswith("FIELD_")},
                               "FIELD_PROXY_URL": rec.base})
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "unrecognized arguments" in proc.stderr or "invalid choice" in proc.stderr, proc.stderr
    assert rec.seen == []


# -- 2/3. the proxy-root tools on the wire ---------------------------------------------


def test_estate_probe_sends_the_pair_only_on_allowlisted_guarded_routes(rec):
    e = estate_probe.Estate(rec.base, None, operator=(OP_ID, OP_KEY))
    for method, path in [("GET", "/registry/agents"), ("GET", "/registry/agents/canary-gb10"),
                         ("POST", "/killswitch/heartbeat/canary-gb10"), ("POST", "/sentinel/check"),
                         ("GET", "/killswitch/kill/canary-gb10"), ("POST", "/delegation/oauth/introspect"),
                         ("POST", "/killswitch/kill/canary-gb10"), ("POST", "/killswitch/revive/canary-gb10"),
                         ("POST", "/killswitch/drill/canary-gb10"), ("POST", "/registry/agents/canary-gb10/attest"),
                         ("POST", "/delegation/tokens/abc/revoke"), ("POST", "/ledger/events"),
                         ("GET", "/delegation/tokens/abc")]:
        e.call(method, path, {} if method == "POST" else None)
    carried = rec.carried()
    want = {("POST", "/killswitch/kill/canary-gb10"), ("POST", "/killswitch/revive/canary-gb10"),
            ("POST", "/killswitch/drill/canary-gb10"), ("POST", "/registry/agents/canary-gb10/attest"),
            ("POST", "/delegation/tokens/abc/revoke")}
    assert {k for k, v in carried.items() if v != (None, None)} == want
    assert all(carried[k] == (OP_ID, OP_KEY) for k in want)


def test_renew_token_sends_the_pair_only_on_mint_and_revoke(rec):
    api = renew_token.Api(rec.base, None, operator=(OP_ID, OP_KEY))
    for method, path in [("GET", "/delegation/tokens/abc"), ("GET", "/delegation/tokens?agent_id=x"),
                         ("POST", "/delegation/tokens"), ("POST", "/delegation/tokens/abc/revoke"),
                         ("POST", "/ledger/events")]:
        api.call(method, path, {} if method == "POST" else None)
    carried = rec.carried()
    assert {k for k, v in carried.items() if v != (None, None)} == {
        ("POST", "/delegation/tokens"), ("POST", "/delegation/tokens/abc/revoke")}


def test_estate_probe_cli_reads_the_key_file_and_never_prints_it(rec, clean_env, key_file):
    code, out = _run_tool("estate_probe.py", "--base", rec.base, "--operator-id", OP_ID, "--operator-key-file",
                          str(key_file), "registry")
    assert OP_KEY not in out
    assert rec.seen and all(op is None and key is None for _, _, op, key, _ in rec.seen)  # a read: no pair


def _run_tool(tool: str, *argv: str, env_extra: dict | None = None) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_")}
    env.update(env_extra or {})
    proc = subprocess.run([PY, str(TOOLS / tool), *argv], capture_output=True, env=env, timeout=120)
    out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    assert OP_KEY not in out and ENV_KEY not in out and FILE_ENV_KEY not in out, out
    return proc.returncode, out


@pytest.mark.parametrize("content,why", [(b"", "empty"), (b"two words\n", "not a single key token"),
                                         (b"\xff\xfe\x00", "not UTF-8"), (None, "unreadable")])
@pytest.mark.parametrize("tool,tail", [("estate_probe.py", ["registry"]),
                                       ("renew_token.py", ["--agent", "a", "--env-file", "x", "--env-key", "K",
                                                           "--check"])])
def test_a_broken_key_file_on_the_command_line_refuses_before_anything_is_sent(rec, tmp_path, content, why, tool,
                                                                                  tail):
    path = tmp_path / "op.key"
    if content is not None:
        path.write_bytes(content)
    head = ["--base", rec.base]
    code, out = _run_tool(tool, *head, "--operator-id", OP_ID, "--operator-key-file", str(path), *tail)
    assert code == 2, out
    assert f"--operator-key-file is {why}" in out, out  # refused for the file itself, not a warning
    assert rec.seen == []


@pytest.mark.parametrize("tool,tail", [("estate_probe.py", ["registry"]),
                                       ("renew_token.py", ["--agent", "a", "--env-file", "x", "--env-key", "K",
                                                           "--check"])])
def test_an_operator_id_without_a_key_refuses(rec, tool, tail):
    code, out = _run_tool(tool, "--base", rec.base, "--operator-id", OP_ID, *tail)
    assert code == 2, out
    assert rec.seen == []


def test_precedence_flag_file_then_env_file_then_env_key(tmp_path, clean_env, key_file):
    env_file = tmp_path / "env.key"
    env_file.write_text(FILE_ENV_KEY + "\n")
    clean_env.setenv("FIELD_OPERATOR", "env-op")
    clean_env.setenv("FIELD_OPERATOR_KEY", ENV_KEY)
    for mod in (estate_probe, renew_token):
        assert mod.operator_pair(None, None) == ("env-op", ENV_KEY)
        clean_env.setenv("FIELD_OPERATOR_KEY_FILE", str(env_file))
        assert mod.operator_pair(None, None) == ("env-op", FILE_ENV_KEY)
        assert mod.operator_pair(OP_ID, str(key_file)) == (OP_ID, OP_KEY)
        clean_env.delenv("FIELD_OPERATOR_KEY_FILE")


def test_an_unusable_env_key_file_sends_no_identity_and_never_falls_back(tmp_path, clean_env):
    clean_env.setenv("FIELD_OPERATOR", "env-op")
    clean_env.setenv("FIELD_OPERATOR_KEY", ENV_KEY)
    clean_env.setenv("FIELD_OPERATOR_KEY_FILE", str(tmp_path / "missing.key"))
    for mod in (estate_probe, renew_token):
        assert mod.operator_pair(None, None) is None


def test_renew_token_masks_the_operator_key_in_relayed_verify_output():
    lines = renew_token.scrub([f"verifier echoed {OP_KEY} here"], renew_token.secret_forms(OP_KEY), ())
    assert OP_KEY not in "".join(lines) and OP_KEY[:12] not in "".join(lines)


def test_renew_token_refuses_a_public_cleartext_base_when_a_key_is_present(clean_env, key_file):
    code, out = _run_tool("renew_token.py", "--base", "http://estate.example.com:18080", "--operator-id", OP_ID,
                          "--operator-key-file", str(key_file), "--agent", "a", "--env-file", "x", "--env-key", "K",
                          "--check")
    assert code == 2 and "cleartext" in out, out


def test_estate_probe_refuses_a_public_cleartext_base_when_a_key_is_present(clean_env, key_file):
    code, out = _run_tool("estate_probe.py", "--base", "http://estate.example.com:18080", "--operator-id", OP_ID,
                          "--operator-key-file", str(key_file), "registry")
    assert code == 2 and "cleartext" in out, out


# -- the service CLIs on the wire -----------------------------------------------------


def _invoke(app, args, env):
    from typer.testing import CliRunner

    result = CliRunner().invoke(app, args, env=env)
    out = result.output + (getattr(result, "stderr", "") if hasattr(result, "stderr_bytes") else "")
    assert OP_KEY not in out and ENV_KEY not in out, out
    return result.exit_code, out


def test_killswitch_cli_pair_only_on_guarded_verbs(rec, clean_env, key_file):
    from kill_switch import cli

    rec.answer = lambda m, p: (200, {"killed": False})
    env = {"FIELD_KILLSWITCH_URL": f"{rec.base}/killswitch", "FIELD_OPERATOR": OP_ID, "FIELD_OPERATOR_KEY": ENV_KEY}
    for args in (["heartbeat", "a1"], ["checkin", "a1"], ["liveness"]):
        assert _invoke(cli.app, args, env)[0] == 0
    assert rec.seen and all(op is None and key is None for _, _, op, key, _ in rec.seen)
    rec.seen.clear()
    for args in (["agent", "a1"], ["domain", "d1"], ["drill", "a1"], ["revive", "a1"]):
        code, out = _invoke(cli.app, [*args, "--operator", "Don", *(["--reason", "r"] if args[0] != "drill" else []),
                                      "--operator-id", OP_ID, "--operator-key-file", str(key_file)], env)
        assert code == 0, out
    assert [(m, p, op, key) for m, p, op, key, _ in rec.seen] == [
        ("POST", "/killswitch/kill/a1", OP_ID, OP_KEY), ("POST", "/killswitch/kill/domain/d1", OP_ID, OP_KEY),
        ("POST", "/killswitch/drill/a1", OP_ID, OP_KEY), ("POST", "/killswitch/revive/a1", OP_ID, OP_KEY)]


def test_killswitch_cli_env_pair_is_used_on_guarded_verbs(rec, clean_env):
    from kill_switch import cli

    env = {"FIELD_KILLSWITCH_URL": rec.base, "FIELD_OPERATOR": OP_ID, "FIELD_OPERATOR_KEY": ENV_KEY}
    assert _invoke(cli.app, ["agent", "a1", "--operator", "Don", "--reason", "r"], env)[0] == 0
    assert [(m, p, op, key) for m, p, op, key, _ in rec.seen] == [("POST", "/kill/a1", OP_ID, ENV_KEY)]


def test_killswitch_cli_broken_key_file_refuses_before_sending(rec, clean_env, tmp_path):
    from kill_switch import cli

    (tmp_path / "e.key").write_text("")
    code, out = _invoke(cli.app, ["agent", "a1", "--operator", "Don", "--reason", "r", "--operator-id", OP_ID,
                                  "--operator-key-file", str(tmp_path / "e.key")],
                        {"FIELD_KILLSWITCH_URL": rec.base})
    assert code == 2 and rec.seen == [], out
    assert "--operator-key-file is empty" in out, out


@pytest.mark.parametrize("module,guarded,unguarded", [
    ("kill_switch.cli", [("POST", "/kill/a1"), ("POST", "/kill/domain/d1"), ("POST", "/revive/a1"),
                         ("POST", "/drill/a1")],
     [("GET", "/heartbeat/a1"), ("POST", "/heartbeat/a1"), ("GET", "/liveness"), ("GET", "/kill/a1"),
      ("POST", "/kill/a1/extra")]),
    ("delegation_authority.cli", [("POST", "/tokens"), ("POST", "/tokens/t1/revoke")],
     [("GET", "/tokens"), ("GET", "/tokens/t1"), ("POST", "/introspect"), ("POST", "/oauth/introspect"),
      ("PUT", "/tokens")]),
])
def test_a_service_cli_client_holding_the_pair_still_sends_it_only_on_guarded_routes(module, guarded, unguarded,
                                                                                   rec, clean_env):
    """The verbs hand the pair only to the client of a guarded call; the client's own
    allowlist is the second fence, so a pair-holding client never puts it on a read."""
    import importlib

    mod = importlib.import_module(module)
    var = {"kill_switch.cli": "FIELD_KILLSWITCH_URL", "delegation_authority.cli": "FIELD_DELEGATION_URL"}[module]
    clean_env.setenv(var, f"{rec.base}/svc")
    with mod._client((OP_ID, OP_KEY)) as http:
        for method, path in guarded + unguarded:
            http.request(method, f"{rec.base}/svc{path}")
    carried = {k for k, v in rec.carried().items() if v != (None, None)}
    assert carried == {(m, f"/svc{p}") for m, p in guarded}


def test_delegation_cli_pair_only_on_mint_and_revoke(rec, clean_env, key_file):
    from delegation_authority import cli

    rec.answer = lambda m, p: ((201 if p.rstrip("/").endswith("/tokens") and m == "POST" else 200),
                               ([] if m == "GET" else {"active": True}))
    env = {"FIELD_DELEGATION_URL": f"{rec.base}/delegation", "FIELD_OPERATOR": OP_ID, "FIELD_OPERATOR_KEY": ENV_KEY}
    for args in (["list"], ["introspect", "t1"], ["oauth-introspect", "t1"]):
        assert _invoke(cli.app, args, env)[0] == 0
    assert rec.seen and all(op is None and key is None for _, _, op, key, _ in rec.seen)
    rec.seen.clear()
    op = ["--operator-id", OP_ID, "--operator-key-file", str(key_file)]
    assert _invoke(cli.app, ["mint", "a1", "--granted-by", OP_ID, "--scope", "s", *op], env)[0] == 0
    assert _invoke(cli.app, ["revoke", "t1", *op], env)[0] == 0
    assert [(m, p, o, k) for m, p, o, k, _ in rec.seen] == [
        ("POST", "/delegation/tokens", OP_ID, OP_KEY), ("POST", "/delegation/tokens/t1/revoke", OP_ID, OP_KEY)]


def test_lifecycle_clients_send_the_pair_only_on_guarded_routes(rec, clean_env, monkeypatch):
    from lifecycle_manager import cli

    for var, prefix in (("FIELD_REGISTRY_URL", "registry"), ("FIELD_LEDGER_URL", "ledger"),
                        ("FIELD_DELEGATION_URL", "delegation"), ("FIELD_GOVERNOR_URL", "governor"),
                        ("FIELD_KILLSWITCH_URL", "killswitch")):
        monkeypatch.setenv(var, f"{rec.base}/{prefix}")
    monkeypatch.setenv("FIELD_OPERATOR", "env-op")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", ENV_KEY)  # the env pair must not leak onto reads either
    rec.answer = lambda m, p: (201 if p.endswith("/events") else 200, {"agent_id": "a1", "status": "active"})
    c = cli.estate_clients((OP_ID, OP_KEY))
    c["registry"].get_agent("a1")
    c["registry"].list_agents()
    c["registry"].set_status("a1", "retired")
    c["registry_http"].post("/agents", json={})
    c["registry_http"].get("/agents/a1")
    c["delegation"].get("/tokens")
    c["delegation"].post("/tokens", json={})
    c["delegation"].post("/tokens/t1/revoke")
    c["governor"].put("/caps/a1", json={})
    c["governor"].get("/rate-limits/a1")
    c["governor"].put("/rate-limits/a1", json={})
    c["killswitch"].post("/kill/a1", json={})
    c["killswitch"].post("/heartbeat/a1")
    c["ledger"].append("lifecycle.test", {"x": 1}, "a1")
    carried = {k for k, v in rec.carried().items() if v != (None, None)}
    assert carried == {("PATCH", "/registry/agents/a1"), ("POST", "/registry/agents"),
                       ("POST", "/delegation/tokens"), ("POST", "/delegation/tokens/t1/revoke"),
                       ("PUT", "/governor/caps/a1"), ("PUT", "/governor/rate-limits/a1"),
                       ("POST", "/killswitch/kill/a1")}
    assert all(v == (OP_ID, OP_KEY) for k, v in rec.carried().items() if k in carried)


@pytest.mark.parametrize("module,attr", [("kill_switch.cli", None), ("delegation_authority.cli", None),
                                         ("lifecycle_manager.cli", "ALL")])
def test_service_cli_allowlists_are_exactly_guarded_routes(module, attr):
    import importlib

    mod = importlib.import_module(module)
    if attr is None:
        prefix = {"kill_switch.cli": "killswitch", "delegation_authority.cli": "delegation"}[module]
        tables = {prefix: mod.GUARDED_ROUTES}
    else:
        tables = mod.GUARDED_ROUTES
    _check_allowlist(module, lambda p: list(tables.get(p, ())),
                     lambda p, m, path: any(mm == m and rx.fullmatch(path) for mm, rx in tables.get(p, ())))


def test_provision_ssl_agents_sends_the_pair_only_on_guarded_routes(rec, clean_env, key_file, monkeypatch):
    import importlib.util

    monkeypatch.setenv("FIELD_PROXY_URL", rec.base)
    spec = importlib.util.spec_from_file_location("provision_ssl_agents_c2", TOOLS / "provision_ssl_agents.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    http = mod.client((OP_ID, OP_KEY))
    for method, path in [("GET", "/registry/health"), ("GET", "/killswitch/heartbeat/a1"),
                         ("POST", "/sentinel/check"), ("GET", "/ledger/verify"), ("POST", "/registry/agents"),
                         ("PATCH", "/registry/agents/a1"), ("PUT", "/governor/caps/a1"),
                         ("PUT", "/governor/rate-limits/a1"), ("POST", "/delegation/tokens"),
                         ("GET", "/delegation/tokens"), ("POST", "/ledger/events")]:
        http.request(method, f"{rec.base}{path}", json={} if method != "GET" else None)
    carried = {k for k, v in rec.carried().items() if v != (None, None)}
    assert carried == {("POST", "/registry/agents"), ("PATCH", "/registry/agents/a1"), ("PUT", "/governor/caps/a1"),
                       ("PUT", "/governor/rate-limits/a1"), ("POST", "/delegation/tokens")}
    _check_allowlist("provision_ssl_agents", _split_proxy_routes(mod.GUARDED_ROUTES),
                     lambda p, m, path: mod.is_guarded(m, f"/{p}{path}"))


# -- review round 1 (PG0-CLI-R1-04, -05, -06, -08, -10) ------------------------------------


def _provision_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("provision_ssl_agents_r1", TOOLS / "provision_ssl_agents.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _operator_pair_copies() -> dict:
    """The six hand-duplicated operator_pair copies (their block comments say so)."""
    from delegation_authority import cli as delegation_cli
    from kill_switch import cli as killswitch_cli
    from lifecycle_manager import cli as lifecycle_cli

    return {"renew_token": renew_token.operator_pair, "estate_probe": estate_probe.operator_pair,
            "provision_ssl_agents": _provision_module().operator_pair,
            "kill_switch.cli": killswitch_cli.operator_pair,
            "delegation_authority.cli": delegation_cli.operator_pair,
            "lifecycle_manager.cli": lifecycle_cli.operator_pair}


REFUSED = "REFUSED"


def _outcome(fn, operator_id, key_file):
    """fn's pair, or REFUSED (each copy refuses its own way, all with exit 2), plus the refusal text."""
    try:
        return fn(operator_id, key_file), ""
    except renew_token.Refused as exc:
        return REFUSED, str(exc)
    except SystemExit as exc:
        assert exc.code == 2, exc.code
        return REFUSED, ""
    except Exception as exc:  # typer.Exit / click.exceptions.Exit
        if type(exc).__name__ == "Exit" and getattr(exc, "exit_code", None) == 2:
            return REFUSED, ""
        raise


@pytest.mark.parametrize("copy", ["renew_token", "estate_probe", "provision_ssl_agents", "kill_switch.cli",
                                  "delegation_authority.cli", "lifecycle_manager.cli"])
@pytest.mark.parametrize("given", ["id-only", "key-file-only"])
def test_every_operator_pair_copy_refuses_an_operator_id_or_a_key_file_alone(copy, given, clean_env, key_file,
                                                                             capsys):
    """PG0-CLI-R1-04: without this refusal `--operator-id job-renewal-rog` with a forgotten key
    file runs with NO identity (and renew_token keeps the old grantor). Pinned on all six copies,
    in-process, so no other refusal (a missing store, a bad flag) can make it pass."""
    fn = _operator_pair_copies()[copy]
    capsys.readouterr()
    args = (OP_ID, None) if given == "id-only" else (None, str(key_file))
    got, text = _outcome(fn, *args)
    text += capsys.readouterr().err
    assert got == REFUSED, got
    assert "go together" in text and OP_KEY not in text, text


def test_the_six_operator_pair_copies_agree_on_every_input(tmp_path, clean_env, key_file, capsys):
    """The copies are hand-duplicated: one table, one expected answer per row, all six must give it."""
    env_file = tmp_path / "env.key"
    env_file.write_text(FILE_ENV_KEY + "\n")
    broken = tmp_path / "broken.key"
    broken.write_text("two words\n")
    kf = str(key_file)
    rows = [  # (env, operator_id, key_file, expected)
        ({}, None, None, None),
        ({"FIELD_OPERATOR": "env-op", "FIELD_OPERATOR_KEY": ENV_KEY}, None, None, ("env-op", ENV_KEY)),
        ({"FIELD_OPERATOR": "env-op", "FIELD_OPERATOR_KEY": ENV_KEY}, OP_ID, kf, (OP_ID, OP_KEY)),
        ({"FIELD_OPERATOR": "env-op", "FIELD_OPERATOR_KEY": ENV_KEY, "FIELD_OPERATOR_KEY_FILE": str(env_file)},
         None, None, ("env-op", FILE_ENV_KEY)),
        ({"FIELD_OPERATOR": "env-op", "FIELD_OPERATOR_KEY": ENV_KEY,
          "FIELD_OPERATOR_KEY_FILE": str(tmp_path / "missing.key")}, None, None, None),
        ({"FIELD_OPERATOR_KEY_FILE": str(broken)}, OP_ID, kf, (OP_ID, OP_KEY)),
        ({"FIELD_OPERATOR": "env-op"}, None, None, None),
        ({"FIELD_OPERATOR_KEY": ENV_KEY}, None, None, None),
        ({}, OP_ID, None, REFUSED),
        ({}, None, kf, REFUSED),
        ({"FIELD_OPERATOR": "env-op"}, None, kf, ("env-op", OP_KEY)),
        ({"FIELD_OPERATOR_KEY": ENV_KEY}, OP_ID, None, (OP_ID, ENV_KEY)),
        ({}, "not an id", kf, REFUSED),
        ({"FIELD_OPERATOR": "env-op", "FIELD_OPERATOR_KEY": "two words"}, None, None, REFUSED),
    ]
    copies = _operator_pair_copies()
    for i, (env, operator_id, key, want) in enumerate(rows):
        for var in OPERATOR_VARS:
            clean_env.delenv(var, raising=False)
        for var, value in env.items():
            clean_env.setenv(var, value)
        answers = {name: _outcome(fn, operator_id, key)[0] for name, fn in copies.items()}
        assert all(got == want for got in answers.values()), (i, want, answers)
    assert OP_KEY not in "".join(capsys.readouterr())


def _json_store(tmp_path) -> Path:
    store = tmp_path / "tokens.json"
    store.write_text(json.dumps({"a": "00000000-0000-4000-8000-000000000001"}), encoding="utf-8")
    return store


def test_renew_token_cli_refuses_an_operator_id_without_a_key_before_reading_the_store(rec, clean_env, tmp_path):
    """The store exists and is valid, so only the id-without-key rule can refuse (PG0-CLI-R1-04)."""
    store = _json_store(tmp_path)
    code, out = _run_tool("renew_token.py", "--base", rec.base, "--operator-id", OP_ID, "--agent", "a",
                          "--json-file", str(store), "--json-key", "a", "--check")
    assert code == 2 and "go together" in out, out
    assert rec.seen == []


def test_renew_token_log_first_line_names_the_phase_g_revision(rec, clean_env, tmp_path):
    """PG0-CLI-R1-08: VERSION stays 1.5 (test_ssl_renewal pins "renew_token 1.5 "), and the
    revision word after it tells this file's log apart from the installed 1.5's."""
    store = _json_store(tmp_path)
    code, out = _run_tool("renew_token.py", "--base", rec.base, "--agent", "a", "--json-file", str(store),
                          "--json-key", "a", "--check")
    first = out.splitlines()[0]
    assert first.startswith("renew_token 1.5 phase-g "), out
    assert first.startswith("renew_token 1.5 ")  # the test_ssl_renewal pin still holds


def test_estate_probe_redacts_the_operator_key_from_what_it_prints(rec, clean_env, key_file):
    """PG0-CLI-R1-05: a registry row whose id IS the key (printable, so _plain passes it) must
    reach stdout as <redacted>: the stream redactor carries the operator key, not only the secret."""
    rec.answer = lambda m, p: (200, [{"agent_id": OP_KEY, "domain": "d", "status": "active"}])
    code, out = _run_tool("estate_probe.py", "--base", rec.base, "--operator-id", OP_ID, "--operator-key-file",
                          str(key_file), "registry")  # _run_tool asserts the key is absent
    assert code == 0, out
    assert "<redacted> d active" in out, out


@pytest.mark.parametrize("module", ["kill_switch.cli", "delegation_authority.cli", "lifecycle_manager.cli"])
def test_service_cli_apps_never_print_locals_on_an_uncaught_exception(module):
    """PG0-CLI-R1-06: the verbs hold (id, key) in a local; typer>=0.12 is allowed, and the
    default of pretty_exceptions_show_locals is not the same in every version. The app must say
    False itself, not inherit the installed typer's default."""
    import ast
    import importlib

    mod = importlib.import_module(module)
    assert mod.app.pretty_exceptions_show_locals is False
    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    calls = [node.value for node in tree.body if isinstance(node, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "app" for t in node.targets)]
    assert len(calls) == 1 and isinstance(calls[0], ast.Call), "app = typer.Typer(...) not found"
    kw = {k.arg: k.value for k in calls[0].keywords}
    assert "pretty_exceptions_show_locals" in kw, "the app relies on typer's default"
    assert isinstance(kw["pretty_exceptions_show_locals"], ast.Constant)
    assert kw["pretty_exceptions_show_locals"].value is False


def _help_at(width: int, *cmd: str) -> str:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("FIELD_") and k not in ("FORCE_COLOR", "PY_COLORS", "CLICOLOR_FORCE", "GITHUB_ACTIONS")}
    env.update(COLUMNS=str(width), NO_COLOR="1", TERM="dumb")
    proc = subprocess.run([PY, *cmd, "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return re.sub(chr(27) + r"\[[0-9;]*[A-Za-z]", "", proc.stdout)


@pytest.mark.parametrize("cmd", [
    ("-m", "lifecycle_manager.cli", "provision"), ("-m", "lifecycle_manager.cli", "decommission"),
    ("-m", "lifecycle_manager.cli", "sweep"),
    ("-m", "kill_switch.cli", "agent"), ("-m", "kill_switch.cli", "domain"), ("-m", "kill_switch.cli", "drill"),
    ("-m", "kill_switch.cli", "revive"),
    ("-m", "delegation_authority.cli", "mint"), ("-m", "delegation_authority.cli", "revoke"),
    (str(TOOLS / "estate_probe.py"),), (str(TOOLS / "renew_token.py"),), (str(TOOLS / "provision_ssl_agents.py"),),
])
def test_help_names_operator_key_file_whole_on_a_narrow_terminal(cmd):
    """PG0-CLI-R1-10: the Stage 0 exit line greps --help for --operator-key-file. rich cuts the
    option column to "--operator-ke..." at 60 columns, so the command's own help text names the
    flag in full and 60 columns must still match (the width under docker exec -T is UNVERIFIED)."""
    out = _help_at(60, *cmd)
    assert "--operator-key-file" in out and "--operator-id" in out, out


# -- review round 2 LOW pins (PG0-CLI-R2-01, -02, -03, -05; Phase G Stage 0 follow-ups) ---------------


def test_renew_token_redacts_the_operator_key_from_a_line_it_prints_itself(rec, clean_env, key_file, tmp_path):
    """PG0-CLI-R2-01: renew_token's stream redactor (``Redact``) carries the operator key, not only
    the perimeter secret. Here the store's key name IS the operator key, and the tool's first log
    line prints the store's key name: it must reach the output as <redacted> (_run_tool also
    asserts the key appears nowhere), with no secret configured at all."""
    store = tmp_path / "tokens.json"
    store.write_text(json.dumps({OP_KEY: "00000000-0000-4000-8000-000000000001"}), encoding="utf-8")
    code, out = _run_tool("renew_token.py", "--base", rec.base, "--operator-id", OP_ID, "--operator-key-file",
                          str(key_file), "--agent", "a", "--json-file", str(store), "--json-key", OP_KEY, "--check")
    first = out.splitlines()[0]
    assert first.startswith("renew_token 1.5 ") and f"key <redacted>" in first, out


def _lifecycle_env(rec) -> dict[str, str]:
    return {var: f"{rec.base}/{prefix}" for var, prefix in (
        ("FIELD_REGISTRY_URL", "registry"), ("FIELD_LEDGER_URL", "ledger"), ("FIELD_DELEGATION_URL", "delegation"),
        ("FIELD_GOVERNOR_URL", "governor"), ("FIELD_KILLSWITCH_URL", "killswitch"))}


def test_lifecycle_decommission_local_gate_authenticates_the_flag_pair_not_the_environment(rec, clean_env, key_file,
                                                                                         tmp_path):
    """PG0-CLI-R2-02 (M15): under REQUIRE, with a clean environment (no FIELD_OPERATOR*), the
    local decommission gate must authenticate the pair the FLAGS name. Gating on the environment
    instead refuses at the gate (exit 2) before anything is sent."""
    from field_core import operator_auth as oa
    from lifecycle_manager import cli

    ops = tmp_path / "operators.json"
    ops.write_text(json.dumps([{"operator_id": OP_ID, "key_sha256": oa.key_sha256(OP_KEY), "status": "active",
                                "scopes": ["decommission", "revoke", "kill"]}]), encoding="utf-8")
    agent = {"agent_id": "a1", "name": "a1", "owner": "O", "domain": "d", "status": "active",
             "created_at": "2026-10-01T00:00:00+00:00", "updated_at": "2026-10-01T00:00:00+00:00"}
    rec.answer = lambda m, p: ((200, agent) if p.split("?")[0].startswith("/registry/agents/")
                               else (200, []) if m == "GET" else (201, {}) if p.endswith("/events") else (200, agent))
    env = {**_lifecycle_env(rec), "FIELD_OPERATOR_REGISTRY": str(ops), "FIELD_OPERATOR_REQUIRE": "1"}
    code, out = _invoke(cli.app, ["decommission", "a1", "--by", "Don", "--reason", "r", "--operator-id", OP_ID,
                                  "--operator-key-file", str(key_file)], env)
    assert code != 2 and "operator auth refused" not in out, out
    assert ("PATCH", "/registry/agents/a1") in rec.carried(), rec.seen
    assert rec.carried()[("PATCH", "/registry/agents/a1")] == (OP_ID, OP_KEY)


def test_lifecycle_sweep_auto_kill_carries_the_flag_pair_on_the_kill(rec, clean_env, key_file, tmp_path):
    """PG0-CLI-R2-02 (M22): `lifecycle sweep --auto-kill-orphans --operator-id/--operator-key-file`
    sends the flag pair on the kill-switch POST (and on nothing else it calls)."""
    from lifecycle_manager import cli

    roster = tmp_path / "owners.csv"
    roster.write_text("owner\nDon Hagell\n", encoding="utf-8")
    orphan = {"agent_id": "orph", "name": "orph", "owner": "Nobody", "domain": "d", "status": "active",
              "created_at": "2026-10-20T00:00:00+00:00", "updated_at": "2026-10-20T00:00:00+00:00"}

    def answer(m, p):
        path = p.split("?")[0]
        if m == "GET" and path == "/registry/agents":
            return 200, [orphan]
        if m == "GET" and path == "/delegation/tokens":
            return 200, []
        if path.endswith("/events"):
            return 201, {}
        return 200, {}

    rec.answer = answer
    code, out = _invoke(cli.app, ["sweep", "--roster", str(roster), "--auto-kill-orphans", "--operator-id", OP_ID,
                                  "--operator-key-file", str(key_file)], _lifecycle_env(rec))
    assert code == 3, out                                            # an orphan was found
    carried = {k: v for k, v in rec.carried().items() if v != (None, None)}
    assert carried == {("POST", "/killswitch/kill/orph"): (OP_ID, OP_KEY)}, rec.seen


def test_provision_ssl_agents_main_hands_the_flag_pair_to_the_engine_client(rec, clean_env, key_file, monkeypatch):
    """PG0-CLI-R2-02 (M20): main() builds the lifecycle engine's client from the --operator-id /
    --operator-key-file pair. The engine is stopped at construction; the client it was handed
    then sends one guarded and one unguarded request to the recorder."""
    mod = _provision_module()
    captured = {}

    class Stop(Exception):
        pass

    def build_engine(http):
        captured["http"] = http
        raise Stop

    monkeypatch.setattr(mod, "health", lambda: None)
    monkeypatch.setattr(mod, "build_engine", build_engine)
    with pytest.raises(Stop):
        mod.main(["--operator-id", OP_ID, "--operator-key-file", str(key_file)])
    http = captured["http"]
    http.request("POST", f"{rec.base}/registry/agents", json={})
    http.request("GET", f"{rec.base}/registry/agents")
    assert rec.carried() == {("POST", "/registry/agents"): (OP_ID, OP_KEY), ("GET", "/registry/agents"): (None, None)}


@pytest.mark.parametrize("copy", ["renew_token", "estate_probe", "provision_ssl_agents", "kill_switch.cli",
                                  "delegation_authority.cli", "lifecycle_manager.cli"])
@pytest.mark.parametrize("via", ["flag", "env-key-file"])
def test_every_operator_pair_copy_accepts_a_key_file_with_a_bom_and_crlf(copy, via, clean_env, tmp_path):
    """PG0-CLI-R2-03: Windows PowerShell 5.1 (`Set-Content -Encoding utf8`) writes a BOM, and
    job-renewal-rog's key is generated on the PC. Every copy reads the key file as utf-8-sig and
    strips the line end, whether the file is named by --operator-key-file or FIELD_OPERATOR_KEY_FILE."""
    p = tmp_path / "bom.key"
    p.write_bytes(b"\xef\xbb\xbf" + OP_KEY.encode("ascii") + b"\r\n")
    fn = _operator_pair_copies()[copy]
    if via == "flag":
        got, text = _outcome(fn, OP_ID, str(p))
    else:
        clean_env.setenv("FIELD_OPERATOR", OP_ID)
        clean_env.setenv("FIELD_OPERATOR_KEY_FILE", str(p))
        got, text = _outcome(fn, None, None)
    assert got == (OP_ID, OP_KEY), (got, text)


def test_estate_probe_call_without_auth_never_attaches_the_operator_pair(rec):
    """PG0-CLI-R2-05: ``Estate.call(..., auth=False)`` is an unauthenticated call. It drops the
    perimeter secret and must drop the operator pair too, even on a guarded route."""
    assert estate_probe.is_guarded("POST", "/killswitch/kill/a1")
    e = estate_probe.Estate(rec.base, "not-a-real-secret-r205", operator=(OP_ID, OP_KEY))
    e.call("POST", "/killswitch/kill/a1", {}, auth=False)
    e.call("POST", "/killswitch/kill/a1", {})
    assert [(op, key, auth) for _, _, op, key, auth in rec.seen] == [
        (None, None, None), (OP_ID, OP_KEY, "not-a-real-secret-r205")]


def test_lifecycle_decommission_as_don_admin_is_act_first_when_revoke_and_kill_are_refused(rec, clean_env,
                                                                                           key_file, tmp_path):
    """PG0-CLI-R2-07: the decommission docstring and the runbook say that as don-admin (design
    2.2.1: decommission, no revoke, no kill) the revoke and the kill are refused (403) and the run
    still retires the agent, act-first, exiting 1. The two 403s come from the recorder standing in
    for the services (their scope tables are pinned in the service suites); this pins what the
    CLI and the engine do with them: the retire PATCH is still sent, with the don-admin pair, the
    report says retired / not killed / tokens unrevoked, and the exit code is 1."""
    from field_core import operator_auth as oa
    from lifecycle_manager import cli

    ops = tmp_path / "operators.json"
    ops.write_text(json.dumps([{"operator_id": "don-admin", "key_sha256": oa.key_sha256(OP_KEY), "status": "active",
                                "scopes": ["registry_edit", "decommission", "rotate", "retention", "hold", "export",
                                           "federation", "sweep"]}]), encoding="utf-8")
    agent = {"agent_id": "a1", "name": "a1", "owner": "O", "domain": "d", "status": "active",
             "created_at": "2026-10-01T00:00:00+00:00", "updated_at": "2026-10-01T00:00:00+00:00"}
    refused = (403, {"detail": "operator not authorised"})

    def answer(m, p):
        path = p.split("?")[0]
        if m == "GET" and path == "/registry/agents/a1":
            return 200, agent
        if m == "GET" and path == "/delegation/tokens":
            return 200, [{"token_id": "t1", "agent_id": "a1", "revoked": False}]
        if (m, path) in (("POST", "/delegation/tokens/t1/revoke"), ("POST", "/killswitch/kill/a1")):
            return refused
        if m == "PATCH" and path == "/registry/agents/a1":
            return 200, {**agent, "status": "retired"}
        return (201, {}) if path.endswith("/events") else (200, {})

    rec.answer = answer
    out_file = tmp_path / "report.json"
    env = {**_lifecycle_env(rec), "FIELD_OPERATOR_REGISTRY": str(ops), "FIELD_OPERATOR_REQUIRE": "1"}
    code, out = _invoke(cli.app, ["decommission", "a1", "--by", "Don", "--reason", "r", "--operator-id", "don-admin",
                                  "--operator-key-file", str(key_file), "--out", str(out_file)], env)
    assert code == 1 and "act-first" in out, out
    report = json.loads(out_file.read_text(encoding="utf-8"))
    steps = {s["step"]: s for s in report["steps"]}
    assert report["retired"] is True and report["killed"] is False and report["tokens_revoked"] == []
    assert [f["http_status"] for f in report["revoke_failures"]] == [403]
    assert (steps["revoke"]["outcome"], steps["kill"]["outcome"], steps["kill"]["http_status"],
            steps["retire"]["outcome"]) == ("failed", "failed", 403, "ok"), report["steps"]
    sent = [(m, p) for m, p, _, _, _ in rec.seen]
    assert sent.index(("PATCH", "/registry/agents/a1")) > sent.index(("POST", "/killswitch/kill/a1"))
    assert rec.carried()[("PATCH", "/registry/agents/a1")] == ("don-admin", OP_KEY)
