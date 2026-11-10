"""S10-3: ``internal_secret_problem()`` named directly, one case per branch. It returns fixed text (never a secret or a
hash) when the internal-secret setup cannot work or adds nothing, and ``install_routes`` stops the service at start on it.
New: BOTH forms set and the hash is not the sha256 of the value. The request check needs both to match, so such a pair
used to leave /operator/verify-hash and /operator/rotation-state answering 404 to every caller, the "route silently dead"
case install-time checking exists to prevent. Every value is made up."""
from __future__ import annotations

import hashlib
import os

import pytest
from fastapi import FastAPI

from field_core import authn
from field_core import operator_health as oh

SECRET = "tkv-s103-internal-0123456789abcdef"
HASH = hashlib.sha256(SECRET.encode()).hexdigest()
OTHER = "tkv-s103-another-secret-0123456789"
PERIMETER = "tkv-s103-perimeter-0123456789ab"
READ = "tkv-s103-read-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for name in (oh.ENV_INTERNAL_SECRET, oh.ENV_INTERNAL_SECRET_SHA256, authn.ENV_VAR, oh.ENV_READ_KEY):
        monkeypatch.delenv(name, raising=False)
    for name in [k for k in os.environ if k.startswith(oh.READ_KEY_PREFIX)]:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def never_carries(text, *values):
    assert isinstance(text, str) and text
    for v in values:
        assert v not in text


# -- no problem --------------------------------------------------------------------------------------------------------
def test_nothing_set_is_no_problem():
    assert oh.internal_secret_problem() is None


def test_each_form_alone_is_no_problem(_env):
    _env.setenv(oh.ENV_INTERNAL_SECRET, SECRET)
    assert oh.internal_secret_problem() is None
    _env.delenv(oh.ENV_INTERNAL_SECRET)
    _env.setenv(oh.ENV_INTERNAL_SECRET_SHA256, HASH)
    assert oh.internal_secret_problem() is None


def test_a_matching_pair_is_no_problem(_env):
    _env.setenv(oh.ENV_INTERNAL_SECRET, SECRET)
    _env.setenv(oh.ENV_INTERNAL_SECRET_SHA256, HASH)
    assert oh.internal_secret_problem() is None


# -- each existing branch ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bad_hash", ["not-hex", "ab" * 31, "zz" * 32, ("AB" * 32), "   "], ids=repr)
def test_a_hash_that_is_not_64_lower_case_hex(_env, bad_hash):
    _env.setenv(oh.ENV_INTERNAL_SECRET_SHA256, bad_hash)
    text = oh.internal_secret_problem()
    assert "64 lower-case hex" in text
    if bad_hash.strip():
        never_carries(text, bad_hash)


def test_the_hash_of_the_empty_string(_env):
    empty = hashlib.sha256(b"").hexdigest()
    _env.setenv(oh.ENV_INTERNAL_SECRET_SHA256, empty)
    assert "hash of the empty string" in oh.internal_secret_problem()
    never_carries(oh.internal_secret_problem(), empty)


@pytest.mark.parametrize("value", ["has a space", "tab\there", "line\nbreak", "café-0123456789abcdef"], ids=repr)
def test_a_value_that_is_not_printable_ascii_without_whitespace(_env, value):
    _env.setenv(oh.ENV_INTERNAL_SECRET, value)
    assert "printable ASCII" in oh.internal_secret_problem()
    never_carries(oh.internal_secret_problem(), value)


def test_a_value_over_the_length_limit_and_one_at_it(_env):
    _env.setenv(oh.ENV_INTERNAL_SECRET, "a" * oh.MAX_INTERNAL_SECRET_LEN)
    assert oh.internal_secret_problem() is None
    _env.setenv(oh.ENV_INTERNAL_SECRET, "a" * (oh.MAX_INTERNAL_SECRET_LEN + 1))
    assert "longer than" in oh.internal_secret_problem()
    never_carries(oh.internal_secret_problem(), "a" * 20)


def test_a_value_equal_to_the_perimeter_secret(_env):
    _env.setenv(authn.ENV_VAR, PERIMETER)
    _env.setenv(oh.ENV_INTERNAL_SECRET, PERIMETER)
    assert "equals the perimeter secret" in oh.internal_secret_problem()
    never_carries(oh.internal_secret_problem(), PERIMETER)


def test_a_hash_of_the_perimeter_secret(_env):
    _env.setenv(authn.ENV_VAR, PERIMETER)
    h = hashlib.sha256(PERIMETER.encode()).hexdigest()
    _env.setenv(oh.ENV_INTERNAL_SECRET_SHA256, h)
    assert "equals the perimeter secret" in oh.internal_secret_problem()
    never_carries(oh.internal_secret_problem(), PERIMETER, h)


def test_a_value_or_hash_equal_to_a_read_tier_key(_env):
    _env.setenv(oh.READ_KEY_PREFIX + "REGISTRY", READ)
    _env.setenv(oh.ENV_INTERNAL_SECRET, READ)
    assert "equals the perimeter secret or a read key" in oh.internal_secret_problem()
    _env.delenv(oh.ENV_INTERNAL_SECRET)
    h = hashlib.sha256(READ.encode()).hexdigest()
    _env.setenv(oh.ENV_INTERNAL_SECRET_SHA256, h)
    assert "equals the perimeter secret or a read key" in oh.internal_secret_problem()
    never_carries(oh.internal_secret_problem(), READ, h)


# -- the new branch ----------------------------------------------------------------------------------------------------
def test_a_hash_that_is_not_the_sha256_of_the_value_is_a_problem(_env):
    other_hash = hashlib.sha256(OTHER.encode()).hexdigest()
    _env.setenv(oh.ENV_INTERNAL_SECRET_SHA256, other_hash)
    _env.setenv(oh.ENV_INTERNAL_SECRET, SECRET)
    text = oh.internal_secret_problem()
    assert text and "not the sha256 of" in text and "dead" in text
    never_carries(text, SECRET, OTHER, other_hash, HASH)


def test_the_mismatched_pair_stops_the_service_at_install(_env):
    _env.setenv(oh.ENV_INTERNAL_SECRET_SHA256, hashlib.sha256(OTHER.encode()).hexdigest())
    _env.setenv(oh.ENV_INTERNAL_SECRET, SECRET)
    app = FastAPI()
    authn.install(app)
    with pytest.raises(ValueError) as exc:
        oh.install(app, ledger_getter=lambda a: None)
    never_carries(str(exc.value), SECRET, OTHER)


def test_a_matching_pair_installs(_env):
    _env.setenv(oh.ENV_INTERNAL_SECRET_SHA256, HASH)
    _env.setenv(oh.ENV_INTERNAL_SECRET, SECRET)
    app = FastAPI()
    authn.install(app)
    oh.install(app, ledger_getter=lambda a: None)


def test_the_request_time_check_still_refuses_a_pair_set_after_install(_env):
    """Defence in depth: the pair can change after start; the request check needs both to match."""
    _env.setenv(oh.ENV_INTERNAL_SECRET_SHA256, HASH)
    assert oh.internal_request_allowed(SECRET) is True
    _env.setenv(oh.ENV_INTERNAL_SECRET, OTHER)
    assert oh.internal_request_allowed(SECRET) is False and oh.internal_request_allowed(OTHER) is False
