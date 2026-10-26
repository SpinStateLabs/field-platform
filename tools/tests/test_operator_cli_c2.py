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
