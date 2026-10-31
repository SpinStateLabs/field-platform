"""C-726 (reviewer C-693 F-C693-1): the Windows-only PowerShell tests (test_ssl_renewal.py, test_field_rest_secret.py)
are skipped everywhere but a Windows box, so a change that makes them stale goes unseen. PR 342 put placeholders into
the runbook and these tests still held the old literal paths: on Windows every `assert RUNBOOK_PATHS[key] in args`
would have failed. These checks read the two files as TEXT (no PowerShell, no msvcrt) and hold the three couplings:

1. every RUNBOOK_PATHS literal the ssl test swaps out is a string the runbook's own `$template` / `$secret` lines hold;
2. the shape the decoy shims use to find the shim's real default paths matches the shim's code, once per default;
3. neither Windows-only test file names a personal path or address itself (the guard allowlist holds no entry for them).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

TESTS = Path(__file__).parent
TOOLS = TESTS.parent
REPO = TOOLS.parent
SSL_TEST = TESTS / "test_ssl_renewal.py"
REST_TEST = TESTS / "test_field_rest_secret.py"
SHIM = TOOLS / "field-rest.ps1"
RUNBOOK = REPO / "docs" / "runbooks" / "token-renewal.md"
ALLOWLIST = TESTS / "public_safety_allowlist.txt"


def _module_value(path: Path, name: str):
    """Evaluate the module-level assignment `name = <literal expression>` without importing the module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return eval(compile(ast.Expression(node.value), str(path), "eval"), {})  # noqa: S307 (literal expressions only)
    raise AssertionError(f"{path.name} has no module-level {name}")


def _template_and_secret_lines() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    section = text[text.index("## 5. Install for the ssl agents"):text.index("## 6. Evidence")]
    lines = re.findall(r"^\$(?:template|secret) = '.*'$", section, flags=re.M)
    assert lines, "the runbook has no $template / $secret line"
    return "\n".join(lines)


RUNBOOK_PATHS = _module_value(SSL_TEST, "RUNBOOK_PATHS")


@pytest.mark.parametrize("key", sorted(RUNBOOK_PATHS))
def test_every_runbook_literal_the_ssl_test_swaps_out_is_in_the_runbook(key: str):
    assert RUNBOOK_PATHS[key] in _template_and_secret_lines(), key


def test_the_runbook_paths_table_has_the_six_keys_the_swap_loop_uses():
    assert set(RUNBOOK_PATHS) == {"python", "tool", "store", "secret", "repo", "base"}


@pytest.mark.parametrize("test_file", [SSL_TEST, REST_TEST], ids=lambda p: p.name)
@pytest.mark.parametrize("name", ["tokens-gb10.json", "gb10-estate-secret"])
def test_the_decoy_shape_finds_the_shims_real_default_exactly_where_it_is(test_file: Path, name: str):
    profile = _module_value(test_file, "_PROFILE")
    rx = re.compile(profile + re.escape(name))
    shim = SHIM.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in shim.splitlines() if not ln.lstrip().startswith("#"))
    assert rx.search(code), f"{test_file.name}: the shape no longer finds the shim's {name} default"
    swapped, hits = rx.subn(lambda _m: "swapped", code)
    assert hits >= 1 and not rx.search(swapped)


@pytest.mark.parametrize("test_file", [SSL_TEST, REST_TEST], ids=lambda p: p.name)
def test_the_windows_only_test_files_hold_no_personal_path_or_address(test_file: Path):
    import test_public_safety_c560 as guard  # same directory; its classes are the definition of "personal"

    assert dict(guard.scan_text(test_file.read_text(encoding="utf-8"))) == {}
    keys = guard.parse_allowlist(ALLOWLIST.read_text(encoding="utf-8"))
    assert not [k for k in keys if k.startswith(f"tools/tests/{test_file.name}::")]
