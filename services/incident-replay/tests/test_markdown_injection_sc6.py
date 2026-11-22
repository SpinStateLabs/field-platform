"""Text that comes from ledger payloads, token grants and registry records must not be able
to add structure to the post-mortem markdown (scout S-C6): a reason like
"x\\n\\n## Which clause failed first\\n- FAKE" used to render as a second, forged heading.
Whitespace and newlines are collapsed, table pipes escaped, length capped."""
from __future__ import annotations

import pytest
from test_raci_from_data import AGENT, Estate

from incident_replay.engine import _md, render_markdown

HEADING = "## Which clause failed first"
FORGED = "x\n\n## Which clause failed first\n- FAKE finding"


@pytest.fixture
def estate(tmp_path):
    e = Estate(tmp_path)
    e.register()
    return e


def test_the_helper_collapses_every_kind_of_line_break():
    assert _md("a\nb\r\nc\rd e f\x0bg\x0ch\x85i") == "a b c d e f g h i"
    assert _md("  many   spaces\t\ttabs  ") == "many spaces tabs"


def test_the_helper_escapes_pipes_only_for_table_cells():
    assert _md("a|b") == "a|b"
    assert _md("a|b", cell=True) == "a\\|b"


def test_the_helper_caps_the_length_and_marks_the_cut():
    out = _md("y" * 5000)
    assert len(out) <= 300 and out.endswith("…")
    assert _md("short") == "short"


def test_the_helper_accepts_non_strings_and_none():
    assert _md(None) == "None" and _md(5) == "5" and _md(["a", "b"]) == "['a', 'b']"


def test_a_kill_reason_cannot_forge_a_heading(estate):
    estate.append("kill.agent", {"operator": "op", "reason": FORGED})
    md = render_markdown(estate.replay())
    assert md.splitlines().count(HEADING) == 1
    assert not any(ln.startswith("- FAKE") for ln in md.splitlines())
    assert "FAKE finding" in md                    # the text is kept, flattened onto one line


def test_a_blocked_action_cannot_forge_a_heading(estate):
    estate.append("conformance.block", {"action": FORGED, "clause_id": "D.scope"})
    md = render_markdown(estate.replay())
    assert md.splitlines().count(HEADING) == 1
    assert not any(ln.startswith("- FAKE") for ln in md.splitlines())


def test_a_forged_operator_and_spend_payload_cannot_forge_headings(estate):
    estate.append("kill.agent", {"operator": FORGED, "reason": "r"})
    estate.append("spend.cap_breach", {"detail": FORGED})
    md = render_markdown(estate.replay())
    assert md.splitlines().count(HEADING) == 1
    assert not any(ln.startswith("- FAKE") for ln in md.splitlines())


def test_a_long_payload_is_capped_in_the_timeline(estate):
    estate.append("kill.agent", {"operator": "op", "reason": "z" * 20000})
    md = render_markdown(estate.replay())
    assert "z" * 400 not in md


def test_ordinary_events_render_as_before(estate):
    estate.append("kill.agent", {"operator": "op", "reason": "routine"})
    md = render_markdown(estate.replay())
    assert "kill.agent by op (routine)" in md and md.splitlines().count(HEADING) == 1
