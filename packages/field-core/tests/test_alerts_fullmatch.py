"""S5-5: the alert patterns are anchored with \\Z, not $ ($ also matches before a final newline), so 'prod\\n' is not an estate,
and a NUL in `alert-topic-init --out` is a named exit 2. Also pins content_problem, which no test named."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from field_core import alerts
from field_core.cli import app

LONG_TOPIC = "field-" + "a" * 20


# ---- the patterns --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("pattern,good", [
    (alerts.TOPIC_RE, LONG_TOPIC),
    (alerts._TOKEN_RE, "tk" + "x" * 10),
    (alerts._FIELD_RE["estate"], "prod"),
    (alerts._FIELD_RE["subject"], "agent-1"),
    (alerts._FIELD_RE["detail"], "a plain detail"),
], ids=["topic", "token", "estate", "subject", "detail"])
def test_a_pattern_refuses_its_good_value_plus_a_trailing_newline_by_match_and_fullmatch(pattern, good):
    assert pattern.match(good) and pattern.fullmatch(good)
    for bad in (good + "\n", good + "\r\n", good + "\n\n"):
        assert pattern.match(bad) is None, repr(bad)
        assert pattern.fullmatch(bad) is None, repr(bad)


# ---- render: the fields that reach the alert body ----------------------------------------------------------------------

@pytest.mark.parametrize("field", ["estate", "subject", "detail"])
def test_a_trailing_newline_in_a_field_is_withheld(field):
    kw = {"estate": "prod", "subject": "agent-1", "detail": "all good"}
    kw[field] += "\n"
    title, body, tags, withheld = alerts.render("test", **kw)
    assert field in withheld
    assert f"{field}: {alerts.WITHHELD}" in body
    others = {"estate": "prod", "subject": "agent-1", "detail": "all good"}
    for name, value in others.items():
        if name != field:
            assert f"{name}: {value}" in body          # the other fields are untouched


def test_good_fields_pass_unchanged():
    title, body, tags, withheld = alerts.render("test", estate="prod", subject="agent-1", detail="all good")
    assert withheld == ()
    assert "estate: prod" in body and "subject: agent-1" in body and "detail: all good" in body


# ---- the topic file command ------------------------------------------------------------------------------------------

def test_a_nul_in_the_out_path_is_exit_2_with_one_line_and_no_traceback():
    res = CliRunner().invoke(app, ["alert-topic-init", "--out", "a\x00b"])
    assert res.exit_code == 2, res.output
    assert "Traceback" not in res.output
    lines = [ln for ln in res.output.splitlines() if ln.strip()]
    assert len(lines) == 1 and "cannot write" in lines[0] and "nothing written" in lines[0]
    assert "ValueError" in lines[0]


def test_the_existing_refusals_are_unchanged(tmp_path):
    out = tmp_path / "topic"
    assert CliRunner().invoke(app, ["alert-topic-init", "--out", str(out)]).exit_code == 0
    again = CliRunner().invoke(app, ["alert-topic-init", "--out", str(out)])
    assert again.exit_code == 1 and "exists" in again.output
    blocked = CliRunner().invoke(app, ["alert-topic-init", "--out", str(out / "sub" / "topic")])
    assert blocked.exit_code == 2


# ---- content_problem: each verdict ------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,secrets_,expected", [
    ("fok_abc", (), "secret_prefix"),
    ("see TK_abc", (), "secret_prefix"),
    ("deadbeefdeadbeef", (), "hex_run"),
    ("G" * 32, (), "opaque_run"),
    ("-----BEGIN PRIVATE KEY", (), "pem"),
    ("my TopicX here", ("topicx",), "configured_secret"),
    ("an ordinary sentence", (), None),
    ("an ordinary sentence", ("",), None),                     # a blank configured secret never matches
    ("fok_ and deadbeefdeadbeef", (), "secret_prefix"),        # the first rule wins
    ("deadbeefdeadbeef and -----BEGIN", (), "hex_run"),
])
def test_content_problem_names_each_reason(text, secrets_, expected):
    assert alerts.content_problem(text, secrets_=secrets_) == expected
