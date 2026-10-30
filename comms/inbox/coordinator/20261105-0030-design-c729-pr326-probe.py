import sys, json, logging, httpx
sys.path.insert(0, "/tmp/pr326c/packages/field-agent/tests")
from field_agent.errors import HeartbeatUnreachable, NoSpendCapError, UsageReportError
from field_agent.federation import CrossingBlocked, FederationClient
from field_agent.liveness import LivenessClient
from field_agent.usage import UsageClient
from test_federation_sdk import COUNTERPARTY, DATA_CLASS, OUR_AGENT, SCOPE, Canned, our_manifest
import test_sdk_errors_c642 as T
MARK = "ZZ-MADEUP-MARK-91"; BIG = MARK + "y" * 5000
class Up:
    def __init__(self, status, content=None, exc=None, headers=None): self.status, self.content, self.exc, self.headers = status, content, exc, headers or {}
    def _r(self, verb, url):
        if self.exc: raise self.exc
        return httpx.Response(self.status, content=self.content, headers=self.headers, request=httpx.Request(verb, url))
    def get(self, url, **kw): return self._r("GET", url)
    def post(self, url, **kw): return self._r("POST", url)
def chain(e):
    seen, todo = [], [e]
    while todo:
        x = todo.pop()
        if x is None or any(x is s for s in seen): continue
        seen.append(x); todo += [x.__cause__, x.__context__]
    return seen
def leaks(exc):
    out = []
    for e in chain(exc):
        for t in (str(e), repr(e), repr(e.args), repr(getattr(e, "__dict__", {}))):
            if MARK in t: out.append(type(e).__name__)
    return sorted(set(out))
def call_site(site, up):
    if site == "heartbeat": return lambda: LivenessClient(client=up, base_url="http://kill.invalid").heartbeat("a")
    if site == "checkin": return lambda: LivenessClient(client=up, base_url="http://kill.invalid").checkin("a")
    if site == "usage": return lambda: UsageClient(client=up, base_url="http://gov.invalid").report("a", "claude-haiku-4-5", 10, 10)
    if site == "spend": return lambda: UsageClient(client=up, base_url="http://gov.invalid").spend("a", cents=5)
    if site == "cross": return lambda: FederationClient(client=up, base_url="http://fed.invalid").cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
rows = []
ran = {}
from collections import Counter
ran = Counter()
for site in ("heartbeat", "checkin", "usage", "spend", "cross"):
    for status in (200, 204, 302, 400, 401, 403, 404, 500, 502, 503):
        for kind, content, headers in (("text", BIG.encode(), {}), ("json-detail", json.dumps({"detail": BIG}).encode(), {}), ("bad-utf8", b"\xff\xfe" + BIG.encode(), {}), ("marker-in-header", b"", {"X-Detail": BIG}), ("200-json-field", json.dumps({"decision": "BLOCK", "reasons": [BIG], "clause_id": BIG}).encode(), {})):
            try: fn = call_site(site, Up(status, content, headers=headers)); fn(); ran[(site, "no exception")] += 1
            except (HeartbeatUnreachable, NoSpendCapError, UsageReportError, CrossingBlocked) as e:
                ran[(site, "sdk exception")] += 1
                l = leaks(e)
                if l: rows.append((site, status, kind, l, len(str(e))))
            except Exception as e: ran[(site, "OTHER " + type(e).__name__)] += 1
print("outcomes:", dict(ran))
print("leaking combinations:", len(rows))
for r in rows[:12]: print(" ", r)
# transport-error text
for site, exc in (("heartbeat", httpx.ConnectError("conn refused to http://10.0.0.1:8003/x")), ("usage", httpx.ReadTimeout("t/o http://10.0.0.1:8002")), ("cross", httpx.ConnectError("conn http://10.0.0.1:8009"))):
    try: call_site(site, Up(0, exc=exc))()
    except Exception as e: print("transport", site, "->", str(e)[:120])
