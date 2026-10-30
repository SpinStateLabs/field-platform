import sys, threading, time
sys.path.insert(0, "/tmp/pr349/services/delegation-authority/tests")
import tempfile, pathlib
from test_revoke_c625 import *   # reuse fixtures' imports
def build(tmp, ledger_wrap=None, store=None):
    registry = TestClient(create_registry_app(store=RegistryStore(tmp / "agents.sqlite3")))
    lh = TestClient(create_ledger_app(store=LedgerStore(tmp / "events.jsonl")))
    ledger = LedgerClient(client=lh, base_url="http://testserver")
    store = store or TokenStore(tmp / "tokens.sqlite3")
    app = create_delegation_app(store=store, ledger=(ledger_wrap(ledger) if ledger_wrap else ledger),
                                registry=RegistryClient(client=registry, base_url="http://testserver"))
    registry.post("/agents", json={"agent_id": "invoicing-agent", "name": "Invoice Copilot", "owner": "Controller", "domain": "finance"})
    return TestClient(app), app, store, lh, ledger
def mint_(c):
    return c.post("/tokens", json={"agent_id":"invoicing-agent","granted_by":"Controller","scope":["read timesheets"],"ttl_seconds":3600}).json()["token_id"]
ev = lambda lh: [e["payload"]["revocation_id"] for e in lh.get("/events", params={"event_type":"delegation.revoke"}).json()]

# 1. crash between ledger append and store write, then retry
class CrashStore(TokenStore):
    boom = True
    def save_revoked(self, t):
        if CrashStore.boom: CrashStore.boom = False; raise RuntimeError("crash after ledger")
        return super().save_revoked(t)
tmp = pathlib.Path(tempfile.mkdtemp())
c, app, st, lh, led = build(tmp, store=CrashStore(tmp/"t.sqlite3"))
tid = mint_(c)
try: r1 = c.post(f"/tokens/{tid}/revoke").status_code
except Exception as e: r1 = f"raised {type(e).__name__}"
print("1 first revoke:", r1, "| status after crash:", c.post("/introspect", json={"token_id":tid}).json()["status"])
r2 = c.post(f"/tokens/{tid}/revoke"); print("  retry:", r2.status_code, "| events:", len(ev(lh)), "distinct ids:", len(set(ev(lh))), "| stored id is one of them:", r2.json().get("revocation_id") in ev(lh))

# 2. two processes (two apps, one store file, one ledger) revoking the same token
tmp = pathlib.Path(tempfile.mkdtemp())
c1, a1, st1, lh, led = build(tmp, ledger_wrap=lambda l: SlowLedger(l, 0.3))
st2 = TokenStore(tmp/"tokens.sqlite3")
registry2 = TestClient(create_registry_app(store=RegistryStore(tmp / "agents.sqlite3")))
a2 = create_delegation_app(store=st2, ledger=SlowLedger(led, 0.3), registry=RegistryClient(client=registry2, base_url="http://testserver"))
c2 = TestClient(a2)
tid = mint_(c1); out = []
ts = [threading.Thread(target=lambda c=c: out.append(c.post(f"/tokens/{tid}/revoke").json().get("revocation_id"))) for c in (c1, c2)]
[t.start() for t in ts]; [t.join() for t in ts]
print("2 returned ids:", len(set(out)), "distinct | ledger events:", len(ev(lh)), "| stored:", st1.get(tid).revocation_id in ev(lh), "| ids returned equal:", out[0]==out[1])

# 3. lock scope: a slow ledger blocks a revoke of a DIFFERENT token in the same process
tmp = pathlib.Path(tempfile.mkdtemp())
c, app, st, lh, led = build(tmp, ledger_wrap=lambda l: SlowLedger(l, 1.0))
a, b = mint_(c), mint_(c)
t0 = time.perf_counter(); times = {}
def go(name, t):
    c.post(f"/tokens/{t}/revoke"); times[name] = round(time.perf_counter() - t0, 2)
th = [threading.Thread(target=go, args=(n, t)) for n, t in (("A", a), ("B", b))]
[x.start() for x in th]; [x.join() for x in th]; print("3 two different tokens, ledger 1.0s each:", times)

# 4. introspection of unknown / revoked / padded / case-changed ids
tmp = pathlib.Path(tempfile.mkdtemp()); c, app, st, lh, led = build(tmp); tid = mint_(c); c.post(f"/tokens/{tid}/revoke")
for label, v in (("revoked", tid), ("unknown", "nope"), ("padded", " "+tid), ("upper", tid.upper()), ("trail-nl", tid+"\n")):
    j = c.post("/introspect", json={"token_id": v}).json(); o = c.post("/oauth/introspect", data={"token": v}, headers=FORM).json()
    print("4", label, "| /introspect:", j["status"], "|", j.get("reason"), "| oauth:", o)
