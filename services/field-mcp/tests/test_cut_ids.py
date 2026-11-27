"""Services shorten free text before it reaches this server. An id cut by that shortening is still replaced. The cuts
are made here by the services' own functions, so each case ends exactly as that service ends it.

Mutant T4: the rule for a shortened id removed.
"""
import pytest

from compliance_crosswalk.engine import ONE_LINE_MAX, one_line
from incident_replay.engine import MD_FIELD_MAX, SUMMARY_MAX, _one_md_line, _summarize
from lifecycle_manager.engine import _body
from field_mcp import client as cl

TID = "7d3f9a1c-52be-4c08-9e6a-1b2c3d4e5f60"          # made up, the shape field_core.delegation mints
LIFECYCLE_MAX = 500
#: how many characters of the id are left before the cut: from "eight and a dash" to all but the last
KEPT = range(9, len(TID))


def padded(start: int) -> str:
    """Text whose character number ``start`` is the first character of the id."""
    return "z" * (start - 1) + " " + TID + " end"


def replay_summary(kept: int) -> str:
    head = "kill.agent by o ("
    event = {"event_type": "kill.agent", "payload": {"operator": "o", "reason": padded(SUMMARY_MAX - kept - len(head))}}
    return _summarize(event)


def replay_markdown(kept: int) -> str:
    return _one_md_line(padded(MD_FIELD_MAX - 1 - kept))


def lifecycle_refusal(kept: int) -> str:
    class Reply:
        text = padded(LIFECYCLE_MAX - kept)

    return _body(Reply())


def crosswalk_line(kept: int) -> str:
    return one_line(padded(ONE_LINE_MAX - 1 - kept))


CUTS = [replay_summary, replay_markdown, lifecycle_refusal, crosswalk_line]


@pytest.mark.parametrize("kept", KEPT)
@pytest.mark.parametrize("cut", CUTS, ids=lambda f: f.__name__)
def test_the_start_of_an_id_left_by_a_services_cut_is_replaced(cut, kept):
    text = cut(kept)
    assert TID[:kept] in text and TID[:kept + 1] not in text      # the service cut it exactly here
    shown = cl._bound({"detail": text, text: 1}, ())
    shown_key = next(k for k in shown if k != "detail")
    for value in (shown["detail"], shown_key):
        assert TID[:9] not in value
        assert cl.token_ref(TID[:kept]) in value


def test_a_whole_id_keeps_its_own_reference():
    assert cl._bound(f"token {TID} expired", ()) == f"token {cl.token_ref(TID)} expired"


@pytest.mark.parametrize("text", [
    f"token {TID[:8]}\u2026 revoked",                       # the eight characters the platform prints on purpose
    "deadbeef-agent and cafebabe-gateway",
    "2026-11-27T01:00:00Z",
    "[id:0123456789ab]",
], ids=["printed-prefix", "words", "time", "reference"])
def test_text_that_is_not_a_shortened_id_is_left_alone(text):
    assert cl._bound(text, ()) == text
