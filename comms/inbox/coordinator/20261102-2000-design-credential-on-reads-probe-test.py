"""Lane 10 probe (C-491): the operator pair (x-field-operator / x-field-operator-key) must be attached only to a guarded
write; the perimeter secret may ride every call. Made-up values. A FAILING case is a read that carries the pair.
Run: FIELD_REPO=<checkout> python -m pytest -q test_credential_on_reads.py"""
import glob, importlib, os, sys
import httpx, pytest
R = os.environ.get("FIELD_REPO", ".")
for sub in glob.glob(os.path.join(R, "packages/*/src")) + glob.glob(os.path.join(R, "services/*/src")): sys.path.insert(0, sub)
OP, KEY, SECRET = "x-field-operator", "x-field-operator-key", "x-field-auth"

@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", "MADE-UP-SHARED")
    monkeypatch.setenv("FIELD_OPERATOR", "svc-made-up")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", "MADE-UP-KEY")
    monkeypatch.delenv("FIELD_OPERATOR_KEY_FILE", raising=False)

def capture():
    seen = []
    def handler(req):
        seen.append(dict(req.headers)); return httpx.Response(200, json=[] if req.url.path.endswith("s") else {"agent_id": "a", "status": "active"})
    return seen, httpx.MockTransport(handler)

def test_field_core_registry_client_read_carries_no_operator_pair():
    clients = importlib.import_module("field_core.clients")
    seen, tr = capture()
    c = clients.RegistryClient(base_url="http://registry.invalid")
    c._client = httpx.Client(transport=tr, base_url="http://registry.invalid")   # same own-client construction path (_own_client True)
    c._own_client = True
    try: c.get_agent("a1")
    except Exception: pass
    assert seen, "no request captured"
    assert OP not in seen[0] and KEY not in seen[0], "registry READ carries the operator pair"
    assert SECRET in seen[0]

def test_field_core_ledger_client_read_carries_no_operator_pair():
    clients = importlib.import_module("field_core.clients")
    seen, tr = capture()
    c = clients.LedgerClient(base_url="http://ledger.invalid", caller=object())
    c._client = httpx.Client(transport=tr, base_url="http://ledger.invalid"); c._own_client = True
    for name in ("events", "read_events", "list_events", "recent"):
        fn = getattr(c, name, None)
        if fn:
            try: fn()
            except Exception: pass
            break
    if not seen: pytest.skip("no read method found on this LedgerClient")
    assert OP not in seen[0] and KEY not in seen[0], "ledger READ carries the operator pair"

def test_lifecycle_client_read_carries_no_operator_pair():
    api = importlib.import_module("lifecycle_manager.api")
    seen, tr = capture()
    c = api.PerRequestAuthClient(base_url="http://delegation.invalid", transport=tr)
    c.get("/tokens")
    assert OP not in seen[0] and KEY not in seen[0], "lifecycle READ carries the operator pair"

def test_ops_console_service_client_never_carries_the_operator_pair():
    api = importlib.import_module("ops_console.api")
    h = api._console_headers()
    assert OP not in h and KEY not in h

def test_the_cli_pattern_is_guarded():
    cli = importlib.import_module("kill_switch.cli")
    seen, tr = capture()
    c = httpx.Client(transport=tr, headers=cli._perimeter(), auth=cli.GuardedOperatorAuth("http://ks.invalid", ("svc", "MADE-UP-KEY")))
    c.get("http://ks.invalid/agents")
    assert OP not in seen[0] and KEY not in seen[0]
