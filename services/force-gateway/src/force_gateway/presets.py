"""FORCE preset system blocks, assembled from the shipped protocol text.

``data/protocol.md`` is vendored VERBATIM from the Force-Field plugin
(`plugins/force/skills/force/protocol.md`). This module parses its five
component sections and the OUTPUT RULES, and composes preset blocks per the
shipped preset table:

    analysis   F+O+R+C+E   (full protocol)
    brainstorm F+C+E       (no objections-first, no source gating)
    draft      F+C         (writing assistance)
    audit      F+R+C+E     (skip objections, prioritize source grounding)

No FORCE language is authored here — if it isn't in protocol.md, it isn't
in the injected block.
"""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

PRESETS: dict[str, str] = {
    "analysis": "FORCE",
    "brainstorm": "FCE",
    "draft": "FC",
    "audit": "FRCE",
}

_SECTION_RE = re.compile(
    r"^## \[(?P<letter>[FORCE])\] (?P<title>.+?)$(?P<body>.*?)(?=^## |^---\s*$(?!.))",
    re.M | re.S,
)


def _protocol_text() -> str:
    root = resources.files("force_gateway") / "data"
    return Path(str(root / "protocol.md")).read_text(encoding="utf-8")


def _parse() -> tuple[dict[str, str], str]:
    text = _protocol_text()
    blocks: dict[str, str] = {}
    for match in re.finditer(r"^## \[([FORCE])\] (.+)$", text, re.M):
        letter = match.group(1)
        start = match.start()
        nxt = text.find("\n## ", start + 1)
        section = text[start: nxt if nxt != -1 else len(text)]
        section = section.rsplit("\n---", 1)[0].rstrip()
        blocks[letter] = section
    rules_match = re.search(r"^## OUTPUT RULES.*?(?=\n---|\Z)", text, re.M | re.S)
    output_rules = rules_match.group(0).rstrip() if rules_match else ""
    return blocks, output_rules


_BLOCKS, _OUTPUT_RULES = _parse()


def component_block(letter: str) -> str:
    return _BLOCKS[letter]


def preset_block(preset: str) -> str:
    """Compose the injectable system block for a preset."""
    if preset not in PRESETS:
        raise KeyError(
            f"unknown FORCE preset {preset!r}; choose from {', '.join(PRESETS)}"
        )
    letters = PRESETS[preset]
    parts = [
        "# FORCE Runtime Protocol — Spin State Labs "
        f"(preset: {preset}, components: {'+'.join(letters)})",
        "Apply the following operational instructions to every response.",
    ]
    parts += [_BLOCKS[letter] for letter in letters]
    parts.append(_OUTPUT_RULES)
    return "\n\n".join(p for p in parts if p)
