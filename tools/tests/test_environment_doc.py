"""C-329 (reviewer B-03): docs/ENVIRONMENT.md lists every environment variable the source reads.

An AST pass over packages/*/src and services/*/src collects (a) every string constant that is exactly
a platform variable name (FIELD_*, FORCE_*, CLAUDE_*, ANTHROPIC_*, CROSSWALK_*; this catches reads
through module constants, helper functions, typer `envvar=` and ops-console `env=` arguments) and
(b) any name read as `.get/.pop/.setdefault(...)`, `[...]` or an `in` test on `os.environ`, a copy of it
(`dict(...)`, `.copy()`, `copy.copy(...)`, `getattr(os, "environ")`), or a name or attribute bound to either
(plain, annotated or walrus assignment, a parameter default, `from os import environ as x`), and through
`os.getenv(...)` or an alias of it; the key may be a literal, a function-local, module, imported or class
constant. Not followed (stated limits): `.items()`, `{**os.environ}`, `self.NAME` keys, keys built at run time, joined from constants or in f-strings, and lower-case platform names (C-747 F-C747-2).
A name read in the source and missing from
the first column of the file's table fails. The test also pins the names the reviewer found missing or
documented only in a changelog or spec, and that no row has an empty column.
"""
from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "ENVIRONMENT.md"
PLATFORM_NAME = re.compile(r"^(FIELD|FORCE|CLAUDE|ANTHROPIC|CROSSWALK)_[A-Z0-9_]+$")

# B-03 finding 1 (in no .md before) and finding 2 (changelog or spec only)
REVIEWER_NAMES = {
    "CROSSWALK_SUGGEST_MODEL", "FIELD_CANARY_AGENT_ID", "FIELD_CANARY_HOST", "FIELD_CANARY_PORT",
    "FIELD_CANARY_WORK_EVERY", "FORCE_HYGIENE_BASELINE_WINDOWS",
    "FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM", "FIELD_LEDGER_CRASH_AT",
}


def source_files(root: Path = ROOT) -> dict[str, str]:
    files: dict[str, str] = {}
    for pattern in ("packages/*/src/**/*.py", "services/*/src/**/*.py"):
        for p in sorted(root.glob(pattern)):
            files[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
    return files


def _component(path: str) -> str:
    """packages/field-core/src/... -> field-core"""
    return path.split("/")[1]


READ_METHODS = ("get", "pop", "setdefault")


@functools.lru_cache(maxsize=1024)
def _parse(path: str, text: str) -> ast.Module:
    """Each mutant test changes one file; every other file is parsed once per run, not once per test."""
    return ast.parse(text, filename=path)


def _is_environ(node: ast.AST | None, names: set[str], attrs: set[str]) -> bool:
    """An expression that is (or is a copy of) os.environ: `os.environ`, a name or attribute bound to it,
    `dict(os.environ)`, `os.environ.copy()`, `copy.copy(os.environ)`, `getattr(os, "environ")` (C-353)."""
    if isinstance(node, ast.Attribute):
        return node.attr == "environ" or node.attr in attrs
    if isinstance(node, ast.Name):
        return node.id in names
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "copy" and _is_environ(f.value, names, attrs):
            return True
        if isinstance(f, ast.Name) and f.id in ("dict", "copy") and node.args and _is_environ(node.args[0], names, attrs):
            return True
        if isinstance(f, ast.Attribute) and f.attr == "copy" and node.args and _is_environ(node.args[0], names, attrs):
            return True
        if (isinstance(f, ast.Name) and f.id == "getattr" and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant) and node.args[1].value == "environ"):
            return True
    return False


def _aliases(tree: ast.AST) -> tuple[set[str], set[str], set[str]]:
    """(names bound to os.environ, attribute names bound to it, names bound to os.getenv) in this module:
    `x = os.environ`, `self.e = os.environ`, `from os import environ as x`, `from os import getenv as g`, a
    parameter whose default is os.environ (C-338, F-C336-2; attributes, copies and getenv added by C-353)."""
    names, attrs, getenvs = {"env", "environ"}, set(), set()
    for _ in range(3):  # a few passes so `a = os.environ; b = a` settles
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "os":
                names.update(a.asname or a.name for a in node.names if a.name == "environ")
                getenvs.update(a.asname or a.name for a in node.names if a.name == "getenv")
            elif isinstance(node, ast.Assign) and _is_environ(node.value, names, attrs):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
                    elif isinstance(t, ast.Attribute):
                        attrs.add(t.attr)
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Tuple):   # `e, _ = os.environ, 1` (C-831)
                for t in node.targets:
                    if isinstance(t, ast.Tuple) and len(t.elts) == len(node.value.elts):
                        for target, value in zip(t.elts, node.value.elts):
                            if _is_environ(value, names, attrs):
                                if isinstance(target, ast.Name):
                                    names.add(target.id)
                                elif isinstance(target, ast.Attribute):
                                    attrs.add(target.attr)
            elif (isinstance(node, ast.AnnAssign) and node.value is not None
                    and _is_environ(node.value, names, attrs)):       # `e: dict = os.environ` (C-397)
                if isinstance(node.target, ast.Name):
                    names.add(node.target.id)
                elif isinstance(node.target, ast.Attribute):
                    attrs.add(node.target.attr)
            elif (isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name)
                    and _is_environ(node.value, names, attrs)):       # `(e := os.environ)` (C-397)
                names.add(node.target.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args
                positional = args.posonlyargs + args.args
                for arg, default in zip(positional[len(positional) - len(args.defaults):], args.defaults):
                    if _is_environ(default, names, attrs):
                        names.add(arg.arg)
                for arg, default in zip(args.kwonlyargs, args.kw_defaults):
                    if _is_environ(default, names, attrs):
                        names.add(arg.arg)
    return names, attrs, getenvs


def _own_strings(body) -> dict[str, set[str]]:
    """name -> string values assigned to that plain name directly in these statements (not in nested scopes)."""
    out: dict[str, set[str]] = {}
    for stmt in body:
        for node in ast.walk(stmt):
            if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        out.setdefault(t.id, set()).add(node.value.value)
            elif (isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and isinstance(node.target, ast.Name)
                    and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                out.setdefault(node.target.id, set()).add(node.value.value)       # `K: str = "X"`, `(k := "X")` (C-831)
    return out


def _function_scope(node: ast.AST) -> dict[str, set[str]]:
    """A function's own bindings: parameters and non-constant assignments are bound-but-unknown (an empty set,
    never resolved from elsewhere); a plain string assignment is a function-local constant."""
    scope: dict[str, set[str]] = {}
    args = node.args
    for arg in args.posonlyargs + args.args + args.kwonlyargs + [a for a in (args.vararg, args.kwarg) if a]:
        scope[arg.arg] = set()
    for stmt in node.body:
        for sub in ast.walk(stmt):
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(sub, ast.Assign):
                for t in sub.targets:
                    if isinstance(t, ast.Name):
                        if isinstance(sub.value, ast.Constant) and isinstance(sub.value.value, str):
                            scope.setdefault(t.id, set()).add(sub.value.value)
                        else:
                            scope.setdefault(t.id, set())
            elif (isinstance(sub, (ast.AnnAssign, ast.NamedExpr)) and isinstance(sub.target, ast.Name)):
                if isinstance(sub.value, ast.Constant) and isinstance(sub.value.value, str):
                    scope.setdefault(sub.target.id, set()).add(sub.value.value)    # (C-831)
                else:
                    scope.setdefault(sub.target.id, set())
            elif isinstance(sub, (ast.For, ast.comprehension)) and isinstance(sub.target, ast.Name):
                scope.setdefault(sub.target.id, set())
    return scope


def _module_name(path: str) -> str:
    """services/x/src/pkg/mod.py -> pkg.mod (pkg/__init__.py -> pkg)"""
    rel = path.split("/src/", 1)[1][: -len(".py")]
    return rel[: -len("/__init__")].replace("/", ".") if rel.endswith("/__init__") else rel.replace("/", ".")


def _freeze(d: dict[str, set[str]]) -> tuple:
    return tuple(sorted((k, tuple(sorted(v))) for k, v in d.items()))


@functools.lru_cache(maxsize=1024)
def _file_keys(path: str, text: str, ctx: tuple) -> frozenset[str]:
    """The variable names one file reads or names. `ctx` is everything it needs from other files (constants it
    imports, modules it imports by name, its own module and class constants), so a mutant that changes one file
    re-scans that file only."""
    tree = _parse(path, text)
    imported_t, aliases_t, own_t, classes_t = ctx
    imported = {k: set(v) for k, v in imported_t}
    aliases = {k: {n: set(v) for n, v in strs} for k, strs in aliases_t}
    own = {k: set(v) for k, v in own_t}
    classes = {cls: {n: set(v) for n, v in strs} for cls, strs in classes_t}
    names, attrs, getenvs = _aliases(tree)
    found: set[str] = set()

    def keys_of(node: ast.AST, local: dict[str, set[str]]) -> set[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return {node.value}
        if isinstance(node, ast.Name):
            if node.id in local:
                return set(local[node.id])
            return set(own.get(node.id) or imported.get(node.id) or ())
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            holder = node.value.id
            if holder in aliases:                                  # `module.NAME`
                return set(aliases[holder].get(node.attr) or ())
            return set(classes.get(holder, {}).get(node.attr) or ())   # `Class.NAME`
        return set()

    def visit(node: ast.AST, local: dict[str, set[str]]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            local = {**local, **_function_scope(node)}
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and PLATFORM_NAME.match(node.value):
            found.add(node.value)
        elif isinstance(node, ast.Call) and node.args:
            f = node.func
            if isinstance(f, ast.Attribute) and (
                    (f.attr in READ_METHODS and _is_environ(f.value, names, attrs)) or f.attr == "getenv"):
                found.update(keys_of(node.args[0], local))
            elif isinstance(f, ast.Name) and f.id in getenvs:
                found.update(keys_of(node.args[0], local))
        elif isinstance(node, ast.Subscript) and _is_environ(node.value, names, attrs):
            found.update(keys_of(node.slice, local))
        elif isinstance(node, ast.Compare):          # `"X" in os.environ`
            for op, right in zip(node.ops, node.comparators):
                if isinstance(op, (ast.In, ast.NotIn)) and _is_environ(right, names, attrs):
                    found.update(keys_of(node.left, local))
        for child in ast.iter_child_nodes(node):
            visit(child, local)

    visit(tree, {})
    return frozenset(found)


def read_sites(sources: dict[str, str]) -> dict[str, set[str]]:
    """variable name -> the components whose source reads or names it (see the module docstring)."""
    trees = {path: _parse(path, text) for path, text in sources.items()}
    by_module = {_module_name(path): path for path in trees}
    module_strings = {path: _own_strings(t.body) for path, t in trees.items()}
    class_strings: dict[str, dict[str, dict[str, set[str]]]] = {path: {} for path in trees}
    for path, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_strings[path][node.name] = _own_strings(node.body)
    found: dict[str, set[str]] = {}
    for path, tree in trees.items():
        imported: dict[str, set[str]] = {}
        module_aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                target = by_module.get(node.module)
                for alias in node.names:
                    local = alias.asname or alias.name
                    if target and alias.name in module_strings[target]:
                        imported[local] = module_strings[target][alias.name]
                    sub = by_module.get(f"{node.module}.{alias.name}")
                    if sub:
                        module_aliases[local] = sub
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in by_module:
                        module_aliases[alias.asname or alias.name.split(".")[0]] = by_module[alias.name]
        ctx = (_freeze(imported),
               tuple(sorted((alias, _freeze(module_strings[target])) for alias, target in module_aliases.items())),
               _freeze(module_strings[path]),
               tuple(sorted((cls, _freeze(strs)) for cls, strs in class_strings[path].items())))
        for key in _file_keys(path, sources[path], ctx):
            found.setdefault(key, set()).add(_component(path))
    return found


def read_names(sources: dict[str, str]) -> set[str]:
    return set(read_sites(sources))


ROW = re.compile(r"^\|\s*`([A-Za-z0-9_]+)`\s*\|(.*)\|\s*$")


def doc_rows(text: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in text.splitlines():
        m = ROW.match(line)
        if m:
            # a literal pipe inside a cell is written `\|`; split only on an unescaped one
            rows[m.group(1)] = [c.strip() for c in re.split(r"(?<!\\)\|", m.group(2))]
    return rows


def missing(sources: dict[str, str], doc_text: str) -> set[str]:
    return read_names(sources) - set(doc_rows(doc_text))


def test_the_scan_sees_the_platform():
    names = read_names(source_files())
    assert len(names) >= 90, len(names)
    assert {"FIELD_SHARED_SECRET", "FIELD_DATA_DIR", "FORCE_GATEWAY_ENFORCE"} <= names


def test_every_variable_the_source_reads_is_in_the_environment_doc():
    gap = missing(source_files(), DOC.read_text(encoding="utf-8"))
    assert not gap, f"read in packages/*/src or services/*/src but absent from docs/ENVIRONMENT.md: {sorted(gap)}"


def test_the_reviewer_named_variables_are_documented():
    assert REVIEWER_NAMES <= set(doc_rows(DOC.read_text(encoding="utf-8")))


def _components(cell: str) -> set[str]:
    return {c.strip() for c in cell.split(",") if c.strip()}


def component_mismatches(sources: dict[str, str], doc_text: str) -> dict[str, tuple[set[str], set[str]]]:
    """variable -> (components in the doc row, components whose source names it), where they differ."""
    sites = read_sites(sources)
    out = {}
    for name, cells in doc_rows(doc_text).items():
        if name in sites and _components(cells[0]) != sites[name]:
            out[name] = (_components(cells[0]), sites[name])
    return out


def test_every_row_lists_exactly_the_components_whose_source_names_the_variable():
    """C-338 (reviewer C-336 F-C336-1): the Component column is compared with the scan, not hand-kept."""
    bad = component_mismatches(source_files(), DOC.read_text(encoding="utf-8"))
    assert not bad, "Component column differs from the source (doc, source): " + repr(sorted(bad.items()))


def test_the_doc_prose_carries_no_count_that_could_go_stale():
    """F-C336-4: the number of variables is the number of rows; the prose does not repeat it."""
    head = DOC.read_text(encoding="utf-8").split("| Variable |", 1)[0]
    assert not re.search(r"\*\*\d+\*\*|\b\d{2,3} (environment )?variables\b", head)


def test_the_doc_states_which_columns_are_not_machine_checked():
    """F-C336-3: only names and components are compared with the source."""
    head = DOC.read_text(encoding="utf-8").split("| Variable |", 1)[0]
    assert "hand-maintained" in head.lower() and "Default" in head and "Accepted values" in head


def test_no_documented_variable_is_unread():
    stale = set(doc_rows(DOC.read_text(encoding="utf-8"))) - read_names(source_files())
    assert not stale, f"documented but no longer read by any source file: {sorted(stale)}"


def test_every_row_has_every_column():
    for name, cells in doc_rows(DOC.read_text(encoding="utf-8")).items():
        assert len(cells) == 5, f"{name}: expected 5 further columns, found {len(cells)}"
        assert all(cells), f"{name}: an empty column"


# --- mutants: each must turn the check RED -----------------------------------------------------

def _first_service_file(sources: dict[str, str]) -> str:
    return next(p for p in sources if p.startswith("services/"))


@pytest.mark.parametrize("statement", [
    "_a = os.environ.get('FIELD_X')", "_a = os.getenv('FIELD_X_GETENV')", "_a = os.environ['FIELD_X_INDEX']",
    "_a = env.get('FIELD_X_ENV')", "_a = 'FIELD_X_CONSTANT'", "_a = os.environ.get('NOT_PLATFORM_X')",
])
def test_a_new_read_in_a_service_turns_the_check_red(statement: str):
    sources = source_files()
    target = _first_service_file(sources)
    sources[target] += "\nimport os\nenv = os.environ\n" + statement + "\n"
    assert missing(sources, DOC.read_text(encoding="utf-8")), f"{statement!r} was not caught"


@pytest.mark.parametrize("statement", [
    "cfg = os.environ\n_a = cfg.get('MY_NEW_VAR')",
    "from os import environ as _e\n_a = _e.get('MY_NEW_VAR')",
    "K = 'MY_NEW_VAR'\n_a = os.environ.get(K)",
    "K = 'MY_NEW_VAR'\n_a = os.environ[K]",
    "def _f(source=os.environ):\n    return source.get('MY_NEW_VAR')",
    "first = os.environ\nsecond = first\n_a = second.get('MY_NEW_VAR')",
])
def test_an_aliased_or_constant_held_read_turns_the_check_red(statement: str):
    """C-338 (F-C336-2): the shapes the first scan missed."""
    sources = source_files()
    target = _first_service_file(sources)
    sources[target] += "\nimport os\n" + statement + "\n"
    assert "MY_NEW_VAR" in missing(sources, DOC.read_text(encoding="utf-8")), f"{statement!r} was not caught"


SHAPES = {
    "an attribute alias": "class _C:\n    def __init__(self):\n        self.e = os.environ\n"
                          "    def f(self):\n        return self.e.get('MY_NEW_VAR')",
    "a dict copy": "snap = dict(os.environ)\n_a = snap.get('MY_NEW_VAR')",
    "an os.environ.copy()": "snap = os.environ.copy()\n_a = snap['MY_NEW_VAR']",
    "a bare getenv": "from os import getenv\n_a = getenv('MY_NEW_VAR')",
    "a renamed getenv": "from os import getenv as _g\n_a = _g('MY_NEW_VAR')",
    "an in test": "_a = 'MY_NEW_VAR' in os.environ",
    "a not-in test": "_a = 'MY_NEW_VAR' not in os.environ",
    "a function-local constant": "def _f():\n    k = 'MY_NEW_VAR'\n    return os.environ.get(k)",
    "a class constant": "class _K:\n    NAME = 'MY_NEW_VAR'\n_a = os.environ.get(_K.NAME)",
    "getattr(os, 'environ')": "_a = getattr(os, 'environ').get('MY_NEW_VAR')",
    "setdefault": "os.environ.setdefault('MY_NEW_VAR', 'x')",
    "copy.copy": "import copy\n_a = copy.copy(os.environ).get('MY_NEW_VAR')",
    # C-397 (reviewer C-391A F-C391A-1 and -3): the annotated and walrus aliases, and the two read forms whose
    # branch of the scan had no test of its own (a mutant removing it survived)
    "an annotated alias": "e2: dict = os.environ\n_a = e2.get('MY_NEW_VAR')",
    "a walrus alias": "(w2 := os.environ)\n_a = w2.get('MY_NEW_VAR')",
    "os.getenv as an attribute": "_a = os.getenv('MY_NEW_VAR')",
    "os.getenv with a default": "_a = os.getenv('MY_NEW_VAR', 'x')",
    "a pop": "_a = os.environ.pop('MY_NEW_VAR', None)",
    # C-831 (reviewer C-747 F-C747-1): a tuple-unpack alias and annotated / walrus key constants
    "a tuple-unpack alias": "e3, _x3 = os.environ, 1\n_a = e3.get('MY_NEW_VAR')",
    "an annotated key constant": "KEYC: str = 'MY_NEW_VAR'\n_a = os.environ.get(KEYC)",
    "a walrus key constant": "(kw := 'MY_NEW_VAR')\n_a = os.environ.get(kw)",
    "an annotated function-local constant": "def _f4():\n    k4: str = 'MY_NEW_VAR'\n    return os.environ.get(k4)",
    # C-831 follow-up (reviewer C-43 F-C388-1, -2): lists, nested unpacking, a tuple of KEYS, an attribute target
    "a list-target alias": "[e6, _x6] = os.environ, 1\n_a = e6.get('MY_NEW_VAR')",
    "a list-value alias": "e7, _y7 = [os.environ, 1]\n_a = e7.get('MY_NEW_VAR')",
    "a nested-unpack alias": "(a8, (e8, b8)) = (1, (os.environ, 2))\n_a = e8.get('MY_NEW_VAR')",
    "a tuple of keys": "K1, K2 = 'MY_NEW_VAR', 'OTHER_X'\n_a = os.environ.get(K1)",
    "an attribute tuple alias": ("class _C9:\n    def __init__(self):\n        self.e9, _z9 = os.environ, 1\n"
                                 "    def f(self):\n        return self.e9.get('MY_NEW_VAR')"),
    "a tuple of keys in a function": "def _f10():\n    k1, k2 = 'MY_NEW_VAR', 'OTHER_X'\n    return os.environ.get(k1)",
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_read_shape_for_a_non_platform_name_turns_the_check_red(shape: str):
    """C-353 (reviewer C-351 F-C351-1): the shapes a first scan missed, probed with a NON-platform name."""
    sources = source_files()
    target = _first_service_file(sources)
    sources[target] += "\nimport os\n" + SHAPES[shape] + "\n"
    assert "MY_NEW_VAR" in missing(sources, DOC.read_text(encoding="utf-8")), f"{shape}: not caught"


def test_a_constant_imported_from_another_module_turns_the_check_red():
    sources = source_files()
    first, second = [p for p in sources if p.startswith("services/")][:2]
    sources[first] += "\nOTHER_MODULE_NAME = 'MY_NEW_VAR'\n"
    sources[second] += (f"\nimport os\nfrom {_module_name(first)} import OTHER_MODULE_NAME\n"
                        "_a = os.environ.get(OTHER_MODULE_NAME)\n")
    assert "MY_NEW_VAR" in missing(sources, DOC.read_text(encoding="utf-8"))


def test_a_module_constant_reached_as_module_dot_name_turns_the_check_red():
    sources = source_files()
    services = [p for p in sources if p.startswith("services/")]
    first = next(p for p in services if "." in _module_name(p))      # a module inside a package
    second = next(p for p in services if p != first)
    pkg, _, mod = _module_name(first).rpartition(".")
    sources[first] += "\nOTHER_MODULE_NAME = 'MY_NEW_VAR'\n"
    sources[second] += f"\nimport os\nfrom {pkg} import {mod} as _m\n_a = os.environ.get(_m.OTHER_MODULE_NAME)\n"
    assert "MY_NEW_VAR" in missing(sources, DOC.read_text(encoding="utf-8"))


def test_a_parameter_shadowing_a_module_constant_is_not_resolved_to_it():
    """`name = "X"` at module level and `def f(name): os.environ.get(name)`: the read is of the PARAMETER, not of
    "X" (a parameter, a loop variable or a non-constant assignment is bound-but-unknown in its function)."""
    sources = source_files()
    target = _first_service_file(sources)
    sources[target] += ("\nimport os\nname = 'NOT_A_VARIABLE_AT_ALL'\nkey = 'NOT_A_VARIABLE_EITHER'\n"
                        "def _g(name):\n    return os.environ.get(name)\n"
                        "def _h(items):\n    for key in items:\n        os.environ.get(key)\n")
    assert not {"NOT_A_VARIABLE_AT_ALL", "NOT_A_VARIABLE_EITHER"} & read_names(sources)


def test_a_non_constant_annotated_local_shadows_a_module_constant():
    """C-43 F-C388-2: `k: str = compute()` in a function makes `k` bound-but-unknown there; the module's `k = "X"`
    must not be read as the key."""
    sources = source_files()
    target = _first_service_file(sources)
    sources[target] += ("\nimport os\nshadowed = 'NOT_A_VARIABLE_SHADOWED'\n"
                        "def _s(compute):\n    shadowed: str = compute()\n    return os.environ.get(shadowed)\n")
    assert "NOT_A_VARIABLE_SHADOWED" not in read_names(sources)


def test_a_lowercase_module_constant_is_followed():
    sources = source_files()
    target = _first_service_file(sources)
    sources[target] += "\nimport os\nlowered = 'MY_NEW_VAR'\n_a = os.environ.get(lowered)\n"
    assert "MY_NEW_VAR" in missing(sources, DOC.read_text(encoding="utf-8"))


def _src_line(sources: dict[str, str], cell: str) -> str:
    rel, _, number = cell.rpartition(":")
    matches = [p for p in sources if p.endswith("/src/" + rel.replace("\\", "/"))]
    assert matches, f"First read {cell!r} names no source file"
    return sources[matches[0]].splitlines()[int(number) - 1]


def test_every_first_read_cell_still_points_at_a_line_that_names_the_variable():
    """C-353 (reviewer C-351 F-C351-2): the First read column cannot drift silently."""
    sources = source_files()
    for name, cells in doc_rows(DOC.read_text(encoding="utf-8")).items():
        assert name in _src_line(sources, cells[4]), f"{name}: First read {cells[4]} no longer names it"


NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")


def _literal_default(name: str, line: str) -> str | None:
    m = re.search(r"[\"']" + re.escape(name) + r"[\"']\s*,\s*[\"']?(-?\d+(?:\.\d+)?)[\"']?\s*[,)]", line)
    return m.group(1) if m else None


def numeric_default_mismatches(sources: dict[str, str], doc_text: str) -> tuple[list[str], int]:
    bad, compared = [], 0
    for name, cells in doc_rows(doc_text).items():
        if not NUMBER.match(cells[1]):
            continue
        literal = _literal_default(name, _src_line(sources, cells[4]))
        if literal is None:
            continue
        compared += 1
        if float(literal) != float(cells[1]):
            bad.append(f"{name}: doc {cells[1]}, source {literal}")
    return bad, compared


def test_a_numeric_default_in_the_doc_equals_the_literal_in_source():
    bad, compared = numeric_default_mismatches(source_files(), DOC.read_text(encoding="utf-8"))
    assert not bad, bad
    assert compared >= 5, f"only {compared} numeric defaults could be compared (the check went vacuous)"


def test_a_changed_numeric_default_turns_the_check_red():
    text = DOC.read_text(encoding="utf-8")
    name = "FORCE_GATEWAY_BYPASS_COOLDOWN"
    default = doc_rows(text)[name][1]
    assert NUMBER.match(default), default
    row = next(ln for ln in text.splitlines() if ln.startswith(f"| `{name}` |"))
    changed = row.replace(f"| {default} |", f"| {int(float(default)) + 1} |", 1)
    assert changed != row
    bad, _ = numeric_default_mismatches(source_files(), text.replace(row, changed, 1))
    assert any(name in b for b in bad)


def test_a_first_read_cell_pointing_at_another_line_turns_the_check_red():
    text = DOC.read_text(encoding="utf-8")
    first = doc_rows(text)["FIELD_SHARED_SECRET"][4]
    moved = text.replace(first, first.rsplit(":", 1)[0] + ":1", 1)
    assert moved != text
    sources = source_files()
    assert any(n not in _src_line(sources, c[4]) for n, c in doc_rows(moved).items())


def test_a_component_deleted_from_a_row_turns_the_check_red():
    text = DOC.read_text(encoding="utf-8")
    lines = text.splitlines()
    i = next(n for n, ln in enumerate(lines) if ln.startswith("| `FIELD_LEDGER_URL` |"))
    cells = lines[i].split(" | ")
    parts = [c.strip() for c in cells[1].split(",")]
    assert len(parts) > 1
    cells[1] = ", ".join(parts[:-1])
    lines[i] = " | ".join(cells)
    assert "FIELD_LEDGER_URL" in component_mismatches(source_files(), "\n".join(lines))


def test_a_component_added_to_a_row_turns_the_check_red():
    text = DOC.read_text(encoding="utf-8")
    mutated = text.replace("| `FIELD_SHARED_SECRET` | ", "| `FIELD_SHARED_SECRET` | not-a-component, ", 1)
    assert mutated != text
    assert "FIELD_SHARED_SECRET" in component_mismatches(source_files(), mutated)


def test_a_row_removed_from_the_doc_turns_the_check_red():
    text = DOC.read_text(encoding="utf-8")
    kept = "\n".join(ln for ln in text.splitlines() if not ln.startswith("| `FIELD_SHARED_SECRET`"))
    assert kept != text
    assert missing(source_files(), kept) == {"FIELD_SHARED_SECRET"}
