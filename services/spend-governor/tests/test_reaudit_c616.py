"""C-616 (reviewer C-526 F-C526-1..4): the spend-governor's request bounds, its /totals instant and its exact action key.

* F-C526-1: ``/totals`` answers 422, not 500, for an instant that parses but cannot be converted to UTC;
* F-C526-2: the ``ge=0`` and ``le=MAX_AMOUNT`` bounds of SpendRequest and UsageRequest are pinned (a negative token
  count would otherwise lower the window total, a refund);
* F-C526-3: a naive ``since`` is read as UTC whatever the host time zone is (a subprocess with ``TZ`` set; skipped
  where the platform has no ``tzset``);
* F-C526-4: the per-action rate window is keyed on the EXACT action string. That is the documented behaviour
  (README row on throttling; ``test_throttle.py`` pins case and whitespace); the spellings the re-audit named
  (a zero-width character, a hyphen for an underscore) are pinned here too. Whether to normalise them is a decision
  for Don, not made in this change."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import MAX_AMOUNT, GovernorStore

AGENT = "probe-agent"
T0 = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def client(tmp_path):
    store = GovernorStore(tmp_path / "spend.sqlite3")
    c = TestClient(create_app(store=store, clock=lambda: T0))
    r = c.put(f"/caps/{AGENT}", json={"agent_id": AGENT, "limit_cents": 50_000, "period": "daily",
                                      "escalate_at_pct": 80})
    assert r.status_code == 200, r.text
    yield c
    store.close()


# ---- F-C526-1: an instant that cannot be converted ---------------------------------------------


@pytest.mark.parametrize("since", ["0001-01-01T00:00:00+05:00", "9999-12-31T23:59:59-23:59"])
def test_an_instant_that_overflows_the_utc_conversion_is_422_not_500(client, since):
    r = client.get(f"/totals/{AGENT}", params={"since": since})
    assert r.status_code == 422, r.text
    assert "ISO 8601" in r.text


@pytest.mark.parametrize("since", ["2026-10-30", "2026-10-30T00:00:00Z", "2026-10-30T00:00:00+05:00",
                                   "2026-10-30T00:00:00-07:30", "2026-10-30T12:00:00"])
def test_valid_instants_still_answer_200_and_are_reported_in_utc(client, since):
    r = client.get(f"/totals/{AGENT}", params={"since": since})
    assert r.status_code == 200, r.text
    assert r.json()["since"].endswith("+00:00")


@pytest.mark.parametrize("since", ["garbage", "", "2026-13-40", "yesterday"])
def test_garbage_is_still_422(client, since):
    assert client.get(f"/totals/{AGENT}", params={"since": since}).status_code == 422


def test_an_uncapped_agent_is_still_404_before_the_instant_is_read(client):
    assert client.get("/totals/nobody", params={"since": "0001-01-01T00:00:00+05:00"}).status_code == 404


# ---- F-C526-2: the request bounds ---------------------------------------------------------------


@pytest.mark.parametrize("field", ["cents", "tokens", "actions"])
def test_a_negative_spend_amount_is_422_and_writes_nothing(client, field):
    before = client.get(f"/status/{AGENT}").json()
    r = client.post("/spend", json={"agent_id": AGENT, field: -1})
    assert r.status_code == 422
    assert client.get(f"/status/{AGENT}").json() == before


@pytest.mark.parametrize("field", ["cents", "tokens", "actions"])
def test_a_spend_amount_at_the_bound_is_accepted_and_one_over_is_422(client, field):
    assert client.post("/spend", json={"agent_id": AGENT, field: 0}).status_code == 201
    assert client.post("/spend", json={"agent_id": AGENT, field: MAX_AMOUNT + 1}).status_code == 422


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens", "cache_read_tokens"])
def test_a_negative_usage_count_is_422(client, field):
    r = client.post("/usage", json={"agent_id": AGENT, "model": "claude-haiku-4-5", field: -1})
    assert r.status_code == 422


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens", "cache_read_tokens"])
def test_a_usage_count_over_the_bound_is_422(client, field):
    r = client.post("/usage", json={"agent_id": AGENT, "model": "claude-haiku-4-5", field: MAX_AMOUNT + 1})
    assert r.status_code == 422


def test_a_negative_token_count_cannot_lower_the_window_total(client):
    client.post("/spend", json={"agent_id": AGENT, "tokens": 100})
    assert client.post("/spend", json={"agent_id": AGENT, "tokens": -100}).status_code == 422
    t = client.get(f"/totals/{AGENT}", params={"since": "2026-10-30"}).json()
    assert t["spent_cents"] == 0 and client.get(f"/status/{AGENT}").status_code == 200


# ---- F-C526-3: a naive instant is UTC whatever the host zone ------------------------------------

_CHILD = textwrap.dedent("""
    import sys, tempfile
    from datetime import datetime, timezone
    from pathlib import Path
    from fastapi.testclient import TestClient
    from spend_governor.api import create_app
    from spend_governor.core import GovernorStore

    d = Path(tempfile.mkdtemp())
    store = GovernorStore(d / "s.sqlite3")
    c = TestClient(create_app(store=store, clock=lambda: datetime(2026, 10, 30, 12, tzinfo=timezone.utc)))
    c.put("/caps/probe-agent", json={"agent_id": "probe-agent", "limit_cents": 100, "period": "daily",
                                     "escalate_at_pct": 80})
    print(c.get("/totals/probe-agent", params={"since": "2026-10-30T12:00:00"}).json()["since"])
""")


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="needs a platform with time.tzset")
@pytest.mark.parametrize("tz", ["America/Toronto", "Asia/Kolkata", "Pacific/Auckland", "UTC"])
def test_a_naive_since_is_read_as_utc_in_any_host_time_zone(tz):
    here = Path(__file__).resolve().parents[1]
    env = dict(os.environ, TZ=tz, PYTHONPATH=os.pathsep.join([str(here / "src"), os.environ.get("PYTHONPATH", "")]))
    out = subprocess.run([sys.executable, "-c", _CHILD], capture_output=True, text=True, env=env, timeout=120)
    assert out.returncode == 0, out.stderr[-400:]
    assert out.stdout.strip() == "2026-10-30T12:00:00+00:00"


# ---- F-C526-4: the exact action key (declared; see the module docstring) ------------------------------


def _limit_tool_call(client):
    r = client.put(f"/rate-limits/{AGENT}", json={"agent_id": AGENT, "rate_limits": [
        {"action": "tool_call", "max": 2, "period": "hourly"}]})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("variant", ["Tool_Call", "tool_call ", " tool_call", "tool_call​", "tool-call",
                                     "tool_call ", "tооl_call"])
def test_rows_under_another_spelling_do_not_feed_the_exact_window(client, variant):
    """Declared: the rate-limit key is the raw string, so a spelling variant is metered elsewhere and never throttled."""
    _limit_tool_call(client)
    for _ in range(3):
        assert client.post("/spend", json={"agent_id": AGENT, "actions": 1, "action": variant}).status_code == 201
    assert client.get(f"/status/{AGENT}", params={"action": "tool_call"}).json()["state"] == "OK"


def test_two_exact_rows_do_throttle(client):
    _limit_tool_call(client)
    for _ in range(2):
        client.post("/spend", json={"agent_id": AGENT, "actions": 1, "action": "tool_call"})
    assert client.get(f"/status/{AGENT}", params={"action": "tool_call"}).json()["state"] == "THROTTLED"
