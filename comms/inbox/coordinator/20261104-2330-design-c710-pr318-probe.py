import sys, importlib.util
sys.path.insert(0, "/tmp/pr318b/tools/tests")
spec = importlib.util.spec_from_file_location("lint", "/tmp/pr318b/tools/tests/test_http_env_proxy_lint_c57.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
U = "import httpx\nclass U(httpx.Client):\n    pass\n"
cases = {
 # shapes the PR says it catches (controls)
 "alias import as": U + "from m import U as P\nP()\n",
 "K = U": U + "K = U\nK()\n",
 "defaultdict(httpx.Client)": "import httpx\nfrom collections import defaultdict\nd = defaultdict(httpx.Client)\n",
 "cls()": "import httpx\nclass U(httpx.Client):\n    @classmethod\n    def make(cls):\n        return cls()\n",
 # shapes it may still miss
 "AnnAssign K: type = U": U + "K: type = U\nK()\n",
 "tuple unpack A, B = U, U": U + "A, B = U, U\nA()\n",
 "walrus (K := U)()": U + "(K := U)()\n",
 "chained K = L = U": U + "K = L = U\nL()\n",
 "list holds class": U + "L = [U]\nL[0]()\n",
 "dict holds class (documented)": U + "R = {'c': U}\nR['c']()\n",
 "map(U, xs)": U + "list(map(U, [1]))\n",
 "lambda: U()": U + "f = lambda: U()\nf()\n",
 "subclass of subclass": U + "class W(U):\n    pass\nW()\n",
 "subclass of alias": U + "from m import U as P\nclass W(P):\n    pass\nW()\n",
 "type(...) dynamic class": U + "type('X', (U,), {})()\n",
 "self.__class__()": "import httpx\nclass U(httpx.Client):\n    def clone(self):\n        return self.__class__()\n",
 "U.__new__": U + "U.__new__(U)\n",
 "import httpx as h": "import httpx as h\nh.Client()\n",
 "from httpx import Client as C": "from httpx import Client as C\nC()\n",
 "C = httpx.Client; C()": "import httpx\nC = httpx.Client\nC()\n",
 "star import": "from httpx import *\nClient()\n",
 "trust_env=0 (falsy, not False)": "import httpx\nhttpx.Client(trust_env=0)\n",
 "trust_env=flag var": "import httpx\nflag=False\nhttpx.Client(trust_env=flag)\n",
 "**kwargs with trust_env True": "import httpx\nhttpx.Client(**{'trust_env': True})\n",
 "trust_env=not True": "import httpx\nhttpx.Client(trust_env=not True)\n",
 "trust_env=False (control green)": "import httpx\nhttpx.Client(trust_env=False)\n",
 "AsyncClient": "import httpx\nhttpx.AsyncClient()\n",
 "httpx.get module func": "import httpx\nhttpx.get('http://x')\n",
 "requests.get": "import requests\nrequests.get('http://x')\n",
 "requests.Session()": "import requests\nrequests.Session()\n",
 "aiohttp.ClientSession": "import aiohttp\naiohttp.ClientSession()\n",
 "urllib.request.urlopen": "import urllib.request\nurllib.request.urlopen('http://x')\n",
 "urllib build_opener no ProxyHandler": "import urllib.request\nurllib.request.build_opener().open('http://x')\n",
 "getattr(httpx,'Client') (documented)": "import httpx\ngetattr(httpx, 'Client')()\n",
 "importlib (documented)": "import importlib\nimportlib.import_module('httpx').Client()\n",
 "__import__ (documented)": "__import__('httpx').Client()\n",
 "class attr factory in dataclass": U + "from dataclasses import dataclass\n@dataclass\nclass D:\n    k: type = U\n    def go(self):\n        return self.k()\n",
 "decorator returns class": U + "def deco(c):\n    return c\n@deco\nclass V(httpx.Client):\n    pass\nV()\n",
 "metaclass/keyword base": "import httpx\nclass V(httpx.Client, metaclass=type):\n    pass\nV()\n",
 "base via module attr": "import m\nclass V(m.U):\n    pass\nV()\n",
}
for k, src in cases.items():
    try: r = sum(m.scan_source(src, frozenset({"U"})).values())
    except Exception as e: r = f"EXC {type(e).__name__}"
    print(f"{k:42} {'FLAGGED' if r else 'green  '} {r}")
