"""phase_g_check against an estate whose ledger REQUIRES caller signatures (the GB10's ledger).

GB10, 2026-10-27, Stage 1 LOG-ONLY (armed 20:06:08Z, rolled back 20:07:58Z):
FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1 + a caller keyring +
FIELD_LEDGER_REQUIRE_SIGNING=1. phase_g_check's no-credential,
incomplete-credential and bad-credential probes against the kill-switch left
ZERO operator.unauthenticated rows: the kill-switch's 4 normal (stop-type)
events were accepted, its 4 operator.unauthenticated records were refused 403,
and /health dropped_unauthenticated_records stayed 0. Every estate CI booted
ran WITHOUT caller signatures, which is why every review missed it.

This module boots the same harness as test_phase_g_check.py (every service's
real create_app over real HTTP) with the GB10 ledger configuration (fake keys)
and requires: one operator.unauthenticated row per unauthenticated LOG-ONLY
write, each signed by the service (caller signature verified over the stored
row), kill-switch /health dropped_unauthenticated_records 0, phase_g_check
green in LOG-ONLY and ENFORCE, and the positive path's kill/revive rows
caller-signed (not ``caller_unsigned``). The first test fails if the estate
does not actually require caller signatures, so dropping the configuration
from the harness cannot turn this module into a copy of the unsigned one.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).parent))

import phase_g_check  # noqa: E402
from test_estate_probe import CANARY, HARNESS_CALLER_ID, SECRET, Estate, _http  # noqa: E402
from test_phase_g_check import (  # noqa: E402
    FP_DON, KEY_DON, KEY_OTHER, KEY_SVC, _arm, _row, assert_secret_free, events, run,
)

from field_core.signing import verify_caller_signature  # noqa: E402

phase_g_check.SETTLE_S = 3.0
PROBE_REASONS = {"no_credential", "incomplete_credential", "bad_credential"}


@pytest.fixture(scope="module")
def sest(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("phase_g_signed")
    saved = {k: os.environ.get(k) for k in ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY")}
    os.environ.update(FIELD_OPERATOR="svc", FIELD_OPERATOR_KEY=KEY_SVC)
    try:
        e = Estate(tmp, secret=True, caller_signed=True)
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    e.ops_file = tmp / "operators.json"
    e.ops_file.write_text(json.dumps([
        _row("don", KEY_DON, ["*"], ["Don Hagell, Spin State Labs"]),
        _row("other", KEY_OTHER, ["*"]),
        _row("svc", KEY_SVC, ["*", "bypass_operator_list", "ledger_attribute"],
             event_prefixes=["kill.", "registry.", "debug."]),
    ]))
    e.secret_file = tmp / "perimeter.secret"
    e.secret_file.write_text(SECRET + "\n")
    e.key_file = tmp / "don.key"
    e.key_file.write_text(KEY_DON + "\n")
    try:
        yield e
    finally:
        _arm(e, "off")
        e.close()


@pytest.fixture
def signed(sest):
    _arm(sest, "off")
    sest.reset()
    yield sest
    _arm(sest, "off")
    sest.reset()


def ks_health(e: Estate) -> dict:
    status, body = _http("GET", f"{e.base}/killswitch/health", None, SECRET)
    assert status == 200
    return body


def assert_caller_signed(e: Estate, ev: dict) -> None:
    assert ev.get("caller_id") == HARNESS_CALLER_ID and not ev.get("caller_unsigned"), ev
    assert verify_caller_signature(ev, e.caller_pub), f"{ev['event_type']}: stored row does not verify"


def test_the_estate_requires_caller_signatures_like_the_gb10(signed):
    """Guard: without this configuration every test below would pass on an
    estate that cannot show the GB10 failure."""
    status, h = _http("GET", f"{signed.base}/ledger/health", None, SECRET)
    assert status == 200
    assert h["require_caller_signature"] is True and h["caller_keyring"] == "on" and h["caller_keys"] == 1
    status, body = _http("POST", f"{signed.base}/ledger/events",
                         {"event_type": "operator.unauthenticated", "agent_id": None,
                          "payload": {"action": "revive"}}, SECRET)
    assert status == 403 and "FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE" in json.dumps(body)
    # and the estate's own provisioning went through the signed path
    reg = events(signed, event_type="registry.registered")
    assert reg and all(e.get("caller_id") == HARNESS_CALLER_ID for e in reg)


def test_log_only_one_signed_unauthenticated_row_per_probe(signed):
    _arm(signed, "log-only")
    u0 = len(events(signed, event_type="operator.unauthenticated"))
    r0 = len(events(signed, event_type="kill.revive", agent_id=CANARY))
    dropped0 = ks_health(signed)["dropped_unauthenticated_records"]
    code, out = run(signed, "--expect-mode", "log-only")
    assert code == 0, out
    assert "left exactly one operator.unauthenticated event" in out
    unauth = events(signed, event_type="operator.unauthenticated")[u0:]
    # every unauthenticated LOG-ONLY write was allowed (one unattributed kill.revive
    # each) and left exactly one record: today's GB10 left none
    anon_revives = [e for e in events(signed, event_type="kill.revive", agent_id=CANARY)[r0:]
                    if e["payload"].get("operator_id_authenticated") is None]
    assert anon_revives and len(unauth) == len(anon_revives), (len(unauth), len(anon_revives))
    assert {e["payload"]["reason"] for e in unauth} == PROBE_REASONS
    for e in unauth:
        assert e["payload"]["action"] == "revive"
        assert e["payload"]["self_reported"] is False          # the kill-switch attributes (svc)
        assert_caller_signed(signed, e)
    for e in anon_revives:
        assert_caller_signed(signed, e)
    assert ks_health(signed)["dropped_unauthenticated_records"] == dropped0 == 0
    assert_secret_free(out)


def test_enforce_refusals_are_signed_operator_refused_rows(signed):
    _arm(signed, "enforce")
    f0 = len(events(signed, event_type="operator.refused"))
    code, out = run(signed, "--expect-mode", "enforce")
    assert code == 0, out
    refused = events(signed, event_type="operator.refused")[f0:]
    assert refused, "ENFORCE refusals left no operator.refused row"
    for e in refused:
        assert_caller_signed(signed, e)
    assert ks_health(signed)["dropped_refused_records"] == 0
    assert_secret_free(out)


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_the_positive_path_rows_are_caller_signed_and_attributed(signed, mode):
    """The kill-switch's own kill/revive rows: attributed AND signed. Before,
    a stop-type row whose reserved keys the ledger stripped landed
    caller_unsigned; an attributing service kept them but nothing pinned it."""
    _arm(signed, mode)
    k0 = len(events(signed, event_type="kill.agent", agent_id=CANARY))
    r0 = len(events(signed, event_type="kill.revive", agent_id=CANARY))
    code, out = run(signed, "--expect-mode", mode, keyed=True)
    assert code == 0, out
    [kill] = events(signed, event_type="kill.agent", agent_id=CANARY)[k0:]
    revives = events(signed, event_type="kill.revive", agent_id=CANARY)[r0:]
    assert kill["payload"]["operator_key_fp"] == FP_DON
    for ev in [kill, *revives]:
        assert_caller_signed(signed, ev)
    assert_secret_free(out)
