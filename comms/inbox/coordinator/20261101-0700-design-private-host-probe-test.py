"""Lane 10 probe: 'is this URL's host estate-internal?' is implemented in several places with different rules.
Each test asserts the INVARIANT; a FAILING case is a miss of that implementation. Made-up values only.
Run: FIELD_REPO=<checkout> python -m pytest -q test_private_host_class.py"""
import importlib, ipaddress, os, sys, socket
from urllib.parse import urlparse, urlsplit
import pytest
R = os.environ.get("FIELD_REPO", ".")
import glob
for sub in glob.glob(os.path.join(R, "packages/*/src")) + glob.glob(os.path.join(R, "services/*/src")): sys.path.insert(0, sub)
llm = importlib.import_module("field_core.llm")
fc = importlib.import_module("field_agent.field_client")

def tools_style(host):          # tools/renew_token.py:1561, estate_probe.py:978, phase_g_check.py:797 (same expression)
    try: return ipaddress.ip_address(host).is_loopback or ipaddress.ip_address(host).is_private
    except ValueError: return host == "localhost"
def gateway_style(host):        # services/force-gateway/src/force_gateway/api.py:184
    try: return ipaddress.ip_address(host).is_private or host == "localhost"
    except ValueError: return host == "localhost"
def of(fn_url):                 # adapt a host predicate to a URL
    return lambda url: fn_url(urlparse(url).hostname or "")

IMPLS = {
 "llm.cleartext_ok": lambda url: llm.cleartext_ok(url),
 "field_client._private_host": of(fc._private_host),
 "tools_style (renew_token/estate_probe/phase_g_check)": of(tools_style),
 "gateway_style (force-gateway api.py:184)": of(gateway_style),
}
# URLs that must be REFUSED by every implementation (public, or not a host the check validated)
PUBLIC = [
 "http://8.8.8.8/", "http://134744072/", "http://0x08080808/", "http://01001001010/", "http://8.8.2056/",
 "http://[::ffff:8.8.8.8]/", "http://[2001:4860:4860::8888]/", "http://[64:ff9b::808:808]/",   # NAT64 of a public v4
 "http://100.64.0.1/", "http://192.0.0.1/", "http://198.18.0.1/", "http://0.0.0.0/", "http://0.1.2.3/",
 "http://255.255.255.255/", "http://169.254.169.254/", "http://[fe80::1]/", "http://[::]/", "http://[2002:808:808::]/",
 "http://127.0.0.1.evil.test/", "http://localhost.evil.test/", "http://127.0.0.1@evil.test/", "http://evil.test#@127.0.0.1/",
 "http://127.0.0.1%2f@evil.test/", "http://local/",
]
BY_DESIGN = {"http://198.18.0.1/", "http://0.0.0.0/", "http://0.1.2.3/", "http://255.255.255.255/", "http://169.254.169.254/",
             "http://[fe80::1]/", "http://[::]/", "http://local/", "http://192.0.0.1/"}   # accepted per coordinator ruling (C-197 F-C197-2, C-213); xfail documents them
URLS = [pytest.param(u, marks=pytest.mark.xfail(reason="ruled by design, see note", strict=False)) if u in BY_DESIGN else u for u in PUBLIC]
NEW = ["http://[2002:808:808::]/"]   # 6to4 of a public v4: NOT in the rulings
URLS = [pytest.param(u, marks=pytest.mark.xfail(strict=False)) if False else u for u in URLS]
@pytest.mark.parametrize("name", sorted(IMPLS))
@pytest.mark.parametrize("url", URLS)
def test_refuses(name, url):
    assert not IMPLS[name](url), f"{name} ACCEPTS {url}"

@pytest.mark.parametrize("name", sorted(IMPLS))
@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://10.1.2.3/", "http://[::1]/", "http://localhost/"])
def test_accepts_the_legitimate(name, url):
    assert IMPLS[name](url), f"{name} refuses {url}"

def test_parser_differential_hostname_is_the_connected_host():
    """what urlparse validates must equal what the HTTP library connects to"""
    httpx = pytest.importorskip("httpx")
    bad = []
    for url in PUBLIC + ["http://127.0.0.1:80@evil.test/", "http://127.0.0.1 .evil.test/", "http://127.0.0.1\t.evil.test/"]:
        h1 = (urlparse(url).hostname or "").lower()
        try: from urllib.parse import unquote; h2 = unquote(httpx.URL(url).host).lower()
        except Exception: continue
        if h1 and h1 != h2: bad.append((url, h1, h2))
    assert not bad, f"urlparse host != httpx host: {bad}"
