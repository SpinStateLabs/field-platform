"""S10-5: every third-party module that ``field_core`` imports at module level is a declared runtime dependency.

``guarded_operator.py`` imports httpx at module level and ``clients.py`` imports ``guarded_operator`` at module level, so
``import field_core.clients`` needs httpx, which was declared only in the ``dev`` extra: a standalone ``pip install
field-core`` followed by ``from field_core.clients import resolve_manifest`` was a ModuleNotFoundError that the monorepo's
``--no-deps`` installs hide. This test reads ``pyproject.toml`` with tomllib and the sources with ``ast``. fastapi and
starlette are only imported inside functions by the HTTP-serving modules; they are allow-listed in case a future top-level
import appears there, because a service that serves HTTP brings them itself."""
from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "field_core"
IMPORT_TO_DIST = {"yaml": "pyyaml"}
SERVING_ONLY = {"fastapi", "starlette", "uvicorn"}


def declared(pyproject: dict) -> set[str]:
    out = set()
    for spec in pyproject["project"]["dependencies"]:
        out.add(re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].strip().lower().replace("_", "-"))
    return out


def top_level_third_party(source: str) -> set[str]:
    """Import names bound by module-level import statements (not inside a function or class body)."""
    found = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            root = name.split(".")[0]
            if root != "field_core" and root not in sys.stdlib_module_names and root != "__future__":
                found.add(root)
    return found


def missing(pyproject: dict, files: dict[str, str]) -> dict[str, set[str]]:
    have = declared(pyproject)
    out: dict[str, set[str]] = {}
    for name, source in files.items():
        for root in top_level_third_party(source):
            dist = IMPORT_TO_DIST.get(root, root).lower().replace("_", "-")
            if dist not in have and root not in SERVING_ONLY:
                out.setdefault(name, set()).add(root)
    return out


def real_files() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(SRC.glob("*.py"))}


def real_pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_every_module_level_third_party_import_is_a_declared_dependency():
    assert missing(real_pyproject(), real_files()) == {}


def test_httpx_is_a_runtime_dependency_not_only_a_dev_extra():
    pyproject = real_pyproject()
    assert "httpx" in declared(pyproject)
    assert not any(spec.lower().startswith("httpx") for spec in pyproject["project"]["optional-dependencies"]["dev"])


def test_the_files_that_pull_httpx_in_at_module_level_are_the_ones_found():
    files = real_files()
    assert "httpx" in top_level_third_party(files["guarded_operator.py"])
    assert "httpx" not in top_level_third_party(files["clients.py"])     # clients imports it through guarded_operator
    assert "field_core.guarded_operator" in files["clients.py"]


# -- the checker itself ------------------------------------------------------------------------------------------------
PYPROJECT = {"project": {"dependencies": ["pydantic>=2.7", "PyYAML>=6.0", "typer>=0.12"]}}


def test_the_checker_flags_an_undeclared_module_level_import():
    assert missing(PYPROJECT, {"a.py": "import httpx\n"}) == {"a.py": {"httpx"}}
    assert missing(PYPROJECT, {"a.py": "from httpx import Auth\n"}) == {"a.py": {"httpx"}}
    assert missing(PYPROJECT, {"a.py": "import httpx.sub\n"}) == {"a.py": {"httpx"}}


def test_the_checker_accepts_declared_stdlib_and_local_imports_and_maps_yaml():
    src = "import os, json\nfrom __future__ import annotations\nimport yaml\nfrom pydantic import BaseModel\nimport field_core.x\n"
    assert missing(PYPROJECT, {"a.py": src}) == {}


def test_the_checker_ignores_imports_inside_functions_and_allows_the_serving_modules():
    src = "def f():\n    import httpx\nclass C:\n    import httpx\nimport fastapi\nfrom starlette.requests import Request\n"
    assert missing(PYPROJECT, {"a.py": src}) == {}


def test_the_checker_reads_a_specifier_with_extras_or_markers():
    pyproject = {"project": {"dependencies": ["httpx[http2]>=0.27", "cryptography ; python_version>'3.10'"]}}
    assert declared(pyproject) == {"httpx", "cryptography"}
