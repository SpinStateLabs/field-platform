"""The ADR 10 notes name code by symbol, not by line number (C-1026, F-C1016-1).

Line numbers in api.py move whenever another PR inserts above them, and git
merges those PRs without a conflict, so a line citation goes stale silently.
The notes therefore cite symbols; this test fails if a cited symbol is
renamed or removed, or if a line-range citation of those files comes back.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / "docs/adr/ADR_Pack_10_FORCE_Gateway.md"
SRC = ROOT / "services/force-gateway/src/force_gateway"

_NOTES = re.compile(r"^> \d\. .*$", re.M)


def _notes_text() -> str:
    text = ADR.read_text(encoding="utf-8")
    return "\n".join(_NOTES.findall(text))


def test_the_notes_exist() -> None:
    assert len(_NOTES.findall(ADR.read_text(encoding="utf-8"))) >= 6


def test_no_line_citation_of_the_gateway_sources_in_the_notes() -> None:
    notes = _notes_text()
    for name in ("api.py", "store.py"):
        assert not re.search(re.escape(name) + r":\d", notes), name


def test_every_symbol_the_notes_cite_still_exists() -> None:
    api = (SRC / "api.py").read_text(encoding="utf-8")
    store = (SRC / "store.py").read_text(encoding="utf-8")
    notes = _notes_text()
    cited = {
        "_enter_bypass": api,
        "_ledger_event": api,
        "_posture_flag": api,
        "judge_bypassed": api,
        "commit_request": store,
        "DEFAULT_RETAIN": store,
    }
    for symbol, source in cited.items():
        assert symbol in notes, f"note no longer cites {symbol}"
        assert re.search(r"\b" + re.escape(symbol) + r"\b", source), symbol
