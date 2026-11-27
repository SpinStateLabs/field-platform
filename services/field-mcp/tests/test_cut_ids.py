"""Services shorten free text before it reaches this server. The start of an id left by that shortening is replaced
once it holds eight hex characters, a dash, four hex characters and a dash. The cuts are made here by the services' own
functions, so each case ends exactly as that service ends it.

Mutants: T4 the rule removed; T5 the second dash optional; T6 something required after the second dash; T7 the rule
applied only before an ellipsis or the end of a text.
"""
import pytest

from compliance_crosswalk.engine import ONE_LINE_MAX, evaluate, one_line
from incident_replay.engine import MD_FIELD_MAX, SUMMARY_MAX, _one_md_line, _summarize
from lifecycle_manager.engine import _body
from field_mcp import client as cl

TID = "7d3f9a1c-52be-4c08-9e6a-1b2c3d4e5f60"          # made up, the shape field_core.delegation mints
LIFECYCLE_MAX = 500
#: how many characters of the id are left before the cut: from "eight and a dash" to all but the last
KEPT = range(9, len(TID))
#: the shortest start that is replaced: "xxxxxxxx-xxxx-"
SHORTEST = 14


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


def crosswalk_declared(kept: int) -> str:
    """The whole report path: the declared value is cut, then put on one line. The value holds a run of spaces."""
    before = len("identity.principal = 'a b ")                       # as printed, with the run collapsed
    value = "a  b " + padded(119 - kept - before)
    report = evaluate({"identity": {"principal": value}})
    return next(c.declared_detail for c in report.controls if c.manifest_path == "identity.principal")


CUTS = [replay_summary, replay_markdown, lifecycle_refusal, crosswalk_line, crosswalk_declared]


@pytest.mark.parametrize("kept", KEPT)
@pytest.mark.parametrize("cut", CUTS, ids=lambda f: f.__name__)
def test_the_start_of_an_id_left_by_a_services_cut_is_replaced(cut, kept):
    text = cut(kept)
    assert TID[:kept] in text and TID[:kept + 1] not in text      # the service cut it exactly here
    shown = cl._bound({"detail": text, text: 1}, ())
    shown_key = next(k for k in shown if k != "detail")
    for value in (shown["detail"], shown_key):
        if kept >= SHORTEST:
            assert TID[:9] not in value
            assert cl.token_ref(TID[:kept]) in value
        else:
            assert value == text                                  # thirteen characters or fewer: left as it is


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


LOOK_ALIKE = ["20261127-0249 UTC", "events-20261127-000001.jsonl", "10000000-20000000", "cafebabe-fed",
              "build 7e04c055-1", "agent cafebabe-fed is active", "from 20261127-0249 to 20261128-0100"]


@pytest.mark.parametrize("text", LOOK_ALIKE)
def test_dates_ranges_and_short_hex_in_a_short_text_are_left_alone(text):
    assert cl._bound({"detail": text, text: 1}, ()) == {"detail": text, text: 1}


@pytest.mark.parametrize("text", LOOK_ALIKE)
def test_dates_ranges_and_short_hex_inside_a_long_text_are_left_alone(text):
    for long in ("z" * 300 + " " + text + " z", "z" * 300 + " " + text, text + "\u2026"):
        assert cl._bound(long, ()) == long


#: what may stand after a shortened id: nothing, a mark, punctuation, white space, a letter
AFTER = ["", "\u2026", "...", " next", "\n next", "' }", '"', "; next", ")", " |", ",", "]", "}", "<", "&", "`", ".", ":",
         "\\", "zz", "-agent"]


@pytest.mark.parametrize("after", AFTER)
@pytest.mark.parametrize("kept", [14, 18, 19, 23, 24, 35])
@pytest.mark.parametrize("before", ["", "id ", "z" * 300], ids=["start", "short", "long"])
def test_the_start_is_replaced_wherever_it_stands(before, kept, after):
    fragment = TID[:kept]
    shown = cl._bound(before + fragment + after, ())
    # after a start that ends in a full group, a dash and a hex letter continue the id's grouping and go with it
    taken = fragment + "-a" if after == "-agent" and kept in (18, 23) else fragment
    assert shown == (before + fragment + after).replace(taken, cl.token_ref(taken))


@pytest.mark.parametrize("kept", range(9, SHORTEST))
def test_thirteen_characters_or_fewer_are_left_alone(kept):
    for text in ("z " + TID[:kept], "z " + TID[:kept] + "\u2026", "z" * 300 + " " + TID[:kept]):
        assert cl._bound(text, ()) == text


def test_other_text_of_the_shape_is_replaced_too():
    assert cl._bound("agent deadbeef-0000-agent", ()) == f"agent {cl.token_ref('deadbeef-0000-')}agent"


def test_a_whole_id_followed_by_a_shortened_one():
    shown = cl._bound(f"{TID} {TID[:20]}", ())
    assert shown == f"{cl.token_ref(TID)} {cl.token_ref(TID[:20])}"
