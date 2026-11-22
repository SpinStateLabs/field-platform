"""S5-7: load_rate_limits never raises on a 200 whose body is not JSON or is the wrong shape; that is outcome 'failed' with the
status code 200 and a detail that names the problem, never the body. Non-200 behaviour and good answers are unchanged."""
from __future__ import annotations

import json

import pytest

from spend_governor.core import RateLimitSet
from spend_governor.provisioning import load_rate_limits

AGENT = "agent-1"
MARK = "SECRET-BODY-MARKER-0f3a"
ROW = {"action": "tool_call", "max": 5, "period": "hourly"}
DECLARED = RateLimitSet(agent_id=AGENT, rate_limits=[ROW])
EMPTY = RateLimitSet(agent_id=AGENT, rate_limits=[])


class Resp:
    def __init__(self, status=200, body=None, text=None, raw=None):
        self.status_code = status
        self._body, self._raw = body, raw
        self.text = text if text is not None else (raw if raw is not None else json.dumps(body))

    def json(self):
        return json.loads(self._raw) if self._raw is not None else self._body


BAD = [
    ("not-json", Resp(raw="<html>" + MARK + "</html>")),
    ("empty-text", Resp(raw="")),
    ("list", Resp(body=[])),
    ("null", Resp(body=None, raw="null")),
    ("number", Resp(body=42)),
    ("rows-not-a-list", Resp(body={"rate_limits": "x"})),
    ("rows-null", Resp(body={"rate_limits": None})),
    ("rows-a-number", Resp(body={"rate_limits": 5})),
    ("rows-a-mapping", Resp(body={"rate_limits": {"a": {}}})),
    ("rows-of-ints", Resp(body={"rate_limits": [1, 2]})),
    ("a-non-dict-row", Resp(body={"rate_limits": [{"status": "enforced"}, "x"]})),
]


def _put_ok(resp):
    return lambda path, json=None: resp


def _never(path, json=None):  # pragma: no cover - the test fails if it is reached
    raise AssertionError("PUT must not be reached")


@pytest.mark.parametrize("name,resp", BAD, ids=[n for n, _ in BAD])
def test_a_bad_200_on_the_put_is_failed_not_an_exception(name, resp):
    out = load_rate_limits(lambda p: Resp(404, {}), _put_ok(resp), DECLARED)
    assert out.outcome == "failed" and out.status_code == 200
    assert out.enforced == [] and out.declared_unenforced == []
    assert "NOT loaded (200)" in out.detail and "unreadable" in out.detail
    assert MARK not in out.detail


@pytest.mark.parametrize("name,resp", BAD, ids=[n for n, _ in BAD])
def test_a_bad_200_on_the_get_is_failed_and_nothing_is_put(name, resp):
    out = load_rate_limits(lambda p: resp, _never, EMPTY)
    assert out.outcome == "failed" and out.status_code == 200
    assert "NOT loaded (200)" in out.detail and "unreadable" in out.detail and MARK not in out.detail


def test_a_non_200_get_is_still_unchanged_whatever_the_body():
    out = load_rate_limits(lambda p: Resp(404, raw="<html>" + MARK), _never, EMPTY)
    assert (out.outcome, out.status_code) == ("unchanged", 404)


def test_a_non_200_put_keeps_its_existing_detail():
    out = load_rate_limits(lambda p: Resp(404), _put_ok(Resp(422, text="refused: bad period")), DECLARED)
    assert (out.outcome, out.status_code) == ("failed", 422)
    assert out.detail == "rate limits NOT loaded (422): refused: bad period"


def test_good_answers_are_unchanged():
    rows = [{"status": "enforced", "action": "tool_call"}, {"status": "declared_unenforced", "action": "x"}]
    out = load_rate_limits(lambda p: Resp(404), _put_ok(Resp(200, {"rate_limits": rows})), DECLARED)
    assert out.outcome == "loaded" and len(out.enforced) == 1 and len(out.declared_unenforced) == 1
    assert out.detail == "1 enforced, 1 declared-unenforced"
    # nothing declared and nothing held: unchanged, nothing put
    held_none = load_rate_limits(lambda p: Resp(200, {"rate_limits": []}), _never, EMPTY)
    assert held_none.outcome == "unchanged" and held_none.status_code == 200
    # nothing declared but a stale set held: the empty set is put
    cleared = load_rate_limits(lambda p: Resp(200, {"rate_limits": [ROW]}), _put_ok(Resp(200, {"rate_limits": []})), EMPTY)
    assert cleared.outcome == "loaded"


def test_a_put_answer_with_no_rate_limits_key_is_an_empty_set_as_before():
    out = load_rate_limits(lambda p: Resp(404), _put_ok(Resp(200, {})), DECLARED)
    assert out.outcome == "loaded" and out.enforced == []
