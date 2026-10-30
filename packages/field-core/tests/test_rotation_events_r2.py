"""Key rotation slice R2: the ``keyrotation.*`` ledger event schema is FROZEN (design
v0.2 section 5.1, O15). Names and fields exactly as the design lists them; payloads
hold ids, 16-hex fingerprints, generations, sha prefixes, phases and reason classes,
never a key, a full hash or free text. Values here are throwaway constants."""

from __future__ import annotations

import copy

import pytest

from field_core import rotation_events as re_

FP_A = "0123456789abcdef"
FP_B = "fedcba9876543210"
SHA16 = "a1b2c3d4e5f60718"

#: design 5.1, every event the table names (the frozen contract)
DESIGN_EVENTS = {
    "keyrotation.started", "keyrotation.published", "keyrotation.cutover",
    "keyrotation.retired", "keyrotation.completed", "keyrotation.failed",
    "keyrotation.aborted", "keyrotation.skipped", "keyrotation.reconciled",
    "keyrotation.extended", "keyrotation.recovery_started", "keyrotation.recovery_ended",
    "keyrotation.requested", "keyrotation.enrolled", "keyrotation.cancelled",
    "keyrotation.overdue", "keyrotation.breakglass_used", "keyrotation.breakglass_attempt",
    "keyrotation.expired_key_used", "keyrotation.seed_stale",
}

RUN = {"estate": "gb10", "run_id": "r-20261120T031209Z-1"}
VALID = {
    "keyrotation.started": {"operator_id": "svc-killswitch", **RUN, "reason": "schedule",
                            "old_fp": FP_A},
    "keyrotation.published": {"operator_id": "svc-killswitch", **RUN, "new_fp": FP_B,
                              "generation": 42, "registry_sha16": SHA16},
    "keyrotation.cutover": {"operator_id": "svc-killswitch", **RUN, "new_fp": FP_B},
    "keyrotation.retired": {"operator_id": "svc-killswitch", **RUN, "old_fp": FP_A,
                            "generation": 43, "registry_sha16": SHA16},
    "keyrotation.completed": {"operator_id": "svc-killswitch", **RUN, "old_fp": FP_A,
                              "new_fp": FP_B, "generation": 43},
    "keyrotation.failed": {"operator_id": "svc-killswitch", **RUN, "phase": "publish",
                           "reason_class": "publish_not_seen", "reverted": True,
                           "generation": 41, "registry_sha16": SHA16},
    "keyrotation.aborted": {"operator_id": "svc-killswitch", **RUN, "phase": "soak",
                            "reason_class": "refusal_seen", "reverted": True,
                            "generation": 43, "registry_sha16": SHA16},
    "keyrotation.skipped": {"operator_id": None, **RUN, "skip_reason": "lock"},
    "keyrotation.reconciled": {**RUN, "operator_ids": ["svc-killswitch", "svc-registry"],
                               "generation": 50, "registry_sha16": SHA16},
    "keyrotation.extended": {"operator_id": "don", **RUN, "until": "2027-03-01T00:00:00Z",
                             "extend_reason": "human_migration", "generation": 45,
                             "registry_sha16": SHA16},
    "keyrotation.recovery_started": {**RUN, "operator_ids": ["svc-rotator-gb10"]},
    "keyrotation.recovery_ended": {**RUN},
    "keyrotation.requested": {"operator_id": "don", "estate": "gb10", "request_id": "q-1",
                              "request_type": "passkey_enrol",
                              "not_before": "2026-11-21T03:00:00Z"},
    "keyrotation.enrolled": {"operator_id": "don", "estate": "gb10", "request_id": "q-1",
                             "request_type": "passkey_enrol", "generation": 44,
                             "registry_sha16": SHA16},
    "keyrotation.cancelled": {"operator_id": "don", "estate": "gb10", "request_id": "q-1",
                              "request_type": "breakglass_reseal"},
    "keyrotation.overdue": {"operator_id": "svc-registry", "estate": "fly",
                            "severity": "critical", "overdue_reason": "expiry_near"},
    "keyrotation.breakglass_used": {"estate": "gb10", "service": "kill-switch", "count": 1,
                                    "previous_count": 0},
    "keyrotation.breakglass_attempt": {"estate": "fly", "service": "sealed-ledger", "count": 3,
                                       "previous_count": 2},
    "keyrotation.expired_key_used": {"operator_id": "svc-killswitch", "estate": "gb10",
                                     "service": "kill-switch", "fp": FP_A, "action": "kill"},
    "keyrotation.seed_stale": {"operator_id": "svc-delegation", "estate": "fly"},
}


def test_the_frozen_names_are_exactly_the_design_table():
    assert set(re_.EVENTS) == DESIGN_EVENTS
    assert all(t.startswith(re_.PREFIX) for t in re_.EVENTS)
    assert set(VALID) == DESIGN_EVENTS


def test_the_design_fields_are_frozen():
    # 5.1 rows quoted field by field
    assert re_.EVENTS["keyrotation.started"] == {"operator_id", "estate", "reason", "old_fp", "run_id"}
    assert {"phase", "reason_class", "reverted"} <= re_.EVENTS["keyrotation.failed"]
    assert re_.EVENTS["keyrotation.failed"] == re_.EVENTS["keyrotation.aborted"]
    assert {"old_fp", "new_fp", "generation"} <= re_.EVENTS["keyrotation.completed"]  # 4.3 step 11
    assert re_.START_REASONS == {"schedule", "incident", "request", "recovery"}
    assert re_.SKIP_REASONS == {"freeze", "lock", "precheck", "foreign_edit", "clock"}
    assert "policy" in re_.REASON_CLASSES
    assert set(re_.FIELD_TYPES) == set().union(*re_.EVENTS.values())


@pytest.mark.parametrize("event_type", sorted(DESIGN_EVENTS))
def test_every_frozen_event_validates(event_type):
    re_.validate(event_type, copy.deepcopy(VALID[event_type]))


@pytest.mark.parametrize("event_type", sorted(DESIGN_EVENTS))
def test_a_missing_or_extra_field_is_refused(event_type):
    p = copy.deepcopy(VALID[event_type])
    p["note"] = "free text"
    with pytest.raises(re_.SchemaError):
        re_.validate(event_type, p)
    p = copy.deepcopy(VALID[event_type])
    p.pop(sorted(p)[0])
    with pytest.raises(re_.SchemaError):
        re_.validate(event_type, p)


@pytest.mark.parametrize("event_type,field,value", [
    ("keyrotation.started", "old_fp", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"),
    ("keyrotation.started", "old_fp", "01234567"),                      # 8 hex is grindable (S11)
    ("keyrotation.started", "old_fp", "0123456789ABCDEF"),
    ("keyrotation.started", "reason", "because"),
    ("keyrotation.started", "operator_id", "fok_abcdefabcdefabcdefabcdefabcdefabcdefabc"),
    ("keyrotation.started", "estate", "GB10"),
    ("keyrotation.published", "generation", 0),
    ("keyrotation.published", "generation", True),
    ("keyrotation.published", "registry_sha16", "a1b2c3d4"),
    ("keyrotation.failed", "phase", "somewhere"),
    ("keyrotation.failed", "reason_class", "it broke: see log"),
    ("keyrotation.failed", "reverted", "yes"),
    ("keyrotation.skipped", "skip_reason", "busy"),
    ("keyrotation.reconciled", "operator_ids", ["a", "a"]),
    ("keyrotation.reconciled", "operator_ids", "svc-killswitch"),
    ("keyrotation.extended", "until", "2027-03-01"),
    ("keyrotation.extended", "extend_reason", "Don said so"),
    ("keyrotation.overdue", "severity", "panic"),
    ("keyrotation.breakglass_used", "service", "gateway"),
    ("keyrotation.breakglass_used", "count", -1),
    ("keyrotation.expired_key_used", "action", "revive"),            # K4: kills only
    ("keyrotation.cutover", "run_id", "r" * 65),
])
def test_a_wrong_value_is_refused_and_never_echoed(event_type, field, value):
    p = copy.deepcopy(VALID[event_type])
    p[field] = value
    with pytest.raises(re_.SchemaError) as exc:
        re_.validate(event_type, p)
    if isinstance(value, str) and len(value) > 3:
        assert value not in str(exc.value)


def test_null_only_where_the_schema_allows_it():
    re_.validate("keyrotation.skipped", dict(VALID["keyrotation.skipped"]))
    p = dict(VALID["keyrotation.started"], operator_id=None)
    with pytest.raises(re_.SchemaError):
        re_.validate("keyrotation.started", p)


def test_unknown_types_and_non_objects_are_refused():
    with pytest.raises(re_.SchemaError):
        re_.validate("keyrotation.rotated", {})
    with pytest.raises(re_.SchemaError):
        re_.validate("operator.registry_changed", {})
    with pytest.raises(re_.SchemaError):
        re_.validate("keyrotation.recovery_ended", ["gb10"])


def test_fingerprint_is_the_first_16_hex_of_a_sha256():
    h = "ab" * 32
    assert re_.fingerprint(h) == "ab" * 8
    for bad in ("AB" * 32, "ab" * 8, "fok_x"):
        with pytest.raises(re_.SchemaError):
            re_.fingerprint(bad)


# --- R2 review M1: every file-writing event names the generation and file it left -------------

#: design 5.2: "every observed generation step matched by a rotator event". These events
#: write the operators file, so each carries the generation and sha16 of what it wrote.
FILE_WRITING = ("keyrotation.published", "keyrotation.retired", "keyrotation.reconciled",
                "keyrotation.enrolled", "keyrotation.extended", "keyrotation.failed",
                "keyrotation.aborted")


@pytest.mark.parametrize("event_type", FILE_WRITING)
def test_every_file_writing_event_carries_generation_and_registry_sha16(event_type):
    assert {"generation", "registry_sha16"} <= re_.EVENTS[event_type]


@pytest.mark.parametrize("event_type", ["keyrotation.failed", "keyrotation.aborted"])
def test_a_failure_that_wrote_nothing_reports_null_generation_and_sha(event_type):
    p = dict(VALID[event_type], reverted=False, generation=None, registry_sha16=None)
    re_.validate(event_type, p)


@pytest.mark.parametrize("event_type", ["keyrotation.failed", "keyrotation.aborted"])
@pytest.mark.parametrize("reverted,generation,sha", [
    (True, None, None),      # a revert wrote the file: it must say which generation / file
    (True, 41, None),
    (True, None, SHA16),
    (False, 41, SHA16),      # nothing written: no generation step to claim
    (False, 41, None),
    (False, None, SHA16),
])
def test_generation_and_sha_are_set_exactly_when_the_file_was_reverted(event_type, reverted,
                                                                       generation, sha):
    p = dict(VALID[event_type], reverted=reverted, generation=generation, registry_sha16=sha)
    with pytest.raises(re_.SchemaError) as exc:
        re_.validate(event_type, p)
    assert SHA16 not in str(exc.value)


@pytest.mark.parametrize("event_type", ["keyrotation.failed", "keyrotation.aborted"])
@pytest.mark.parametrize("field,value", [("generation", 0), ("generation", "41"),
                                         ("registry_sha16", "a1b2c3d4"),
                                         ("registry_sha16", "A1B2C3D4E5F60718")])
def test_a_reverted_failure_still_types_its_generation_and_sha(event_type, field, value):
    p = dict(VALID[event_type], **{field: value})
    with pytest.raises(re_.SchemaError):
        re_.validate(event_type, p)


@pytest.mark.parametrize("field", ["generation", "registry_sha16"])
def test_an_extend_always_names_the_file_it_wrote(field):
    # --extend always rewrites key_not_after (design 4.4 O20): never null
    p = dict(VALID["keyrotation.extended"], **{field: None})
    with pytest.raises(re_.SchemaError):
        re_.validate("keyrotation.extended", p)


@pytest.mark.parametrize("event_type", sorted(set(re_.EVENTS) - set(re_.NULLABLE)))
def test_no_other_event_admits_a_null(event_type):
    for name in sorted(re_.EVENTS[event_type]):
        p = dict(VALID[event_type], **{name: None})
        with pytest.raises(re_.SchemaError):
            re_.validate(event_type, p)


# --- R2 review L1: the one field name that differs from the design 5.1 text --------------------


def test_a_skip_carries_skip_reason_not_the_design_texts_reason():
    assert "skip_reason" in re_.EVENTS["keyrotation.skipped"]
    assert "reason" not in re_.EVENTS["keyrotation.skipped"]
    assert "skip_reason" in (re_.__doc__ or "") and "reason: ..." in (re_.__doc__ or "")
    p = dict(VALID["keyrotation.skipped"])
    p["reason"] = p.pop("skip_reason")          # a writer following the 5.1 text
    with pytest.raises(re_.SchemaError):
        re_.validate("keyrotation.skipped", p)


# --- R2 review L2: the 64-hex / key-prefix scan is what refuses these ---------------------------

HEX64 = "0123456789abcdef" * 4


@pytest.mark.parametrize("event_type,field,value", [
    ("keyrotation.cutover", "run_id", HEX64),                       # admitted by the run_id type
    ("keyrotation.cutover", "run_id", HEX64.upper()),
    ("keyrotation.cutover", "run_id", "fok_" + "a" * 20),           # admitted by the run_id type
    ("keyrotation.cutover", "run_id", "r:fok_abc"),
    ("keyrotation.requested", "request_id", HEX64),
    ("keyrotation.requested", "request_id", "fok_q1"),
    ("keyrotation.started", "operator_id", "x-fok_abc"),            # admitted by printable_id
    ("keyrotation.reconciled", "operator_ids", ["svc-killswitch", "x.fok_abc"]),
])
def test_the_scan_refuses_a_hash_or_key_prefix_that_a_field_type_admits(event_type, field, value):
    from field_core import rotation_events as mod

    assert mod.FIELD_TYPES[field](value)        # the type alone would let it through
    p = copy.deepcopy(VALID[event_type])
    p[field] = value
    with pytest.raises(re_.SchemaError) as exc:
        re_.validate(event_type, p)
    for v in (value if isinstance(value, list) else [value]):
        assert v not in str(exc.value)


# --- C-51 follow-up (reviewer C-690 F-C690-2 / F-C690-5, C-702): the two lower and upper bounds of the schema ---


def test_generation_one_is_accepted_and_zero_is_refused():
    """`_gen` is `>= 1`: `> 1` would refuse the very first generation (zero is pinned above)."""
    ev = copy.deepcopy(VALID["keyrotation.published"])
    ev["generation"] = 1
    re_.validate("keyrotation.published", ev)
    ev["generation"] = 0
    with pytest.raises(re_.SchemaError):
        re_.validate("keyrotation.published", ev)


def test_operator_ids_at_the_cap_are_accepted_and_one_more_is_refused():
    """`_ids` allows MAX_OPERATOR_IDS entries; the bound is inclusive."""
    ev = copy.deepcopy(VALID["keyrotation.reconciled"])
    ev["operator_ids"] = [f"svc-{n}" for n in range(re_.MAX_OPERATOR_IDS)]
    re_.validate("keyrotation.reconciled", ev)
    ev["operator_ids"] = [f"svc-{n}" for n in range(re_.MAX_OPERATOR_IDS + 1)]
    with pytest.raises(re_.SchemaError):
        re_.validate("keyrotation.reconciled", ev)
