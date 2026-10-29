"""C-329 (reviewer B-03): docs/ENVIRONMENT.md lists every environment variable the source reads.

An AST pass over packages/*/src and services/*/src collects (a) every string constant that is exactly
a platform variable name (FIELD_*, FORCE_*, CLAUDE_*, ANTHROPIC_*, CROSSWALK_*; this catches reads
through module constants, helper functions, typer `envvar=` and ops-console `env=` arguments) and
(b) any name read directly as `os.environ.get/pop(...)`, `os.environ[...]`, `os.getenv(...)` or
`env.get(...)`/`env[...]` on a name called env or environ. A name read in the source and missing from
the first column of the file's table fails. The test also pins the names the reviewer found missing or
documented only in a changelog or spec, and that no row has an empty column.
"""
from __future__ import annotations

import ast
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


def _environ_names(tree: ast.AST) -> set[str]:
    """Every name that holds os.environ in this module: env, environ, `x = os.environ`,
    `from os import environ as x`, and a parameter whose default is os.environ (C-338, F-C336-2)."""
    names = {"env", "environ"}

    def is_environ(node: ast.AST | None) -> bool:
        return (isinstance(node, ast.Attribute) and node.attr == "environ") or (
            isinstance(node, ast.Name) and node.id in names)

    for _ in range(3):  # a few passes so `a = os.environ; b = a` settles
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "os":
                names.update(a.asname or a.name for a in node.names if a.name == "environ")
            elif isinstance(node, ast.Assign) and is_environ(node.value):
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args
                positional = args.posonlyargs + args.args
                for arg, default in zip(positional[len(positional) - len(args.defaults):], args.defaults):
                    if is_environ(default):
                        names.add(arg.arg)
                for arg, default in zip(args.kwonlyargs, args.kw_defaults):
                    if is_environ(default):
                        names.add(arg.arg)
    return names


def read_sites(sources: dict[str, str]) -> dict[str, set[str]]:
    """variable name -> the components whose source reads or names it (see the module docstring)."""
    found: dict[str, set[str]] = {}
    for path, text in sources.items():
        tree = ast.parse(text, filename=path)
        comp = _component(path)
        environ = _environ_names(tree)
        consts = {t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign)
                  and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
                  for t in n.targets if isinstance(t, ast.Name)}

        def is_environ(node: ast.AST) -> bool:
            return (isinstance(node, ast.Attribute) and node.attr == "environ") or (
                isinstance(node, ast.Name) and node.id in environ)

        def key_of(node: ast.AST) -> str | None:
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return node.value
            if isinstance(node, ast.Name):
                return consts.get(node.id)   # a name held in a module constant (F-C336-2)
            return None

        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and PLATFORM_NAME.match(node.value):
                name = node.value
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args:
                if (node.func.attr in ("get", "pop") and is_environ(node.func.value)) or node.func.attr == "getenv":
                    name = key_of(node.args[0])
            elif isinstance(node, ast.Subscript) and is_environ(node.value):
                name = key_of(node.slice)
            if name:
                found.setdefault(name, set()).add(comp)
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
