"""An internal-only secret for the two internal operator routes (C-801, Don ruling D-12; design note C-54).

``POST /operator/verify-hash`` and ``GET /operator/rotation-state`` answer only with the perimeter secret
(``x-field-auth``) today. With ``FIELD_INTERNAL_SECRET_SHA256`` (a hash: the verifier never holds the secret) or
``FIELD_INTERNAL_SECRET`` (the value) set, they also need ``x-field-internal``; a request without it gets the same
404 as a route that is off. Unset = unchanged. All values here are throwaway constants."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from field_core import authn
from field_core import operator_auth as oa
from field_core import operator_health as oh

PERIMETER = "tkv-c801-perimeter-0123456789"
INTERNAL = "tkv-c801-internal-0123456789abcdef"
INTERNAL_HASH = hashlib.sha256(INTERNAL.encode()).hexdigest()
H_INTERNAL = oh.INTERNAL_HEADER
BODY = json.dumps({"operator_id": "don", "key_sha256": "0" * 64})


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE,
              authn.ENV_VAR, oh.ENV_INTERNAL_SECRET, oh.ENV_INTERNAL_SECRET_SHA256):
        monkeypatch.delenv(n, raising=False)
    p = tmp_path / "operators.json"
    p.write_bytes(json.dumps({"format": 1, "operators": []}).encode())
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))          # LOG-ONLY: the routes exist
    monkeypatch.setenv(authn.ENV_VAR, PERIMETER)


def client() -> TestClient:
    app = FastAPI()
    authn.install(app)
    oh.install(app, ledger_getter=lambda a: None)
    return TestClient(app)


def state(c, internal=None, perimeter=PERIMETER):
    h = {authn.HEADER: perimeter} if perimeter else {}
    if internal is not None:
        h[H_INTERNAL] = internal
    return c.get(oh.ROTATION_STATE_PATH, headers=h)


def verify(c, internal=None, perimeter=PERIMETER):
    h = {authn.HEADER: perimeter} if perimeter else {}
    if internal is not None:
        h[H_INTERNAL] = internal
    return c.post(oh.VERIFY_HASH_PATH, content=BODY, headers=h)


# ------------------------------------------------------------ unset: unchanged

def test_with_no_internal_secret_the_perimeter_secret_alone_still_reaches_both_routes():
    c = client()
    assert state(c).status_code == 200
    assert verify(c).status_code != 404


# ------------------------------------------------------------ the hash form

@pytest.mark.parametrize("env", [oh.ENV_INTERNAL_SECRET_SHA256, oh.ENV_INTERNAL_SECRET])
def test_the_perimeter_secret_alone_is_refused_when_an_internal_secret_is_set(monkeypatch, env):
    monkeypatch.setenv(env, INTERNAL_HASH if env == oh.ENV_INTERNAL_SECRET_SHA256 else INTERNAL)
    c = client()
    assert state(c).status_code == 404
    assert verify(c).status_code == 404


@pytest.mark.parametrize("env", [oh.ENV_INTERNAL_SECRET_SHA256, oh.ENV_INTERNAL_SECRET])
def test_the_internal_secret_with_the_perimeter_secret_reaches_both_routes(monkeypatch, env):
    monkeypatch.setenv(env, INTERNAL_HASH if env == oh.ENV_INTERNAL_SECRET_SHA256 else INTERNAL)
    c = client()
    assert state(c, INTERNAL).status_code == 200
    assert verify(c, INTERNAL).status_code != 404


def test_a_wrong_empty_or_hash_valued_header_is_refused(monkeypatch):
    """The hash is not a credential: presenting the configured hash itself must not work."""
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, INTERNAL_HASH)
    c = client()
    for bad in ("", "wrong", INTERNAL + "x", INTERNAL_HASH, INTERNAL_HASH.upper()):
        assert state(c, bad).status_code == 404, bad
        assert verify(c, bad).status_code == 404, bad


def test_the_value_form_refuses_a_wrong_or_empty_header(monkeypatch):
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET, INTERNAL)
    c = client()
    for bad in ("", "wrong", INTERNAL[:-1], INTERNAL + "x"):
        assert state(c, bad).status_code == 404, bad
        assert verify(c, bad).status_code == 404, bad


def test_when_both_forms_are_set_the_header_must_satisfy_both(monkeypatch):
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, INTERNAL_HASH)
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET, "tkv-c801-a-different-value-0123")
    c = client()
    assert state(c, INTERNAL).status_code == 404
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET, INTERNAL)
    assert state(c, INTERNAL).status_code == 200


@pytest.mark.parametrize("bad_hash", ["not-hex", "ab" * 31, "zz" * 32, "   ", ("AB" * 32)])
def test_a_malformed_hash_is_refused_at_install(monkeypatch, bad_hash):
    """C-859 C3: a hash that can never match is a configuration error at start, not a silently dead route."""
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, bad_hash)
    with pytest.raises(ValueError) as exc:
        client()
    assert bad_hash.strip() not in str(exc.value) or not bad_hash.strip()


def test_a_malformed_hash_set_after_install_still_fails_closed(monkeypatch):
    c = client()
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, "not-hex")
    assert state(c, INTERNAL).status_code == 404
    assert verify(c, INTERNAL).status_code == 404


def test_an_internal_secret_equal_to_the_perimeter_secret_is_refused_at_install(monkeypatch):
    """C-859 C2: a second secret that is the first one adds nothing."""
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET, PERIMETER)
    with pytest.raises(ValueError):
        client()
    monkeypatch.delenv(oh.ENV_INTERNAL_SECRET)
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, hashlib.sha256(PERIMETER.encode()).hexdigest())
    with pytest.raises(ValueError):
        client()


def test_the_install_error_never_holds_a_secret(monkeypatch):
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET, PERIMETER)
    with pytest.raises(ValueError) as exc:
        client()
    for i in range(0, len(PERIMETER) - 7, 4):
        assert PERIMETER[i:i + 8] not in str(exc.value)


# ------------------------------------------------------------ what the refusal looks like

def test_a_refusal_is_the_same_404_as_a_route_that_is_off(monkeypatch, tmp_path):
    c = client()
    registry = oa.registry_path()
    monkeypatch.delenv(oa.ENV_REGISTRY)                  # operator layer off: the routes answer 404 as absent
    off = state(c)
    assert off.status_code == 404
    monkeypatch.setenv(oa.ENV_REGISTRY, registry)
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, INTERNAL_HASH)
    refused = state(c)
    assert (refused.status_code, refused.json()) == (off.status_code, off.json())
    assert refused.headers.get("cache-control") == off.headers.get("cache-control")


def test_the_perimeter_check_still_comes_first(monkeypatch):
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, INTERNAL_HASH)
    c = client()
    assert state(c, INTERNAL, perimeter=None).status_code == 401
    assert state(c, INTERNAL, perimeter="wrong").status_code == 401


def test_no_response_or_health_carries_the_secret_or_its_hash(monkeypatch):
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, INTERNAL_HASH)
    c = client()
    texts = []
    for r in (state(c), verify(c), state(c, INTERNAL), verify(c, INTERNAL), state(c, "wrong")):
        texts.append(r.text + str(dict(r.headers)))
    blob = "\n".join(texts)
    for secret in (INTERNAL, INTERNAL_HASH):
        for i in range(0, len(secret) - 11, 4):
            assert secret[i:i + 12] not in blob


def test_the_comparison_goes_through_compare_digest(monkeypatch):
    """The perimeter check also calls compare_digest, so look for a call that holds the configured hash."""
    monkeypatch.setenv(oh.ENV_INTERNAL_SECRET_SHA256, INTERNAL_HASH)
    seen = []
    real = oh.hmac.compare_digest

    def spy(a, b):
        seen.append((a, b))
        return real(a, b)

    monkeypatch.setattr(oh.hmac, "compare_digest", spy)
    state(client(), INTERNAL)
    assert any(INTERNAL_HASH.encode() in pair for pair in seen)
