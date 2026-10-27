"""Phase G Stage 0 follow-up: ``sweep_kill`` is a known scope that ``*`` never implies.

C-11 (design 9.5, RT1-1) gates lifecycle auto-kill under ENFORCE on ``sweep_kill``
held explicitly by the caller's row; lifecycle reads the row's scopes directly.
field-core did not know the name, so ``operator_keygen.py`` refused to write it
and ``OperatorAuth.has_scope("sweep_kill")`` answered True for any ``*`` row, so
a reader that asks field-core (health, probes, a future tool) would report
``don`` as holding a scope lifecycle refuses him. Now it is in ``ACTIONS`` and in
``EXPLICIT_ONLY``, next to ``mint_for_others``, ``ledger_attribute`` and
``bypass_operator_list``. (Design 2.2.1 / 5.1: no row is meant to hold it through
Stage 3; that is an operators-file decision, not a code one.)

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from field_core import operator_auth as oa

KEY_DON = "tkv-sk-don-key-0123456789abcdef"
KEY_SWEEPER = "tkv-sk-sweeper-key-0123456789abcdef"
KEY_BOTH = "tkv-sk-both-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture(params=["log-only", "enforce"])
def armed(request, tmp_path, monkeypatch):
    rows = [
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active", "scopes": ["*"]},
        {"operator_id": "sweeper", "key_sha256": oa.key_sha256(KEY_SWEEPER), "status": "active",
         "scopes": ["sweep", "sweep_kill"]},
        {"operator_id": "both", "key_sha256": oa.key_sha256(KEY_BOTH), "status": "active",
         "scopes": ["*", "sweep_kill"]},
    ]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    if request.param == "enforce":
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    return request.param


def H(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


def test_sweep_kill_is_a_known_scope_and_explicit_only():
    assert "sweep_kill" in oa.ACTIONS and "sweep_kill" in oa.EXPLICIT_ONLY
    assert "sweep_kill" not in oa.REJECTED_SCOPES


def test_star_does_not_hold_sweep_kill_an_explicit_row_does(armed):
    don = oa.authenticate(H("don", KEY_DON), "sweep")
    assert don.authenticated and don.has_scope("sweep") and not don.has_scope("sweep_kill")
    assert oa.authenticate(H("sweeper", KEY_SWEEPER), "sweep").has_scope("sweep_kill")
    assert oa.authenticate(H("both", KEY_BOTH), "sweep").has_scope("sweep_kill")


def test_a_star_row_is_refused_when_sweep_kill_is_the_action_asked_for(armed):
    """authorize/authenticate for the action itself: ``*`` is 403 under ENFORCE (and an
    unauthenticated-for-scope LOG-ONLY record), the explicit row passes."""
    if armed == "enforce":
        with pytest.raises(oa.OperatorRefused) as e:
            oa.authenticate(H("don", KEY_DON), "sweep_kill")
        assert e.value.status == 403
    else:
        a = oa.authenticate(H("don", KEY_DON), "sweep_kill")
        assert not a.authenticated and a.failure == "scope", a.failure
    assert oa.authenticate(H("sweeper", KEY_SWEEPER), "sweep_kill").authenticated


def test_operator_keygen_writes_sweep_kill_only_when_named(tmp_path, capsys):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
    import operator_keygen as kg

    f = tmp_path / "operators.json"
    assert kg.main(["--operator-id", "sweeper", "--scopes", "sweep,sweep_kill", "--add-to", str(f)]) == 0
    assert json.loads(f.read_text())[0]["scopes"] == ["sweep", "sweep_kill"]
