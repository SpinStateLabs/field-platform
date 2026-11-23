"""S11-3: load_manifest refuses a repeated mapping key, and validate_manifest_data accepts a naive `now`.

PyYAML's safe_load keeps the LAST of a repeated key without a word, so a manifest with two `enforcement:` (or two
`kill_switch:`, two `spend_cap:`) blocks validated on whichever came last and every reader saw only that. The refusal
is a ValueError (callers already treat it as invalid/unreadable) naming the dotted PATH, never a value. A naive `now`
compared with the aware expiry raised TypeError; it is read as UTC.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from field_core.templates_api import template_data
from field_core.validation import load_manifest, validate_manifest_data

SECRET = "SECRETISH-value"
REPO = Path(__file__).resolve().parents[3]


def write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "m.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def refusal(tmp_path, text) -> str:
    with pytest.raises(ValueError) as exc:
        load_manifest(write(tmp_path, text))
    return str(exc.value)


def test_a_duplicate_top_level_key_is_refused_by_path(tmp_path):
    msg = refusal(tmp_path, f"enforcement:\n  a: {SECRET}\nledger:\n  x: 1\nenforcement:\n  b: 2\n")
    assert msg == "manifest has a duplicate key at enforcement"


def test_a_nested_duplicate_key_names_the_dotted_path(tmp_path):
    msg = refusal(tmp_path, f"enforcement:\n  kill_switch:\n    on: {SECRET}\n  kill_switch:\n    on: false\n")
    assert msg == "manifest has a duplicate key at enforcement.kill_switch"


def test_a_duplicate_inside_a_list_item_names_the_index(tmp_path):
    msg = refusal(tmp_path, f"delegation:\n  grants:\n    - who: a\n    - who: b\n      cap: {SECRET}\n      cap: 2\n")
    assert msg == "manifest has a duplicate key at delegation.grants[1].cap"


def test_a_json_style_duplicate_is_refused(tmp_path):
    msg = refusal(tmp_path, '{"spend_cap": {"usd": 1}, "spend_cap": {"usd": 2}}')
    assert msg == "manifest has a duplicate key at spend_cap"


def test_the_refusal_never_carries_a_value(tmp_path):
    for text in (f"k: {SECRET}\nk: {SECRET}\n", f"a:\n  k: {SECRET}\n  k: 1\n"):
        assert SECRET not in refusal(tmp_path, text)


def test_distinct_keys_and_a_repeat_in_different_mappings_are_fine(tmp_path):
    data = load_manifest(write(tmp_path, "a:\n  k: 1\nb:\n  k: 2\nc: [{k: 1}, {k: 2}]\n"))
    assert data == {"a": {"k": 1}, "b": {"k": 2}, "c": [{"k": 1}, {"k": 2}]}


def test_a_merge_key_still_loads_and_an_override_is_not_a_duplicate(tmp_path):
    text = "base: &b\n  x: 1\n  y: 2\nderived:\n  <<: *b\n  y: 3\n"
    assert load_manifest(write(tmp_path, text))["derived"] == {"x": 1, "y": 3}


def test_an_anchor_alias_is_not_a_duplicate(tmp_path):
    assert load_manifest(write(tmp_path, "a: &x {k: 1}\nb: *x\n"))["b"] == {"k": 1}


def test_a_non_mapping_is_still_the_existing_error(tmp_path):
    with pytest.raises(ValueError, match="did not parse to a mapping"):
        load_manifest(write(tmp_path, "- a\n- b\n"))


@pytest.mark.parametrize("name", ["default", "financial-agent", "read-only-agent", "client-facing-agent"])
def test_every_template_still_loads(tmp_path, name):
    import yaml
    p = write(tmp_path, yaml.safe_dump(template_data(name), sort_keys=False))
    assert load_manifest(p) == template_data(name)


def test_every_shipped_yaml_still_loads():
    files = sorted((REPO / "manifests").glob("*.yaml")) + sorted(
        (REPO / "packages" / "field-core" / "src" / "field_core" / "templates").glob("*.yaml"))
    assert len(files) >= 13
    for f in files:
        assert isinstance(load_manifest(f), dict), f


GOOD_NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def test_a_naive_now_is_read_as_utc():
    data = template_data("default")
    aware = validate_manifest_data(data, now=GOOD_NOW)
    naive = validate_manifest_data(data, now=datetime(2026, 8, 8))
    assert naive == aware   # the whole result, so no field can differ


def test_a_naive_now_past_the_expiry_still_warns():
    data = template_data("default")
    data["delegation"]["expiry"] = "2026-01-01"
    naive = validate_manifest_data(data, now=datetime(2026, 8, 8))
    assert naive.warnings == validate_manifest_data(data, now=GOOD_NOW).warnings and naive.warnings


def test_a_naive_now_is_utc_whatever_the_machine_timezone(monkeypatch):
    """An expiry at exactly `now` is past (UTC). Reading the naive clock in a UTC+9 machine zone would put `now`
    nine hours earlier and the same expiry would read as near-term instead."""
    import time
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    time.tzset()
    try:
        data = template_data("default")
        data["delegation"]["expiry"] = "2026-08-08T00:00:00Z"
        naive = validate_manifest_data(data, now=datetime(2026, 8, 8))
        assert naive == validate_manifest_data(data, now=GOOD_NOW)
        assert any("past" in w or "expired" in w for w in naive.warnings), naive.warnings
    finally:
        monkeypatch.undo()
        time.tzset()


def test_two_merge_keys_in_one_mapping_are_not_a_duplicate_key(tmp_path):
    text = "a: &a {x: 1}\nb: &b {y: 2}\nc:\n  <<: *a\n  <<: *b\n"
    assert load_manifest(write(tmp_path, text))["c"]["y"] == 2


def test_the_int_key_one_and_the_string_key_one_are_different_keys(tmp_path):
    assert load_manifest(write(tmp_path, "1: a\n'1': b\n")) == {1: "a", "1": "b"}


def test_a_self_referential_anchor_does_not_recurse_forever(tmp_path):
    assert load_manifest(write(tmp_path, "a: &x [*x]\n"))["a"] is not None
