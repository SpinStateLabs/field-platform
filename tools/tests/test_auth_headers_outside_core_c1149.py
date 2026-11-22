"""C-1149 (B-19, Lane 10 design 20261102-2000-design-credential-on-reads, section 4.3): non-test code outside field-core
must not call `field_core.authn.auth_headers()` or `field_core.operator_auth.operator_headers()`.

Both functions merge the service's own operator key pair into the headers they return, so a client built with
`headers=auth_headers()` sends that pair on every request it makes, reads included. The closed rule is that the pair
travels only through the guarded auth (`GuardedOperatorAuth`, route table owned by the service that guards the
routes) and that the perimeter secret (`perimeter_headers()`) is the only thing every internal request carries. This is
an AST scan (the shape of test_http_env_proxy_lint_c57.py) over the non-test Python of the repo, skipping
`packages/field-core/` (the home of both functions). TARGETS lists the two functions; a finding is reported under the
function's short name (`auth_headers`, `operator_headers`):

* a call to a target, however it is reached: `from field_core.authn import auth_headers [as x]`, the module as
  `authn`, `field_core.authn` or an alias of either, a local alias assigned from any of these (`h = authn.auth_headers`),
  or a re-alias of the module (`x = an; x.auth_headers()`);
* a use as a value (`headers=auth_headers`, `fn = auth_headers`) is a finding too, since the callee gets the pair;
* `from field_core.authn import *` and `from field_core.operator_auth import *` are findings.

Scoping: aliases are tracked per function/class scope (a copy on entry, dropped on exit). A `def`, `class`, argument or
plain assignment that rebinds a tracked name resets the alias, so a local `def auth_headers` shadowing the import is not
a finding.

Known limits (a review has to catch these): `getattr(authn, "auth_headers")`, `importlib`, `__import__`, an attribute of
an attribute (`self.authn.auth_headers()`), a function defined elsewhere that returns the result of one of these (that
function is the finding), tuple/starred/augmented/walrus rebinding, and Python that is not a `.py` file: the heredoc
Python in `packages/field-agent/demo.sh` calls `auth_headers()` and is out of scan scope.

Sites not yet migrated are listed in `auth_headers_allowlist.txt` as `path::function::call = count`. The list must
equal the scan: a new site fails, and so does an entry whose site was fixed (so the list only shrinks). It is
regenerated from the scan, not edited by hand: `python tools/tests/test_auth_headers_outside_core_c1149.py` prints the
lines. A PR that migrates callers (for example open PR 1282, auth_headers to perimeter_headers) changes the scan, so
whichever of two such PRs lands second regenerates the list.
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = Path(__file__).with_name("auth_headers_allowlist.txt")
SCAN_ROOTS = ["packages", "services", "tools", "plugins", "integration", "defence-shield"]
SKIP_DIRS = {"tests", "node_modules", "__pycache__", ".venv", ".git"}
#: the home of both functions: their own use is not a finding
HOME = "packages/field-core/"
#: dotted origin -> the call name a finding is reported under
TARGETS = {
    "field_core.authn.auth_headers": "auth_headers",
    "field_core.operator_auth.operator_headers": "operator_headers",
}
#: modules that, once re-aliased (`x = an`), make `x.<target>` a target
MODULES = {"field_core", "field_core.authn", "field_core.operator_auth"}
#: `from <module> import *` is a finding; the star brings this name in
STAR_MODULES = {"field_core.authn": "auth_headers", "field_core.operator_auth": "operator_headers"}


def _is_test_file(path: Path) -> bool:
    return path.name.startswith("test_") or path.name == "conftest.py" or any(p in SKIP_DIRS for p in path.parts)


def python_files() -> list[Path]:
    out: list[Path] = []
    for top in SCAN_ROOTS:
        base = ROOT / top
        if base.is_dir():
            out += [p for p in base.rglob("*.py")
                    if not _is_test_file(p.relative_to(ROOT)) and not p.relative_to(ROOT).as_posix().startswith(HOME)]
    return sorted(out)


class _Scan(ast.NodeVisitor):
    def __init__(self) -> None:
        self.alias: dict[str, str] = {}   # local name -> dotted origin, per scope
        self.stack: list[str] = []
        self.found: Counter[tuple[str, str]] = Counter()   # (function, call)

    def _flag(self, call: str) -> None:
        self.found[(".".join(self.stack) or "<module>", call)] += 1

    def _dotted(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return self.alias.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = self._dotted(node.value)
            return f"{base}.{node.attr}" if base else None
        return None

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            self.alias[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.level == 0:
            for a in node.names:
                if a.name == "*" and node.module in STAR_MODULES:
                    short = STAR_MODULES[node.module]
                    self.alias.setdefault(short, f"{node.module}.{short}")
                    self._flag("import *")
                elif a.name != "*":
                    self.alias[a.asname or a.name] = f"{node.module}.{a.name}"
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # `h = authn.auth_headers` then `h()`, and `x = an` then `x.auth_headers()`: follow the alias (a target used as a
        # value is flagged by visiting it; a module alone is not a finding). Any other value rebinds the name.
        self.generic_visit(node)
        origin = self._dotted(node.value)
        for t in node.targets:
            if isinstance(t, ast.Name):
                if origin in TARGETS or origin in MODULES:
                    self.alias[t.id] = origin
                else:
                    self.alias.pop(t.id, None)

    def _body_scope(self, name: str, body: list[ast.stmt], params: list[str]) -> None:
        outer = self.alias
        self.alias = dict(outer)
        for p in params:
            self.alias.pop(p, None)
        self.stack.append(name)
        for stmt in body:
            self.visit(stmt)
        self.stack.pop()
        self.alias = outer

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # decorators and defaults are evaluated in the enclosing scope, before the def rebinds its own name there
        a = node.args
        for e in [*node.decorator_list, *a.defaults, *[d for d in a.kw_defaults if d is not None]]:
            self.visit(e)
        self.alias.pop(node.name, None)
        params = [x.arg for x in [*a.posonlyargs, *a.args, *a.kwonlyargs, *[v for v in (a.vararg, a.kwarg) if v]]]
        self._body_scope(node.name, node.body, params)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for e in [*node.decorator_list, *node.bases, *[k.value for k in node.keywords]]:
            self.visit(e)
        self.alias.pop(node.name, None)
        self._body_scope(node.name, node.body, [])

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            hit = TARGETS.get(self._dotted(node) or "")
            if hit:
                self._flag(hit)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, ast.Load):
            hit = TARGETS.get(self._dotted(node) or "")
            if hit:
                self._flag(hit)
                return   # the chain below it is the module path, not another use
        self.generic_visit(node)


def scan_source(src: str) -> Counter[tuple[str, str]]:
    s = _Scan()
    s.visit(ast.parse(src))
    return s.found


def scan_texts(texts: dict[str, str]) -> Counter[str]:
    out: Counter[str] = Counter()
    for path, t in texts.items():
        if path.startswith(HOME):
            continue
        for (fn, call), n in scan_source(t).items():
            out[f"{path}::{fn}::{call}"] += n
    return out


def scan_repo() -> Counter[str]:
    return scan_texts({p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8") for p in python_files()})


def parse_allowlist(text: str) -> Counter[str]:
    out: Counter[str] = Counter()
    for ln in text.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            key, _, n = ln.rpartition(" = ")
            out[key] = int(n)
    return out


def problems(found: Counter[str], allowed: Counter[str]) -> list[str]:
    out = [f"new auth_headers()/operator_headers() use outside field-core (use the guarded auth, perimeter secret only): "
           f"{k} x{found[k] - allowed.get(k, 0)}" for k in sorted(found) if found[k] > allowed.get(k, 0)]
    out += [f"stale allowlist entry (site fixed or moved, remove it): {k}" for k in sorted(allowed) if found.get(k, 0) < allowed[k]]
    return out


def test_the_repo_matches_the_allowlist():
    assert problems(scan_repo(), parse_allowlist(ALLOWLIST.read_text(encoding="utf-8"))) == []


def test_the_scan_is_not_blind():
    # An independent control: it must keep passing when every site has been migrated, so it counts scanned files and
    # built-in snippets, never the number of sites still on the allowlist.
    assert len(python_files()) >= 100, "the repo has well over a hundred non-test Python files; a scan of fewer is broken"
    assert sum(scan_source("from field_core.authn import auth_headers\nauth_headers()\n").values()) == 1
    assert sum(scan_source("from field_core.operator_auth import operator_headers\noperator_headers()\n").values()) == 1


def test_the_home_is_exempt_and_the_exemption_is_not_vacuous():
    assert not any(p.relative_to(ROOT).as_posix().startswith(HOME) for p in python_files())
    llm = ROOT / HOME / "src/field_core/llm.py"
    assert sum(scan_source(llm.read_text(encoding="utf-8")).values()) >= 1, "field-core itself uses it: the home must stay exempt"


#: (source, exact number of findings). Exact counts, not ">= 1": a scan that double-counts or under-counts an alias
#: shape is a different scan (mutants A1 and A2 of the review survived `>= 1`).
FLAGGED = [
    ("from field_core.authn import auth_headers\ndef f():\n    return auth_headers()\n", 1),
    ("from field_core.authn import auth_headers as ah\nah()\n", 1),
    ("from field_core import authn\nauthn.auth_headers()\n", 1),
    ("from field_core import authn as a\na.auth_headers()\n", 1),
    ("import field_core.authn\nfield_core.authn.auth_headers()\n", 1),
    ("import field_core.authn as an\nan.auth_headers()\n", 1),
    ("from field_core.authn import auth_headers\nimport httpx\nhttpx.Client(headers=auth_headers)\n", 1),
    ("from field_core.authn import auth_headers\nfn = auth_headers\nfn()\n", 2),        # the value use, then the call
    ("from field_core import authn\nh = authn.auth_headers\nh()\n", 2),
    ("from field_core.authn import auth_headers\nh = auth_headers\nk = h\nk()\n", 3),     # the alias chain is followed
    ("from field_core.authn import *\nauth_headers()\n", 2),                            # the star import, then the call
    ("from field_core.authn import *\n", 1),
    ("from field_core.authn import auth_headers\nclass C:\n    def m(self):\n        return {**auth_headers(), 'a': 1}\n", 1),
    # the module re-alias the first version of this lint missed
    ("import field_core.authn as an\nx = an\nx.auth_headers()\n", 1),
    ("from field_core import authn\nx = authn\ny = x\ny.auth_headers()\n", 1),
    ("import field_core\nx = field_core\nx.authn.auth_headers()\n", 1),
    # operator_headers() direct calls (the canary shape: an import inside a function, then a call)
    ("from field_core.operator_auth import operator_headers\noperator_headers()\n", 1),
    ("from field_core import operator_auth\noperator_auth.operator_headers()\n", 1),
    ("from field_core import operator_auth as oa\nif oa.operator_headers() and oa.mode():\n    pass\n", 1),
    ("import field_core.operator_auth as oa\nx = oa\nx.operator_headers()\n", 1),
    ("def send():\n    from field_core.operator_auth import operator_headers\n\n    return operator_headers()\n", 1),
    ("from field_core.operator_auth import *\noperator_headers()\n", 2),
    ("from field_core.operator_auth import operator_headers\nfn = operator_headers\nfn()\n", 2),
    # both in one file are counted separately
    ("from field_core import authn, operator_auth\nauthn.auth_headers()\noperator_auth.operator_headers()\n", 2),
    # async scope (mutant V3: the async def was not scanned or not named)
    ("from field_core.authn import auth_headers\nasync def f():\n    return auth_headers()\n", 1),
    ("from field_core.operator_auth import operator_headers\nclass C:\n    async def m(self):\n        return operator_headers()\n", 1),
    # a name imported again after a reset is tracked again
    ("from field_core.authn import auth_headers\ndef auth_headers():\n    pass\nfrom field_core.authn import auth_headers\nauth_headers()\n", 1),
    # a shadow in one function does not hide a use in another
    ("from field_core.authn import auth_headers\ndef f(auth_headers):\n    return auth_headers\ndef g():\n    return auth_headers()\n", 1),
]


@pytest.mark.parametrize("src,n", FLAGGED)
def test_the_scanner_flags(src, n):
    assert sum(scan_source(src).values()) == n, src


SAFE = [
    "def auth_headers():\n    return {}\nauth_headers()\n",                       # a function of the same name, not the import
    "class X:\n    def auth_headers(self):\n        return {}\nX().auth_headers()\n",
    "import httpx\nhttpx.Client(headers={'x-field-auth': 's'})\n",
    "from field_core.authn import shared_secret\nshared_secret()\n",
    "from field_core import authn\nauthn.shared_secret()\n",
    "from field_core.authn import auth_headers\n",                                  # imported, never used
    "# auth_headers() in a comment\nx = 'auth_headers()'\n",
    "from other_pkg import auth_headers\nauth_headers()\n",
    "def perimeter_headers():\n    return {}\nperimeter_headers()\n",
    "from field_core.guarded_operator import perimeter_headers\nperimeter_headers()\n",
    "from field_core import operator_auth\noperator_auth.mode()\noperator_auth.parse_headers({})\n",
    "from field_core.operator_auth import mode\nmode()\n",
    "from other_pkg import operator_headers\noperator_headers()\n",
    # a local def or class shadowing the import (the false positive of the first version of this lint)
    "from field_core.authn import auth_headers\ndef auth_headers():\n    return {}\nauth_headers()\n",
    "from field_core.authn import auth_headers\nclass auth_headers:\n    pass\nauth_headers()\n",
    "from field_core.authn import auth_headers\nasync def auth_headers():\n    return {}\nauth_headers()\n",
    "from field_core.operator_auth import operator_headers\ndef operator_headers():\n    return {}\noperator_headers()\n",
    # a parameter or a plain assignment shadowing it
    "from field_core.authn import auth_headers\ndef f(auth_headers):\n    return auth_headers()\n",
    "from field_core.authn import auth_headers\nauth_headers = dict\nauth_headers()\n",
    # a re-alias reassigned to something else
    "import field_core.authn as an\nx = an\nx = object()\nx.auth_headers()\n",
]


@pytest.mark.parametrize("src", SAFE)
def test_the_scanner_passes_the_safe_shapes(src):
    assert sum(scan_source(src).values()) == 0, src


def test_a_def_inside_a_function_shadows_only_there():
    # Scope is per function: the inner def resets the alias inside f, and a use in g is still a finding.
    src = ("from field_core.authn import auth_headers\n"
           "def f():\n    def auth_headers():\n        return {}\n    return auth_headers()\n"
           "def g():\n    return auth_headers()\n")
    assert list(scan_source(src)) == [("g", "auth_headers")]


def test_the_scanner_names_the_enclosing_function():
    src = "from field_core.authn import auth_headers\nclass C:\n    def m(self):\n        def inner():\n            return auth_headers()\n"
    assert list(scan_source(src)) == [("C.m.inner", "auth_headers")]
    src = "from field_core.authn import auth_headers\nclass C:\n    async def m(self):\n        return auth_headers()\n"
    assert list(scan_source(src)) == [("C.m", "auth_headers")]


def test_the_two_targets_are_reported_under_their_own_names():
    src = ("from field_core import authn, operator_auth\n"
           "def f():\n    return authn.auth_headers(), operator_auth.operator_headers()\n")
    assert scan_source(src) == Counter({("f", "auth_headers"): 1, ("f", "operator_headers"): 1})


def test_a_known_operator_headers_site_is_found_in_the_repo():
    # The canary builds its request headers with a direct operator_headers() call (Phase G S8); the lint must see it.
    assert any(k.startswith("packages/field-agent/src/field_agent/canary.py::") and k.endswith("::operator_headers")
               for k in scan_repo())


def test_a_new_site_and_a_stale_entry_are_both_caught():
    allowed = parse_allowlist(ALLOWLIST.read_text(encoding="utf-8"))
    found = scan_repo()
    assert problems(found + Counter({"services/x/src/x.py::f::auth_headers": 1}), allowed)
    assert problems(found + Counter({"services/x/src/x.py::f::operator_headers": 1}), allowed)
    key = sorted(allowed)[0]
    assert problems(found, allowed + Counter({key: 1})) and problems(found, Counter({k: v for k, v in allowed.items() if k != key}))


def test_a_call_added_to_a_real_file_turns_the_repo_scan_red():
    # The mutant the card names: add one call to an existing non-test file and the lint must go red (both functions).
    allowed = parse_allowlist(ALLOWLIST.read_text(encoding="utf-8"))
    path = next(p for p in python_files() if p.relative_to(ROOT).as_posix().startswith("services/"))
    rel = path.relative_to(ROOT).as_posix()
    for imp, call in (("from field_core.authn import auth_headers", "auth_headers"),
                      ("from field_core.operator_auth import operator_headers", "operator_headers")):
        texts = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8") for p in python_files()}
        texts[rel] += f"\n{imp}\n\n\ndef _mutant():\n    return {call}()\n"
        assert any(rel in pr and "_mutant" in pr for pr in problems(scan_texts(texts), allowed))


def test_the_allowlist_lines_are_well_formed():
    for ln in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        if ln.strip() and not ln.startswith("#"):
            assert re.fullmatch(r"[\w./-]+::[\w.<>]+::(auth_headers|operator_headers|import \*) = [1-9]\d*", ln), ln


if __name__ == "__main__":
    # regenerate the allowlist body from the scan (header lines stay): python tools/tests/test_auth_headers_outside_core_c1149.py
    for key, n in sorted(scan_repo().items()):
        print(f"{key} = {n}")
