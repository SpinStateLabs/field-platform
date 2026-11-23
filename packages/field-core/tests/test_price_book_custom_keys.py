"""S7-1: a custom price book's keys are matched the way a model id is looked up.

`PriceBook.price_for` looked up `prices.get(normalize_model(model))`, but the keys of a FIELD_PRICE_BOOK file were used
verbatim, so a book keyed 'claude-haiku-4.5', 'Claude-Sonnet-5' or 'claude_opus_4_8' never matched: the model was
unpriced and the spend-governor opened usage:unpriced escalations. Keys are normalised at construction (two keys that
normalise to one id are refused) and the dated-suffix fallback also resolves against the book's own keys."""

import json

import pytest
from pydantic import ValidationError

from field_core.pricing import DEFAULT_BOOK, DEFAULT_PRICES, ModelPrice, PriceBook, load_price_book


def mp(n):
    return ModelPrice(input_units=n, output_units=n * 5)


@pytest.mark.parametrize("key, model", [
    ("claude-haiku-4.5", "claude-haiku-4-5"),
    ("Claude-Sonnet-5", "claude-sonnet-5"),
    ("claude_opus_4_8", "claude-opus-4-8"),
    ("claude-opus-4.8", "Claude_Opus_4.8"),
])
def test_a_custom_key_in_another_spelling_prices_the_matching_model(key, model):
    book = PriceBook(prices={key: mp(7)})
    assert book.is_priced(model) and book.price_for(model) == mp(7)
    assert book.cost_units(model, 10, 10) == 10 * 7 + 10 * 35


def test_a_book_loaded_from_a_file_normalises_its_keys(tmp_path):
    path = tmp_path / "book.json"
    path.write_text(json.dumps({"book_id": "acme", "source": "msa", "prices": {
        "claude-haiku-4.5": {"input_units": 3, "output_units": 15}}}), encoding="utf-8")
    book = load_price_book(str(path))
    assert list(book.prices) == ["claude-haiku-4-5"]
    assert book.cost_units("claude-haiku-4-5-20251001", 1, 1) == 3 + 15   # and the dated id of it


def test_two_keys_that_normalise_to_one_id_are_refused():
    with pytest.raises(ValidationError, match="same model"):
        PriceBook(prices={"claude-haiku-4.5": mp(1), "claude-haiku-4-5": mp(2)})


def test_a_dated_id_of_a_custom_only_model_resolves_to_the_books_own_key():
    book = PriceBook(prices={"acme-1": mp(9)})
    assert book.price_for("acme-1-20260101") == mp(9)
    assert book.price_for("ACME_1") == mp(9)
    assert book.price_for("acme-2-20260101") is None
    assert book.price_for("acme-1-2026") is None            # not an 8-digit date


def test_an_exact_dated_key_in_the_book_wins_over_its_base():
    book = PriceBook(prices={"acme-1": mp(9), "acme-1-20260101": mp(4)})
    assert book.price_for("acme-1-20260101") == mp(4)
    assert book.price_for("acme-1-20260202") == mp(9)


def test_the_default_book_is_unchanged():
    assert DEFAULT_BOOK.prices == DEFAULT_PRICES
    assert list(DEFAULT_BOOK.prices) == list(DEFAULT_PRICES)
    assert DEFAULT_BOOK.price_for("claude-haiku-4-5-20251001") == DEFAULT_PRICES["claude-haiku-4-5"]
    assert DEFAULT_BOOK.price_for("haiku-4.5") == DEFAULT_PRICES["claude-haiku-4-5"]
    assert DEFAULT_BOOK.price_for("claude-unknown-1") is None
