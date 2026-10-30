import os, httpx
os.environ["FIELD_SHARED_SECRET"] = "made-up-perimeter"; os.environ["FIELD_OPERATOR"] = "made-up-op"; os.environ["FIELD_OPERATOR_KEY"] = "made-up-key"
from lifecycle_manager.api import PerRequestAuthClient
from field_core.guarded_operator import DELEGATION_GUARDED, KILLSWITCH_GUARDED, LEDGER_GUARDED, REGISTRY_GUARDED, compile_routes
from field_core import clients as fc
seen = []
def handler(req): seen.append(req); return httpx.Response(200, json={})
def mk(base, routes=KILLSWITCH_GUARDED):
    c = PerRequestAuthClient(base_url=base, guarded_routes=routes, transport=httpx.MockTransport(handler)); return c
def hdr(c, method, url, **kw):
    seen.clear(); c.request(method, url, **kw); r = seen[-1]
    return ("PAIR" if "x-field-operator-key" in r.headers else ("secret" if "x-field-auth" in r.headers else "none")), str(r.url)[:70]
B = "http://ks.test:8005"
print("== kill-switch table, base", B)
for m, u in [("POST","/kill/a"),("post","/kill/a"),("POST","kill/a"),("POST","/kill/a/"),("POST","/kill/%2e%2e/health"),("POST","/kill/../health"),("POST","/kill/a/../b"),("POST","/kill/a%2Fb"),("POST","/kill/a?x=1"),("POST","/kill/a#f"),("POST","//kill/a"),("POST","/./kill/a"),("POST","/kill/%2e"),("POST","/kill/."),("POST","/kill/.."),("POST","/kill/ a"),("POST","/kill/é"),("GET","/kill/a"),("POST","/revive/a"),("POST","/drill/a"),("POST","/health"),("POST","/KILL/a"),("POST","/kill/a;x"),("POST","/kill/a\\b")]:
    try: print(f"  {m:5} {u:24} ->", *hdr(mk(B), m, u))
    except Exception as e: print(f"  {m:5} {u:24} -> EXC {type(e).__name__}")
print("== absolute URLs")
for u in ["http://ks.test:8005/kill/a","http://KS.test:8005/kill/a","http://ks.test:80/kill/a","http://ks.test.:8005/kill/a","http://ks.test:8005@evil/kill/a","http://evil/kill/a","https://ks.test:8005/kill/a","http://ks.test:8005/kill/a/../health","http://u@ks.test:8005/kill/a"]:
    try: print(f"  {u:44} ->", *hdr(mk(B), "POST", u))
    except Exception as e: print(f"  {u:44} -> EXC {type(e).__name__}")
print("== base with path prefix /api")
for u in ["/kill/a","/api/kill/a","http://ks.test:8005/api/kill/a","http://ks.test:8005/apix/kill/a","http://ks.test:8005/kill/a","http://ks.test:8005/api/../kill/a","http://ks.test:8005/api/%2e%2e/kill/a"]:
    try: print(f"  {u:48} ->", *hdr(mk(B + "/api"), "POST", u))
    except Exception as e: print(f"  {u:48} -> EXC {type(e).__name__}")
print("== no base URL")
c = PerRequestAuthClient(guarded_routes=KILLSWITCH_GUARDED, transport=httpx.MockTransport(handler))
for u in ["http://ks.test:8005/kill/a","http://evil/kill/a"]: print(f"  {u:34} ->", *hdr(c, "POST", u))
print("== per-call override, follow_redirects, params, stream, send()")
c = mk(B); seen.clear(); c.post("/kill/a", headers={"x-field-operator-key": "other"}); print("  per-call header replaces:", seen[-1].headers.get("x-field-operator-key"))
c2 = PerRequestAuthClient(base_url=B, guarded_routes=KILLSWITCH_GUARDED, follow_redirects=True, trust_env=True, transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "http://evil/x"}) if "evil" not in str(r.url) else httpx.Response(200)))
r = c2.post("/kill/a", follow_redirects=True); print("  redirect with follow_redirects=True ->", r.status_code, "| trust_env:", c2.trust_env, "| follow:", c2.follow_redirects)
seen.clear(); c.post("/kill/a", params={"a": "../x"}); print("  params path:", seen[-1].url.path, "pair:", "x-field-operator-key" in seen[-1].headers)
req = httpx.Request("POST", B + "/kill/a"); seen.clear(); c.send(req); print("  send(prebuilt request) pair:", "x-field-operator-key" in seen[-1].headers, "secret:", "x-field-auth" in seen[-1].headers)
print("== field_core clients _request_auth (own client)")
for tbl, name, m, p in [(REGISTRY_GUARDED,"registry","GET","/agents/abc"),(REGISTRY_GUARDED,"registry","GET","/agents/.."),(REGISTRY_GUARDED,"registry","GET","/agents/a b"),(REGISTRY_GUARDED,"registry","GET","/agents/é"),(REGISTRY_GUARDED,"registry","GET","/agents/a?x=1"),(REGISTRY_GUARDED,"registry","GET","/agents/a%2Fb"),(LEDGER_GUARDED,"ledger","POST","/events"),(LEDGER_GUARDED,"ledger","GET","/events")]:
    h = fc._request_auth(True, m, p, tbl).get("headers", {}); print(f"  {name:8} {m:4} {p:16} ->", "PAIR" if "x-field-operator-key" in h else ("secret" if "x-field-auth" in h else "none"))
