"""B-RT2 LOW findings F3, F5, F6 (reviewer-10 on main 250154d3), one test each. F4 (the controller's per-step alert) is in
tools/tests/test_stage_controller_alert_async_rt2.py. Every value here is made up."""

import dataclasses
import json

import pytest

from field_core import alert_senders, alerts

TOPIC = "faketopic_unit_test_only_rt2xyz"
TOKEN = "tk_fakeTokenForUnitTestsOnly"


# ---- F3: the senders docstring is not stale about the stage controller --------------------------------------------------

def test_the_senders_docstring_no_longer_says_the_stage_controller_is_missing():
    doc = alert_senders.__doc__
    assert "which is not in this repository" not in doc
    assert "wait for the Phase G stage controller" not in doc
    assert "tools/stage_controller.py" in doc and "stage_transition" in doc and "stage_aborted" in doc


# ---- F5: the field regexes use fullmatch, so a trailing newline is refused --------------------------------------------

@pytest.mark.parametrize("field,value", [("estate", "gb10" + chr(10)), ("subject", "stage-2" + chr(10)),
                                          ("detail", "step done" + chr(10))])
def test_a_trailing_newline_in_a_field_is_withheld(field, value):
    withheld = alerts.render("test", **{"estate": "gb10", field: value})[3]
    assert field in withheld


@pytest.mark.parametrize("field,value", [("estate", "gb10"), ("subject", "stage-2"), ("detail", "step done")])
def test_the_same_field_without_the_newline_is_kept(field, value):
    assert alerts.render("test", **{"estate": "gb10", field: value})[3] == ()


def test_the_field_regexes_are_matched_whole():
    src = open(alerts.__file__, encoding="utf-8").read()
    assert "_FIELD_RE[name].fullmatch(value)" in src and "_FIELD_RE[name].match(value)" not in src


# ---- F6: dataclasses.asdict / astuple of a Destination does not hand out the URL, topic or token -------------------------

def _destination():
    env = {alerts.ENV_TOPIC: TOPIC, alerts.ENV_TOKEN: TOKEN, alerts.ENV_BASE_URL: "https://ntfy.example.test"}
    return alerts.resolve_destination(env)


def test_asdict_and_astuple_of_a_destination_carry_neither_url_nor_topic_nor_token():
    dest = _destination()
    for dumped in (json.dumps(dataclasses.asdict(dest)), json.dumps(dataclasses.astuple(dest))):
        assert TOPIC not in dumped and TOKEN not in dumped and "ntfy.example.test" not in dumped, dumped


def test_a_destination_still_works_as_strings_for_the_sender():
    dest = _destination()
    assert dest.url.startswith("https://ntfy.example.test/") and dest.url.endswith(TOPIC)
    assert dest.topic == TOPIC and dest.token == TOKEN
    assert repr(dest) == "Destination(configured, token=yes)" and str(dest) == repr(dest)
