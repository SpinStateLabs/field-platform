"""C-1114 (reviewer C-1109 F-C1109-1): every service that builds a FastAPI app installs the no-echo 422 handler.

FastAPI's default 422 repeats the rejected input, and anything that keeps response bodies keeps it. The field-core
helper `install_validation_handler` (C-1018) stops that; it was installed in one service only. A scan of each
`services/*/src/*/api.py` (C-1128, C-1123 F2: the syntax tree, not the text): the file must CALL the helper, or the
service must be in `NOT_YET` with the reason. A name in a comment, a string or a docstring is not a call. An entry
whose service now installs the helper fails too, so the list only shrinks.

Stated limit: this reads source, it does not send a request; the per-service `test_422_no_echo_<service>_c1114.py`
files do that for the services listed in `MEASURED`."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = "install_validation_handler"

# service -> why it has no field-core install yet (C-1109 F-C1109-3)
NOT_YET = {
    "federation-broker": "keeps its own handler for the rule messages its validators write; its loc names are replaced by "
                         "field_core.http_errors.redacted_loc (C-1128); the full install waits on C-1123 F3 (Don)",
    "attestation-reporter": "no static body route gave a 422 in the C-1109 probe; not measured (F-C1109-3)",
    "claude-approver": "no static body route gave a 422 in the C-1109 probe; not measured (F-C1109-3)",
    "kill-switch": "its one probed route gave no 422 in the C-1109 probe; not measured (F-C1109-3)",
}
MEASURED = {"agent-registry", "compliance-crosswalk", "conformance-sentinel", "delegation-authority",
            "force-gateway", "incident-replay", "lifecycle-manager", "ops-console",
            "sealed-ledger", "spend-governor"}


def _calls(source: str, name: str) -> bool:
    """True when the source holds a CALL of `name`, bare (`name(app)`) or through a module (`mod.name(app)`)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Name) and func.id == name) or (isinstance(func, ast.Attribute) and func.attr == name):
                return True
    return False


def installs_helper(source: str) -> bool:
    return _calls(source, HELPER)


def builds_app(source: str) -> bool:
    return _calls(source, "FastAPI")


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


def test_every_service_is_either_measured_or_named_not_yet_and_never_both():
    found = set(_api_files())
    assert not (MEASURED & set(NOT_YET)), sorted(MEASURED & set(NOT_YET))
    assert MEASURED | set(NOT_YET) == found, sorted(found ^ (MEASURED | set(NOT_YET)))


@pytest.mark.parametrize("service", sorted(MEASURED))
def test_a_measured_service_has_a_test_that_sends_a_request(service):
    """The docstring's claim: the source scan above is backed, per service, by a test that posts a marker."""
    tests = sorted((ROOT / "services" / service / "tests").glob("test_*422*no_echo*.py"))
    assert tests, f"{service} is in MEASURED but has no test_*422*no_echo*.py"


# --- the scan itself (C-1123 F2: it passed on a call that only appeared in a comment) -------------------------------

@pytest.mark.parametrize("source", [
    "# install_validation_handler(app)\napp = FastAPI()\n",                          # a comment
    "TEXT = 'install_validation_handler(app)'\napp = FastAPI()\n",                   # a string
    '"""Call install_validation_handler(app) here."""\napp = FastAPI()\n',            # a docstring
    "def f():\n    '''install_validation_handler(app)'''\napp = FastAPI()\n",       # a function docstring
    "from field_core.http_errors import install_validation_handler\napp = FastAPI()\n",   # an import, never called
    "x = install_validation_handler\napp = FastAPI()\n",                             # a reference, never called
    "def install_validation_handler(app):\n    pass\napp = FastAPI()\n",              # a definition
    "this is not python (\n",                                                         # does not parse: not a call
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
