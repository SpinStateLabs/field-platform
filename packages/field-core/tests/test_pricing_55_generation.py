"""The Claude 5.5 generation + Fable 5.1 / Mythos 5.1 in the default price
book (P30 item 1).

Source: https://platform.claude.com/docs/en/about-claude/pricing, "Model
pricing" table, fetched 2026-10-27. Every expectation below is exact integer
arithmetic in price units (1e-7 USD); the official $/MTok figures are held as
``Fraction`` so the comparison with the book never touches a float.
"""

from fractions import Fraction as F
from math import ceil

import pytest

from field_core.pricing import (
    DEFAULT_BOOK,
    DEFAULT_PRICES,
    PRICE_BOOK_ID,
    PRICE_BOOK_SOURCE,
    USD_UNITS,
    ModelPrice,
    PriceBook,
    load_price_book,
    normalize_model,
)

#: $ per MTok as published 2026-10-27: (base input, output, cache hits).
OFFICIAL_2026_10_27 = {
    "claude-opus-5-5": (F(4), F(20), F("0.20")),
    "claude-sonnet-5-5": (F(2), F(10), F("0.10")),
    "claude-fable-5-1": (F(10), F(50), F("0.25")),
    "claude-mythos-5-1": (F(10), F(50), F("0.25")),
    # the over-100,000-token-prompt row (the upper bound; see pricing.py)
    "claude-haiku-5-5": (F("0.50"), F("2.50"), F("0.05")),
}
#: Haiku 5.5's lower row (prompts up to 100,000 tokens), same source.
HAIKU_55_UP_TO_100K = (F("0.10"), F("0.50"), F("0.01"))


def _units_per_token(dollars_per_mtok: F) -> F:
    # $1/MTok = 1e-6 $/token = 10 units/token (1 unit = 1e-7 USD)
    return dollars_per_mtok * 10


def test_the_whole_default_book_is_pinned():
    """Every model and every rate, existing entries included: a change to ANY
    price (or a dropped model) turns this red. The 11 pre-5.5 entries are the
    2026-08-10 transcription, re-checked against the 2026-10-27 page."""
    got = {m: (p.input_units, p.output_units, p.cache_read_units)
           for m, p in DEFAULT_PRICES.items()}
    assert got == {
        "claude-fable-5-1": (100, 500, 3),
        "claude-mythos-5-1": (100, 500, 3),
        "claude-opus-5-5": (40, 200, 2),
        "claude-sonnet-5-5": (20, 100, 1),
        "claude-haiku-5-5": (5, 25, 1),
        "claude-fable-5": (100, 500, 10),
        "claude-mythos-5": (100, 500, 10),
        "claude-opus-5": (50, 250, 5),
        "claude-opus-4-8": (50, 250, 5),
        "claude-opus-4-7": (50, 250, 5),
        "claude-opus-4-6": (50, 250, 5),
        "claude-opus-4-5": (50, 250, 5),
        "claude-sonnet-5": (20, 100, 2),
        "claude-sonnet-4-6": (30, 150, 3),
        "claude-sonnet-4-5": (30, 150, 3),
        "claude-haiku-4-5": (10, 50, 1),
    }


@pytest.mark.parametrize("model", sorted(OFFICIAL_2026_10_27))
def test_book_equals_the_official_rate_or_rounds_it_up(model):
    """A whole-unit official rate is transcribed exactly; a fractional one is
    the NEXT whole unit (never below the official rate, never a unit above)."""
    price = DEFAULT_BOOK.price_for(model)
    assert price is not None
    for book_units, official in zip(
        (price.input_units, price.output_units, price.cache_read_units),
        OFFICIAL_2026_10_27[model],
    ):
        exact = _units_per_token(official)
        assert book_units == ceil(exact)
        assert book_units >= exact
        assert book_units - exact < 1


def test_only_two_rates_are_rounded_and_both_up():
    rounded = sorted(
        (m, field)
        for m, rates in OFFICIAL_2026_10_27.items()
        for field, official in zip(("input", "output", "cache_read"), rates)
        if _units_per_token(official).denominator != 1
    )
    assert rounded == [("claude-fable-5-1", "cache_read"), ("claude-haiku-5-5", "cache_read"),
                       ("claude-mythos-5-1", "cache_read")]
    assert DEFAULT_BOOK.price_for("claude-fable-5-1").cache_read_units == 3   # official 2.5
    assert DEFAULT_BOOK.price_for("claude-mythos-5-1").cache_read_units == 3  # official 2.5
    assert DEFAULT_BOOK.price_for("claude-haiku-5-5").cache_read_units == 1   # official 0.5


def test_haiku_55_is_priced_at_an_upper_bound_for_every_request():
    """Usage arrives aggregated (per-session deltas), so the per-request
    prompt-length tier is unknowable here: every Haiku 5.5 rate in the book
    is >= both official rows."""
    price = DEFAULT_BOOK.price_for("claude-haiku-5-5")
    for book_units, low in zip(
        (price.input_units, price.output_units, price.cache_read_units),
        HAIKU_55_UP_TO_100K,
    ):
        assert book_units >= _units_per_token(low)
    # and exactly the over-100K row for input and output (5x the lower row)
    assert (price.input_units, price.output_units) == (5, 25)


def test_exact_costs_one_million_tokens_each_way():
    mtok = 1_000_000
    assert DEFAULT_BOOK.cost_units("claude-opus-5-5", mtok, 0) == 4 * USD_UNITS
    assert DEFAULT_BOOK.cost_units("claude-opus-5-5", 0, mtok) == 20 * USD_UNITS
    assert DEFAULT_BOOK.cost_units("claude-opus-5-5", 0, 0, mtok) == USD_UNITS // 5      # $0.20
    assert DEFAULT_BOOK.cost_units("claude-sonnet-5-5", mtok, 0) == 2 * USD_UNITS
    assert DEFAULT_BOOK.cost_units("claude-sonnet-5-5", 0, mtok) == 10 * USD_UNITS
    assert DEFAULT_BOOK.cost_units("claude-sonnet-5-5", 0, 0, mtok) == USD_UNITS // 10   # $0.10
    assert DEFAULT_BOOK.cost_units("claude-fable-5-1", mtok, 0) == 10 * USD_UNITS
    assert DEFAULT_BOOK.cost_units("claude-fable-5-1", 0, mtok) == 50 * USD_UNITS
    assert DEFAULT_BOOK.cost_units("claude-fable-5-1", 0, 0, mtok) == 3_000_000          # $0.30
    assert DEFAULT_BOOK.cost_units("claude-haiku-5-5", mtok, 0) == USD_UNITS // 2        # $0.50
    assert DEFAULT_BOOK.cost_units("claude-haiku-5-5", 0, mtok) == 25_000_000            # $2.50
    assert DEFAULT_BOOK.cost_units("claude-haiku-5-5", 0, 0, mtok) == USD_UNITS // 10    # $0.10


def test_exact_mixed_cost_per_model():
    # 1,234 input + 567 output + 8,900 cache-read tokens
    args = (1_234, 567, 8_900)
    assert DEFAULT_BOOK.cost_units("claude-opus-5-5", *args) == 1_234 * 40 + 567 * 200 + 8_900 * 2
    assert DEFAULT_BOOK.cost_units("claude-opus-5-5", *args) == 180_560
    assert DEFAULT_BOOK.cost_units("claude-sonnet-5-5", *args) == 90_280
    assert DEFAULT_BOOK.cost_units("claude-fable-5-1", *args) == 123_400 + 283_500 + 26_700
    assert DEFAULT_BOOK.cost_units("claude-haiku-5-5", *args) == 6_170 + 14_175 + 8_900
    for m in OFFICIAL_2026_10_27:
        assert isinstance(DEFAULT_BOOK.cost_units(m, *args), int)


@pytest.mark.parametrize("reported, canonical", [
    ("claude-sonnet-5-5", "claude-sonnet-5-5"),
    ("claude-sonnet-5.5", "claude-sonnet-5-5"),
    ("Claude Haiku 5.5", "claude-haiku-5-5"),
    ("haiku-5-5", "claude-haiku-5-5"),
    ("claude-opus-5-5-20261001", "claude-opus-5-5"),
    ("claude-fable-5-1-20260901", "claude-fable-5-1"),
    ("claude-mythos-5.1", "claude-mythos-5-1"),
])
def test_the_5_5_ids_the_api_and_operators_report_are_priced(reported, canonical):
    assert normalize_model(reported) == canonical
    assert DEFAULT_BOOK.is_priced(reported)
    assert DEFAULT_BOOK.price_for(reported) == DEFAULT_PRICES[canonical]


@pytest.mark.parametrize("model", [
    "claude-sonnet-9-9",            # unknown family member
    "claude-haiku-5-6",             # adjacent, unpublished version
    "claude-sonnet-5-5-preview",    # suffix that is not a date
    "gpt-4o",
])
def test_a_model_absent_from_the_book_still_fails_closed(model):
    assert DEFAULT_BOOK.price_for(model) is None
    assert DEFAULT_BOOK.cost_units(model, 1_000, 1_000, 1_000) is None


def test_an_operator_book_without_the_5_5_generation_leaves_it_unpriced(tmp_path):
    path = tmp_path / "book.json"
    path.write_text(
        '{"book_id": "acme-2026", "source": "ACME MSA", "prices": '
        '{"claude-opus-4-8": {"input_units": 30, "output_units": 150}}}',
        encoding="utf-8",
    )
    book = load_price_book(str(path))
    assert book.cost_units("claude-sonnet-5-5", 10, 10) is None
    assert not PriceBook(prices={"claude-opus-4-8": ModelPrice(input_units=1, output_units=1)}
                         ).is_priced("claude-haiku-5-5")


def test_book_id_and_source_name_the_page_and_the_fetch_date():
    assert PRICE_BOOK_ID == "anthropic-list-2026-10-27"
    assert DEFAULT_BOOK.book_id == PRICE_BOOK_ID
    assert "platform.claude.com/docs/en/about-claude/pricing" in PRICE_BOOK_SOURCE
    assert "2026-10-27" in PRICE_BOOK_SOURCE
