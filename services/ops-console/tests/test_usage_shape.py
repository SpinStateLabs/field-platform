"""S5-20: a 200 governor /usage answer that is not an object is no usage row and no 500 on /api/overview or /api/stream
(C-936 F-C936-6d fixed the agents list; this is the sibling read). The section says how many were unreadable."""

from __future__ import annotations

import pytest

from ops_console.api import MAX_USAGE_ROWS
from test_ops_console_c184 import Stub, console, sc

AGENTS = [{"agent_id": "a"}, {"agent_id": "b"}]
BODIES = [[1, 2], "x", 7, None, True, 3.5, [], [{"total_input_tokens": 9}]]


class Governor(Stub):
    """Answers /usage/<id> from ``usage`` (id -> body) and everything else with an empty object."""

    def __init__(self, usage):
        super().__init__(body={})
        self.usage = usage

    def _answer(self, path, kw):
        if path.startswith("/usage/"):
            self.calls.append((path, kw))
            body = self.usage.get(path.split("/")[-1], {})

            class R:
                status_code = 200

                def json(_):  # noqa: N805
                    return body
            return R()
        return super()._answer(path, kw)


def overview(usage, agents=None):
    gov = Governor(usage)
    c = console(registry=sc(Stub(body=AGENTS if agents is None else agents)), governor=sc(gov))
    return c, c.get("/api/overview")


@pytest.mark.parametrize("body", BODIES, ids=repr)
def test_a_non_object_usage_answer_is_not_a_500_and_the_rest_is_intact(body):
    c, r = overview({"a": body, "b": {"total_input_tokens": 5}})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["token_usage"]["available"] is True
    assert [row["total_input_tokens"] for row in j["token_usage"]["data"]] == [5]      # the good agent's row survives
    assert "1 agent usage answer(s) were not readable" in j["token_usage"]["error"]
    for name in ("agents", "tokens", "escalations", "ledger_verify", "recent_events"):
        assert name in j and j[name]["available"] is True, name


def test_every_answer_unreadable_is_an_empty_section_that_says_so():
    c, r = overview({"a": 7, "b": "x"})
    j = r.json()["token_usage"]
    assert r.status_code == 200 and j["data"] == [] and "2 agent usage answer(s)" in j["error"]


def test_an_empty_object_is_idle_not_unreadable():
    c, r = overview({"a": {}, "b": {"total_output_tokens": 0}})
    j = r.json()["token_usage"]
    assert j["data"] == [] and j["error"] is None


def test_readable_rows_are_unchanged():
    c, r = overview({"a": {"total_input_tokens": 3, "agent_id": "a"}, "b": {"open_rogue_flags": 2, "agent_id": "b"}})
    j = r.json()["token_usage"]
    assert [row["agent_id"] for row in j["data"]] == ["a", "b"] and j["error"] is None


def test_the_rows_are_capped_and_the_cap_is_stated():
    agents = [{"agent_id": f"a{i}"} for i in range(MAX_USAGE_ROWS + 5)]
    usage = {a["agent_id"]: {"total_input_tokens": 1, "agent_id": a["agent_id"]} for a in agents}
    c, r = overview(usage, agents)
    j = r.json()["token_usage"]
    assert len(j["data"]) == MAX_USAGE_ROWS and f"first {MAX_USAGE_ROWS}" in j["error"]


def test_exactly_the_cap_is_not_flagged():
    agents = [{"agent_id": f"a{i}"} for i in range(MAX_USAGE_ROWS)]
    usage = {a["agent_id"]: {"total_input_tokens": 1} for a in agents}
    c, r = overview(usage, agents)
    j = r.json()["token_usage"]
    assert len(j["data"]) == MAX_USAGE_ROWS and j["error"] is None


@pytest.mark.parametrize("body", [{"detail": "down"}, {"total_input_tokens": 99}, [1, 2], "x"], ids=repr)
def test_a_non_200_usage_answer_is_skipped_silently_whatever_it_holds(body):
    gov = Stub(status=503, body=body)
    c = console(registry=sc(Stub(body=AGENTS)), governor=sc(gov))
    j = c.get("/api/overview").json()["token_usage"]
    assert j["data"] == [] and j["error"] is None


@pytest.mark.parametrize("body", [[1, 2], "x", 7, None], ids=repr)
def test_the_stream_still_yields_an_overview_frame(body):
    c, _ = overview({"a": body})
    with c.stream("GET", "/api/stream", params={"frames": 1}) as r:
        text = "".join(r.iter_text())
    assert r.status_code == 200 and text.startswith("event: overview\n")
    assert "usage answer(s) were not readable" in text
