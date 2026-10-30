"""C-474 (reviewer C-42 F-C42-1): the dollar table of docs/agent-estate.md closes on its own displayed values.

The cost column is recomputed from the table's token counts and the price book beside it, in integer arithmetic (a
price in dollars per million tokens times tokens is micro-dollars), cents rounded half up; the estate total is the sum
of the displayed rows; the worked example states the same rounding."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "docs" / "agent-estate.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def _prices(text: str) -> dict[str, tuple[int, int]]:
    return {m.group(1): (int(m.group(2)), int(m.group(3)))
            for m in re.finditer(r"^\| (claude-[a-z0-9-]+) \| \$(\d+) \| \$(\d+) \|$", text, re.M)}


def _rows(text: str) -> list[tuple[str, str, int, int, Decimal]]:
    out = []
    for m in re.finditer(r"^\| (\S+-agent) \([^|]*\) \| \**(claude-[a-z0-9-]+)\** \| ([\d,]+) / ([\d,]+) \| \*\*\$([\d.]+)\*\*", text, re.M):
        out.append((m.group(1), m.group(2), int(m.group(3).replace(",", "")), int(m.group(4).replace(",", "")), Decimal(m.group(5))))
    return out


def cents(model_prices: tuple[int, int], tokens_in: int, tokens_out: int) -> Decimal:
    micro = tokens_in * model_prices[0] + tokens_out * model_prices[1]          # millionths of a dollar
    return (Decimal(micro) / Decimal(1_000_000)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def test_the_table_has_three_agents_and_the_price_book_has_three_models():
    text = _text()
    assert len(_rows(text)) == 3 and len(_prices(text)) == 3


def test_every_cost_in_the_table_is_the_recomputed_cost_rounded_half_up():
    text, prices = _text(), _prices(_text())
    for name, model, tin, tout, shown in _rows(text):
        assert shown == cents(prices[model], tin, tout), (name, shown, cents(prices[model], tin, tout))


def test_the_estate_total_is_the_sum_of_the_displayed_rows_and_the_token_totals_add_up():
    text = _text()
    rows = _rows(text)
    m = re.search(r"\*\*Estate total\*\* \| — \| \*\*([\d,]+) / ([\d,]+)\*\* \(([\d,]+)\) \| \*\*\$([\d.]+)\*\*", text)
    assert m, "the estate total row moved or changed shape"
    tin, tout, both, total = int(m[1].replace(",", "")), int(m[2].replace(",", "")), int(m[3].replace(",", "")), Decimal(m[4])
    assert tin == sum(r[2] for r in rows) and tout == sum(r[3] for r in rows) and both == tin + tout
    assert total == sum(r[4] for r in rows)


def test_the_worked_example_states_the_same_rounding_and_the_table_value():
    text, prices = _text(), _prices(_text())
    inv = [r for r in _rows(text) if r[0] == "invoicing-agent"][0]
    assert "$0.30 + $0.375 = **$0.675 → $0.68**" in text and "half up" in text
    assert inv[4] == Decimal("0.68") == cents(prices[inv[1]], inv[2], inv[3])


def test_the_old_inconsistent_rounding_is_gone():
    text = _text()
    assert "$0.675 → $0.67**" not in text and "| **$0.67** |" not in text


def test_the_cents_helper_rounds_half_up_not_half_even_or_down():
    assert cents((5, 25), 60_000, 15_000) == Decimal("0.68")                     # 0.675 exactly
    assert cents((1, 5), 80_000, 12_000) == Decimal("0.14")                      # 0.140 exactly
    assert cents((1, 1), 5, 0) == Decimal("0.00") and cents((1, 1), 5_000, 0) == Decimal("0.01")   # 0.005 -> 0.01
