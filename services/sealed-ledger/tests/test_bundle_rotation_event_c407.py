"""C-407 (reviewer C-400 F-C400-1, F-C400-2): the "first live event must be the rotation event" check of
`verify_bundle`, one comparison at a time, and the events-array guard of the witness.

An export of a ledger whose oldest segments are archived starts at the rotation event that closed the last archived
segment (here index 8). The check refuses a bundle whose first live event is not that rotation event, names another end
index, or names another closed head. The tamper tests of C-193 only edited the verification block, which trips earlier
checks; here the first live event itself is rewritten and the rest of the bundle is RELINKED to match (events re-hashed
and re-chained, the spine and both head hashes updated), the forgery a holder without the signing key can build, so
that the rotation-event check is the only thing standing in its way."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from field_core.ledger import compute_event_hash
from ledger_c2_support import archive_oldest_for_test, three_segments
from sealed_ledger import witness as w
from sealed_ledger.bundle import verify_bundle

REASON = "should be the rotation event closing archived segment 2 (global 0..7), but it is not"


@pytest.fixture()
def archived_bundle(tmp_path):
    """Three segments (0..3, 4..7, 8..10), the two oldest archived: the live part is indices 8..10."""
    s, _, _ = three_segments(tmp_path / "ledger")
    archive_oldest_for_test(s, tmp_path / "archive")
    archive_oldest_for_test(s, tmp_path / "archive")
    bundle = Path(s.export(tmp_path / "exports").bundle_dir)
    v = verify_bundle(bundle)
    assert v.ok and v.archived_prefix == 8, v
    return bundle


def _read(bundle: Path, name: str):
    return json.loads((bundle / name).read_text(encoding="utf-8"))


def _write(bundle: Path, name: str, obj) -> None:
    (bundle / name).write_text(json.dumps(obj, indent=2), encoding="utf-8")


def _forge_first_live_event(bundle: Path, mutate) -> None:
    """Rewrite the first live event with `mutate(record)`, then relink everything after it so only the content of
    that event differs: each later event gets the new `prev_hash` and is re-hashed, the spine entries and both
    `head_hash` fields follow."""
    lines = (bundle / "events.jsonl").read_text(encoding="utf-8").splitlines()
    summary = _read(bundle, "summary.json")
    proof = _read(bundle, "chain_proof.json")
    first = proof["first_index"]
    prev = None
    for j, line in enumerate(lines):
        rec = json.loads(line)
        if j == 0:
            mutate(rec)
        else:
            rec["prev_hash"] = prev
        rec["hash"] = compute_event_hash(rec)
        lines[j] = json.dumps(rec)
        entry = proof["spine"][summary["indices"][j] - first]
        entry["prev_hash"], entry["hash"] = rec["prev_hash"], rec["hash"]
        prev = rec["hash"]
    (bundle / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary["head_hash"] = proof["head_hash"] = prev
    _write(bundle, "summary.json", summary)
    _write(bundle, "chain_proof.json", proof)


def test_the_relink_forgery_of_an_innocent_edit_still_verifies_so_the_refusals_below_are_the_check_alone(archived_bundle):
    """The control: the same forgery that changes only the operator's name inside the rotation payload (a field the
    check does not look at) leaves a bundle that verifies, so the machinery relinks the whole bundle consistently."""
    _forge_first_live_event(archived_bundle, lambda rec: rec["payload"].update(operator="somebody-else"))
    v = verify_bundle(archived_bundle)
    assert v.ok, v.reason


@pytest.mark.parametrize("etype", ["action", "spend", "ledger.segment.rotated.x", "Ledger.Segment.Rotated", ""])
def test_a_first_live_event_that_is_not_a_rotation_event_is_refused(archived_bundle, etype):
    _forge_first_live_event(archived_bundle, lambda rec: rec.update(event_type=etype))
    v = verify_bundle(archived_bundle)
    assert not v.ok and v.first_failing_index == 8 and REASON in v.reason, v.reason


@pytest.mark.parametrize("end_index", [6, 8, 0, None, "7", 7.5])
def test_a_rotation_event_that_names_another_end_index_is_refused(archived_bundle, end_index):
    _forge_first_live_event(archived_bundle, lambda rec: rec["payload"].update(end_index=end_index))
    v = verify_bundle(archived_bundle)
    assert not v.ok and v.first_failing_index == 8 and REASON in v.reason, v.reason


def test_a_rotation_event_without_an_end_index_is_refused(archived_bundle):
    _forge_first_live_event(archived_bundle, lambda rec: rec["payload"].pop("end_index"))
    v = verify_bundle(archived_bundle)
    assert not v.ok and v.first_failing_index == 8 and REASON in v.reason, v.reason


@pytest.mark.parametrize("head", ["0" * 64, "f" * 64, "", None])
def test_a_rotation_event_that_names_another_closed_head_is_refused(archived_bundle, head):
    _forge_first_live_event(archived_bundle, lambda rec: rec["payload"].update(head_hash=head))
    v = verify_bundle(archived_bundle)
    assert not v.ok and v.first_failing_index == 8 and REASON in v.reason, v.reason


def test_a_rotation_event_without_a_closed_head_is_refused(archived_bundle):
    _forge_first_live_event(archived_bundle, lambda rec: rec["payload"].pop("head_hash"))
    v = verify_bundle(archived_bundle)
    assert not v.ok and v.first_failing_index == 8 and REASON in v.reason, v.reason


@pytest.mark.parametrize("segment_closed", [1, 3, 0, None, "2", True, [2]])
def test_a_rotation_event_that_closes_another_segment_is_refused(archived_bundle, segment_closed):
    _forge_first_live_event(archived_bundle, lambda rec: rec["payload"].update(segment_closed=segment_closed))
    v = verify_bundle(archived_bundle)
    assert not v.ok and v.first_failing_index == 8 and REASON in v.reason, v.reason


def test_the_rotation_event_check_names_the_first_live_index_not_a_later_one(archived_bundle):
    """Only the first live event is held to the rotation rule: a later event of any type is not."""
    _forge_first_live_event(archived_bundle, lambda rec: rec["payload"].update(end_index=1))
    v = verify_bundle(archived_bundle)
    assert v.first_failing_index == 8 and "index 8 should be the rotation event" in v.reason


# --- F-C400-2: the witness's events-array guard -------------------------------------------------------------------


def test_an_events_source_that_is_a_json_array_is_read_as_the_list_it_is():
    assert w.load_events(b'[{"event_type": "anchor.remote"}, {"event_type": "x"}]') == [
        {"event_type": "anchor.remote"}, {"event_type": "x"}]


def test_an_events_source_that_is_one_json_object_is_read_as_one_jsonl_event_not_as_an_array():
    """A body that starts with `{` is not the array form, so it is a one-line JSONL file."""
    assert w.load_events(b'{"event_type": "anchor.remote"}') == [{"event_type": "anchor.remote"}]


def test_an_array_form_that_does_not_decode_to_a_list_is_refused_with_the_array_message(monkeypatch):
    """`[` always decodes to a list with a real JSON parser, so the guard is a defence in depth against the parser
    (or its strict wrapper) ever answering with something else; pinned by making the parser do exactly that."""
    monkeypatch.setattr(w, "strict_json_loads", lambda text: {"events": []})
    with pytest.raises(w.WitnessError, match="events source is not a JSON array"):
        w.load_events(b'[{"event_type": "anchor.remote"}]')


def test_a_duplicate_key_inside_the_array_form_is_still_refused():
    with pytest.raises(Exception, match="(?i)duplicate"):
        w.load_events(b'[{"a": 1, "a": 2}]')


def test_a_rotation_event_without_a_segment_closed_is_refused(archived_bundle):
    """C-426 (reviewer C-425 F-C425-1): a forged rotation event that omits the field is not read as matching."""
    _forge_first_live_event(archived_bundle, lambda rec: rec["payload"].pop("segment_closed"))
    v = verify_bundle(archived_bundle)
    assert not v.ok and v.first_failing_index == 8 and REASON in v.reason, v.reason
