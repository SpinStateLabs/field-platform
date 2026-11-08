"""S11-5: a malformed FORCE_GATEWAY_URL / ANTHROPIC_BASE_URL is the documented fail-closed refusal.

`urlparse('http://[::1')` raises ValueError and `httpx.Client(base_url=...)` raises httpx.InvalidURL for a port out of
range; the three platform callers (crosswalk suggestions, sentinel judge, gateway hygiene judge) catch only
InsecureBaseURLError, so one typo in an estate variable became an uncaught ValueError at judge construction.
`cleartext_ok` is now False for such a value and `make_http_client` raises InsecureBaseURLError with a fixed text that
names the deciding variable and never the URL (it may hold credentials).
"""
from __future__ import annotations

import httpx
import pytest

from field_core import llm

KEY = "sk-test-key-0000"
BAD = ["http://[::1", "http://[abc", "http://h:99999999999", "forcegw:8080", "http://"]
SECRETISH = "http://user:SECRETISH@[::1"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (llm.GATEWAY_URL_ENV, llm.BASE_URL_ENV, llm.REQUIRE_TLS_ENV, "FIELD_SHARED_SECRET"):
        monkeypatch.delenv(var, raising=False)
    llm._warned.clear()


@pytest.mark.parametrize("base", BAD + [SECRETISH])
def test_cleartext_ok_is_false_for_a_malformed_value_and_never_raises(base):
    assert llm.cleartext_ok(base) is False


@pytest.mark.parametrize("var", [llm.GATEWAY_URL_ENV, llm.BASE_URL_ENV])
@pytest.mark.parametrize("base", BAD + [SECRETISH])
def test_make_http_client_raises_the_named_refusal_never_a_value_error(monkeypatch, var, base):
    monkeypatch.setenv(var, base)
    with pytest.raises(llm.InsecureBaseURLError) as exc:
        llm.make_http_client(KEY)
    text = str(exc.value)
    assert var in text
    assert KEY not in text and "SECRETISH" not in text and "user" not in text
    for piece in ("[::1", "[abc", "99999999999", "forcegw", "8080", "://"):
        assert piece not in text, piece


@pytest.mark.parametrize("var", [llm.GATEWAY_URL_ENV, llm.BASE_URL_ENV])
def test_the_refusal_is_a_runtime_error_the_callers_already_catch(monkeypatch, var):
    monkeypatch.setenv(var, "http://[::1")
    with pytest.raises(RuntimeError):
        llm.make_http_client(KEY)
    assert issubclass(llm.InsecureBaseURLError, RuntimeError)


def test_the_deciding_variable_is_named_when_both_are_set(monkeypatch):
    """FORCE_GATEWAY_URL wins over ANTHROPIC_BASE_URL (anthropic_base_url), so it is the one named."""
    monkeypatch.setenv(llm.GATEWAY_URL_ENV, "http://[::1")
    monkeypatch.setenv(llm.BASE_URL_ENV, "https://api.anthropic.com")
    with pytest.raises(llm.InsecureBaseURLError) as exc:
        llm.make_http_client(KEY)
    assert llm.GATEWAY_URL_ENV in str(exc.value) and llm.BASE_URL_ENV not in str(exc.value)


def test_a_port_out_of_range_is_refused_before_httpx(monkeypatch):
    """`http://h:99999999999` parses (single-label host), so `cleartext_ok` used to say True; reading `.port` raises
    ValueError. (httpx 0.28 builds a client for it without complaint, so the refusal cannot lean on httpx.)"""
    monkeypatch.setenv(llm.BASE_URL_ENV, "http://h:99999999999")
    assert llm.cleartext_ok("http://h:99999999999") is False
    assert llm.cleartext_ok("http://h:65535") is True
    with pytest.raises(llm.InsecureBaseURLError):
        llm.make_http_client(KEY)


@pytest.mark.parametrize("exc", [httpx.InvalidURL("SECRETISH"), ValueError("SECRETISH")])
@pytest.mark.parametrize("var", [llm.GATEWAY_URL_ENV, llm.BASE_URL_ENV])
def test_an_httpx_construction_error_is_the_same_named_refusal(monkeypatch, var, exc):
    """Defence in depth: a base URL httpx itself refuses (some other malformed value or another httpx version)."""
    monkeypatch.setenv(var, "https://api.example.test")

    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(httpx, "Client", boom)
    with pytest.raises(llm.InsecureBaseURLError) as e:
        llm.make_http_client(KEY)
    assert var in str(e.value) and "SECRETISH" not in str(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__ is True


def test_a_valid_internal_and_a_valid_https_base_url_still_build_a_client(monkeypatch):
    monkeypatch.setenv(llm.BASE_URL_ENV, "https://api.anthropic.com")
    assert llm.make_http_client(KEY) is not None
    monkeypatch.setenv(llm.GATEWAY_URL_ENV, "http://forcegw:8009")
    assert llm.make_http_client(KEY) is not None


def test_the_existing_refusal_for_an_external_cleartext_host_still_names_the_host(monkeypatch):
    monkeypatch.setenv(llm.GATEWAY_URL_ENV, "http://gw.example.test:8009")
    with pytest.raises(llm.InsecureBaseURLError) as exc:
        llm.make_http_client(KEY)
    assert "gw.example.test" in str(exc.value)


@pytest.mark.parametrize("var", [llm.GATEWAY_URL_ENV, llm.BASE_URL_ENV])
@pytest.mark.parametrize("base", ["ftp://gw.example.test", "file:///etc/passwd", "ws://box.local:9"])
def test_a_non_http_scheme_is_the_fixed_named_refusal(monkeypatch, var, base):
    monkeypatch.setenv(var, base)
    with pytest.raises(llm.InsecureBaseURLError) as exc:
        llm.make_http_client(KEY)
    text = str(exc.value)
    assert var in text and "gw.example.test" not in text and "passwd" not in text and "box.local" not in text
