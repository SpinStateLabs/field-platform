"""Price book + cost engine tests. Costs must be exact integers; unpriced
models must be flagged, never guessed."""

import pytest

from field_core.pricing import (
    CENT_UNITS,
    DEFAULT_BOOK,
    USD_UNITS,
    ModelPrice,
    PriceBook,
    normalize_model,
    units_to_cents,
)


def test_official_list_prices_transcribed():
    # Opus 4.8: $5/MTok in, $25/MTok out → 50 / 250 units per token.
    opus = DEFAULT_BOOK.price_for("claude-opus-4-8")
    assert (opus.input_units, opus.output_units, opus.cache_read_units) == (50, 250, 5)
    haiku = DEFAULT_BOOK.price_for("claude-haiku-4-5")
    assert (haiku.input_units, haiku.output_units) == (10, 50)
    assert DEFAULT_BOOK.price_for("claude-sonnet-5").input_units == 20
    assert DEFAULT_BOOK.price_for("claude-fable-5").output_units == 500


def test_cost_is_exact_integer():
    # 240 input + 118 output on Opus 4.8:
    # 240*50 + 118*250 = 12000 + 29500 = 41500 units = $0.00415.
    cost = DEFAULT_BOOK.cost_units("claude-opus-4-8", 240, 118)
    assert cost == 41_500
    assert cost / USD_UNITS == pytest.approx(0.00415)


def test_one_million_opus_input_is_five_dollars():
    cost = DEFAULT_BOOK.cost_units("claude-opus-4-8", 1_000_000, 0)
    assert cost == 5 * USD_UNITS  # exactly $5.00


def test_cache_read_is_tenth_of_input():
    got = DEFAULT_BOOK.cost_units("claude-opus-4-8", 0, 0, cache_read_tokens=1000)
    assert got == 1000 * 5  # 5 units/token


def test_model_aliases_normalize():
    assert normalize_model("Opus") == "claude-opus-4-8"
    assert normalize_model("claude-opus-4.8") == "claude-opus-4-8"
    assert normalize_model("Haiku 4.5") == "claude-haiku-4-5"


def test_unpriced_model_returns_none_not_a_guess():
    assert DEFAULT_BOOK.price_for("gpt-4o") is None
    assert DEFAULT_BOOK.is_priced("gpt-4o") is False
    assert DEFAULT_BOOK.cost_units("some-unknown-model", 1000, 1000) is None


def test_operator_override_book():
    book = PriceBook(
        book_id="acme-negotiated-2026",
        source="ACME MSA Schedule B",
        prices={"claude-opus-4-8": ModelPrice(input_units=30, output_units=150)},
    )
    assert book.cost_units("claude-opus-4-8", 1000, 1000) == 30_000 + 150_000
    assert book.price_for("claude-haiku-4-5") is None  # not in the override


def test_units_to_cents_floors():
    assert units_to_cents(CENT_UNITS - 1) == 0
    assert units_to_cents(CENT_UNITS) == 1
    assert units_to_cents(41_500) == 0        # $0.00415 → 0 whole cents
    assert units_to_cents(5 * USD_UNITS) == 500



def test_dated_model_ids_price_as_their_base_model():
    """The API answers with a DATED id (claude-haiku-4-5-20251001); the price
    book keys the undated one. Found live 2026-09-14: an unpriced first call
    opened a usage:unpriced escalation and the enforcing gateway refused the
    agent's next call. A dated id must price as its base; an unknown dated id
    must stay unpriced (never a silent guess)."""
    from field_core.pricing import PriceBook, normalize_model

    book = PriceBook()
    assert normalize_model("claude-haiku-4-5-20251001") == "claude-haiku-4-5"
    assert normalize_model("claude-sonnet-5-20260301") == "claude-sonnet-5"
    assert normalize_model("Claude-Opus-4.8-20260101") == "claude-opus-4-8"
    assert book.is_priced("claude-haiku-4-5-20251001")
    assert book.price_for("claude-haiku-4-5-20251001") == book.price_for("claude-haiku-4-5")
    # an unknown family stays unknown, dated or not; a bare date is not a model
    assert normalize_model("claude-nova-9-20260101") == "claude-nova-9-20260101"
    assert not book.is_priced("claude-nova-9-20260101")
    assert not book.is_priced("20251001")
