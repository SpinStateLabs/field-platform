"""Lane 10: evasion spellings for PR 295's lint (test_http_env_proxy_lint_c57.py). A case that FAILS = the lint misses it.
Run: C57=<checkout>/tools/tests python -m pytest -q test_c57_evasions.py"""
import importlib.util, os, sys, pathlib, pytest
p = pathlib.Path(os.environ["C57"]) / "test_http_env_proxy_lint_c57.py"
s = importlib.util.spec_from_file_location("lint", p); m = importlib.util.module_from_spec(s); sys.modules["lint"] = m; s.loader.exec_module(m)
EVADE = {
 "subclass then instantiate": "import httpx\nclass C(httpx.Client):\n    pass\nC(timeout=3)\n",
 "subclass super().__init__": "import httpx\nclass C(httpx.Client):\n    def __init__(self):\n        super().__init__()\nC()\n",
 "class alias then call": "import httpx\nK = httpx.Client\nK()\n",
 "alias in local var": "import httpx\ndef f():\n    k = httpx.Client\n    return k()\n",
 "functools.partial": "import httpx, functools\nmk = functools.partial(httpx.Client, timeout=3)\nmk()\n",
 "getattr": "import httpx\ngetattr(httpx, 'Client')()\n",
 "importlib": "import importlib\nimportlib.import_module('httpx').Client()\n",
 "httpx2 package": "import httpx2\nhttpx2.Client()\n",
 "from httpx2": "from httpx2 import Client\nClient()\n",
 "trust_env via variable": "import httpx\nf = False\nhttpx.Client(trust_env=f)\n",
 "trust_env set after": "import httpx\nc = httpx.Client(trust_env=False)\nc.trust_env = True\n",
 "opener.open on default opener": "import urllib.request\nurllib.request.install_opener(None)\nurllib.request.build_opener().open('http://x')\n",
 "requests": "import requests\nrequests.get('http://x')\n",
 "urllib3": "import urllib3\nurllib3.PoolManager().request('GET','http://x')\n",
 "aiohttp trust_env": "import aiohttp\naiohttp.ClientSession(trust_env=True)\n",
 "relative import of wrapper": "",  # not expressible here
 "ProxyHandler with None": "import urllib.request\nurllib.request.build_opener(urllib.request.ProxyHandler(None))\n",
 "ProxyHandler({}) built apart": "import urllib.request\nh = urllib.request.ProxyHandler({'http':'p'})\nurllib.request.build_opener(h)\n",
 "from httpx import * ": "from httpx import *\nClient()\n",
 "ProxyHandler({}) then add proxy": "import urllib.request\no = urllib.request.build_opener(urllib.request.ProxyHandler({}))\n",
}
@pytest.mark.parametrize("name", [k for k, v in EVADE.items() if v])
def test_lint_flags(name):
    if name == "ProxyHandler({}) then add proxy": pytest.skip("safe shape, control")
    assert sum(m.scan_source(EVADE[name]).values()) >= 1, f"not flagged: {name}"

def test_placement_evasion_dirs():
    """a non-test module under a directory named build/dist/tests, or a file named test_*.py, is never scanned"""
    for part in ("build", "dist", "tests", "venv"):
        assert not m._is_test_file(pathlib.Path("services/x/src") / "x.py") 
        assert not m._is_test_file(pathlib.Path("services/x") / part / "client.py"), f"dir {part} skipped"
    assert not m._is_test_file(pathlib.Path("services/x/src/test_client_factory.py")), "test_ prefix skipped"

def test_syntax_error_does_not_hide_a_file():
    with pytest.raises(SyntaxError):  # control: documents what happens (a crash, not a silent skip)
        m.scan_source("def (:\n")
    assert False, "a file the scanner cannot parse aborts the whole scan (SyntaxError) rather than being reported"

def test_scan_roots_cover_every_top_level_python_dir():
    root = m.ROOT
    dirs = {d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")}
    missing = sorted(d for d in dirs if d not in m.SCAN_ROOTS and any(root.joinpath(d).rglob("*.py")) and d not in {"docs", "tasks", "manifests"})
    assert not missing, f"python outside SCAN_ROOTS: {missing}"
