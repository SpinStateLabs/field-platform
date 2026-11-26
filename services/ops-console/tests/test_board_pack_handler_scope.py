"""Reviewer regression (ssl-ff-reviewer-7): the board pack click handler must run where the helpers it calls exist.

console.html has TWO <script> blocks: the main one, and a second one holding the guided-setup IIFE, which is where
`g`, `sfetch` and `describe` are defined (function scope). A handler that calls them from the first block throws
ReferenceError on click (measured in a real browser engine on PR 833 head d322c43a: `g is not defined`, link inert).
This test finds the <script> block that contains the `a[data-pack]` click handler and requires every helper it calls to
be defined in a scope that block can see: defined at the top level of the same block, not inside an IIFE the handler is
outside of."""
from __future__ import annotations

import re
from pathlib import Path

CONSOLE = Path(__file__).resolve().parents[1] / "src" / "ops_console" / "static" / "console.html"
HELPERS = ("g", "sfetch", "describe")


def _scripts(text: str) -> list[str]:
    return re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", text, flags=re.S)


def _handler_block(text: str) -> tuple[str, int]:
    for s in _scripts(text):
        i = s.find("closest(\"a[data-pack]\")")
        if i >= 0:
            return s, i
    raise AssertionError("no click handler for a[data-pack] found")


def _defined_at_top_level(block: str, name: str, upto: int) -> bool:
    """True when `name` is declared at brace depth 0 of the block (before or after the handler: functions hoist, a
    const/let must come before the handler runs, which a click always is)."""
    depth = 0
    for line in block.splitlines():
        stripped = line.strip()
        if depth == 0 and re.match(rf"(async\s+)?function\s+{name}\b|(const|let|var)\s+{name}\s*=", stripped):
            return True
        depth += line.count("{") + line.count("(") - line.count("}") - line.count(")")
    return False


def test_every_helper_the_board_pack_handler_calls_is_defined_in_its_own_script_scope():
    text = CONSOLE.read_text(encoding="utf-8")
    block, at = _handler_block(text)
    handler = block[at - 200: block.find("});", at) + 3]
    for name in HELPERS:
        if re.search(rf"(?<![\w.]){name}\(", handler):
            assert _defined_at_top_level(block, name, at), (
                f"`{name}` is called by the board pack click handler but is not defined at the top level of the "
                "<script> block that holds the handler (it is local to the setup IIFE in the second block), so a click "
                "throws ReferenceError and the link does nothing")
