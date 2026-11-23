"""Pins the README "Enforced vs. Declared" row: **No LLM in the report path**.

Two independent checks, because each alone has a blind spot:

* STATIC: an AST walk over every module of the ``incident_replay`` package
  (function-local imports included) and over the ``field_core`` modules it
  imports, transitively, finds no import of an LLM client (``field_core.llm``,
  ``anthropic``, ``openai``, ``force_gateway``) and no mention of the gateway or
  LLM environment variables or LLM API hosts. In the ``incident_replay`` package
  it also refuses any absolute http(s) URL literal outside a three-entry
  loopback allow-list, and any httpx/urllib/requests call handed a literal URL.
  Catches an LLM call on a branch the runtime test does not execute.
* RUNTIME: the whole report path (``/replay``, ``/replay/markdown``, the engine
  and ``render_markdown``) runs with every LLM client import refused and
  recorded, and every socket connection, datagram send and name lookup refused. The report must
  still complete and be correct. Catches a dynamic import or a call the AST walk
  cannot see (``importlib.import_module(name)``) on the executed path.

Both checks are shown to fail against a mutant (see the PR): an LLM import added
to ``engine.py`` fails the static test and, when on the executed path, the
runtime test.
"""

from __future__ import annotations

import ast
import importlib.abc
import importlib.util
import socket
import sys
from pathlib import Path

import pytest

from test_incident_replay import WINDOW, stack  # noqa: F401  (stack is a fixture)

import incident_replay

FORBIDDEN_MODULES = ("field_core.llm", "anthropic", "openai", "force_gateway")
FORBIDDEN_TEXT = (
    "FORCE_GATEWAY_URL",
    "FIELD_GATEWAY_URL",
    "ANTHROPIC_",
    "FIELD_LLM",
    "api.anthropic.com",
    "api.openai.com",
)

# The only absolute-URL string literals the incident_replay package may contain:
# the loopback defaults of the three sibling-service base URLs (FIELD_REPLAY_URL
# in cli.py, FIELD_LEDGER_URL and FIELD_DELEGATION_URL in engine.py), each
# overridable by an env var and each a first-party service on this host. Any
# other http:// or https:// literal is a hard-coded endpoint on a path the
# runtime test may not execute, so the static test refuses it.
ALLOWED_URL_LITERALS = {
    "http://127.0.0.1:8007",  # cli.py: FIELD_REPLAY_URL default
    "http://127.0.0.1:8002",  # engine.py: FIELD_LEDGER_URL default
    "http://127.0.0.1:8003",  # engine.py: FIELD_DELEGATION_URL default
}
HTTP_CLIENT_ROOTS = ("httpx", "urllib", "requests")


def _is_forbidden(name: str) -> bool:
    return any(name == m or name.startswith(m + ".") for m in FORBIDDEN_MODULES)


def _imports(tree: ast.AST) -> list[str]:
    """Every module name a tree imports, wherever the import statement sits."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
            # `from field_core import llm` imports the submodule field_core.llm
            names.extend(f"{node.module}.{a.name}" for a in node.names)
    return names


def _call_root(func: ast.expr) -> str | None:
    """`httpx.post` -> "httpx", `urllib.request.urlopen` -> "urllib", else None."""
    while isinstance(func, ast.Attribute):
        func = func.value
    return func.id if isinstance(func, ast.Name) else None


def _url_findings(tree: ast.AST) -> list[str]:
    """Absolute http(s) URL literals not on the allow-list, and any call into
    httpx/urllib/requests that is handed a literal string as its URL."""
    found: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith(("http://", "https://"))
            and node.value not in ALLOWED_URL_LITERALS
        ):
            found.append(f"URL literal {node.value!r}")
        if isinstance(node, ast.Call) and _call_root(node.func) in HTTP_CLIENT_ROOTS:
            args = list(node.args[:1]) + [k.value for k in node.keywords if k.arg == "url"]
            if any(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in args):
                found.append(f"{_call_root(node.func)} call with a literal URL")
    return found


def _source_of(module: str) -> Path | None:
    try:
        spec = importlib.util.find_spec(module)
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.origin or not spec.origin.endswith(".py"):
        return None
    return Path(spec.origin)


def _closure() -> dict[str, Path]:
    """incident_replay's own modules plus the field_core modules they reach."""
    pkg_dir = Path(incident_replay.__file__).parent
    found: dict[str, Path] = {
        f"incident_replay.{p.stem}" if p.stem != "__init__" else "incident_replay": p
        for p in sorted(pkg_dir.glob("*.py"))
    }
    assert len(found) >= 4, found  # __init__, api, cli, engine: the walk is not vacuous
    todo = list(found)
    while todo:
        mod = todo.pop()
        for name in _imports(ast.parse(found[mod].read_text(encoding="utf-8"))):
            if not name.startswith(("field_core", "incident_replay")) or name in found:
                continue
            path = _source_of(name)
            if path is not None:
                found[name] = path
                todo.append(name)
    return found


def test_static_no_llm_client_in_the_package_or_what_it_imports():
    closure = _closure()
    assert "incident_replay.engine" in closure
    assert "field_core.clients" in closure  # the walk really followed field_core
    bad: list[str] = []
    for mod, path in closure.items():
        text = path.read_text(encoding="utf-8")
        bad += [f"{mod} imports {n}" for n in _imports(ast.parse(text)) if _is_forbidden(n)]
        bad += [f"{mod} mentions {t}" for t in FORBIDDEN_TEXT if t in text]
        if mod.startswith("incident_replay"):  # the package itself, not field_core
            bad += [f"{mod}: {f}" for f in _url_findings(ast.parse(text))]
    assert bad == [], bad


def test_static_check_flags_a_hard_coded_llm_url_and_a_literal_url_call():
    # survivor #12: a hard-coded call on a branch no test executes
    post = ast.parse("def f():\n    httpx.post('https://api.anthropic.com/v1/messages')\n")
    assert any("URL literal" in f for f in _url_findings(post))
    assert any("httpx call with a literal URL" in f for f in _url_findings(post))
    # any absolute URL, not only known LLM hosts, and a bare scheme prefix
    assert _url_findings(ast.parse("U = 'http://example.invalid/x'"))
    assert _url_findings(ast.parse("U = 'https://' + host"))
    # urllib / requests with a literal URL, relative or not
    assert _url_findings(ast.parse("urllib.request.urlopen('/x')"))
    assert _url_findings(ast.parse("requests.get(url='/x')"))
    # what exists today stays allowed: loopback defaults, calls on a client object
    assert _url_findings(ast.parse("U = 'http://127.0.0.1:8002'")) == []
    assert _url_findings(ast.parse("client.get('/replay')")) == []
    assert _url_findings(ast.parse("httpx.Client(base_url=base)")) == []
    # the allow-list cannot go stale: every entry still appears in the package
    pkg = Path(incident_replay.__file__).parent
    text = "\n".join(p.read_text(encoding="utf-8") for p in pkg.glob("*.py"))
    assert all(u in text for u in ALLOWED_URL_LITERALS)


def test_static_check_would_see_a_lazy_llm_import():
    # the checker itself: a function-local import and a from-import both count
    lazy = ast.parse("def f():\n    import anthropic\n")
    assert [n for n in _imports(lazy) if _is_forbidden(n)] == ["anthropic"]
    sub = ast.parse("from field_core import llm\n")
    assert [n for n in _imports(sub) if _is_forbidden(n)] == ["field_core.llm"]


class _RefuseLLM(importlib.abc.MetaPathFinder):
    def __init__(self) -> None:
        self.attempts: list[str] = []

    def find_spec(self, name, path=None, target=None):
        if _is_forbidden(name):
            self.attempts.append(name)
            raise ImportError(f"LLM client import refused in the report path: {name}")
        return None


@pytest.fixture()
def no_llm_no_network(monkeypatch):
    finder = _RefuseLLM()
    for name in list(sys.modules):
        if _is_forbidden(name):
            monkeypatch.delitem(sys.modules, name)
    import field_core

    if hasattr(field_core, "llm"):
        monkeypatch.delattr(field_core, "llm")
    monkeypatch.setattr(sys, "meta_path", [finder, *sys.meta_path])

    refused: list[str] = []

    def _refuse(*args, **kwargs):
        refused.append(repr(args[:2]))
        raise OSError("network is off in the report path")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)
    monkeypatch.setattr(socket.socket, "sendto", _refuse)  # UDP with no connect
    monkeypatch.setattr(socket.socket, "sendmsg", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)
    return finder, refused


def test_guard_is_live(no_llm_no_network):
    finder, refused = no_llm_no_network
    with pytest.raises(ImportError):
        import anthropic  # noqa: F401
    with pytest.raises(ImportError):
        import field_core.llm  # noqa: F401
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", 9))
    assert finder.attempts == ["anthropic", "field_core.llm"]
    assert refused


def test_guard_refuses_unconnected_udp_sends(no_llm_no_network):
    # survivor #17: sendto / sendmsg need no connect(), so patching connect alone
    # leaves a datagram channel open
    _, refused = no_llm_no_network
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        with pytest.raises(OSError):
            s.sendto(b"x", ("127.0.0.1", 9))
        with pytest.raises(OSError):
            s.sendmsg([b"x"], [], 0, ("127.0.0.1", 9))
    assert len(refused) == 2


def test_report_completes_with_every_llm_client_and_all_networking_refused(
    stack, no_llm_no_network  # noqa: F811
):
    replay, _, _ = stack
    finder, refused = no_llm_no_network

    pm = replay.post("/replay", json={"agent_id": "invoicing-agent", **WINDOW}).json()
    md = replay.post("/replay/markdown", json={"agent_id": "invoicing-agent", **WINDOW})

    assert md.status_code == 200
    assert pm["ledger_integrity_ok"] is True
    assert pm["first_failure"]["clause_id"] == "D.scope"
    assert [t["event_type"] for t in pm["timeline"]][-1] == "kill.agent"
    assert "# Post-mortem" in md.text and "`D.scope`" in md.text
    assert "no LLM" in pm["method"] and "no LLM" in md.text
    assert finder.attempts == [], finder.attempts
    assert refused == [], refused
