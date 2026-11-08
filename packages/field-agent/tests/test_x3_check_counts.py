"""S11-8: x3_check counts new ledger rows through a bounded snapshot, not through the whole event list.

`count()` GETs `/events?event_type=X&agent_id=Y` with no `limit`; the ledger returns every match, but `urllib_call`
refuses a reply over 64 KiB (`{'response_too_large': ...}`), so once the canary had enough kill.endpoint_called /
kill.revive / kill.drill.complete rows every later run failed the three "exactly +1" checks with no hint why. The check
now asks for `limit=20` (the ledger keeps the LAST N matches), takes the set of event_id values before and after, and
requires exactly one new id. Driven with injected platform/canary callables: no sockets.
"""
from __future__ import annotations

import re
import urllib.parse

import pytest

from field_agent import canary as canary_mod

AGENT = "canary-gb10"
CANARY_URL = "http://canary-agent:8090"
TOO_LARGE = {"response_too_large": 65536}


class Estate:
    """A ledger that keeps `old` rows per type and answers like sealed-ledger: the LAST `limit` matches, every match
    when `limit` is omitted (and, like urllib_call, a too-large marker once an unbounded reply would cross 64 KiB)."""

    def __init__(self, old: int = 0, rows_per_kill: int = 1, rows_per_revive: int = 1, rows_per_drill: int = 1,
                 cap_unbounded_at: int = 150):
        self.rows: dict[str, list[dict]] = {t: [] for t in ("kill.endpoint_called", "kill.revive", "kill.drill.complete")}
        self.seq = 0
        for t in self.rows:
            for _ in range(old):
                self._add(t)
        self.per = {"kill": rows_per_kill, "revive": rows_per_revive, "drill": rows_per_drill}
        self.cap = cap_unbounded_at
        self.queries: list[str] = []
        self.halted, self.nonce, self.halts = False, None, 0

    def _add(self, t):
        self.seq += 1
        self.rows[t].append({"event_id": f"ev-{self.seq}", "event_type": t, "agent_id": AGENT})

    def platform(self, method, url, body=None):
        parts = urllib.parse.urlsplit(url)
        host, path = parts.hostname, parts.path
        if host == "registry":
            return 200, {"agent_id": AGENT, "domain": canary_mod.CANARY_DOMAIN, "status": "active"}
        if host == "ledger":
            self.queries.append(parts.query)
            q = dict(urllib.parse.parse_qsl(parts.query))
            rows = self.rows[q["event_type"]]
            if "limit" in q:
                return 200, rows[-int(q["limit"]):]
            return (200, TOO_LARGE) if len(rows) > self.cap else (200, list(rows))
        if path.startswith("/kill/"):
            for _ in range(self.per["kill"]):
                self._add("kill.endpoint_called")
            self.halted, self.halts = True, self.halts + 1
            self.nonce = re.search(r"x3-([0-9a-f]+)", body["reason"]).group(1)
            return 200, {"endpoint_result": {"outcome": "called", "http_status": 200, "endpoint_host": "canary-agent"}}
        if path.startswith("/revive/"):
            for _ in range(self.per["revive"]):
                self._add("kill.revive")
            return 200, {}
        if path.startswith("/heartbeat/"):
            return 200, {"killed": False}
        if path.startswith("/drill/"):
            for _ in range(self.per["drill"]):
                self._add("kill.drill.complete")
            self.nonce = re.search(r"x3-([0-9a-f]+)", body["reason"]).group(1)
            return 200, {"endpoint_result": {"outcome": "called"}, "endpoint_confirmed_ms": 12.5,
                         "restored": True, "restored_status": "active"}
        raise AssertionError(url)

    def canary(self, method, url, body=None):
        return 200, {"agent_id": AGENT, "heartbeat_every": 0, "halts": self.halts, "halted": self.halted,
                     "nonce": self.nonce, "last_halted_by": "endpoint" if self.halted else None,
                     "since": "t" if self.halted else None}


def run(estate: Estate, agent: str = AGENT):
    out: list[str] = []
    code = canary_mod.x3_check(agent, killswitch_url="http://killswitch", registry_url="http://registry",
                               ledger_url="http://ledger", canary_url=CANARY_URL, platform=estate.platform,
                               canary=estate.canary, out=out.append)
    return code, "\n".join(out)


def test_a_clean_run_passes():
    code, text = run(Estate())
    assert code == 0, text


def test_500_old_rows_per_type_still_pass_because_the_query_is_bounded():
    estate = Estate(old=500)
    code, text = run(estate)
    assert code == 0, text
    assert estate.queries and all("limit=" in q for q in estate.queries)


def test_an_unbounded_query_would_have_hit_the_reply_cap_so_the_new_query_never_is():
    """Control: the fake answers an unbounded query over its cap with the marker (like urllib_call at 64 KiB)."""
    estate = Estate(old=500)
    assert estate.platform("GET", "http://ledger/events?event_type=kill.revive&agent_id=x") == (200, TOO_LARGE)
    assert estate.platform("GET", "http://ledger/events?event_type=kill.revive&agent_id=x&limit=20")[1][-1]["event_id"]


def test_the_query_names_the_type_the_agent_and_a_limit_of_20():
    estate = Estate()
    run(estate)
    parsed = [dict(urllib.parse.parse_qsl(q)) for q in estate.queries]
    assert {p["limit"] for p in parsed} == {"20"}
    assert {p["agent_id"] for p in parsed} == {AGENT}
    assert {p["event_type"] for p in parsed} == {"kill.endpoint_called", "kill.revive", "kill.drill.complete"}


@pytest.mark.parametrize("which,label", [("rows_per_kill", "kill.endpoint_called"), ("rows_per_revive", "kill.revive"),
                                         ("rows_per_drill", "kill.drill.complete")])
@pytest.mark.parametrize("n", [0, 2])
def test_zero_or_two_new_rows_fails_the_exactly_one_check(which, label, n):
    """old=100 is under the fake's unbounded cap, so the OLD code reads real counts too: this fails for the right reason."""
    code, text = run(Estate(old=100, **{which: n}))
    assert code == 1, text
    assert f"[FAIL] exactly +1 {label}" in text or f"[FAIL] revive 200 and exactly +1 {label}" in text


def test_an_unreadable_ledger_reply_is_reported_unreadable_not_as_arithmetic():
    estate = Estate()
    real = estate.platform

    def broken(method, url, body=None):
        if "ledger" in url:
            return 200, TOO_LARGE
        return real(method, url, body)
    out: list[str] = []
    code = canary_mod.x3_check(AGENT, killswitch_url="http://killswitch", registry_url="http://registry",
                               ledger_url="http://ledger", canary_url=CANARY_URL, platform=broken,
                               canary=estate.canary, out=out.append)
    text = "\n".join(out)
    assert code == 1 and "unreadable" in text and "-> None" not in text and "(None" not in text


def test_a_non_200_or_malformed_ledger_reply_is_unreadable_too():
    for reply in ((500, []), (200, {"events": []}), (200, [{"no_id": 1}]), (200, ["x"])):
        estate = Estate()
        real = estate.platform

        def broken(method, url, body=None, _r=reply):
            return _r if "ledger" in url else real(method, url, body)
        out: list[str] = []
        code = canary_mod.x3_check(AGENT, killswitch_url="http://killswitch", registry_url="http://registry",
                                   ledger_url="http://ledger", canary_url=CANARY_URL, platform=broken,
                                   canary=estate.canary, out=out.append)
        assert code == 1, reply


def test_the_window_sliding_by_one_still_counts_one_new_id():
    """With a full window of 20 old rows, one new row pushes the oldest out: exactly one id is new."""
    code, text = run(Estate(old=20))
    assert code == 0, text


def test_other_checks_labels_and_exit_codes_are_unchanged():
    code, text = run(Estate())
    for label in ("canary-agent GET /status 200", "heartbeat polling disabled for the test",
                  "heartbeat killed=false after revive", "canary process still halted after revive",
                  "checks passed"):
        assert label in text
    code2, text2 = run(Estate(), agent="not-a-canary")
    assert code2 == 2 and "refusing" in text2


@pytest.mark.parametrize("which", ["rows_per_kill", "rows_per_revive", "rows_per_drill"])
@pytest.mark.parametrize("n", [0, 2])
def test_zero_or_two_new_rows_also_fails_when_the_history_is_far_past_the_cap(which, n):
    code, text = run(Estate(old=500, **{which: n}))
    assert code == 1 and "exactly +1" in text and f"{n} new)" in text
