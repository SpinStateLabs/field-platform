"""Lane 10 probe (C-490): a body returned by another service must not be echoed into an exception message that a
service then relays to ITS caller. Made-up marker only. A FAILING case is a miss.
Run: FIELD_REPO=<checkout> python -m pytest -q test_error_echo_class.py"""
import glob, importlib, os, sys
import httpx, pytest
R = os.environ.get("FIELD_REPO", ".")
for sub in glob.glob(os.path.join(R, "packages/*/src")) + glob.glob(os.path.join(R, "services/*/src")): sys.path.insert(0, sub)
MARK = "MADE-UP-SECRET-1234"
BIG = "x" * 5000

def transport(status, body):
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status, text=body)), base_url="http://svc.invalid")

def raised(fn):
    try: fn()
    except Exception as e: return str(e)
    return None

def cases():
    clients = importlib.import_module("field_core.clients")
    reg = lambda body, st=500: clients.RegistryClient(client=transport(st, body), base_url="http://svc.invalid")
    yield "RegistryClient.get_agent echoes body", lambda b: reg(b).get_agent("a1")
    yield "RegistryClient.list_agents echoes body", lambda b: reg(b).list_agents()
    boot = importlib.import_module("field_agent.bootstrap")
    yield "field_agent.bootstrap register echoes body", lambda b: boot.register_agent(transport(500, b), "http://svc.invalid", "a1", "o", "d", "m") if hasattr(boot, "register_agent") else (_ for _ in ()).throw(RuntimeError("n/a"))

@pytest.mark.parametrize("name,call", list(cases()), ids=[n for n, _ in cases()])
def test_body_marker_is_not_in_the_error(name, call):
    msg = raised(lambda: call(f"detail {MARK}"))
    if msg is None or msg == "n/a": pytest.skip("no error raised / entry point differs")
    assert MARK not in msg, f"upstream body echoed into: {msg[:80]!r}"

@pytest.mark.parametrize("name,call", list(cases()), ids=[n for n, _ in cases()])
def test_error_length_is_bounded(name, call):
    msg = raised(lambda: call(BIG))
    if msg is None or msg == "n/a": pytest.skip("no error raised / entry point differs")
    assert len(msg) < 600, f"{len(msg)} characters of upstream body in the error"
