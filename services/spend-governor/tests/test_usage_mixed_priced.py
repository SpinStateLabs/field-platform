"""Scout S3-1: `usage_totals_since` grouped by model and took `MIN(priced)`, then summed cost only over groups whose MIN was 1.
A model with even ONE unpriced row in the window (priced 0, cost_units NULL: a price-book change, or a record taken before
the model was priced) got p = 0, so the cost of ALL its priced rows was dropped from the total the API folds into the spend
cap (`/status`, `/totals`) and shown as `priced False, cost_units None` in `/usage/{agent}`: a silent undercount of spend.
The cap total now sums only the priced rows' cost. `by_model[].priced` keeps meaning 'every row in the window was priced';
a model with a mix shows its priced cost with `priced False` (decision for Don, see the PR)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import GovernorStore
from spend_governor.usage import UsageRecord

AGENT = "invoicing-agent"
MODEL = "mixed-model-x"
OTHER = "claude-haiku-4-5"


@pytest.fixture()
def store(tmp_path):
    return GovernorStore(tmp_path / "spend.sqlite3")


@pytest.fixture()
def client(store):
    c = TestClient(create_app(store=store))
    assert c.put(f"/caps/{AGENT}", json={"agent_id": AGENT, "limit_cents": 100_000, "period": "daily",
                                          "escalate_at_pct": 80}).status_code == 200
    return c


def add(store, model, cost_units, *, i=100, o=50):
    store.record_usage(UsageRecord(
        event_id=str(uuid.uuid4()), agent_id=AGENT, ts=datetime.now(timezone.utc).isoformat(), model=model,
        input_tokens=i, output_tokens=o, cost_units=cost_units, priced=cost_units is not None))


def since():
    return "1970-01-01T00:00:00+00:00"


def by_model(client):
    return {m["model"]: m for m in client.get(f"/usage/{AGENT}").json()["by_model"]}


def test_a_model_with_one_unpriced_row_keeps_its_priced_cost_in_the_totals(store):
    add(store, MODEL, None)                  # the unpriced row comes FIRST
    add(store, MODEL, 300_000)
    add(store, MODEL, 200_000)
    total_in, total_out, total_cost, rows = store.usage_totals_since(AGENT, since())
    assert total_cost == 500_000
    assert (total_in, total_out) == (300, 150)             # tokens count for every row
    (row,) = rows
    assert row["c"] == 500_000 and row["p"] == 0           # the priced sum, and the 'some unpriced' signal kept


@pytest.mark.parametrize("order", [["u", "p", "p"], ["p", "u", "p"], ["p", "p", "u"], ["u", "u", "p"]])
def test_the_order_of_the_rows_does_not_matter(store, order):
    for kind in order:
        add(store, MODEL, 100_000 if kind == "p" else None)
    assert store.usage_totals_since(AGENT, since())[2] == 100_000 * order.count("p")


def test_status_and_totals_count_the_priced_rows_of_a_mixed_model(client, store):
    add(store, MODEL, None)
    add(store, MODEL, 5_000_000)             # 50 cents at 100,000 units per cent
    add(store, MODEL, 5_000_000)
    status = client.get(f"/status/{AGENT}").json()
    totals = client.get(f"/totals/{AGENT}", params={"since": since()}).json()
    assert status["token_cost_units"] == 10_000_000 and status["spent_cents"] == 100
    assert totals["token_cost_units"] == 10_000_000 and totals["spent_cents"] == 100
    assert status["spent_cents"] == totals["spent_cents"]


def test_the_cap_trips_on_the_priced_rows_of_a_mixed_model(client, store):
    """With the bug the model's priced cost was dropped, so a cap it had really crossed never tripped."""
    client.put(f"/caps/{AGENT}", json={"agent_id": AGENT, "limit_cents": 100, "period": "daily", "escalate_at_pct": 80})
    add(store, MODEL, None)
    add(store, MODEL, 10_000_000)            # 100 cents = the cap
    s = client.get(f"/status/{AGENT}").json()
    assert s["spent_cents"] == 100 and s["state"] == "BLOCK"


def test_usage_by_model_shows_the_priced_portion_and_keeps_the_unpriced_signal(client, store):
    add(store, MODEL, None)
    add(store, MODEL, 300_000)
    add(store, MODEL, 200_000)
    add(store, OTHER, 60_000)
    m = by_model(client)
    assert m[MODEL]["cost_units"] == 500_000 and m[MODEL]["priced"] is False
    assert m[OTHER]["cost_units"] == 60_000 and m[OTHER]["priced"] is True
    assert client.get(f"/usage/{AGENT}").json()["total_cost_units"] == 560_000


def test_a_model_with_only_unpriced_rows_still_has_no_cost(client, store):
    add(store, MODEL, None)
    add(store, MODEL, None)
    m = by_model(client)[MODEL]
    assert m["priced"] is False and m["cost_units"] is None
    s = client.get(f"/status/{AGENT}").json()
    assert s["token_cost_units"] == 0 and s["spent_tokens"] == 300


def test_a_model_with_only_priced_rows_is_unchanged(client, store):
    add(store, MODEL, 400_000)
    add(store, MODEL, 100_000)
    m = by_model(client)[MODEL]
    assert m["priced"] is True and m["cost_units"] == 500_000


def test_a_zero_cost_priced_row_is_priced_not_unpriced(store):
    add(store, MODEL, 0)
    add(store, MODEL, 250_000)
    (row,) = store.usage_totals_since(AGENT, since())[3]
    assert row["p"] == 1 and row["c"] == 250_000


def test_the_overflow_safe_sum_still_holds_for_a_mixed_model(store):
    big = 2**62
    add(store, MODEL, None)
    add(store, MODEL, big)
    add(store, MODEL, big)
    assert store.usage_totals_since(AGENT, since())[2] == 2 * big      # beyond int64 once added, still exact
