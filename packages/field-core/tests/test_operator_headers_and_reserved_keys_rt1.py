"""Red team RT1 F-H1-4 and F-H1-5 (reviewer-8, LOW): header parsing is a full match, and the reserved-key strip sees
through case, whitespace, NFKC forms and zero-width characters, without touching keys that are not reserved look-alikes.

Every id, key and value here is made up."""
from __future__ import annotations

import pytest

from field_core import operator_auth as oa

KEY = "fok_" + "A1b2C3d4" * 4
RESERVED = sorted(oa.RESERVED_KEYS)


@pytest.fixture()
def armed(monkeypatch):
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")          # any armed mode: merge_payload rewrites (OFF is byte-identical)
    monkeypatch.delenv(oa.ENV_REGISTRY, raising=False)


def hdrs(op="svc", key=KEY):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


# ---- F-H1-4: parse_headers uses fullmatch, so a trailing newline is malformed (400), not a different id ---------------

@pytest.mark.parametrize("op", ["svc\n", "svc\r\n", "svc \n", "\nsvc"])
def test_a_trailing_or_leading_newline_in_the_id_is_a_400_for_a_dict_caller(op):
    with pytest.raises(oa.OperatorRefused) as e:
        oa.parse_headers(hdrs(op=op))
    assert e.value.status == 400


@pytest.mark.parametrize("key", [KEY + "\n", KEY + "\r\n", "\n" + KEY])
def test_a_trailing_or_leading_newline_in_the_key_is_a_400_for_a_dict_caller(key):
    with pytest.raises(oa.OperatorRefused) as e:
        oa.parse_headers(hdrs(key=key))
    assert e.value.status == 400
    assert KEY not in str(e.value.detail)


def test_clean_headers_and_an_absent_pair_still_parse():
    assert oa.parse_headers(hdrs()) == ("svc", KEY)
    assert oa.parse_headers({}) == (None, None)
    assert oa.parse_headers({oa.HEADER_OPERATOR: "Svc.One@x-1"}) == ("Svc.One@x-1", None)


# ---- F-H1-5: reserved keys are matched on a normalised form ----------------------------------------------------------

LOOKALIKES = [
    "{k}", "{K}", "{T}", "{k} ", " {k}", "{k}\n", "\t{k}", "{k}​", "​{k}", "﻿{k}", "{FW}",
]


def spell(template: str, key: str) -> str:
    fullwidth = "".join(chr(ord(c) + 0xFEE0) if c.isalpha() else c for c in key)   # NFKC folds these back to ASCII
    return template.format(k=key, K=key.upper(), T=key.title(), FW=fullwidth)


@pytest.mark.parametrize("template", LOOKALIKES)
@pytest.mark.parametrize("reserved", RESERVED)
def test_every_spelling_of_a_reserved_key_is_stripped_at_every_depth(armed, template, reserved):
    forged = spell(template, reserved)
    payload = {"to": "killed", forged: "mallory", "nested": {forged: "mallory", "list": [{forged: "mallory"}]}}
    out = oa.merge_payload(payload)
    assert forged not in out and forged not in out["nested"] and forged not in out["nested"]["list"][0]
    assert out["to"] == "killed"


def test_the_zero_width_split_of_a_real_reserved_name_is_stripped(armed):
    forged = "operator_id_authen​ticated"
    assert forged not in oa.merge_payload({forged: "mallory", "a": 1})


@pytest.mark.parametrize("key", ["operator", "operator_claimed_by", "operator-claimed", "my_operator_claimed", "name",
                                 "operator_claimed2", "Operatör_claimed", "é", "", " ", "k​ey"])
def test_a_key_that_is_not_a_reserved_look_alike_is_stored_exactly_as_sent(armed, key):
    out = oa.merge_payload({key: "value", "a": [{key: 1}]})
    assert out[key] == "value" and out["a"][0][key] == 1                       # same spelling, nothing renamed or dropped


def test_non_string_keys_are_never_reserved(armed):
    out = oa.merge_payload({1: "x", None: "y", ("t",): "z"})
    assert out[1] == "x" and out[None] == "y" and out[("t",)] == "z"


def test_flags_off_is_byte_identical_to_before(monkeypatch):
    monkeypatch.delenv(oa.ENV_REQUIRE, raising=False)
    monkeypatch.delenv(oa.ENV_REGISTRY, raising=False)
    payload = {"Operator_Claimed": "x", "operator_claimed": "y"}
    assert oa.merge_payload(payload) is payload


def test_the_deprecated_strip_and_admit_use_the_same_test(armed):
    forged = {"Operator_Key_Fp​": "mallory", "x": 1}
    assert oa.strip_reserved_unless_asserted(forged, {}) == {"x": 1}
