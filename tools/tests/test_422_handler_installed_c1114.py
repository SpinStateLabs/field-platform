"""C-1114 (reviewer C-1109 F-C1109-1): every service that builds a FastAPI app installs the no-echo 422 handler.

FastAPI's default 422 repeats the rejected input, and anything that keeps response bodies keeps it. The field-core
helper `install_validation_handler` (C-1018) stops that; it was installed in one service only. A text scan of each
`services/*/src/*/api.py`: the file must call the helper, or the service must be in `NOT_YET` with the reason. An
entry whose service now installs the helper fails too, so the list only shrinks.

Stated limit: this reads source text, it does not send a request; the per-service `test_422_no_echo_<service>_c1114.py`
files do that for the services listed in `MEASURED`."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CALL = "install_validation_handler"


def installs_helper(source: str) -> bool:
    """True if the source CALLS ``install_validation_handler`` (a bare name or an attribute): an ``ast`` Call node, so
    a comment, a string, an import or a bare name does not count (C-1128, reviewer C-1123 F2)."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Name) and func.id == CALL) or (isinstance(func, ast.Attribute) and func.attr == CALL):
                return True
    return False


# service -> why it has no field-core install yet (C-1109 F-C1109-3)
NOT_YET = {
    "federation-broker": "keeps its own handler ON PURPOSE (C-1128): it redacts a caller-chosen key name in loc but keeps "
                         "its validators' messages, which the helper would replace with a fixed phrase (F3, Don's decision)",
    "attestation-reporter": "no static body route gave a 422 in the C-1109 probe; not measured (F-C1109-3)",
    "claude-approver": "no static body route gave a 422 in the C-1109 probe; not measured (F-C1109-3)",
}
MEASURED = {"agent-registry", "compliance-crosswalk", "conformance-sentinel", "delegation-authority",
            "force-gateway", "incident-replay", "kill-switch", "lifecycle-manager", "ops-console", "sealed-ledger",
            "spend-governor"}


def builds_app(source: str) -> bool:
    """True when the source CALLS ``FastAPI`` (a bare name or ``fastapi.FastAPI``): an ``ast`` Call node, so a comment or
    a string that mentions ``FastAPI(`` does not make a file look like an app (C-1128, reviewer C-1123 F2)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    return any(isinstance(n, ast.Call)
               and ((isinstance(n.func, ast.Name) and n.func.id == "FastAPI")
                    or (isinstance(n.func, ast.Attribute) and n.func.attr == "FastAPI"))
               for n in ast.walk(tree))


def _api_files() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for svc in sorted((ROOT / "services").iterdir()):
        for api in sorted(svc.glob("src/*/api.py")):
            if builds_app(api.read_text(encoding="utf-8")):
                out[svc.name] = api
    return out


def test_the_scan_sees_every_service():
    found = _api_files()
    assert len(found) >= 14, sorted(found)


@pytest.mark.parametrize("service", sorted(_api_files()))
def test_a_service_installs_the_helper_or_is_named_with_a_reason(service):
    installs = installs_helper(_api_files()[service].read_text(encoding="utf-8"))
    if service in NOT_YET:
        assert not installs, f"{service} now installs the helper: remove it from NOT_YET"
    else:
        assert installs, f"{service} builds a FastAPI app without install_validation_handler(app)"


def test_the_measured_services_install_the_helper():
    for service in MEASURED:
        assert installs_helper(_api_files()[service].read_text(encoding="utf-8")), service


# --- C-1128 (reviewer C-1123 F2): the guard looks for a Call node, not for text ---------------------------------------
def test_a_call_is_found_and_a_comment_or_string_is_not():
    """F2: a text scan passes when the call text sits only in a comment or a string. The scan must find a real
    ``install_validation_handler(..)`` Call node (a bare name or an attribute) and nothing else."""
    assert installs_helper("install_validation_handler(app)\n")
    assert installs_helper("import m\nm.install_validation_handler(app)\n")
    assert installs_helper("def f(app):\n    install_validation_handler(app)\n")
    assert not installs_helper("# install_validation_handler(app)\n")
    assert not installs_helper("x = 'install_validation_handler(app)'\n")
    assert not installs_helper("'''install_validation_handler(app)'''\n")
    assert not installs_helper("from m import install_validation_handler\n")   # imported, never called
    assert not installs_helper("install_validation_handler\n")                 # named, never called


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


# ---- C-1183 (C-1151 F-C1151-1): the call must be on the app the service SERVES --------------------------------------
# `installs_helper` finds a Call node anywhere, so the call on a throwaway `FastAPI()` or under `if False:` still passes
# it; only the per-service request tests (the services in FIELD_CASES) catch that. This stricter reading needs a
# statement-level call, directly in the body of a function, on the very name that function returns and that is bound to
# `FastAPI(...)` there. It is the same shape in every service today (`app = FastAPI(...)` ... `return app`).
def installs_on_serving_app(source: str) -> bool:
    for fn in ast.walk(ast.parse(source)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        bound = {t.id for n in ast.walk(fn) if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                 and ((isinstance(n.value.func, ast.Name) and n.value.func.id == "FastAPI")
                      or (isinstance(n.value.func, ast.Attribute) and n.value.func.attr == "FastAPI"))
                 for t in n.targets if isinstance(t, ast.Name)}
        returned = {n.value.id for n in ast.walk(fn) if isinstance(n, ast.Return) and isinstance(n.value, ast.Name)}
        for stmt in fn.body:   # direct children only: a call under `if`, `with` or `try` does not count
            if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) and stmt.value.args
                    and isinstance(stmt.value.args[0], ast.Name) and stmt.value.args[0].id in (bound & returned)):
                func = stmt.value.func
                if (isinstance(func, ast.Name) and func.id == CALL) or (isinstance(func, ast.Attribute) and func.attr == CALL):
                    return True
    return False


@pytest.mark.parametrize("service", sorted(set(_api_files()) - set(NOT_YET)))
def test_a_service_installs_the_helper_on_the_app_it_serves(service):
    source = _api_files()[service].read_text(encoding="utf-8")
    assert installs_on_serving_app(source), f"{service}: install_validation_handler is not called on the returned app"


GOOD = "def create_app():\n    app = FastAPI()\n    install_validation_handler(app)\n    return app\n"


def test_the_serving_app_reading_accepts_the_real_shape_and_refuses_the_three_survivors():
    assert installs_on_serving_app(GOOD)
    assert not installs_on_serving_app("def create_app():\n    app = FastAPI()\n    return app\n")              # no call
    assert not installs_on_serving_app("def create_app():\n    app = FastAPI()\n    # install_validation_handler(app)\n"
                                       "    return app\n")                                                  # commented out
    assert not installs_on_serving_app("def create_app():\n    app = FastAPI()\n    install_validation_handler(FastAPI())\n"
                                       "    return app\n")                                                  # throwaway app
    assert not installs_on_serving_app("def create_app():\n    app = FastAPI()\n    other = FastAPI()\n"
                                       "    install_validation_handler(other)\n    return app\n")           # not the served one
    assert not installs_on_serving_app("def create_app():\n    app = FastAPI()\n    if False:\n"
                                       "        install_validation_handler(app)\n    return app\n")        # dead branch


# --- C-1128 (reviewer C-1123 F2): the lists are tied to the services, and the scan is pinned on what it refuses --------
def test_every_service_is_either_measured_or_named_not_yet_and_never_both():
    found = set(_api_files())
    assert not (MEASURED & set(NOT_YET)), sorted(MEASURED & set(NOT_YET))
    assert MEASURED | set(NOT_YET) == found, sorted(found ^ (MEASURED | set(NOT_YET)))


@pytest.mark.parametrize("service", sorted(MEASURED))
def test_a_measured_service_has_a_test_that_sends_a_request(service):
    """The docstring's claim: the source scan above is backed, per service, by a test that posts a marker."""
    tests = sorted((ROOT / "services" / service / "tests").glob("test_*422*no_echo*.py"))
    assert tests, f"{service} is in MEASURED but has no test_*422*no_echo*.py"


@pytest.mark.parametrize("source", [
    "# install_validation_handler(app)\napp = FastAPI()\n",                          # a comment
    "TEXT = 'install_validation_handler(app)'\napp = FastAPI()\n",                   # a string
    '"""Call install_validation_handler(app) here."""\napp = FastAPI()\n',            # a docstring
    "def f():\n    '''install_validation_handler(app)'''\napp = FastAPI()\n",       # a function docstring
    "from field_core.http_errors import install_validation_handler\napp = FastAPI()\n",   # an import, never called
    "x = install_validation_handler\napp = FastAPI()\n",                             # a reference, never called
    "def install_validation_handler(app):\n    pass\napp = FastAPI()\n",              # a definition
])
def test_the_scan_does_not_count_the_name_outside_a_call(source):
    assert installs_helper(source) is False


@pytest.mark.parametrize("source", [
    "install_validation_handler(app)\n",
    "def create_app():\n    app = FastAPI()\n    install_validation_handler(app)\n    return app\n",
    "from field_core import http_errors\nhttp_errors.install_validation_handler(app)\n",
])
def test_the_scan_counts_a_bare_and_a_module_call(source):
    assert installs_helper(source) is True


def test_a_comment_does_not_make_a_file_look_like_an_app():
    assert builds_app("# app = FastAPI()\nx = 1\n") is False
    assert builds_app("import fastapi\napp = fastapi.FastAPI()\n") is True
    assert builds_app("this is not python (\n") is False
