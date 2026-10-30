import os, sys, io, logging, traceback
for p in ("services/force-gateway/src","packages/field-core/src","services/sentinel/src"):
    sys.path.insert(0, os.path.abspath(p))
SECRET = "MADE-UP-SECRET-0123456789"
from force_gateway import api
def try_env(name, val, call):
    old = os.environ.get(name); os.environ[name] = val
    try:
        r = call(); out = f"ok -> {r!r}"
    except BaseException as e:
        tb = "".join(traceback.format_exception(e))
        out = f"{type(e).__name__}: {e}"
        if SECRET in tb: out += "  <<VALUE IN TRACEBACK>>"
    finally:
        if old is None: os.environ.pop(name, None)
        else: os.environ[name] = old
    print(f"{name}={val[:26]!r:32} {out[:150]}")
mk = lambda: (api.create_app(upstream=api.mock_upstream, store=None) and "app")
for name in ("FORCE_HYGIENE_WINDOW","FORCE_HYGIENE_BAND","FORCE_HYGIENE_BASELINE_WINDOWS","FORCE_GATEWAY_LATENCY_BUDGET_MS","FORCE_GATEWAY_BYPASS_COOLDOWN"):
    for v in (SECRET, "nan", "inf", "-1", "0", "1_0", "9"*5000, "١٢"):
        try_env(name, v, mk)
for name in ("FORCE_GATEWAY_ENFORCE","FORCE_GATEWAY_TOOL_CHECK","FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM"):
    try_env(name, SECRET, mk)
for name in ("FORCE_GATEWAY_SENTINEL_TIMEOUT","FORCE_TELEMETRY_WINDOW"):
    try_env(name, SECRET, mk)
for v in ("http://u:"+SECRET+"@h.example:8004/p?k="+SECRET, SECRET, "http://h:"+SECRET, "http://[::1]:8004", SECRET+"://h", "http://h:99999", "http://é.example", "http://h.example:0", "http://h.example:8004#"+SECRET):
    print(repr(v[:40]), "->", api.public_origin(v))
