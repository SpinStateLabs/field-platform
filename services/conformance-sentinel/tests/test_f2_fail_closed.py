"""F2 — the sentinel fails closed on a ledger that cannot take the record.

(2) ``_default_ledger_health`` is False on a non-200, on ``ok: false`` and on
``appendable: false``; a missing ``appendable`` (an older ledger) still
counts as appendable. (3) In ENFORCE mode a failed ALLOW-verdict append is
BLOCK ``L.unreachable`` and metering is never reached; BLOCK/ESCALATE
appends stay best-effort; LOG-ONLY is unchanged. Each branch has the test
that fails when the branch is deleted.
"""

from __future__ import annotations

import httpx
import pytest

from conformance_sentinel.api import _default_ledger_health
from conformance_sentinel.mode import SentinelMode
from field_core.clients import LedgerUnreachableError
from sealed_ledger.store import SigningConfig
from tests.conftest import AGENT_ID

# --------------------------------------------- (2) the step-1 health gate


class _Resp:
    def __init__(self, status_code: int, body=None, raw_json_error: bool = False):
        self.status_code = status_code
        self._body = body
        self._raw_json_error = raw_json_error

    def json(self):
        if self._raw_json_error:
            raise ValueError("not json")
        return self._body


def _gate(monkeypatch, resp=None, exc: Exception | None = None):
    seen = []

    def fake_get(url, timeout=None, **kw):
        seen.append((url, timeout))
        if exc is not None:
            raise exc
        return resp

    monkeypatch.setattr(httpx, "get", fake_get)
    return _default_ledger_health("http://ledger.test/"), seen


def test_gate_true_on_200_ok_and_appendable(monkeypatch):
    """Positive control: the F2 /health shape with appendable: true passes."""
    health, seen = _gate(monkeypatch, _Resp(200, {"ok": True, "appendable": True, "signing": "on"}))
    assert health() is True
    assert seen == [("http://ledger.test/health", 2.0)]


def test_gate_false_when_health_is_not_200(monkeypatch):
    health, _ = _gate(monkeypatch, _Resp(503, {"ok": True, "appendable": True}))
    assert health() is False


def test_gate_false_when_ok_is_false(monkeypatch):
    health, _ = _gate(monkeypatch, _Resp(200, {"ok": False, "appendable": True}))
    assert health() is False


def test_gate_false_when_appendable_is_present_and_false(monkeypatch):
    """THE F2 case: a 200 ok ledger that will refuse the allow record
    (FIELD_LEDGER_REQUIRE_SIGNING=1, no key) is not reachable for our purpose."""
    health, _ = _gate(monkeypatch, _Resp(200, {"ok": True, "appendable": False, "signing": "error",
                                               "require_signing": True}))
    assert health() is False


def test_gate_true_when_appendable_is_missing_older_ledger(monkeypatch):
    health, _ = _gate(monkeypatch, _Resp(200, {"ok": True, "service": "sealed-ledger",
                                               "event_count": 1, "head_hash": "a" * 64}))
    assert health() is True


def test_gate_false_on_transport_error_non_json_or_odd_bodies(monkeypatch):
    health, _ = _gate(monkeypatch, exc=httpx.ConnectError("down"))
    assert health() is False
    health, _ = _gate(monkeypatch, _Resp(200, raw_json_error=True))
    assert health() is False
    health, _ = _gate(monkeypatch, _Resp(200, ["not", "a", "dict"]))
    assert health() is False
    health, _ = _gate(monkeypatch, _Resp(200, {"ok": True, "appendable": "no"}))  # not true => fail closed
    assert health() is False
    health, _ = _gate(monkeypatch, _Resp(200, {"appendable": True}))  # no ok key
    assert health() is False


# ---------------------------------- (3) a failed ALLOW record in enforce mode


def _allow_setup(stack, monkeypatch, exc: Exception):
    """A stack whose every ledger append raises ``exc`` AFTER the step-1 gate
    (ledger_up stays True), with the metering path spied."""
    stack.set_cap()
    token = stack.mint_token()
    engine = stack.sentinel.app.state.engine
    metered = []
    monkeypatch.setattr(engine, "_meter", lambda *a, **k: metered.append(a))
    posted = []
    monkeypatch.setattr(engine.governor, "record_action",
                        lambda *a, **k: posted.append(a) or "metered")

    def boom(*args, **kwargs):
        raise exc

    monkeypatch.setattr(engine.ledger, "append", boom)
    return token, engine, metered, posted


@pytest.mark.parametrize("exc", [LedgerUnreachableError("ledger append returned 503: signing required"),
                                 RuntimeError("socket closed mid-append")])
def test_enforce_failed_allow_append_is_block_l_unreachable_and_never_metered(stack, monkeypatch, exc):
    """Delete the new branch in ``_verdict`` and this fails: the verdict
    would be ALLOW and ``_meter`` would be called."""
    token, engine, metered, posted = _allow_setup(stack, monkeypatch, exc)
    assert engine.mode is SentinelMode.ENFORCE
    v = stack.check("draft invoices", token_id=token)
    assert v["decision"] == "BLOCK" and v["clause_id"] == "L.unreachable"
    assert v["reasons"][0] == "sealed-ledger refused or failed the allow record"
    assert type(exc).__name__ in v["reasons"][1]
    assert v["context"]["allow_record_failed"] is True
    assert v["context"]["token_id"] == token and v["context"]["irreversible"] is False
    assert metered == [] and posted == []  # NO metering
    assert "metered" not in v["context"]


def test_enforce_failed_allow_append_through_the_real_ledger_in_the_require_signing_fault(stack):
    """End to end through the real LedgerClient and the real ledger app: the
    ledger flips to FIELD_LEDGER_REQUIRE_SIGNING=1 with no key AFTER the mint,
    so the step-1 gate (this stack's stub) still passes and the allow record
    is refused 503 => BLOCK L.unreachable; a stop-type write (delegation
    revoke) still succeeds, stamped signing_failed."""
    stack.set_cap()
    token = stack.mint_token()
    assert stack.check("draft invoices", token_id=token)["decision"] == "ALLOW"
    stack.ledger_store.signing = SigningConfig(require_signing=True)  # the fault state
    assert stack.ledger.get("/health").json()["appendable"] is False
    v = stack.check("draft invoices", token_id=token)
    assert v["decision"] == "BLOCK" and v["clause_id"] == "L.unreachable"
    assert "503" in v["reasons"][1] and "FIELD_LEDGER_REQUIRE_SIGNING" in v["reasons"][1]
    allows = stack.ledger.get("/events", params={"event_type": "conformance.allow"}).json()
    assert len(allows) == 1  # only the first check's record landed
    # the stop-type path is still open: the revoke is ledger-first and succeeds
    r = stack.delegation.post(f"/tokens/{token}/revoke")
    assert r.status_code == 200, r.text
    [rev] = stack.ledger.get("/events", params={"event_type": "delegation.revoke"}).json()
    assert rev["signing_failed"] is True and "signature" not in rev
    # and the revoked token now blocks on its own clause (a BLOCK record is
    # best-effort: the 503 does not change the verdict)
    v = stack.check("draft invoices", token_id=token)
    assert v["decision"] == "BLOCK" and v["clause_id"] == "D.revoked"


def test_log_only_failed_allow_append_is_still_allow(stack, monkeypatch):
    """LOG-ONLY is unchanged: the allow record is lost, the caller is not
    blocked (README LIMITS)."""
    token, engine, metered, posted = _allow_setup(stack, monkeypatch, RuntimeError("down"))
    engine.mode = SentinelMode.LOG_ONLY
    v = stack.check("draft invoices", token_id=token)
    assert v["decision"] == "ALLOW" and v["clause_id"] is None
    assert "shadowed" not in v["context"] and "allow_record_failed" not in v["context"]
    assert len(metered) == 1  # a genuine log-only ALLOW is still metered (option A)


def test_enforce_block_and_escalate_appends_stay_best_effort(stack, monkeypatch):
    """A block that cannot be recorded is still a block, with its own clause."""
    stack.set_cap()
    token = stack.mint_token()
    engine = stack.sentinel.app.state.engine

    def boom(*args, **kwargs):
        raise LedgerUnreachableError("503")

    monkeypatch.setattr(engine.ledger, "append", boom)
    v = stack.check("transfer funds", token_id=token)
    assert v["decision"] == "BLOCK" and v["clause_id"] == "D.scope"
    v = stack.check("send invoice email", token_id=token)
    assert v["decision"] == "ESCALATE" and v["clause_id"] == "E.escalation_trigger"


def test_enforce_successful_allow_append_is_unchanged(stack):
    """Positive control for the branch: the allow lands, ALLOW, metered."""
    stack.set_cap()
    token = stack.mint_token()
    v = stack.check("draft invoices", token_id=token)
    assert v["decision"] == "ALLOW" and v["context"]["metered"] is True
    assert "allow_record_failed" not in v["context"]
