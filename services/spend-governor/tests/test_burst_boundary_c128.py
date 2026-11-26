"""C-128 (reviewer R-08 F-R08-6, mutant `>=` to `>` in ``evaluate_rogue``): a token burst EXACTLY at the limit
is a rogue burst. The existing end-to-end test sends 6000 tokens against a limit of 5000, so the boundary was
never exercised. Pure (``evaluate_rogue``) and through the API (a real usage event).

The message carries the count and the limit, so the detail is pinned too: the number an operator reads is the
number the arithmetic used."""

import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import GovernorStore
from spend_governor.usage import RogueKind, UsagePolicy, evaluate_rogue

AGENT = "burst-agent"
LIMIT = 5000


def _policy(limit=LIMIT):
    return UsagePolicy(agent_id=AGENT, token_rate_limit=limit)


def _kinds(findings):
    return [f.kind for f in findings]


@pytest.mark.parametrize("window_tokens,flagged", [
    (LIMIT - 1, False),
    (LIMIT, True),
    (LIMIT + 1, True),
])
def test_the_burst_boundary_is_inclusive(window_tokens, flagged):
    findings = evaluate_rogue(_policy(), "claude-haiku-4-5", True, window_tokens)
    assert (RogueKind.ROGUE_BURST in _kinds(findings)) is flagged


def test_the_burst_detail_names_the_count_and_the_limit():
    (f,) = [x for x in evaluate_rogue(_policy(), "claude-haiku-4-5", True, LIMIT)
            if x.kind == RogueKind.ROGUE_BURST]
    assert f"{LIMIT} tokens" in f.detail and f"limit {LIMIT}" in f.detail


def test_no_limit_never_flags_a_burst():
    assert RogueKind.ROGUE_BURST not in _kinds(evaluate_rogue(_policy(None), "claude-haiku-4-5", True, 10**9))
    assert RogueKind.ROGUE_BURST not in _kinds(evaluate_rogue(None, "claude-haiku-4-5", True, 10**9))


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=GovernorStore(tmp_path / "spend.sqlite3")))


def _setup(client):
    assert client.put(f"/caps/{AGENT}", json={"agent_id": AGENT, "limit_cents": 50_000, "period": "daily",
                                              "escalate_at_pct": 80}).status_code == 200
    assert client.put(f"/policies/{AGENT}", json={"agent_id": AGENT, "token_rate_limit": LIMIT,
                                                  "rate_window_seconds": 3600}).status_code == 200


def _use(client, i, o):
    return client.post("/usage", json={"agent_id": AGENT, "model": "claude-haiku-4-5",
                                       "input_tokens": i, "output_tokens": o})


def test_an_event_that_lands_exactly_on_the_limit_through_the_api_is_flagged(client):
    _setup(client)
    first = _use(client, 1000, 1000)                              # 2000, under
    assert RogueKind.ROGUE_BURST.value not in [f["kind"] for f in first.json()["rogue"]]
    exact = _use(client, 1500, 1500)                              # 2000 + 3000 = 5000, exactly the limit
    assert RogueKind.ROGUE_BURST.value in [f["kind"] for f in exact.json()["rogue"]]


def test_one_token_under_the_limit_through_the_api_is_not_flagged(client):
    _setup(client)
    r = _use(client, 2000, 2999)                                  # 4999
    assert RogueKind.ROGUE_BURST.value not in [f["kind"] for f in r.json()["rogue"]]


# --- the two window edges (reviewer C-703 F-C703-2): the burst sum is inclusive, the rolling throttle strict ---

from spend_governor.usage import UsageRecord  # noqa: E402

_T = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)


def _store_with(tmp_path, offsets_us):
    """A store holding one 100-token usage row per offset (microseconds after _T)."""
    store = GovernorStore(tmp_path / "edge.sqlite3")
    for n, us in enumerate(offsets_us):
        ts = (_T + timedelta(microseconds=us)).isoformat()
        store.record_usage(UsageRecord(event_id=f"e{n}", agent_id=AGENT, ts=ts, model="claude-haiku-4-5",
                                       input_tokens=60, output_tokens=40, cost_units=1))
    return store


def test_the_burst_sum_includes_a_row_exactly_at_the_window_start(tmp_path):
    store = _store_with(tmp_path, [-1, 0, 1])                 # one before, exactly at, one after
    assert store.window_tokens(AGENT, _T.isoformat()) == 200   # the row at the edge counts, the earlier one not


def test_the_burst_sum_excludes_a_row_one_microsecond_before_the_start(tmp_path):
    store = _store_with(tmp_path, [-1])
    assert store.window_tokens(AGENT, _T.isoformat()) == 0


def test_the_rolling_throttle_read_is_strict_at_the_edge(tmp_path):
    store = _store_with(tmp_path, [-1, 0, 1])
    rows = store.token_rows_after(AGENT, _T.isoformat())
    assert [t for _, t in rows] == [100]                       # only the row after the edge
    assert rows[0][0] == (_T + timedelta(microseconds=1)).isoformat()


# --- the window edge through the API (reviewer C-703 / C-827: mutant W2, the window one second shorter) ---


class _Clock:
    def __init__(self):
        self.now = _T

    def __call__(self):
        return self.now


def _edge_client(tmp_path):
    clock = _Clock()
    c = TestClient(create_app(store=GovernorStore(tmp_path / "edge-api.sqlite3"), clock=clock))
    assert c.put(f"/caps/{AGENT}", json={"agent_id": AGENT, "limit_cents": 50_000, "period": "daily",
                                         "escalate_at_pct": 80}).status_code == 200
    assert c.put(f"/policies/{AGENT}", json={"agent_id": AGENT, "token_rate_limit": 200,
                                             "rate_window_seconds": 60}).status_code == 200
    return c, clock


def _use100(c):
    return c.post("/usage", json={"agent_id": AGENT, "model": "claude-haiku-4-5",
                                  "input_tokens": 60, "output_tokens": 40})


def _burst(resp):
    return "rogue_burst" in [f["kind"] for f in resp.json()["rogue"]]


def test_an_event_exactly_one_window_old_still_counts_toward_the_burst(tmp_path):
    c, clock = _edge_client(tmp_path)
    clock.now = _T - timedelta(seconds=60)
    assert _use100(c).status_code == 201
    clock.now = _T
    assert _burst(_use100(c)) is True                           # 100 + 100 = 200 = the limit, edge inclusive


def test_an_event_one_microsecond_older_than_the_window_does_not_count(tmp_path):
    c, clock = _edge_client(tmp_path)
    clock.now = _T - timedelta(seconds=60, microseconds=1)
    assert _use100(c).status_code == 201
    clock.now = _T
    assert _burst(_use100(c)) is False                          # only this event's 100 is inside the window


def test_an_event_one_second_inside_the_window_counts(tmp_path):
    c, clock = _edge_client(tmp_path)
    clock.now = _T - timedelta(seconds=59)
    assert _use100(c).status_code == 201
    clock.now = _T
    assert _burst(_use100(c)) is True


# --- the API converts its clock to UTC (reviewer C-848 F-C848-4, mutant A9: the caller's offset kept) ---------


@pytest.mark.parametrize("offset_h", [14, -5, 0])
def test_a_clock_in_another_offset_stamps_rows_in_utc(tmp_path, offset_h):
    local = timezone(timedelta(hours=offset_h))
    instant = datetime(2026, 10, 30, 11, 0, 0, tzinfo=timezone.utc)
    c = TestClient(create_app(store=GovernorStore(tmp_path / f"tz{offset_h}.sqlite3"),
                              clock=lambda: instant.astimezone(local)))
    assert c.put(f"/caps/{AGENT}", json={"agent_id": AGENT, "limit_cents": 50_000, "period": "daily",
                                         "escalate_at_pct": 80}).status_code == 200
    assert c.post("/spend", json={"agent_id": AGENT, "cents": 7}).status_code == 201
    at = c.get(f"/totals/{AGENT}", params={"since": "2026-10-30T11:00:00Z"}).json()
    after = c.get(f"/totals/{AGENT}", params={"since": "2026-10-30T11:00:01Z"}).json()
    assert at["spent_cents"] == 7 and after["spent_cents"] == 0     # the row is stamped 11:00:00 UTC exactly


def test_window_start_docstring_states_the_utc_precondition():
    from spend_governor.core import window_start
    assert "UTC" in window_start.__doc__ and "answers 500 and" in window_start.__doc__
