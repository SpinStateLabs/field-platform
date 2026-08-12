"""Model price book + deterministic token-cost engine (FIELD letter E).

FIELD calculates the dollar cost of an agent's token usage from the number
of tokens and the model used, so token consumption flows into the same
spend governance as any other cost — and so rogue usage becomes visible.

HONESTY / ANTI-FABRICATION
--------------------------
The default prices below are Anthropic's **public list prices** for the
first-party Claude API, transcribed from the official pricing page
(https://platform.claude.com/docs/en/about-claude/pricing) on the dated
snapshot in ``PRICE_BOOK_SOURCE``. They are NOT invented and NOT a quote of
your negotiated rate. Override them with your actual contract prices via
``load_price_book`` (a JSON file / dict). A model with no price is
``unpriced`` — its usage is still recorded, but cost is flagged and the use
of an unpriced model is itself a rogue signal (you cannot govern the cost of
a model you never priced). Every cost figure carries the price-book id it
was computed under, mirroring the platform's "no number without a source"
discipline.

EXACT INTEGER ACCOUNTING
------------------------
Money is never a float here. The base unit is **1e-7 USD** ("price units",
``USD_UNITS`` per dollar). List prices in $/MTok convert to an integer
number of price units per token (e.g. $5/MTok = 50 units/token; the 0.1x
cache-read rate = 5 units/token), so per-token cost is exact integer
arithmetic all the way to the cap comparison.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# 1 price unit = 1e-7 USD. 10,000,000 units = $1.00; 100,000 units = 1 cent.
USD_UNITS = 10_000_000
CENT_UNITS = 100_000

PRICE_BOOK_SOURCE = (
    "Anthropic public list price, first-party Claude API, "
    "platform.claude.com/docs/en/about-claude/pricing (retrieved 2026-08-10)"
)
PRICE_BOOK_ID = "anthropic-list-2026-08-10"


class ModelPrice(BaseModel):
    """Per-token price in price units (1e-7 USD). Integers, exact."""

    model_config = ConfigDict(extra="forbid")

    input_units: int = Field(ge=0)
    output_units: int = Field(ge=0)
    cache_read_units: int = Field(ge=0, default=0)


def _p(in_dollars_mtok: int | float, out_dollars_mtok: int | float,
       cache_read_units: int) -> ModelPrice:
    # $X/MTok == X*10 units/token (units are 1e-7 USD).
    return ModelPrice(
        input_units=round(in_dollars_mtok * 10),
        output_units=round(out_dollars_mtok * 10),
        cache_read_units=cache_read_units,
    )


# Current (non-retired) first-party models, official base prices.
# cache_read = 0.1x base input (also integer in units).
DEFAULT_PRICES: dict[str, ModelPrice] = {
    "claude-fable-5":   _p(10, 50, 10),
    "claude-mythos-5":  _p(10, 50, 10),
    "claude-opus-5":    _p(5, 25, 5),
    "claude-opus-4-8":  _p(5, 25, 5),
    "claude-opus-4-7":  _p(5, 25, 5),
    "claude-opus-4-6":  _p(5, 25, 5),
    "claude-opus-4-5":  _p(5, 25, 5),
    "claude-sonnet-5":  _p(2, 10, 2),
    "claude-sonnet-4-6": _p(3, 15, 3),
    "claude-sonnet-4-5": _p(3, 15, 3),
    "claude-haiku-4-5": _p(1, 5, 1),
}

# Friendly aliases operators commonly report; normalized to canonical ids.
_ALIASES = {
    "opus": "claude-opus-4-8", "opus-4.8": "claude-opus-4-8",
    "claude-opus-4.8": "claude-opus-4-8", "opus-5": "claude-opus-5",
    "sonnet": "claude-sonnet-5", "sonnet-5": "claude-sonnet-5",
    "haiku": "claude-haiku-4-5", "haiku-4.5": "claude-haiku-4-5",
    "fable": "claude-fable-5", "fable-5": "claude-fable-5",
}


def normalize_model(model: str) -> str:
    key = (model or "").strip().lower()
    for ch in (".", "_", " ", "/"):
        key = key.replace(ch, "-")
    while "--" in key:
        key = key.replace("--", "-")
    if key in DEFAULT_PRICES:
        return key
    if key in _ALIASES:
        return _ALIASES[key]
    # bare family+version without the "claude-" prefix (e.g. "haiku-4-5")
    prefixed = f"claude-{key}"
    if prefixed in DEFAULT_PRICES:
        return prefixed
    return key


class PriceBook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: str = PRICE_BOOK_ID
    source: str = PRICE_BOOK_SOURCE
    prices: dict[str, ModelPrice] = Field(default_factory=lambda: dict(DEFAULT_PRICES))

    def price_for(self, model: str) -> ModelPrice | None:
        return self.prices.get(normalize_model(model))

    def is_priced(self, model: str) -> bool:
        return self.price_for(model) is not None

    def cost_units(
        self, model: str, input_tokens: int, output_tokens: int,
        cache_read_tokens: int = 0,
    ) -> int | None:
        """Exact integer cost in price units (1e-7 USD). None if unpriced."""
        price = self.price_for(model)
        if price is None:
            return None
        return (
            input_tokens * price.input_units
            + output_tokens * price.output_units
            + cache_read_tokens * price.cache_read_units
        )


DEFAULT_BOOK = PriceBook()


def load_price_book(path: str | None = None) -> PriceBook:
    """Load an operator price book from ``path`` or ``FIELD_PRICE_BOOK`` env.

    JSON shape: {"book_id": "...", "source": "...", "prices":
    {"model-id": {"input_units": N, "output_units": N,
    "cache_read_units": N}}}. Falls back to the dated Anthropic list book.
    """
    path = path or os.environ.get("FIELD_PRICE_BOOK")
    if not path:
        return DEFAULT_BOOK
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return PriceBook.model_validate(data)


# -- money display helpers (never used in a cap comparison) -----------------

def units_to_usd_str(units: int) -> str:
    whole, frac = divmod(units, USD_UNITS)
    return f"${whole}.{frac // (USD_UNITS // 100):02d}" if units >= CENT_UNITS \
        else f"${units / USD_UNITS:.6f}".rstrip("0").rstrip(".")


def units_to_cents(units: int) -> int:
    """Floor to whole cents — for adding token cost to a cents-denominated cap."""
    return units // CENT_UNITS
