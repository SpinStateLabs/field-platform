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


def _is_environ(node: ast.AST) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "environ") or (
        isinstance(node, ast.Name) and node.id in ("env", "environ"))


def read_names(sources: dict[str, str]) -> set[str]:
    found: set[str] = set()
    for path, text in sources.items():
        for node in ast.walk(ast.parse(text, filename=path)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and PLATFORM_NAME.match(node.value):
                found.add(node.value)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args:
                first = node.args[0]
                if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                    continue
                if (node.func.attr in ("get", "pop") and _is_environ(node.func.value)) or node.func.attr == "getenv":
                    found.add(first.value)
            elif isinstance(node, ast.Subscript) and _is_environ(node.value):
                key = node.slice
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    found.add(key.value)
    return found


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


def test_a_row_removed_from_the_doc_turns_the_check_red():
    text = DOC.read_text(encoding="utf-8")
    kept = "\n".join(ln for ln in text.splitlines() if not ln.startswith("| `FIELD_SHARED_SECRET`"))
    assert kept != text
    assert missing(source_files(), kept) == {"FIELD_SHARED_SECRET"}
