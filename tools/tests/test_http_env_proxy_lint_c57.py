"""C-57 (reviewer C-55): non-test code must not build an HTTP client that reads the process's proxy environment.

httpx and urllib both honour `http_proxy` / `HTTP_PROXY` / `ALL_PROXY` by default, so a request that carries
`x-field-auth`, an operator key or an API key can be sent to a proxy in clear. This is an AST scan (like
topology_lint) over the non-test Python of the repo:

* `httpx.Client|AsyncClient|get|post|put|patch|delete|head|options|request|stream(...)` must pass `trust_env=False`;
* `urllib.request.urlopen(...)` and `urlretrieve(...)` are always a finding (the default opener reads the proxy environment);
* `urllib.request.build_opener(...)` must be given `ProxyHandler({})`;
* a class whose base is `httpx.Client` / `httpx.AsyncClient` is a finding (call name `httpx.<Base>.subclass`) unless its
  `__init__` passes `trust_env=False` (C-476, reviewer C-462 F-C462-2: a subclass is built where the scan cannot see it).

Sites not yet migrated are listed in `http_env_proxy_allowlist.txt` as `path::function::call = count`. The list must
equal the scan: a new site fails, and so does an entry whose site was fixed (so the list only shrinks).
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = Path(__file__).with_name("http_env_proxy_allowlist.txt")
SCAN_ROOTS = ["packages", "services", "tools", "plugins", "integration", "defence-shield"]
SKIP_DIRS = {"tests", "node_modules", "__pycache__", ".venv", "venv", ".git", "build", "dist"}
HTTPX_CALLS = {"Client", "AsyncClient", "get", "post", "put", "patch", "delete", "head", "options", "request", "stream"}


def _is_test_file(path: Path) -> bool:
    return path.name.startswith("test_") or path.name == "conftest.py" or any(p in SKIP_DIRS for p in path.parts)


def python_files() -> list[Path]:
    out: list[Path] = []
    for top in SCAN_ROOTS:
        base = ROOT / top
        if base.is_dir():
            out += [p for p in base.rglob("*.py") if not _is_test_file(p.relative_to(ROOT))]
    return sorted(out)


class _Scan(ast.NodeVisitor):
    def __init__(self) -> None:
        self.alias: dict[str, str] = {}   # local name -> dotted origin
        self.stack: list[str] = []
        self.found: Counter[tuple[str, str]] = Counter()   # (function, call)

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            if a.asname:
                self.alias[a.asname] = a.name
            else:
                self.alias[a.name.split(".")[0]] = a.name.split(".")[0]
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.level == 0:
            for a in node.names:
                self.alias[a.asname or a.name] = f"{node.module}.{a.name}"
        self.generic_visit(node)

    def _scoped(self, node: ast.AST, name: str) -> None:
        self.stack.append(name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = lambda self, n: self._scoped(n, n.name)  # noqa: E731

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        for base in node.bases:
            name = self.dotted(base)
            if name in ("httpx.Client", "httpx.AsyncClient") and not self._init_disables_env(node):
                self.found[(".".join(self.stack), f"{name}.subclass")] += 1
        self.generic_visit(node)
        self.stack.pop()

    @staticmethod
    def _passes_trust_env_false(call: ast.Call) -> bool:
        return any(k.arg == "trust_env" and isinstance(k.value, ast.Constant) and k.value.value is False
                   for k in call.keywords)

    def _init_disables_env(self, node: ast.ClassDef) -> bool:
        return any(isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name == "__init__"
                   and any(isinstance(c, ast.Call) and self._passes_trust_env_false(c) for c in ast.walk(f))
                   for f in node.body)

    def dotted(self, node: ast.AST) -> str | None:
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name) or node.id not in self.alias:
            return None
        return ".".join([self.alias[node.id], *reversed(parts)])

    def visit_Call(self, node: ast.Call) -> None:
        name = self.dotted(node.func)
        bad = False
        if name and name.startswith("httpx.") and name.split(".", 1)[1] in HTTPX_CALLS:
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            ok = isinstance(kw.get("trust_env"), ast.Constant) and kw["trust_env"].value is False
            bad = not ok
        elif name in ("urllib.request.urlopen", "urllib.request.urlretrieve"):
            bad = True
        elif name == "urllib.request.build_opener":
            bad = not any(self._empty_proxy_handler(a) for a in node.args)
        if bad:
            self.found[(".".join(self.stack) or "<module>", name)] += 1
        self.generic_visit(node)

    def _empty_proxy_handler(self, arg: ast.AST) -> bool:
        return (isinstance(arg, ast.Call) and self.dotted(arg.func) == "urllib.request.ProxyHandler"
                and len(arg.args) == 1 and isinstance(arg.args[0], ast.Dict) and not arg.args[0].keys)


def scan_source(source: str) -> Counter[tuple[str, str]]:
    s = _Scan()
    s.visit(ast.parse(source))
    return s.found


def scan_repo() -> Counter[str]:
    out: Counter[str] = Counter()
    for p in python_files():
        for (fn, call), n in scan_source(p.read_text(encoding="utf-8")).items():
            out[f"{p.relative_to(ROOT).as_posix()}::{fn}::{call}"] += n
    return out


def parse_allowlist(text: str) -> Counter[str]:
    out: Counter[str] = Counter()
    for ln in text.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            key, _, n = ln.rpartition(" = ")
            out[key] = int(n)
    return out


def problems(found: Counter[str], allowed: Counter[str]) -> list[str]:
    out = [f"new unproxied-env client (pass trust_env=False / ProxyHandler({{}})): {k} x{found[k] - allowed.get(k, 0)}"
           for k in sorted(found) if found[k] > allowed.get(k, 0)]
    out += [f"stale allowlist entry (site fixed or moved, remove it): {k}" for k in sorted(allowed) if found.get(k, 0) < allowed[k]]
    return out


def test_the_repo_matches_the_allowlist():
    assert problems(scan_repo(), parse_allowlist(ALLOWLIST.read_text(encoding="utf-8"))) == []


BLIND_PROBE = (
    "import httpx\nimport urllib.request\n"
    "def f():\n    httpx.Client()\n    urllib.request.urlopen('http://x')\n"
)


def test_the_scan_is_not_blind():
    # independent of the allowlist: it must still pass once every site is migrated (C-476, F-C462-1)
    assert len(python_files()) >= 100, "the scan roots hold well over 100 non-test files; fewer means the walk is broken"
    assert scan_source(BLIND_PROBE) == Counter({("f", "httpx.Client"): 1, ("f", "urllib.request.urlopen"): 1})


@pytest.mark.parametrize("src", [
    "import httpx\nhttpx.get('http://x')\n",
    "import httpx as h\nh.Client(timeout=3)\n",
    "from httpx import post\npost('http://x')\n",
    "import httpx\nhttpx.Client(trust_env=True)\n",
    "import httpx\nkw = {}\nhttpx.Client(**kw)\n",
    "import urllib.request\nurllib.request.urlopen('http://x')\n",
    "from urllib.request import urlopen\nurlopen('http://x')\n",
    "import urllib.request as u\nu.build_opener()\n",
    "import urllib.request\nurllib.request.build_opener(urllib.request.ProxyHandler({'http': 'p'}))\n",
    "import httpx\nclass A:\n    def f(self):\n        return httpx.stream('GET', 'http://x')\n",
    # C-476 (reviewer C-462 F-C462-3, F-C462-4, F-C462-2)
    "import httpx\nhttpx.AsyncClient()\n",
    "import httpx\nhttpx.put('http://x')\n",
    "import httpx\nhttpx.patch('http://x')\n",
    "import httpx\nhttpx.delete('http://x')\n",
    "import httpx\nhttpx.head('http://x')\n",
    "import httpx\nhttpx.options('http://x')\n",
    "import httpx\nhttpx.request('GET', 'http://x')\n",
    "import urllib.request\nurllib.request.build_opener(urllib.request.ProxyHandler())\n",
    "import urllib.request\nurllib.request.build_opener(urllib.request.ProxyHandler({'a': 'b'}))\n",
    "from httpx import Client as C\nC()\n",
    "import urllib.request\nurllib.request.urlretrieve('http://x', 'f')\n",
    "from urllib.request import urlretrieve\nurlretrieve('http://x')\n",
    "import httpx\nclass A(httpx.Client):\n    pass\n",
    "from httpx import AsyncClient\nclass A(AsyncClient):\n    def __init__(self):\n        super().__init__(timeout=3)\n",
    "import httpx\nclass A(httpx.Client):\n    def __init__(self):\n        super().__init__(trust_env=True)\n",
])
def test_the_scanner_flags(src):
    assert sum(scan_source(src).values()) == 1


@pytest.mark.parametrize("src", [
    "import httpx\nhttpx.get('http://x', trust_env=False)\n",
    "import httpx\nhttpx.AsyncClient(trust_env=False, timeout=3)\n",
    "import urllib.request\nurllib.request.build_opener(urllib.request.ProxyHandler({}))\n",
    "from urllib.request import build_opener, ProxyHandler\nbuild_opener(ProxyHandler({}))\n",
    "import httpx\nx = httpx.Timeout(3)\nhttpx.HTTPError\n",
    "def get(): ...\nget()\n",
    "import httpx\nclass A(httpx.Client):\n    def __init__(self):\n        super().__init__(trust_env=False)\n",
    "import httpx\nclass A(httpx.AsyncClient):\n    def __init__(self, **kw):\n        super().__init__(trust_env=False, **kw)\n",
    "class A(object):\n    pass\n",
])
def test_the_scanner_passes_the_safe_shapes(src):
    assert sum(scan_source(src).values()) == 0


def test_the_scanner_names_the_enclosing_function():
    src = "import httpx\nclass A:\n    def f(self):\n        httpx.get('x')\n"
    assert list(scan_source(src)) == [("A.f", "httpx.get")]


def test_a_new_site_and_a_stale_entry_are_both_caught():
    allowed = parse_allowlist(ALLOWLIST.read_text(encoding="utf-8"))
    found = scan_repo()
    assert problems(found + Counter({"packages/x/src/x.py::f::httpx.get": 1}), allowed)
    key = sorted(allowed)[0]
    assert problems(found, allowed + Counter({key: 1})) and problems(found, Counter({k: v for k, v in allowed.items() if k != key}))


def test_the_allowlist_lines_are_well_formed():
    for ln in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        if ln.strip() and not ln.startswith("#"):
            assert re.fullmatch(r"[\w./-]+::[\w.<>]+::(httpx|urllib\.request)\.[\w.]+ = [1-9]\d*", ln), ln
