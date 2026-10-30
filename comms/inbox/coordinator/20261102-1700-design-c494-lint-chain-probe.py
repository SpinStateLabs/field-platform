import sys, importlib.util
sys.path.insert(0, "/tmp/pr295b/tools/tests")
s = importlib.util.spec_from_file_location("lint", "/tmp/pr295b/tools/tests/test_http_env_proxy_lint_c57.py"); m = importlib.util.module_from_spec(s); sys.modules["lint"]=m; s.loader.exec_module(m)
def flagged(src, unsafe=frozenset()): return sum(m.scan_source(src, unsafe).values())
def texts(**kw): return sum(m.scan_texts(kw).values())
T = {
 "subclass of subclass (same file)": ("import httpx\nclass A(httpx.Client): pass\nclass B(A): pass\nB()\n", 1),
 "subclass of subclass, instantiate only B": ("import httpx\nclass A(httpx.Client):\n    def __init__(self):\n        super().__init__(trust_env=False)\nclass B(A): pass\nB()\n", 0),
 "alias of alias": ("import httpx\nK = httpx.Client\nL = K\nL()\n", 1),
 "alias via tuple unpack": ("import httpx\nK, X = httpx.Client, 1\nK()\n", 1),
 "alias in class attr": ("import httpx\nclass H:\n    factory = httpx.Client\n    def go(self):\n        return self.factory()\n", 1),
 "subclass with __init__ overriding trust_env=True": ("import httpx\nclass A(httpx.Client):\n    def __init__(self):\n        super().__init__(trust_env=True)\nA()\n", 1),
 "subclass pops trust_env but passes via **kw": ("import httpx\nclass A(httpx.Client):\n    def __init__(self, **kw):\n        super().__init__(**kw)\nA()\n", 1),
 "subclass via httpx.Client.__init__(self)": ("import httpx\nclass A(httpx.Client):\n    def __init__(self):\n        httpx.Client.__init__(self)\nA()\n", 1),
 "metaclass/type() dynamic subclass": ("import httpx\nA = type('A', (httpx.Client,), {})\nA()\n", 1),
 "AsyncClient subclass": ("import httpx\nclass A(httpx.AsyncClient): pass\nA()\n", 1),
 "from httpx import Client as C; subclass": ("from httpx import Client as C\nclass A(C): pass\nA()\n", 1),
 "lambda factory": ("import httpx\nmk = lambda: httpx.Client()\nmk()\n", 1),
 "default arg factory": ("import httpx\ndef f(factory=httpx.Client):\n    return factory()\n", 1),
 "injected param named client is fine": ("def f(client):\n    return client.get('x')\n", 0),
 "httpx.Client with trust_env=False + later transport": ("import httpx\nhttpx.Client(trust_env=False, transport=None)\n", 0),
 "trust_env=False passed positionally impossible (kw-only)": ("import httpx\nhttpx.get('http://x', trust_env=False)\n", 0),
 "ternary trust_env": ("import httpx\nhttpx.Client(trust_env=False if 1 else True)\n", 1),
 "trust_env=not True": ("import httpx\nhttpx.Client(trust_env=not True)\n", 1),
}
bad = 0
for k,(src,want) in T.items():
    got = flagged(src); ok = (got >= 1) == bool(want)
    bad += not ok
    print(f"{'ok  ' if ok else 'MISS'} flagged={got} want={'>=1' if want else 0}  {k}")
print("misses", bad)
# repo level
a = m.parse_allowlist(open("/tmp/pr295b/tools/tests/http_env_proxy_allowlist.txt").read()); f = m.scan_repo()
print("allowlist keys", len(a), "sites", sum(a.values()), "scan sites", sum(f.values()), "problems", m.problems(f, a))
print("lifecycle sites flagged:", [k for k in f if "lifecycle_manager/api.py" in k])
