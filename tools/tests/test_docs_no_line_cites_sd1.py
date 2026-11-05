"""docs/ARCHITECTURE.md and docs/IMPLEMENTATION.md cite code by file and symbol,
never by line number: about half of the cites there had drifted (scout S-D1;
read against main: ci.yml, agent_registry/api.py, ops_console/api.py and most
force_gateway/api.py cites were off), and no check watches them. docs/ENVIRONMENT.md keeps
its numbered anchors because tools/environment_anchors.py verifies those."""

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
LINE_CITE = re.compile(r"\.(?:py|yml|yaml|sh|toml|md|html):\d+")
BARE_LINE = re.compile(r"`:\d+(?:-\d+)?`|`:\d+`")


def test_no_file_line_cites():
    bad = []
    for name in ("ARCHITECTURE.md", "IMPLEMENTATION.md"):
        for n, line in enumerate((DOCS / name).read_text(encoding="utf-8").splitlines(), 1):
            if LINE_CITE.search(line) or BARE_LINE.search(line):
                bad.append(f"{name}:{n}")
    assert not bad, f"cite a symbol, not a line: {bad}"


def test_the_check_sees_a_cite():
    assert LINE_CITE.search("`services/x/api.py:187`")
    assert BARE_LINE.search("at `:235`")
