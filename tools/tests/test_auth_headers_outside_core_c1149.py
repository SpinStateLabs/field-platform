"""C-1149 (B-19, Lane 10 design 20261102-2000-design-credential-on-reads, section 4.3): non-test code outside field-core
must not call `field_core.authn.auth_headers()`.

`auth_headers()` merges the service's own operator key pair into the headers it returns, so a client built with
`headers=auth_headers()` sends that pair on every request it makes, reads included. The closed rule is that the pair
travels only through the guarded auth (`GuardedOperatorAuth`, route table owned by the service that guards the
routes) and that the perimeter secret is the only thing every internal request carries. This is an AST scan (the shape
of test_http_env_proxy_lint_c57.py) over the non-test Python of the repo, skipping `packages/field-core/` (the home of
the function):

* a call to `auth_headers`, however it is reached: `from field_core.authn import auth_headers [as x]`, the module as
  `authn`, `field_core.authn` or an alias of either, or a local alias assigned from any of these (`h = authn.auth_headers`);
* a use as a value (`headers=auth_headers`, `fn = auth_headers`) is a finding too, since the callee gets the pair;
* `from field_core.authn import *` is a finding.

Known limits (a review has to catch these): `getattr(authn, "auth_headers")`, `importlib`, an attribute of an attribute
(`self.authn.auth_headers()`), a function defined elsewhere that returns the result of one of these (that function is
the finding), and a name that only shadows the import in an inner scope.

Sites not yet migrated are listed in `auth_headers_allowlist.txt` as `path::function::call = count`. The list must
equal the scan: a new site fails, and so does an entry whose site was fixed (so the list only shrinks).
"""
from __future__ import annotations

import ast
import re
import subprocess
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = Path(__file__).with_name("auth_headers_allowlist.txt")
SCAN_ROOTS = ["packages", "services", "tools", "plugins", "integration", "defence-shield"]
SKIP_DIRS = {"tests", "node_modules", "__pycache__", ".venv", ".git"}
#: the home of the function: its own use is not a finding
HOME = "packages/field-core/"
TARGET = "field_core.authn.auth_headers"


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
        self.alias: dict[str, str] = {}   # local name -> dotted origin
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
                if a.name == "*" and node.module == "field_core.authn":
                    self.alias.setdefault("auth_headers", TARGET)
                    self._flag("import *")
                elif a.name != "*":
                    self.alias[a.asname or a.name] = f"{node.module}.{a.name}"
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # `h = authn.auth_headers` then `h()`: follow the alias (the assignment itself is flagged by visiting its value)
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and self._dotted(node.value) == TARGET:
            self.alias[node.targets[0].id] = TARGET
        self.generic_visit(node)

    def _scope(self, node: ast.AST, name: str) -> None:
        self.stack.append(name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope(node, node.name)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope(node, node.name)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and self._dotted(node) == TARGET:
            self._flag("auth_headers")

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, ast.Load) and self._dotted(node) == TARGET:
            self._flag("auth_headers")
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
    out = [f"new auth_headers() use outside field-core (use the guarded auth, perimeter secret only): {k} x{found[k] - allowed.get(k, 0)}"
           for k in sorted(found) if found[k] > allowed.get(k, 0)]
    out += [f"stale allowlist entry (site fixed or moved, remove it): {k}" for k in sorted(allowed) if found.get(k, 0) < allowed[k]]
    return out


def test_the_repo_matches_the_allowlist():
    assert problems(scan_repo(), parse_allowlist(ALLOWLIST.read_text(encoding="utf-8"))) == []


def test_the_scan_is_not_blind():
    # An independent control: it must keep passing when every site has been migrated, so it counts scanned files and a
    # built-in snippet, never the number of sites still on the allowlist.
    assert len(python_files()) >= 100, "the repo has well over a hundred non-test Python files; a scan of fewer is broken"
    assert sum(scan_source("from field_core.authn import auth_headers\nauth_headers()\n").values()) == 1


def test_the_home_is_exempt_and_the_exemption_is_not_vacuous():
    assert not any(p.relative_to(ROOT).as_posix().startswith(HOME) for p in python_files())
    llm = ROOT / HOME / "src/field_core/llm.py"
    assert sum(scan_source(llm.read_text(encoding="utf-8")).values()) >= 1, "field-core itself uses it: the home must stay exempt"


@pytest.mark.parametrize("src", [
    "from field_core.authn import auth_headers\ndef f():\n    return auth_headers()\n",
    "from field_core.authn import auth_headers as ah\nah()\n",
    "from field_core import authn\nauthn.auth_headers()\n",
    "from field_core import authn as a\na.auth_headers()\n",
    "import field_core.authn\nfield_core.authn.auth_headers()\n",
    "import field_core.authn as an\nan.auth_headers()\n",
    "from field_core.authn import auth_headers\nimport httpx\nhttpx.Client(headers=auth_headers)\n",
    "from field_core.authn import auth_headers\nfn = auth_headers\nfn()\n",
    "from field_core import authn\nh = authn.auth_headers\nh()\n",
    "from field_core.authn import *\nauth_headers()\n",
    "from field_core.authn import auth_headers\nclass C:\n    def m(self):\n        return {**auth_headers(), 'a': 1}\n",
])
def test_the_scanner_flags(src):
    assert sum(scan_source(src).values()) >= 1, src


@pytest.mark.parametrize("src", [
    "def auth_headers():\n    return {}\nauth_headers()\n",                       # a function of the same name, not the import
    "class X:\n    def auth_headers(self):\n        return {}\nX().auth_headers()\n",
    "import httpx\nhttpx.Client(headers={'x-field-auth': 's'})\n",
    "from field_core.authn import shared_secret\nshared_secret()\n",
    "from field_core import authn\nauthn.shared_secret()\n",
    "from field_core.authn import auth_headers\n",                                  # imported, never used
    "# auth_headers() in a comment\nx = 'auth_headers()'\n",
    "from other_pkg import auth_headers\nauth_headers()\n",
    "def perimeter_headers():\n    return {}\nperimeter_headers()\n",
])
def test_the_scanner_passes_the_safe_shapes(src):
    assert sum(scan_source(src).values()) == 0, src


def test_the_scanner_names_the_enclosing_function():
    src = "from field_core.authn import auth_headers\nclass C:\n    def m(self):\n        def inner():\n            return auth_headers()\n"
    assert list(scan_source(src)) == [("C.m.inner", "auth_headers")]


def test_a_new_site_and_a_stale_entry_are_both_caught():
    allowed = parse_allowlist(ALLOWLIST.read_text(encoding="utf-8"))
    found = scan_repo()
    assert problems(found + Counter({"services/x/src/x.py::f::auth_headers": 1}), allowed)
    key = sorted(allowed)[0]
    assert problems(found, allowed + Counter({key: 1})) and problems(found, Counter({k: v for k, v in allowed.items() if k != key}))


def test_a_call_added_to_a_real_file_turns_the_repo_scan_red():
    # The mutant the card names: add one call to an existing non-test file and the lint must go red.
    allowed = parse_allowlist(ALLOWLIST.read_text(encoding="utf-8"))
    path = next(p for p in python_files() if p.relative_to(ROOT).as_posix().startswith("services/"))
    texts = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8") for p in python_files()}
    rel = path.relative_to(ROOT).as_posix()
    texts[rel] += "\nfrom field_core.authn import auth_headers\n\n\ndef _mutant():\n    return auth_headers()\n"
    assert any(rel in pr and "_mutant" in pr for pr in problems(scan_texts(texts), allowed))


def test_the_allowlist_lines_are_well_formed():
    for ln in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        if ln.strip() and not ln.startswith("#"):
            assert re.fullmatch(r"[\w./-]+::[\w.<>]+::(auth_headers|import \*) = [1-9]\d*", ln), ln


# ---- Lane 7 review Q-91 of PR 445 (F1, F2, F5) --------------------------------------------------------------------

@pytest.mark.parametrize("src", [
    "from field_core.operator_auth import operator_headers\ndef f():\n    return operator_headers()\n",
    "from field_core import operator_auth\noperator_auth.operator_headers()\n",
    "import field_core.operator_auth as oa\noa.operator_headers()\n",
    "import field_core.operator_auth\nfield_core.operator_auth.operator_headers()\n",
])
def test_operator_headers_is_a_finding_too(src):
    # F1: the function auth_headers() wraps; a direct call puts the pair in the headers the same way
    assert [call for (_, call) in scan_source(src)] == ["operator_headers"]


def test_a_bare_star_import_is_pinned():
    # F5a: dropping the flag on the star import must turn something red
    assert scan_source("from field_core.authn import *\n") == Counter({("<module>", "import *"): 1})


def test_a_duplicate_allowlist_key_is_refused():
    # F5b: a repeated line with another count used to override silently (last wins)
    with pytest.raises(ValueError):
        parse_allowlist("a.py::f::auth_headers = 1\na.py::f::auth_headers = 2\n")


def test_the_alias_multiplicity_is_pinned():
    # F5c: the aliased value is flagged where it is produced and again where the alias is called: two uses
    assert sum(scan_source("from field_core import authn\nh = authn.auth_headers\nh()\n").values()) == 2


def test_every_top_level_directory_with_python_is_scanned():
    # F2: SCAN_ROOTS is a fixed list; a new top-level directory with Python must be added to it, not skipped by accident
    tracked = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    assert sorted({p.split("/")[0] for p in tracked if "/" in p} - set(SCAN_ROOTS)) == []
