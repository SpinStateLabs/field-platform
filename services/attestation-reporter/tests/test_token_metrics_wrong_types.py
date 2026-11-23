"""S5-16: the two token metrics read ``revoked`` strictly. ``True``/``False`` count as themselves, an absent key is
``False``, and any other value (the string 'false', 1, 0, a list, null) makes THAT metric unavailable with a named
note: never a signed figure built on truthiness. The rest of the pack still builds."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from attestation_reporter.engine import PackEngine

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
REVOKED = "Tokens revoked (all time)"
EXPIRING = "Authorities expiring within 30 days"
ISSUED = "Delegation tokens issued (all time)"


class Answer:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class Stub:
    def __init__(self, **routes):
        self.routes = routes

    def get(self, target):
        return Answer(self.routes.get(target.split("?")[0], []))


def engine(tokens):
    return PackEngine(
        registry=Stub(**{"/agents": []}),
        ledger=Stub(**{"/events": [], "/verify": {"ok": True, "length": 0}, "/health": {},
                       "/retention/check": {"status": "no_estate_policy"}}),
        delegation=Stub(**{"/tokens": tokens}), governor=Stub(**{"/escalations": []}))


def metrics(tokens):
    pack = engine(tokens).build(now=NOW)
    return {m.name: m for m in pack.all_metrics()}


def soon(days=5):
    return (NOW + timedelta(days=days)).isoformat()


def tok(i, expires=None, **kw):
    t = {"token_id": f"t{i}", "agent_id": "a", "expires_at": expires or soon()}
    t.update(kw)
    return t


BAD = ["false", "true", "False", 1, 0, 2.5, ["x"], [], {"a": 1}, None, ""]


@pytest.mark.parametrize("bad", BAD, ids=repr)
def test_a_non_boolean_revoked_makes_both_metrics_unavailable_and_named(bad):
    m = metrics([tok(1, revoked=False), tok(2, revoked=bad)])
    for name in (REVOKED, EXPIRING):
        assert m[name].status == "unavailable" and m[name].value is None, (name, m[name])
        assert "RevokedFlagNotBoolean" in m[name].note and "figure not published" in m[name].note
    assert m[ISSUED].value == 2                             # the rest of the pack still builds


@pytest.mark.parametrize("bad", BAD, ids=repr)
def test_a_non_boolean_on_an_already_expired_token_still_counts_as_wrong_shape(bad):
    m = metrics([tok(1, expires=(NOW - timedelta(days=9)).isoformat(), revoked=bad)])
    assert m[REVOKED].status == "unavailable" and m[EXPIRING].status == "unavailable"


def test_true_and_false_count_as_themselves():
    m = metrics([tok(1, revoked=True), tok(2, revoked=False), tok(3, revoked=True), tok(4, revoked=False)])
    assert m[REVOKED].value == 2 and m[REVOKED].status != "unavailable"
    assert m[EXPIRING].value == 2


def test_a_missing_revoked_key_is_not_revoked():
    m = metrics([tok(1), tok(2, revoked=True)])
    assert m[REVOKED].value == 1 and m[EXPIRING].value == 1


def test_a_revoked_token_is_never_expiring_even_if_its_expiry_is_malformed():
    """short-circuit kept: a revoked token's expires_at is not parsed (unchanged behaviour)."""
    m = metrics([tok(1, revoked=True, expires="not a date"), tok(2, revoked=False)])
    assert m[EXPIRING].value == 1


def test_the_window_edges_are_inclusive_and_exact():
    m = metrics([tok(1, expires=NOW.isoformat(), revoked=False),
                 tok(2, expires=(NOW + timedelta(days=30)).isoformat(), revoked=False),
                 tok(3, expires=(NOW + timedelta(days=30, seconds=1)).isoformat(), revoked=False),
                 tok(4, expires=(NOW - timedelta(seconds=1)).isoformat(), revoked=False)])
    assert m[EXPIRING].value == 2


@pytest.mark.parametrize("expires", ["2026-07-20T12:00:00", "not a date", None, 5, ""])
def test_a_naive_or_malformed_expires_at_is_unavailable_for_the_expiring_metric_only(expires):
    m = metrics([tok(1, expires=expires, revoked=False)]) if expires else metrics(
        [{"token_id": "t", "revoked": False, "expires_at": expires}])
    assert m[EXPIRING].status == "unavailable"
    assert m[REVOKED].value == 0 and m[REVOKED].status != "unavailable"


def test_an_all_boolean_list_is_unchanged():
    m = metrics([tok(i, revoked=bool(i % 2)) for i in range(6)])
    assert m[REVOKED].value == 3 and m[EXPIRING].value == 3
