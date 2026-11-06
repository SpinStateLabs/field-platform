"""S7-6: the pure operator_auth helpers no test named, each pinned at its boundaries."""

import pytest

from field_core import operator_auth as oa
from field_core.operator_auth import (KEY_PREFIX, MAX_EVENT_PREFIX_LEN, MAX_RECORDED_PATH_LEN, NOT_SHOWN,
                                      RegistryUnavailable, decode_registry_document, note_breakglass,
                                      recorded_path, shown_claim, valid_event_prefix)


# -- recorded_path -----------------------------------------------------------------------------------------

def test_recorded_path_none_is_empty_and_a_non_string_is_not_shown():
    assert recorded_path(None) == ""
    for bad in (5, b"/x", ["/x"], object()):
        assert recorded_path(bad) == NOT_SHOWN


def test_recorded_path_keeps_a_clean_path_and_the_empty_string():
    assert recorded_path("/operator/verify-hash") == "/operator/verify-hash"
    assert recorded_path("") == ""
    assert recorded_path("/a/b.c_d~e:f@g+h%20=i,j-k") == "/a/b.c_d~e:f@g+h%20=i,j-k"


def test_recorded_path_clips_at_the_cap_to_197_chars_plus_dots():
    exact = "/" + "a" * (MAX_RECORDED_PATH_LEN - 1)
    assert recorded_path(exact) == exact                              # exactly the cap is kept whole
    over = "/" + "a" * MAX_RECORDED_PATH_LEN
    clipped = recorded_path(over)
    assert clipped == over[:197] + "..." and len(clipped) == MAX_RECORDED_PATH_LEN


@pytest.mark.parametrize("bad", ["/a b", "/a\n", "/a?x=1", "/a#f", "/é", "/a;b", "/a\b", "/a\x00"])
def test_recorded_path_with_a_character_outside_the_url_path_set_is_not_shown(bad):
    assert recorded_path(bad) == NOT_SHOWN


def test_recorded_path_with_the_key_prefix_anywhere_is_not_shown():
    assert recorded_path(f"/x/{KEY_PREFIX}abc") == NOT_SHOWN
    assert recorded_path(f"{KEY_PREFIX}") == NOT_SHOWN
    assert recorded_path("/x/" + "a" * 190 + KEY_PREFIX) == NOT_SHOWN


def test_recorded_path_key_prefix_beyond_the_clip_is_clipped_away_not_leaked():
    # the clip happens first: a prefix past character 197 is cut off and the rest is clean
    assert recorded_path("/" + "a" * 250 + KEY_PREFIX) == "/" + "a" * 196 + "..."


# -- shown_claim -------------------------------------------------------------------------------------------

def test_shown_claim_none_stays_none_and_a_printable_id_is_kept():
    assert shown_claim(None) is None
    assert shown_claim("don") == "don"
    assert shown_claim("svc-killswitch") == "svc-killswitch"


@pytest.mark.parametrize("bad", [KEY_PREFIX + "abc", 5, b"don", ["don"], "", "a b", "x" * 40, "A1_" * 20])
def test_shown_claim_hides_a_key_a_non_string_and_a_long_unbroken_token(bad):
    assert shown_claim(bad) == NOT_SHOWN


def test_shown_claim_keeps_a_39_character_id_and_hides_a_40_character_one():
    assert shown_claim("a" * 39) == "a" * 39
    assert shown_claim("a" * 40) == NOT_SHOWN


# -- valid_event_prefix ------------------------------------------------------------------------------------

@pytest.mark.parametrize("ok", ["a.", "a.b.", "kill.", "a-b_c.d1."])
def test_valid_event_prefix_accepts_dotted_lowercase_segments_ending_in_a_dot(ok):
    assert valid_event_prefix(ok) is True


@pytest.mark.parametrize("bad", ["a", "A.", "a.B.", ".", "a..", ".a.", "a b.", "a.\n", "operator.", "operator.x.",
                                 "a" * 64 + ".", "", None, 5, b"a."])
def test_valid_event_prefix_refuses_the_rest(bad):
    assert valid_event_prefix(bad) is False


def test_valid_event_prefix_length_boundary_is_the_cap():
    assert valid_event_prefix("a" * (MAX_EVENT_PREFIX_LEN - 1) + ".") is True       # 64 chars
    assert valid_event_prefix("a" * MAX_EVENT_PREFIX_LEN + ".") is False            # 65 chars


def test_valid_event_prefix_operator_namespace_only_blocks_the_exact_prefix():
    assert valid_event_prefix("operators.") is True                                 # not 'operator.'
    assert valid_event_prefix("x.operator.") is True


# -- note_breakglass ---------------------------------------------------------------------------------------

def test_note_breakglass_used_moves_only_the_auth_counter(monkeypatch):
    monkeypatch.setattr(oa, "breakglass_auth_count", 0)
    monkeypatch.setattr(oa, "breakglass_attempt_count", 0)
    note_breakglass(used=True)
    note_breakglass(used=True)
    assert (oa.breakglass_auth_count, oa.breakglass_attempt_count) == (2, 0)


def test_note_breakglass_not_used_moves_only_the_attempt_counter(monkeypatch):
    monkeypatch.setattr(oa, "breakglass_auth_count", 0)
    monkeypatch.setattr(oa, "breakglass_attempt_count", 0)
    note_breakglass(used=False)
    assert (oa.breakglass_auth_count, oa.breakglass_attempt_count) == (0, 1)


# -- decode_registry_document ------------------------------------------------------------------------------

def test_decode_tolerates_a_bom_and_returns_the_document():
    assert decode_registry_document(b"\xef\xbb\xbf" + b'{"operators": []}') == {"operators": []}
    assert decode_registry_document(b'{"a": 1}') == {"a": 1}


def test_decode_refuses_a_duplicate_key_and_names_it():
    with pytest.raises(RegistryUnavailable, match="duplicate JSON key") as exc:
        decode_registry_document(b'{"operator_id": "don", "operator_id": "mallory"}')
    assert "operator_id" in str(exc.value) and "mallory" not in str(exc.value)


@pytest.mark.parametrize("data, kind", [
    (b"\xff\xfe\x00bad", "UnicodeDecodeError"),
    (b"[" * 100_000, "RecursionError"),
    (b"not json at all", "JSONDecodeError"),
    (b"", "JSONDecodeError"),
], ids=["invalid-utf8", "deep-nesting", "not-json", "empty"])
def test_decode_failures_are_registry_unavailable_with_only_the_type_name(data, kind):
    with pytest.raises(RegistryUnavailable) as exc:
        decode_registry_document(data)
    assert str(exc.value) == f"operator registry unreadable: {kind}"
