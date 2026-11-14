"""B-S12-3 (signing half): a manifest holding NaN or Infinity cannot be canonicalised, signed or verified.

``canonical_manifest_bytes`` used ``json.dumps`` with the default ``allow_nan=True``, so a manifest with a bare ``NaN``
token (not JSON) was signed, and no non-Python verifier could recompute it. Now a ValueError. The event half of the
card (ledger.py) is open PR 500; sealed-ledger is not touched here."""

from __future__ import annotations

import pytest

from field_core.signing import (
    canonical_manifest_bytes,
    generate_keypair,
    sign_manifest,
    verify_manifest,
)

NON_FINITE = [float("nan"), float("inf"), float("-inf")]


@pytest.mark.parametrize("bad", NON_FINITE, ids=repr)
@pytest.mark.parametrize("shape", ["top", "nested", "list"])
def test_a_non_finite_number_anywhere_is_refused(bad, shape):
    data = {"top": {"v": bad}, "nested": {"a": {"b": bad}}, "list": {"xs": [1, bad]}}[shape]
    with pytest.raises(ValueError):
        canonical_manifest_bytes(data)


def test_sign_manifest_refuses_a_non_finite_number():
    private, _ = generate_keypair()
    with pytest.raises(ValueError):
        sign_manifest({"v": float("nan")}, private)


def test_verify_manifest_does_not_pass_a_non_finite_manifest():
    private, public = generate_keypair()
    sig = sign_manifest({"v": 1.5}, private)
    try:
        ok = verify_manifest({"v": float("nan")}, sig, public)
    except ValueError:
        return
    assert ok is False


def test_finite_values_canonicalise_exactly_as_before():
    data = {"b": [1, 2.5, "é"], "a": {"z": None, "y": True}, "n": 0.0, "big": 10**20}
    assert canonical_manifest_bytes(data) == (
        '{"a":{"y":true,"z":null},"b":[1,2.5,"é"],"big":100000000000000000000,"n":0.0}'.encode("utf-8")
    )
    private, public = generate_keypair()
    assert verify_manifest(data, sign_manifest(data, private), public) is True
