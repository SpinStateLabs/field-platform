"""Services shorten free text before it reaches this server. An id cut by that shortening is still replaced. The cuts
are made here by the services' own functions, so each case ends exactly as that service ends it.

Mutant T4: the rule for a shortened id removed. Mutant T5: every text treated as a cut one. Mutant T6: a start with
three groups counts only before an ellipsis in a short text.
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


LOOK_ALIKE = ["20261127-0249 UTC", "events-20261127-000001.jsonl", "10000000-20000000", "cafebabe-fed",
              "build 7e04c055-1", "agent cafebabe-fed is active", "from 20261127-0249 to 20261128-0100"]


@pytest.mark.parametrize("text", LOOK_ALIKE)
def test_dates_ranges_and_short_hex_in_a_short_text_are_left_alone(text):
    assert cl._bound({"detail": text, text: 1}, ()) == {"detail": text, text: 1}


@pytest.mark.parametrize("text", LOOK_ALIKE)
def test_dates_ranges_and_short_hex_inside_a_long_text_are_left_alone(text):
    long = "z" * cl.SHORTEST_CUT + " " + text + " z"
    assert cl._bound(long, ()) == long


@pytest.mark.parametrize("text", ["10000000-20000000", "events-20261127-000001.jsonl", "deadbeef-0000-agent"])
def test_a_longer_run_at_the_end_of_a_long_text_is_not_an_id(text):
    long = "z" * cl.SHORTEST_CUT + " " + text
    assert cl._bound(long, ()) == long


#: what may follow the start of an id where a service embeds a text it has cut
AFTER = ["", "\n next", "\r\nnext", "' }", '"', "; next", ") next", "|", " | next"]


@pytest.mark.parametrize("after", AFTER)
def test_each_ending_counts_in_a_long_text_and_not_in_a_short_one(after):
    fragment = TID[:16]
    long = "z" * cl.SHORTEST_CUT + " " + fragment + after
    assert cl._bound(long, ()) == long.replace(fragment, cl.token_ref(fragment))
    short = "z " + fragment + after
    assert cl._bound(short, ()) == short


@pytest.mark.parametrize("kept", [19, 23, 24, 35])
@pytest.mark.parametrize("after", AFTER)
def test_three_groups_count_at_an_ending_in_a_text_of_any_length(after, kept):
    fragment = TID[:kept]
    text = "z " + fragment + after
    assert len(text) < cl.SHORTEST_CUT
    assert cl._bound(text, ()) == text.replace(fragment, cl.token_ref(fragment))


@pytest.mark.parametrize("kept", [9, 13, 18])
def test_fewer_groups_in_a_short_text_need_an_ellipsis(kept):
    text = "z " + TID[:kept]
    assert cl._bound(text, ()) == text


@pytest.mark.parametrize("mark", ["\u2026", "..."])
def test_an_ellipsis_marks_a_cut_in_a_text_of_any_length(mark):
    fragment = TID[:11]
    assert cl._bound(f"id {fragment}{mark} more", ()) == f"id {cl.token_ref(fragment)}{mark} more"


def test_a_whole_id_earlier_in_the_text_does_not_hide_a_cut_one():
    # replacing the whole id makes the text shorter than SHORTEST_CUT; it is judged as it arrived
    fragment = TID[:16]
    text = f"{TID} " + "z" * (cl.SHORTEST_CUT - len(TID) - len(fragment) - 2) + " " + fragment
    assert len(text) == cl.SHORTEST_CUT
    shown = cl._bound(text, ())
    assert TID[:9] not in shown and shown.endswith(cl.token_ref(fragment))
