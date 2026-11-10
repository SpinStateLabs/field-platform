"""S7-9: ``decommission`` is act-first (revoke, then KILL, then RETIRE). A token listing that is reachable but wrong, a 5xx
with a JSON object, a non-JSON body, a list whose row has no ``token_id``, used to escape as AttributeError / KeyError /
a JSON error BEFORE the kill and the retire. Each is now a failed ``revoke`` step on the report and the agent is still
killed (once) and retired. A row that says ``revoked: "false"`` is no longer taken as revoked."""

from __future__ import annotations

import pytest

from test_transitions import _provisioned, estate_ref, stack, valid_manifest  # noqa: F401  (fixtures)

AGENT = "invoicing-agent"


class Answer:
    def __init__(self, status=200, body=None, text="", json_raises=None):
        self.status_code, self._body, self.text, self._raises = status, body, text, json_raises

    def json(self):
        if self._raises is not None:
            raise self._raises
        return self._body


class Listing:
    """the real delegation app, except that ``GET /tokens`` answers what the test says"""

    def __init__(self, real, answer):
        self.real, self.answer = real, answer
        self.posts: list[str] = []

    def get(self, path, **kw):
        return self.answer if path == "/tokens" else self.real.get(path, **kw)

    def post(self, path, **kw):
        self.posts.append(path)
        return self.real.post(path, **kw)


def run(stack, valid_manifest, answer):
    engine, registry, _, delegation, _, kill_spy = stack
    _provisioned(engine, valid_manifest)
    fake = Listing(delegation, answer)
    engine.delegation = fake
    report = engine.decommission(AGENT, by="Don", reason="incident")
    return report, registry, kill_spy, fake


CASES = {
    "503-json-dict": (Answer(503, {"detail": "overloaded"}, text='{"detail":"overloaded"}'), "answered 503"),
    "500-html": (Answer(500, None, text="<html>boom</html>", json_raises=ValueError("x")), "answered 500"),
    "200-not-json": (Answer(200, None, text="<html>", json_raises=ValueError("Expecting value")), "is not JSON"),
    "200-dict": (Answer(200, {"tokens": []}), "is a dict, not a list"),
    "200-string": (Answer(200, "oops"), "is a str, not a list"),
    "200-number": (Answer(200, 7), "is a int, not a list"),
    "200-row-without-token-id": (Answer(200, [{"agent_id": AGENT, "revoked": False}]), "row 0 has no usable token_id"),
    "200-row-not-an-object": (Answer(200, ["a", 5, None]), "row 0 has no usable token_id"),
    "200-token-id-not-a-string": (Answer(200, [{"token_id": 7}, {"token_id": ""}, {"token_id": None}]),
                                  "has no usable token_id"),
}


@pytest.mark.parametrize("name", CASES)
def test_a_bad_listing_is_a_failed_step_and_the_agent_is_still_killed_and_retired(stack, valid_manifest, name):
    answer, needle = CASES[name]
    report, registry, kill_spy, _ = run(stack, valid_manifest, answer)
    assert report.ok is False
    assert any(needle in (f.detail or "") for f in report.revoke_failures), [f.detail for f in report.revoke_failures]
    assert report.killed is True and len(kill_spy.calls) == 1
    assert report.retired is True
    assert registry.get(f"/agents/{AGENT}").json()["status"] == "retired"


def test_a_5xx_failure_names_its_status_on_the_step(stack, valid_manifest):
    report, *_ = run(stack, valid_manifest, CASES["503-json-dict"][0])
    assert [f.http_status for f in report.revoke_failures] == [503]


def test_the_failure_text_is_capped(stack, valid_manifest):
    report, *_ = run(stack, valid_manifest, Answer(502, None, text="x" * 5000, json_raises=ValueError("x")))
    assert all(len(f.detail) < 600 for f in report.revoke_failures)


def test_a_mixed_list_revokes_the_good_rows_and_reports_the_bad_ones(stack, valid_manifest):
    engine, _, _, delegation, _, _ = stack
    _provisioned(engine, valid_manifest)
    real = delegation.get("/tokens", params={"agent_id": AGENT}).json()
    good = real[0]["token_id"]
    mixed = [{"agent_id": AGENT}, "junk", dict(real[0])]
    engine.delegation = fake = Listing(delegation, Answer(200, mixed))
    report = engine.decommission(AGENT, by="Don", reason="incident")
    assert report.ok is False
    assert report.tokens_revoked == [good] and fake.posts == [f"/tokens/{good}/revoke"]
    assert len(report.revoke_failures) == 2
    assert report.killed is True and report.retired is True


def test_a_string_revoked_flag_is_not_taken_as_revoked(stack, valid_manifest):
    """"false" is truthy: the old ``token.get("revoked")`` skipped the revoke for it."""
    engine, _, _, delegation, _, _ = stack
    _provisioned(engine, valid_manifest)
    real = delegation.get("/tokens", params={"agent_id": AGENT}).json()[0]
    row = dict(real, revoked="false")
    engine.delegation = fake = Listing(delegation, Answer(200, [row]))
    report = engine.decommission(AGENT, by="Don", reason="incident")
    assert fake.posts == [f"/tokens/{real['token_id']}/revoke"] and report.tokens_revoked == [real["token_id"]]


def test_a_genuinely_revoked_token_is_still_skipped(stack, valid_manifest):
    engine, _, _, delegation, _, _ = stack
    _provisioned(engine, valid_manifest)
    real = delegation.get("/tokens", params={"agent_id": AGENT}).json()[0]
    engine.delegation = fake = Listing(delegation, Answer(200, [dict(real, revoked=True)]))
    report = engine.decommission(AGENT, by="Don", reason="incident")
    assert fake.posts == [] and report.tokens_revoked == [] and report.ok is True


def test_the_plain_list_a_test_hands_in_and_the_empty_listing_still_work(stack, valid_manifest):
    engine, registry, _, delegation, _, kill_spy = stack
    _provisioned(engine, valid_manifest)
    engine.delegation = Listing(delegation, [])           # no status_code, no json(): plain data, nothing to revoke
    report = engine.decommission(AGENT, by="Don", reason="incident")
    assert report.ok is True and report.tokens_revoked == [] and len(kill_spy.calls) == 1
    assert registry.get(f"/agents/{AGENT}").json()["status"] == "retired"


def test_the_happy_path_is_unchanged(stack, valid_manifest):
    engine, registry, _, delegation, _, kill_spy = stack
    _provisioned(engine, valid_manifest)
    report = engine.decommission(AGENT, by="Don", reason="incident")
    assert report.ok is True and len(report.tokens_revoked) == 1 and report.revoke_failures == []
    assert report.killed and report.retired and len(kill_spy.calls) == 1


def test_an_empty_token_id_is_never_posted_to(stack, valid_manifest):
    report, _, _, fake = run(stack, valid_manifest, Answer(200, [{"token_id": ""}]))
    assert fake.posts == [] and report.ok is False and "row 0 has no usable token_id" in report.revoke_failures[0].detail
