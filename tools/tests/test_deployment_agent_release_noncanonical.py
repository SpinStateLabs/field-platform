"""S6-18: a record holding a value json cannot encode is a ReleaseRecordError, never a TypeError.

`canonical_payload(record)` was evaluated as an argument of `_accepts`, outside its try/except, so an extra key holding a
set, bytes, a date (what yaml.safe_load yields for a bare timestamp), mixed-type mapping keys, a cycle or a very deep
nesting raised out of `verify_release`, whose contract is "return a VerifiedRelease or raise ReleaseRecordError"."""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from deployment_agent.release import ReleaseRecordError, refuse_all_verifier, verify_release  # noqa: E402

from test_deployment_agent_release import SHA, accept_ok, record  # noqa: E402

_CYCLE: dict = {}
_CYCLE["self"] = _CYCLE

@pytest.mark.parametrize("extra", [
    {1, 2}, b"bytes", datetime.date(2026, 1, 1), datetime.datetime(2026, 1, 1, 12, 0), {1: "a", "b": 2}, _CYCLE,
], ids=["set", "bytes", "date", "datetime", "mixed-keys", "cycle"])
def test_an_extra_value_json_cannot_encode_is_a_release_record_error(extra):
    with pytest.raises(ReleaseRecordError, match="not canonical JSON"):
        verify_release(record(extra=extra), SHA, accept_ok)


def test_the_valid_cases_still_verify():
    assert verify_release(record(extra={"note": "plain"}), SHA, accept_ok).sha == SHA


def test_a_non_json_value_inside_override_approval_is_a_record_error_too():
    # override_approval is part of the signed record, so the first canonicalisation sees it
    rec = record(adr_override="ADR-1", override_approval={"approver": "Don", "signature": "sig-ok", "extra": {1, 2}})
    with pytest.raises(ReleaseRecordError, match="not canonical JSON"):
        verify_release(rec, SHA, accept_ok)


def test_a_non_json_value_next_to_an_override_is_still_refused_as_a_record_error():
    rec = record(adr_override="ADR-1", override_approval={"approver": "Don", "signature": "sig-ok"}, extra={1, 2})
    with pytest.raises(ReleaseRecordError, match="not canonical JSON"):
        verify_release(rec, SHA, accept_ok)


def test_the_refuse_all_verifier_still_raises_not_implemented_on_a_canonical_record():
    with pytest.raises(NotImplementedError):
        verify_release(record(), SHA, refuse_all_verifier)
