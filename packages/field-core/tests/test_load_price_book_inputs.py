"""S10-6: ``load_price_book`` and ``PriceBook.cost_units`` on hostile inputs.

A BOM file (Windows PowerShell 5.1 writes one) loads; a whitespace-only FIELD_PRICE_BOOK is unset; a missing file, bad
bytes, bad JSON, a top level that is not an object, a schema-refused book and an EMPTY price list are each a ValueError with
a fixed phrase and never file text (an empty price list would record every model unpriced and open a usage:unpriced
escalation on each use). ``cost_units`` refuses a negative, bool or non-int count (a negative cost would LOWER spend).
Every value is made up."""
from __future__ import annotations

import json

import pytest

from field_core.pricing import DEFAULT_BOOK, ModelPrice, PriceBook, load_price_book

MARK = "MARKER-1d7e"
BOOK = {"book_id": "contract-1", "source": "operator contract",
        "prices": {"claude-test-1": {"input_units": 3, "output_units": 7, "cache_read_units": 1}}}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("FIELD_PRICE_BOOK", raising=False)


def write(tmp_path, content: bytes, name="book.json"):
    p = tmp_path / name
    p.write_bytes(content)
    return p


# -- loading -----------------------------------------------------------------------------------------------------------
def test_a_valid_file_loads(tmp_path):
    book = load_price_book(str(write(tmp_path, json.dumps(BOOK).encode())))
    assert book.book_id == "contract-1" and book.prices["claude-test-1"].input_units == 3


def test_a_bom_file_loads(tmp_path):
    book = load_price_book(str(write(tmp_path, b"\xef\xbb\xbf" + json.dumps(BOOK).encode())))
    assert book.book_id == "contract-1"


def test_the_env_variable_is_used_when_no_path_is_given(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_PRICE_BOOK", str(write(tmp_path, json.dumps(BOOK).encode())))
    assert load_price_book().book_id == "contract-1"


def test_an_explicit_path_wins_over_the_env_variable(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_PRICE_BOOK", str(tmp_path / "absent.json"))
    assert load_price_book(str(write(tmp_path, json.dumps(BOOK).encode()))).book_id == "contract-1"


@pytest.mark.parametrize("blank", ["", " ", "  \t\n "], ids=repr)
def test_a_blank_or_whitespace_env_variable_is_unset(monkeypatch, blank):
    monkeypatch.setenv("FIELD_PRICE_BOOK", blank)
    assert load_price_book() is DEFAULT_BOOK


def test_a_path_with_surrounding_whitespace_in_the_env_variable_is_stripped(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_PRICE_BOOK", f"  {write(tmp_path, json.dumps(BOOK).encode())}  ")
    assert load_price_book().book_id == "contract-1"


def test_nothing_set_is_the_default_book():
    assert load_price_book() is DEFAULT_BOOK and load_price_book(None) is DEFAULT_BOOK


def test_a_book_without_a_prices_key_keeps_the_default_prices(tmp_path):
    book = load_price_book(str(write(tmp_path, json.dumps({"book_id": "only-an-id"}).encode())))
    assert book.book_id == "only-an-id" and book.prices


# -- refusals ----------------------------------------------------------------------------------------------------------
REFUSALS = [
    ("missing", None, "cannot be read (FileNotFoundError)"),
    ("not-utf8", b"\xff\xfe\x00bad", "not UTF-8 text"),
    ("bad-json", b'{"prices": ' + MARK.encode(), "not valid JSON"),
    ("empty-file", b"", "not valid JSON"),
    ("list", json.dumps([MARK]).encode(), "must be a JSON object"),
    ("string", json.dumps(MARK).encode(), "must be a JSON object"),
    ("null", b"null", "must be a JSON object"),
    ("unknown-key", json.dumps({"book_id": "x", MARK: 1}).encode(), "its fields do not match the schema"),
    ("bad-price", json.dumps({"prices": {"m": {"input_units": -1, "output_units": 1}}}).encode(),
     "its fields do not match the schema"),
    ("string-price", json.dumps({"prices": {"m": {"input_units": MARK, "output_units": 1}}}).encode(),
     "its fields do not match the schema"),
    ("empty-prices", json.dumps({"book_id": "x", "prices": {}}).encode(), "lists no prices"),
]


@pytest.mark.parametrize("name,content,expect", REFUSALS, ids=[r[0] for r in REFUSALS])
def test_an_unusable_book_is_a_fixed_phrase_value_error_with_no_file_text(tmp_path, name, content, expect):
    path = tmp_path / "absent.json" if content is None else write(tmp_path, content)
    with pytest.raises(ValueError) as exc:
        load_price_book(str(path))
    assert expect in str(exc.value)
    assert MARK not in str(exc.value) and str(path) not in str(exc.value)
    assert exc.value.__cause__ is None and (exc.value.__context__ is None or exc.value.__suppress_context__)


def test_a_directory_as_the_path_is_a_value_error_naming_the_class(tmp_path):
    with pytest.raises(ValueError, match=r"cannot be read \((IsADirectoryError|PermissionError)\)"):
        load_price_book(str(tmp_path))


def test_the_env_path_is_refused_the_same_way(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_PRICE_BOOK", str(write(tmp_path, b'{"prices": {}}')))
    with pytest.raises(ValueError, match="lists no prices"):
        load_price_book()


# -- cost_units --------------------------------------------------------------------------------------------------------
BOOK_OBJ = PriceBook(prices={"m": ModelPrice(input_units=3, output_units=7, cache_read_units=1)})


def test_cost_units_is_exact_for_valid_counts_and_none_when_unpriced():
    assert BOOK_OBJ.cost_units("m", 10, 20, 5) == 10 * 3 + 20 * 7 + 5 * 1
    assert BOOK_OBJ.cost_units("m", 0, 0) == 0
    assert BOOK_OBJ.cost_units("unknown", 10, 20) is None


@pytest.mark.parametrize("args", [(-1, 0, 0), (0, -1, 0), (0, 0, -1), (True, 0, 0), (0, False, 0), (0, 0, True),
                                  (1.5, 0, 0), ("3", 0, 0), (None, 0, 0), (float("nan"), 0, 0)], ids=repr)
def test_cost_units_refuses_a_negative_bool_or_non_int_count(args):
    with pytest.raises(ValueError, match="non-negative whole number"):
        BOOK_OBJ.cost_units("m", *args)


def test_a_bad_count_is_refused_even_for_an_unpriced_model():
    with pytest.raises(ValueError):
        BOOK_OBJ.cost_units("unknown", -1, 0)
