"""Every third-party module the server imports is a declared dependency of the package (C-775 F-8: ``jsonschema`` was
imported by tools.py and declared by nothing; it reached CI only through the hashed closure). Mutant P2: drop a line
from ``dependencies``."""
import ast
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
#: import name -> distribution name, where they differ
DIST = {"field_core": "field-core"}


def imported_top_level_modules() -> set[str]:
    names: set[str] = set()
    for path in ROOT.joinpath("src", "field_mcp").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names - sys.stdlib_module_names - {"field_mcp"}


def declared_dependencies() -> set[str]:
    deps = tomllib.loads(ROOT.joinpath("pyproject.toml").read_text("utf-8"))["project"]["dependencies"]
    return {re.match(r"[A-Za-z0-9_.-]+", d).group(0).lower().replace("_", "-") for d in deps}


def test_every_third_party_import_is_a_declared_dependency():
    imported = {DIST.get(m, m).replace("_", "-") for m in imported_top_level_modules()}
    assert imported, "no third-party import found: the scan is broken"
    assert imported <= declared_dependencies(), sorted(imported - declared_dependencies())
