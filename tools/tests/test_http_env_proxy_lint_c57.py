"""C-57 (reviewer C-55): non-test code must not build an HTTP client that reads the process's proxy environment.

httpx and urllib both honour `http_proxy` / `HTTP_PROXY` / `ALL_PROXY` by default, so a request that carries
`x-field-auth`, an operator key or an API key can be sent to a proxy in clear. This is an AST scan (like
topology_lint) over the non-test Python of the repo:

* `httpx.Client|AsyncClient|get|post|put|patch|delete|head|options|request|stream(...)` (also `httpx2`) must pass
  `trust_env=False`, however it is spelled: through an alias (`K = httpx.Client`), `from httpx import *`,
  `functools.partial(httpx.Client, ...)`, or a subclass (its `super().__init__` must pass it, or every
  instantiation must; a subclass whose constructor passes it is safe);
* `urllib.request.urlopen(...)` and `urlretrieve(...)` are always a finding (the default opener reads the proxy environment);
* `urllib.request.build_opener(...)` must be given `ProxyHandler({})`;
* importing `requests`, `urllib3` or `aiohttp` in non-test code is a finding (they read the environment too).

Known limits (a review has to catch these): `getattr(httpx, "Client")`, `importlib`, setting `trust_env = True` (or
`setattr`) after construction, factories kept in a dict or list (`REG["c"]()`), a client class returned from a
function, and calls through a client passed in from elsewhere (reviewer C-547 F-C547-2).

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
SKIP_DIRS = {"tests", "node_modules", "__pycache__", ".venv", ".git"}
CLIENT_MODULES = {"httpx", "httpx2"}
OTHER_CLIENT_PACKAGES = {"requests", "urllib3", "aiohttp"}
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


def _client_base(node: ast.ClassDef, alias: dict[str, str], extra: set[str]) -> bool:
    for b in node.bases:
        parts: list[str] = []
        n: ast.AST = b
        while isinstance(n, ast.Attribute):
            parts.append(n.attr)
            n = n.value
        if isinstance(n, ast.Name):
            dotted = ".".join([alias.get(n.id, n.id), *reversed(parts)])
            if dotted.split(".")[0] in CLIENT_MODULES and dotted.split(".")[-1] in {"Client", "AsyncClient"}:
                return True
            if not parts and n.id in extra:
                return True
    return False


def _trust_env_false(node: ast.Call) -> bool:
    kw = {k.arg: k.value for k in node.keywords if k.arg}
    return isinstance(kw.get("trust_env"), ast.Constant) and kw["trust_env"].value is False


class _Scan(ast.NodeVisitor):
    def __init__(self, unsafe_classes: frozenset[str] = frozenset()) -> None:
        self.alias: dict[str, str] = {}   # local name -> dotted origin
        self.stack: list[str] = []
        self.classes: list[str] = []
        self.attr_alias: dict[str, str] = {}   # attribute name -> dotted origin (`factory = httpx.Client` in a class)
        self.unsafe = set(unsafe_classes)
        self.found: Counter[tuple[str, str]] = Counter()   # (function, call)

    def _flag(self, call: str) -> None:
        self.found[(".".join(self.stack) or "<module>", call)] += 1

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            top = a.name.split(".")[0]
            self.alias[a.asname or top] = a.name if a.asname else top
            if top in OTHER_CLIENT_PACKAGES:
                self._flag(f"import {top}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.level == 0:
            top = node.module.split(".")[0]
            if top in OTHER_CLIENT_PACKAGES:
                self._flag(f"import {top}")
            for a in node.names:
                if a.name == "*" and top in CLIENT_MODULES:
                    for n in HTTPX_CALLS:
                        self.alias.setdefault(n, f"{node.module}.{n}")
                else:
                    self.alias[a.asname or a.name] = f"{node.module}.{a.name}"
        self.generic_visit(node)

    def _bind(self, target: ast.AST, value: ast.AST) -> None:
        if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)):
            for t, v in zip(target.elts, value.elts):
                self._bind(t, v)
            return
        origin = self.dotted(value) if isinstance(value, (ast.Name, ast.Attribute)) else None
        if origin and origin.split(".")[0] in CLIENT_MODULES | {"urllib"}:
            if isinstance(target, ast.Name):
                self.alias[target.id] = origin
                self.attr_alias[target.id] = origin         # `factory = httpx.Client` in a class body, called as self.factory()
            elif isinstance(target, ast.Attribute):
                self.attr_alias[target.attr] = origin       # `self.factory = httpx.Client`

    def visit_Assign(self, node: ast.Assign) -> None:
        for t in node.targets:
            self._bind(t, node.value)
        self.generic_visit(node)

    def _scoped(self, node: ast.AST, name: str) -> None:
        self.stack.append(name)
        self.generic_visit(node)
        self.stack.pop()

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        a = node.args
        positional = [*a.posonlyargs, *a.args]
        for arg, default in zip(positional[len(positional) - len(a.defaults):], a.defaults):
            self._bind(ast.Name(id=arg.arg), default)        # `def f(factory=httpx.Client)`
        for arg, default in zip(a.kwonlyargs, a.kw_defaults):
            if default is not None:
                self._bind(ast.Name(id=arg.arg), default)
        self._scoped(node, node.name)

    visit_FunctionDef = visit_AsyncFunctionDef = _function

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node.name)
        self._scoped(node, node.name)
        self.classes.pop()

    def dotted(self, node: ast.AST) -> str | None:
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name) or node.id not in self.alias:
            return None
        return ".".join([self.alias[node.id], *reversed(parts)])

    def _is_client_call(self, name: str | None) -> bool:
        return bool(name and name.split(".")[0] in CLIENT_MODULES and name.split(".", 1)[-1] in HTTPX_CALLS)

    def visit_Call(self, node: ast.Call) -> None:
        name = self.dotted(node.func)
        if name is None and isinstance(node.func, ast.Attribute) and node.func.attr in self.attr_alias:
            name = self.attr_alias[node.func.attr]            # `self.factory(...)` where factory = httpx.Client
        bad = False
        if (isinstance(node.func, ast.Name) and node.func.id == "type" and len(node.args) == 3
                and isinstance(node.args[1], (ast.Tuple, ast.List))
                and any(self.dotted(b) and self.dotted(b).split(".")[-1] in {"Client", "AsyncClient"}
                        and self.dotted(b).split(".")[0] in CLIENT_MODULES for b in node.args[1].elts)):
            name, bad = "type(client base)", True            # a subclass made with type()
        elif name == "functools.partial" and node.args and self._is_client_call(self.dotted(node.args[0])):
            name, bad = self.dotted(node.args[0]), not _trust_env_false(node)
        elif self._is_client_call(name):
            bad = not _trust_env_false(node)
        elif name in {"urllib.request.urlopen", "urllib.request.urlretrieve"}:
            bad = True
        elif name == "urllib.request.build_opener":
            bad = not any(self._empty_proxy_handler(a) for a in node.args)
        elif isinstance(node.func, (ast.Name, ast.Attribute)):
            ident = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            if ident in self.unsafe and not _trust_env_false(node):
                name, bad = f"subclass:{ident}", True
            elif (isinstance(node.func, ast.Attribute) and node.func.attr == "__init__" and self.classes
                  and self.classes[-1] in self.unsafe
                  and (isinstance(node.func.value, ast.Call) and isinstance(node.func.value.func, ast.Name)
                       and node.func.value.func.id == "super" or self._is_client_call(self.dotted(node.func.value)))):
                name, bad = "super().__init__", not _trust_env_false(node)
        if bad:
            self._flag(name or "?")
        self.generic_visit(node)

    def _empty_proxy_handler(self, arg: ast.AST) -> bool:
        return (isinstance(arg, ast.Call) and self.dotted(arg.func) == "urllib.request.ProxyHandler"
                and len(arg.args) == 1 and isinstance(arg.args[0], ast.Dict) and not arg.args[0].keys)


def unsafe_subclasses(source: str, known: frozenset[str] = frozenset()) -> set[str]:
    """Names of classes in `source` that subclass an httpx client (or a known unsafe class) and whose constructor
    does not pass `trust_env=False` to the base: instantiating one builds a client that reads the environment."""
    tree = ast.parse(source)
    pre = _Scan()
    pre.visit(tree)           # fills the import aliases
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    out: set[str] = set()
    changed = True
    while changed:
        changed = False
        for c in classes:
            if c.name in out or not _client_base(c, pre.alias, out | set(known)):
                continue
            inits = [f for f in c.body if isinstance(f, ast.FunctionDef) and f.name == "__init__"]
            supers = [x for f in inits for x in ast.walk(f)
                      if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == "__init__"]
            if inits and supers and all(_trust_env_false(x) for x in supers):
                continue                      # a constructor that pins trust_env=False: the class is safe
            out.add(c.name)
            changed = True
    return out


def scan_source(source: str, unsafe_classes: frozenset[str] = frozenset()) -> Counter[tuple[str, str]]:
    s = _Scan(frozenset(unsafe_classes) | unsafe_subclasses(source, unsafe_classes))
    s.visit(ast.parse(source))
    return s.found


def _parse_all() -> dict[Path, str]:
    out: dict[Path, str] = {}
    for p in python_files():
        text = p.read_text(encoding="utf-8")
        try:
            ast.parse(text)
        except SyntaxError as exc:
            raise AssertionError(f"{p.relative_to(ROOT).as_posix()} does not parse ({exc}); the lint cannot scan it") from exc
        out[p] = text
    return out


def scan_texts(texts: dict[str, str]) -> Counter[str]:
    """`{repo-relative path: source}` -> findings keyed `path::function::call`; subclasses are followed across files."""
    unsafe: set[str] = set()
    for t in texts.values():
        unsafe |= unsafe_subclasses(t, frozenset(unsafe))
    out: Counter[str] = Counter()
    for path, t in texts.items():
        for (fn, call), n in scan_source(t, frozenset(unsafe)).items():
            out[f"{path}::{fn}::{call}"] += n
    return out


def scan_repo() -> Counter[str]:
    return scan_texts({p.relative_to(ROOT).as_posix(): t for p, t in _parse_all().items()})


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


def test_the_scan_is_not_blind():
    # An independent control (C-462 F-C462-1): it must keep passing when every site has been migrated, so it counts
    # scanned files and a built-in snippet, never the number of sites still on the allowlist.
    assert len(python_files()) >= 100, "the repo has well over a hundred non-test Python files; a scan of fewer is broken"
    assert sum(scan_source("import httpx\nhttpx.get('http://x')\n").values()) == 1


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
            assert re.fullmatch(r"[\w./-]+::[\w.<>]+::((httpx2?|urllib\.request)\.\w+|subclass:\w+|super\(\)\.__init__|import \w+) = [1-9]\d*", ln), ln


# ---- spellings the first version missed (Lane 10 review of PR 295) -----------------------------------------------

@pytest.mark.parametrize("src", [
    "import httpx\nclass C(httpx.Client):\n    pass\nC(timeout=3)\n",
    "import httpx\nclass C(httpx.Client):\n    def __init__(self):\n        super().__init__()\n",
    "import httpx\nclass C(httpx.AsyncClient):\n    def __init__(self):\n        httpx.AsyncClient.__init__(self)\n",
    "import httpx\nclass C(httpx.Client):\n    pass\nclass D(C):\n    pass\nD()\n",
    "from httpx import Client\nclass C(Client):\n    pass\nC()\n",
    "import httpx\nK = httpx.Client\nK()\n",
    "import httpx\ndef f():\n    k = httpx.Client\n    return k()\n",
    "import httpx, functools\nmk = functools.partial(httpx.Client, timeout=3)\n",
    "import httpx2\nhttpx2.Client()\n",
    "from httpx2 import Client\nClient()\n",
    "from httpx import *\nClient()\n",
    "import requests\n",
    "import urllib3\n",
    "from aiohttp import ClientSession\n",
    "import urllib.request\nurllib.request.build_opener(urllib.request.ProxyHandler(None))\n",
    "import urllib.request\nh = urllib.request.ProxyHandler({'http': 'p'})\nurllib.request.build_opener(h)\n",
])
def test_the_scanner_flags_the_evasion_spellings(src):
    assert sum(scan_source(src).values()) >= 1


@pytest.mark.parametrize("src", [
    "import httpx\nclass C(httpx.Client):\n    def __init__(self):\n        super().__init__(trust_env=False)\nC()\n",
    "import httpx\nclass C(httpx.Client):\n    pass\nC(trust_env=False)\n",
    "import httpx, functools\nmk = functools.partial(httpx.Client, trust_env=False)\n",
    "import httpx\nK = httpx.Client\nK(trust_env=False)\n",
    "class C:\n    pass\nC()\n",
    "import httpx\nclass Err(httpx.HTTPError):\n    pass\nErr('x')\n",
])
def test_the_scanner_passes_the_safe_shapes_of_the_same_spellings(src):
    assert sum(scan_source(src).values()) == 0


def test_a_subclass_defined_in_another_module_is_followed():
    defn = "import httpx\nclass PerCall(httpx.Client):\n    pass\n"
    use = "from elsewhere import PerCall\nPerCall(timeout=3)\nPerCall(trust_env=False)\n"
    assert sum(scan_source(use).values()) == 0                    # unknown class: nothing to follow
    assert sum(scan_source(use, frozenset(unsafe_subclasses(defn))).values()) == 1


def test_a_subclass_in_one_file_is_followed_into_another_by_the_repo_scan():
    texts = {"a/client.py": "import httpx\nclass PerCall(httpx.Client):\n    pass\n",
             "b/use.py": "from a.client import PerCall\ndef make():\n    return PerCall(timeout=3)\n"}
    assert scan_texts(texts) == Counter({"b/use.py::make::subclass:PerCall": 1})


def test_the_lifecycle_manager_client_is_safe_by_its_constructor():
    # C-486: PerRequestAuthClient carries the perimeter secret and the operator pair; its constructor pins
    # trust_env=False, so the scan finds no site for it. Without the constructor the two builders are flagged.
    path = ROOT / "services" / "lifecycle-manager" / "src" / "lifecycle_manager" / "api.py"
    text = path.read_text(encoding="utf-8")
    assert "PerRequestAuthClient" not in unsafe_subclasses(text)
    assert not any("subclass:PerRequestAuthClient" in k for k in scan_repo())
    stripped = text.replace("trust_env=False, follow_redirects=False, **kwargs", "**kwargs")
    assert stripped != text and "PerRequestAuthClient" in unsafe_subclasses(stripped)


def test_a_file_that_does_not_parse_is_named(tmp_path, monkeypatch):
    bad = ROOT / "tools" / "_c57_unparsable_probe.py"
    bad.write_text("def (:\n", encoding="utf-8")
    try:
        with pytest.raises(AssertionError, match="_c57_unparsable_probe.py does not parse"):
            scan_repo()
    finally:
        bad.unlink()


def test_only_real_test_directories_and_files_are_skipped():
    for part in ("build", "dist", "venv", "src"):
        assert not _is_test_file(Path("services/x") / part / "client.py"), part
    for path in ("services/x/tests/client.py", "services/x/src/test_client.py", "tools/tests/conftest.py"):
        assert _is_test_file(Path(path)), path


def test_every_top_level_directory_with_python_is_scanned_or_named():
    # docs/, tasks/ and manifests/ hold examples, not services; anything else holding .py must be in SCAN_ROOTS
    dirs = {d.name for d in ROOT.iterdir() if d.is_dir() and not d.name.startswith(".")}
    missing = sorted(d for d in dirs if d not in SCAN_ROOTS and d not in {"docs", "tasks", "manifests"}
                     and any(p for p in (ROOT / d).rglob("*.py") if not _is_test_file(p.relative_to(ROOT))))
    assert missing == [], f"Python outside SCAN_ROOTS: {missing}"


# ---- the call names and shapes C-462 F-C462-3/-4 found unpinned -----------------------------------------------------

@pytest.mark.parametrize("call", ["Client", "AsyncClient", "get", "post", "put", "patch", "delete", "head", "options", "request", "stream"])
def test_every_httpx_call_name_is_flagged_without_trust_env(call):
    assert sum(scan_source(f"import httpx\nhttpx.{call}('x')\n").values()) == 1
    assert sum(scan_source(f"import httpx\nhttpx.{call}('x', trust_env=False)\n").values()) == 0


@pytest.mark.parametrize("src", [
    "import urllib.request\nurllib.request.build_opener(urllib.request.ProxyHandler())\n",
    "import urllib.request\nurllib.request.build_opener(urllib.request.ProxyHandler({'a': 'b'}))\n",
    "from httpx import Client as C\nC()\n",
    "import urllib.request\nurllib.request.urlretrieve('http://x', 'f')\n",
    "from urllib.request import urlretrieve\nurlretrieve('http://x', 'f')\n",
])
def test_the_remaining_unpinned_shapes_are_flagged(src):
    assert sum(scan_source(src).values()) == 1


# ---- the four alias spellings Lane 10 found (C-494 F-C494-1) --------------------------------------------------------

@pytest.mark.parametrize("src", [
    "import httpx\nK, X = httpx.Client, 1\nK()\n",
    "import httpx\nclass A:\n    factory = httpx.Client\n    def make(self):\n        return self.factory()\n",
    "import httpx\nclass B:\n    def __init__(self):\n        self.factory = httpx.Client\n    def make(self):\n        return self.factory()\n",
    "import httpx\ndef f(factory=httpx.Client):\n    return factory()\n",
    "import httpx\ndef f(*, factory=httpx.AsyncClient):\n    return factory()\n",
    "import httpx\nA = type('A', (httpx.Client,), {})\n",
])
def test_the_scanner_flags_the_alias_spellings_of_the_c494_probe(src):
    assert sum(scan_source(src).values()) >= 1


@pytest.mark.parametrize("src", [
    "import httpx\nK, X = httpx.Client, 1\nK(trust_env=False)\n",
    "import httpx\ndef f(factory=httpx.Client):\n    return factory(trust_env=False)\n",
    "A = type('A', (object,), {})\n",
    "import httpx\nA = type('A', (httpx.HTTPError,), {})\n",
])
def test_the_same_spellings_pass_when_safe(src):
    assert sum(scan_source(src).values()) == 0
