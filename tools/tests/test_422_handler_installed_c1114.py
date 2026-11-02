"""C-1114 (reviewer C-1109 F-C1109-1): every service that builds a FastAPI app installs the no-echo 422 handler.

FastAPI's default 422 repeats the rejected input, and anything that keeps response bodies keeps it. The field-core
helper `install_validation_handler` (C-1018) stops that; it was installed in one service only. A text scan of each
`services/*/src/*/api.py`: the file must call the helper, or the service must be in `NOT_YET` with the reason. An
entry whose service now installs the helper fails too, so the list only shrinks.

Stated limit: this reads source text, it does not send a request; the per-service `test_422_no_echo_<service>_c1114.py`
files do that for the services listed in `MEASURED`."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CALL = "install_validation_handler("

# service -> why it has no field-core install yet (C-1109 F-C1109-2, F-C1109-3)
NOT_YET = {
    "agent-registry": "keeps its own handler, validation_errors_without_values (api.py); moving it onto the helper is F-C1109-2",
    "federation-broker": "keeps its own handler (api.py); moving it onto the helper is F-C1109-2",
    "attestation-reporter": "no static body route gave a 422 in the C-1109 probe; not measured (F-C1109-3)",
    "claude-approver": "no static body route gave a 422 in the C-1109 probe; not measured (F-C1109-3)",
    "kill-switch": "its one probed route gave no 422 in the C-1109 probe; not measured (F-C1109-3)",
}
MEASURED = {"compliance-crosswalk", "conformance-sentinel", "delegation-authority", "force-gateway", "incident-replay",
            "lifecycle-manager", "ops-console", "sealed-ledger", "spend-governor"}


def _api_files() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for svc in sorted((ROOT / "services").iterdir()):
        for api in sorted(svc.glob("src/*/api.py")):
            if "FastAPI(" in api.read_text(encoding="utf-8"):
                out[svc.name] = api
    return out


def test_the_scan_sees_every_service():
    found = _api_files()
    assert len(found) >= 14, sorted(found)


@pytest.mark.parametrize("service", sorted(_api_files()))
def test_a_service_installs_the_helper_or_is_named_with_a_reason(service):
    installs = CALL in _api_files()[service].read_text(encoding="utf-8")
    if service in NOT_YET:
        assert not installs, f"{service} now installs the helper: remove it from NOT_YET"
    else:
        assert installs, f"{service} builds a FastAPI app without install_validation_handler(app)"


def test_the_measured_services_install_the_helper():
    for service in MEASURED:
        assert CALL in _api_files()[service].read_text(encoding="utf-8"), service


# ---- C-1158 (Don's ruling on C-1123 F3): a 422 keeps a fixed reason and the offending field name ----------------------
# The source scan above says the handler is installed; these requests say what it does. Each case sends a wrong value
# for one real field (a made-up marker in a list, or as the whole body) and checks that the answer is a 422, that the
# marker is nowhere in the body, that the field name IS in the body, and that the reason text is fixed (it does not
# change with what was sent). Every value is made up.
import json  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

MARK = "MADE-UP-MARKER-0123456789"


def _delegation(tmp):
    from delegation_authority.api import create_app
    from delegation_authority.store import TokenStore
    return create_app(store=TokenStore(tmp / "t.sqlite3"))


def _sentinel(tmp):
    from conformance_sentinel.api import create_app
    return create_app()


def _replay(tmp):
    from incident_replay.api import create_app
    return create_app()


def _spend(tmp):
    from spend_governor.api import create_app
    from spend_governor.core import GovernorStore
    return create_app(store=GovernorStore(tmp / "s.sqlite3"))


def _ledger(tmp):
    from sealed_ledger.api import create_app
    from sealed_ledger.store import LedgerStore
    return create_app(store=LedgerStore(tmp / "e.jsonl"))


def _lifecycle(tmp):
    from lifecycle_manager.api import create_app
    return create_app()


def _console(tmp):
    from ops_console.api import create_app
    return create_app()


def _gateway(tmp):
    from force_gateway.api import create_app
    from force_gateway.store import GatewayStore
    return create_app(store=GatewayStore(tmp / "g.sqlite3"))


def _crosswalk(tmp):
    from compliance_crosswalk.api import create_app
    return create_app()


# service, builder, route, body that is wrong in one real field, the field name the answer must keep
FIELD_CASES = [
    ("delegation-authority", _delegation, "/tokens",
     {"agent_id": [MARK], "granted_by": "g", "scope": ["s"], "ttl_seconds": 60}, "agent_id"),
    ("conformance-sentinel", _sentinel, "/check", {"agent_id": [MARK], "action": "a"}, "agent_id"),
    ("incident-replay", _replay, "/replay", {"agent_id": [MARK], "since": "x", "until": "y"}, "agent_id"),
    ("spend-governor", _spend, "/spend", {"agent_id": [MARK]}, "agent_id"),
    ("sealed-ledger", _ledger, "/events", {"event_type": [MARK]}, "event_type"),
    ("lifecycle-manager", _lifecycle, "/sweep", {"expiry_days": MARK}, "expiry_days"),
    ("ops-console", _console, "/api/check", {"agent_id": [MARK], "action": "a"}, "agent_id"),
    ("force-gateway", _gateway, "/v1/messages", MARK, "body"),
    ("compliance-crosswalk", _crosswalk, "/pack", {"signer": [MARK], "manifest": {}}, "signer"),
]


@pytest.mark.parametrize("service,build,route,body,field", FIELD_CASES, ids=[c[0] for c in FIELD_CASES])
def test_a_422_keeps_the_field_name_and_a_fixed_reason_and_never_the_value(service, build, route, body, field, tmp_path):
    client = TestClient(build(tmp_path), raise_server_exceptions=False)
    r = client.post(route, json=body)
    assert r.status_code == 422, (service, r.status_code)
    assert MARK not in r.text, r.text
    detail = r.json()["detail"]
    assert isinstance(detail, list) and detail, detail
    assert any(field in err["loc"] for err in detail), (service, detail)       # the offending field is named
    for err in detail:
        assert set(err) == {"type", "loc", "msg"}, err                         # no input, no ctx, nothing else
        assert isinstance(err["msg"], str) and err["msg"]                      # a reason is given
    # the reason is fixed: sending a different made-up value gives the same reasons and the same locations
    other = json.loads(json.dumps(body).replace(MARK, "ANOTHER-MADE-UP-VALUE-987654321"))
    r2 = client.post(route, json=other)
    assert r2.status_code == 422 and "ANOTHER-MADE-UP-VALUE" not in r2.text
    assert [(e["type"], e["loc"], e["msg"]) for e in r2.json()["detail"]] == [(e["type"], e["loc"], e["msg"]) for e in detail]


# Q-93 F-Q93-2: the nine cases above trip TYPE errors, whose messages are fixed phrases. This one trips a CUSTOM validator
# (delegation-authority's "exactly one expiry" check, a model validator that raises ValueError) with a made-up marker in a
# valid field, so the handler's replacement of a validator's text and its refusal to echo the whole input are seen end to end.
def test_a_422_from_a_custom_validator_keeps_a_fixed_reason_and_never_the_value(tmp_path):
    client = TestClient(_delegation(tmp_path), raise_server_exceptions=False)
    body = {"agent_id": MARK, "granted_by": "g", "scope": ["s"], "ttl_seconds": 60, "expires_at": "2999-01-01T00:00:00Z"}
    r = client.post("/tokens", json=body)
    assert r.status_code == 422, r.status_code
    assert MARK not in r.text, r.text
    detail = r.json()["detail"]
    assert isinstance(detail, list) and detail, detail
    assert any("body" in err["loc"] for err in detail), detail                 # the location (the request body) is kept
    for err in detail:
        assert set(err) == {"type", "loc", "msg"}, err                         # no input (the whole body), no ctx
        assert err["type"] == "value_error", err                               # it really is the custom validator
        assert err["msg"] == "Value error", err                                # fixed text; the validator's own words are dropped
    other = dict(body, agent_id="ANOTHER-MADE-UP-VALUE-987654321")
    r2 = client.post("/tokens", json=other)
    assert r2.status_code == 422 and "ANOTHER-MADE-UP-VALUE" not in r2.text
    assert r2.json()["detail"] == detail
