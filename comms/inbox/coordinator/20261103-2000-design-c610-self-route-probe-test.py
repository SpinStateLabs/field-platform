"""Lane 10 probe (C-610): the kill-switch self-route guard (services/kill-switch/src/kill_switch/api.py `_is_self_endpoint`).
An endpoint path a manifest names must never re-enter this service. A FAILING case is a path the guard lets through.
Run: FIELD_REPO=<checkout> python -m pytest -q test_self_route_c610.py"""
import glob, importlib, os, sys, re, tempfile
import pytest
R = os.environ.get("FIELD_REPO", ".")
for sub in glob.glob(os.path.join(R, "packages/*/src")) + glob.glob(os.path.join(R, "services/*/src")): sys.path.insert(0, sub)
api = importlib.import_module("kill_switch.api")
SELF = [  # must be treated as self (guard returns True)
 "/kill/a1", "/kill/other", "/kill/domain/d", "/revive/a1", "/drill/a1", "/heartbeat/a1", "/liveness", "/health",
 "//kill//a1", "/x/kill/a1", "/killswitch/kill/a1", "/%6Bill/a1", "/%256Bill/a1", "/kill%2Fa1", "/kill/a1/", "/./kill/a1", "/x/../kill/a1",
 "/%2e%2e/kill/a1", "/kill\\a1", "/kill/a1\x00", "/kill/%00", "/health/", "/liveness/", "/%6Civeness", "/%68ealth",
 "/KILL/a1", "/Kill/a1", "/HEALTH", "/Liveness", "/kill/A1", "/heartbeat/A1", "/DRILL/a1", "/kill;x=1/a1", "/kill%20/a1", "/kill./a1",
 "/kill/a1", "/ki​ll/a1", "/／kill/a1", "/kill/a1?x=1", "/kill/a1#f",
]
@pytest.mark.parametrize("path", SELF)
def test_guard_treats_as_self(path):
    # parts.path is what the caller passes; a query or fragment never reaches this function
    p = path.split("?")[0].split("#")[0]
    assert api._is_self_endpoint(p, "a1"), f"let through: {path!r}"

def test_every_route_of_the_real_app_is_self():
    """the shapes are a denylist of served routes: derive them from the app instead"""
    from kill_switch.api import create_app
    app = create_app()
    missed = []
    for r in app.routes:
        path = getattr(r, "path", None)
        if not path: continue
        sample = re.sub(r"\{[^/}:]+(:[^}]*)?\}", "x1", path)
        if not api._is_self_endpoint(sample, "a1"): missed.append(sample)
    assert not missed, f"served by this service but not treated as self: {sorted(missed)}"

LEGIT = ["/halt", "/v1/stop", "/api/agents/a1/halt", "/hooks/killer", "/killswitchy", "/healthcheck", "/livenessprobe", "/"]
@pytest.mark.parametrize("path", LEGIT)
def test_legitimate_endpoints_are_not_self(path):
    assert not api._is_self_endpoint(path, "a1"), f"refused a legitimate endpoint: {path!r}"
