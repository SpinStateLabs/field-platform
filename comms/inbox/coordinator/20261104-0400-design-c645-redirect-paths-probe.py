import os, sys, glob, httpx
for sub in glob.glob("/tmp/pr318/packages/*/src")+glob.glob("/tmp/pr318/services/*/src"): sys.path.insert(0, sub)
os.environ.update(FIELD_SHARED_SECRET="MADE-UP-SHARED", FIELD_OPERATOR="svc-made-up", FIELD_OPERATOR_KEY="MADE-UP-KEY")
import lifecycle_manager.api as lm
def mk(**kw):
    seen=[]
    def h(req):
        seen.append((req.url.host, "x-field-auth" in req.headers, "x-field-operator-key" in req.headers))
        if req.url.host=="delegation.invalid": return httpx.Response(307, headers={"location":"http://elsewhere.invalid/steal"})
        return httpx.Response(200, json={})
    kw.setdefault("base_url","http://delegation.invalid")
    c = lm.PerRequestAuthClient(transport=httpx.MockTransport(h), **kw); return c, seen
def hosts(seen): return [s[0] for s in seen]
R = {}
c,s = mk(); c.post("/tokens"); R["default"] = hosts(s)
c,s = mk(follow_redirects=True); c.post("/tokens"); R["constructor follow_redirects=True"] = hosts(s)
c,s = mk(); c.post("/tokens", follow_redirects=True) if "follow_redirects" in httpx.Client.post.__code__.co_varnames else None; R["per-call post(follow_redirects=True)"] = hosts(s)
c,s = mk(); c.request("POST","/tokens", follow_redirects=True) if "follow_redirects" in httpx.Client.request.__code__.co_varnames else None; R["per-call request(follow_redirects=True)"] = hosts(s)
c,s = mk(); 
with c.stream("POST","/tokens", follow_redirects=True) as r: pass
R["per-call stream(follow_redirects=True)"] = hosts(s)
c,s = mk(); c.follow_redirects = True; c.post("/tokens"); R["later attribute client.follow_redirects=True"] = hosts(s)
c,s = mk(); req = c.build_request("POST","/tokens"); c.send(req, follow_redirects=True); R["send(request, follow_redirects=True)"] = hosts(s)
c,s = mk(); req = c.build_request("POST","/tokens"); c.send(req, stream=True, follow_redirects=True); R["send(stream=True, follow_redirects=True)"] = hosts(s)
c,s = mk(); c._follow_redirects = True if hasattr(c,"_follow_redirects") else None; c.post("/tokens"); R["private attr _follow_redirects"] = hosts(s)
c,s = mk(); httpx.Client.send(c, c.build_request("POST","/tokens"), follow_redirects=True); R["base-class send via explicit Client.send(c, ...)"] = hosts(s)
import asyncio
for k,v in R.items(): print(("LEAK " if "elsewhere.invalid" in v else "ok   "), f"{k:52} hosts={v}")
