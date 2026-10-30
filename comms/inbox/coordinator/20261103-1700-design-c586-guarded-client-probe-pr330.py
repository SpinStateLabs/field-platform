import os, sys, glob, httpx
os.environ.update(FIELD_SHARED_SECRET="MADE-UP-SHARED", FIELD_OPERATOR="svc-made-up", FIELD_OPERATOR_KEY="MADE-UP-KEY")
os.environ.pop("FIELD_OPERATOR_KEY_FILE", None)
from field_core import guarded_operator as go
import lifecycle_manager.api as lm
OP="x-field-operator-key"
def carries(headers): return OP in {k.lower() for k in headers}
def via_client(method, url_or_path, base="http://delegation.invalid", routes=go.DELEGATION_GUARDED, **kw):
    seen=[]
    c = lm.PerRequestAuthClient(base_url=base, guarded_routes=routes, transport=httpx.MockTransport(lambda r: (seen.append(dict(r.headers)), httpx.Response(200, json={}))[1]), **kw)
    try: c.request(method, url_or_path)
    except Exception as e: return f"ERR {type(e).__name__}"
    return seen[0] if seen else None
# (label, method, target, must_carry_pair)
T = [
 ("guarded write", "POST", "/tokens", 1), ("guarded write lower-case method", "post", "/tokens", 1),
 ("revoke", "POST", "/tokens/abc/revoke", 1), ("read of the same path", "GET", "/tokens", 0), ("read tokens listing", "GET", "/tokens/abc", 0),
 ("query string on guarded write", "POST", "/tokens?x=1", 1), ("query that looks like a path", "GET", "/health?next=/tokens", 0),
 ("trailing slash on guarded write", "POST", "/tokens/", 0), ("double slash", "POST", "//tokens", 0), ("dot segment", "POST", "/x/../tokens", None),
 ("percent-encoded slash in id", "POST", "/tokens/a%2Fb/revoke", None), ("encoded dot-dot", "POST", "/tokens/%2e%2e/revoke", None),
 ("uppercase path", "POST", "/TOKENS", 0), ("fragment", "POST", "/tokens#frag", 1),
 ("absolute URL, same origin, guarded", "POST", "http://delegation.invalid/tokens", 1),
 ("absolute URL, OTHER host, guarded path", "POST", "http://other.invalid/tokens", 0),
 ("absolute URL, other scheme/port", "POST", "http://delegation.invalid:9999/tokens", 0),
 ("path of another service's guarded route", "POST", "/kill/a1", 0),
 ("PATCH on a POST-only route", "PATCH", "/tokens", 0), ("DELETE", "DELETE", "/tokens/abc/revoke", 0),
]
bad = 0
for label, m, t, want in T:
    h = via_client(m, t)
    if isinstance(h, str) or h is None: print("ERR ", label, h); continue
    got = carries(h); secret = "x-field-auth" in {k.lower() for k in h}
    ok = True if want is None else (got == bool(want)); bad += (not ok)
    print(f"{'ok  ' if ok else 'MISS'} pair={got!s:5} secret={secret!s:5} want={want!s:4} {m:6} {t}   [{label}]")
print("== other-host absolute URL sends the SHARED SECRET to that host?")
h = via_client("GET", "http://other.invalid/anything"); print("   secret to foreign host:", "x-field-auth" in {k.lower() for k in h}, " pair:", carries(h))
print("== base URL with a path prefix")
h = via_client("POST", "/api/tokens", base="http://delegation.invalid/api"); print("   prefix guarded:", carries(h))
h = via_client("POST", "/tokens", base="http://delegation.invalid/api"); print("   prefix wrong path (httpx merges base):", carries(h) if h else None)
print("misses", bad)
