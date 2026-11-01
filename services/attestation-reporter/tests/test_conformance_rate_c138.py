"""C-138 (reviewer R-15 F-R15-1, F-R15-2): the conformance rate is rounded half UP, exactly, and one token with a
naive ``expires_at`` costs one metric, not the pack.

``round(100 * a / b, 1)`` is half-to-even on a float: 1/16 = 6.25 printed 6.2, where a reader recomputing by hand
gets 6.3. ``conformance_percent`` uses Decimal with ``ROUND_HALF_UP``; the pack note says so. Arithmetic used
below (percent = 100 a / b, one decimal, a tie is a second decimal of exactly 5):
  1/16 = 6.25 -> 6.3     3/16 = 18.75 -> 18.8     5/16 = 31.25 -> 31.3     7/16 = 43.75 -> 43.8
  1/160 = 0.625 -> 0.6   3/160 = 1.875 -> 1.9     1/32 = 3.125 -> 3.1     3/32 = 9.375 -> 9.4
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from attestation_reporter import engine as engine_module
from attestation_reporter.engine import PackEngine, conformance_percent
from field_core.ledger import GENESIS_HASH, make_event
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

RATE = "Conformance rate (ALLOW / all verdicts incl. shadow)"
ALLOW = "Conformance ALLOW verdicts"
EXPIRING = "Authorities expiring within 30 days"
ISSUED = "Delegation tokens issued (all time)"


def _half_up_tenths(a: int, b: int) -> int:
    """Independent integer rule: floor(1000 a / b + 1/2) = floor((2000 a + b) / (2 b)): tenths of a percent."""
    return (2000 * a + b) // (2 * b)


@pytest.mark.parametrize("a,b,want", [
    (1, 16, 6.3), (3, 16, 18.8), (5, 16, 31.3), (7, 16, 43.8), (9, 16, 56.3), (11, 16, 68.8), (13, 16, 81.3),
    (15, 16, 93.8), (1, 160, 0.6), (3, 160, 1.9), (1, 32, 3.1), (3, 32, 9.4),   # exact ties and near-ties
    (1, 8, 12.5), (1, 2, 50.0), (1, 3, 33.3), (2, 3, 66.7), (0, 5, 0.0), (5, 5, 100.0), (1, 40, 2.5),
])
def test_known_values(a, b, want):
    assert conformance_percent(a, b) == want


def test_no_verdicts_is_none_not_zero():
    assert conformance_percent(0, 0) is None


def test_every_ratio_up_to_300_matches_the_independent_integer_rule():
    checked = 0
    for b in range(1, 301):
        for a in range(0, b + 1):
            assert conformance_percent(a, b) == _half_up_tenths(a, b) / 10, (a, b)
            checked += 1
    assert checked == sum(b + 1 for b in range(1, 301))


def _chain(path: Path, rows) -> None:
    events, prev = [], GENESIS_HASH
    for event_type, ts in rows:
        ev = make_event(event_type, {}, prev_hash=prev, agent_id="fin-agent", ts=ts)
        events.append(ev)
        prev = ev.hash
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(e.model_dump_json() + "\n" for e in events), encoding="utf-8")


def _engine(tmp_path: Path, rows) -> PackEngine:
    path = tmp_path / "ledger" / "events.jsonl"
    _chain(path, rows)
    return PackEngine(ledger=TestClient(create_ledger_app(store=LedgerStore(path))))


T0 = "2026-08-15T12:00:00+00:00"


def test_the_pack_prints_the_half_up_tie_and_says_the_rounding_mode(tmp_path):
    rows = [("conformance.allow", T0)] + [("conformance.block", T0)] * 15     # 1 of 16 = 6.25
    m = {x.name: x for x in _engine(tmp_path, rows).build(period="2026-Q3").all_metrics()}
    assert m[RATE].value == 6.3 and m[RATE].unit == "%"
    assert "1 / (1+15+0+0+0)" in m[RATE].note and "rounded half up to one decimal" in m[RATE].note


def test_a_ledger_without_verdicts_says_n_a(tmp_path):
    m = {x.name: x for x in _engine(tmp_path, [("kill.agent", T0)]).build(period="2026-Q3").all_metrics()}
    assert m[RATE].value == "n/a — no verdicts in ledger"


def test_a_400_event_ledger_matches_an_independent_recount(tmp_path):
    """The reviewer's differential: 400 events, boundary instants and offsets, recounted without the engine."""
    rng = random.Random(138)
    q_start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    q_end = datetime(2026, 10, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    kinds = ["conformance.allow", "conformance.block", "conformance.escalate", "conformance.shadow_block",
             "conformance.shadow_escalate", "kill.agent", "federation.allow"]
    offsets = [timezone.utc, timezone(timedelta(hours=1)), timezone(timedelta(hours=5)), timezone(timedelta(hours=-8))]
    edges = [q_start - timedelta(microseconds=1), q_start, q_start + timedelta(microseconds=1),
             q_end - timedelta(microseconds=1), q_end, q_end + timedelta(microseconds=1)]
    rows, instants = [], []
    for i in range(400):
        base = edges[i % len(edges)] if i % 3 == 0 else q_start + timedelta(seconds=rng.randrange(-86400 * 20, 86400 * 110))
        tz = rng.choice(offsets)
        stamped = base.astimezone(tz)
        rows.append((rng.choice(kinds), stamped.isoformat()))
        instants.append(datetime.fromisoformat(stamped.isoformat()))
    # the ledger keeps rows in order; timestamps need not be monotonic for the count
    want = {k: 0 for k in kinds}
    for (kind, _), instant in zip(rows, instants):
        if q_start <= instant <= q_end:
            want[kind] += 1
    verdicts = sum(want[k] for k in kinds[:5])
    assert verdicts > 50 and want["conformance.allow"] > 0           # the sample is not vacuous
    m = {x.name: x for x in _engine(tmp_path, rows).build(period="2026-Q3").all_metrics()}
    assert m[ALLOW].value == want["conformance.allow"]
    assert m[RATE].value == _half_up_tenths(want["conformance.allow"], verdicts) / 10


def _delegation(tokens: list[dict]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=tokens)),
                        base_url="http://t")


def test_one_naive_expires_at_makes_that_metric_unavailable_and_the_pack_is_built():
    now = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
    good = {"token_id": "t1", "agent_id": "a", "revoked": False, "expires_at": (now + timedelta(days=3)).isoformat()}
    naive = {"token_id": "t2", "agent_id": "a", "revoked": False, "expires_at": "2026-09-05T12:00:00"}
    pack = PackEngine(delegation=_delegation([good, naive])).build(now=now)
    m = {x.name: x for x in pack.all_metrics()}
    assert m[EXPIRING].status == "unavailable" and "could not be computed" in (m[EXPIRING].note or "")
    assert m[ISSUED].status == "ok"                                   # the other token figures stand


def test_the_engine_has_no_float_round_left_in_the_rate():
    src = Path(engine_module.__file__).read_text(encoding="utf-8")
    assert "pct = round(" not in src and "pct = conformance_percent(" in src


# ---- the input contract (C-555, reviewer C-543 F-C543-2) -----------------------------------------------------------

@pytest.mark.parametrize("a,b", [(1.5, 16), (1, 16.0), ("1", 16), (1, "16"), (None, 3), (True, 3), (1, True), (False, 0)])
def test_a_non_int_is_a_type_error(a, b):
    with pytest.raises(TypeError):
        conformance_percent(a, b)


@pytest.mark.parametrize("a,b", [(-1, 16), (1, -16), (-1, -16), (17, 16), (1, 0), (0, -1)])
def test_a_negative_or_allows_above_total_is_a_value_error(a, b):
    with pytest.raises(ValueError):
        conformance_percent(a, b)


def test_the_boundary_inputs_still_answer():
    assert conformance_percent(0, 0) is None and conformance_percent(0, 1) == 0.0
    assert conformance_percent(16, 16) == 100.0 and conformance_percent(1, 16) == 6.3


def test_the_readme_documents_the_rounding_and_the_contract():
    text = " ".join((Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8").split())  # line breaks are not wording
    for needle in ("rounded **half up** to one decimal", "6.25", "**6.3**", "31.25", "**31.3**", "18.75",
                   "18.75 and printed 18.8 both ways",
                   "0.1 higher than a pack generated before the change", "non-negative integers with `allows <= total`"):
        assert needle in text, needle
