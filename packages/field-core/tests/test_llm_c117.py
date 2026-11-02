"""C-117 (reviewer C-187 F-C187-1/-2): the shared client refuses a cleartext key path to a host
outside the estate and ignores environment proxies; callers cannot build their own client."""

from __future__ import annotations

import pytest

from field_core import llm

KEY = "sk-ant-test-not-a-real-key"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for n in (llm.GATEWAY_URL_ENV, llm.BASE_URL_ENV, llm.SELF_AGENT_ID_ENV, llm.SELF_TOKEN_ID_ENV,
              "FIELD_SHARED_SECRET", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(n, raising=False)


@pytest.mark.parametrize("base", [
    "https://api.anthropic.com", "https://gw.example.test:8009", "HTTPS://Example.test",
    "http://forcegw:8009",                    # a compose service name (integration/demo compose)
    "http://127.0.0.1:8009", "http://localhost:9000", "http://[::1]:9000",
    "http://10.0.2.10:8009", "http://192.168.1.5", "http://172.16.0.9",
    "http://force-gateway.internal:8009", "http://box.local:8009",
])
def test_cleartext_ok_allows_https_and_estate_internal_hosts(base):
    assert llm.cleartext_ok(base)


@pytest.mark.parametrize("base", [
    "http://gw.example.test:8009", "http://plain.example.test:9000", "http://8.8.8.8:80",
    "http://93.184.216.34", "http://api.anthropic.com", "ftp://gw.example.test", "gw.example.test",
    "http://", "", "http://evil.internal.example.test",
    "http://[2001:4860:4860::8888]/", "http://8。8。8。8/", "http://8．8．8．8/", "http://169.254.169.254", "http://169.254.1.1", "http://192.0.2.10:8009",   # C-489: not in the internal set
])
def test_cleartext_ok_refuses_other_http_unknown_schemes_and_empty(base):
    assert not llm.cleartext_ok(base)


def test_make_http_client_refuses_a_plain_http_gateway_outside_the_estate(monkeypatch):
    monkeypatch.setenv(llm.GATEWAY_URL_ENV, "http://gw.example.test:8009")
    monkeypatch.setenv("FIELD_SHARED_SECRET", "shared-secret-test-value")
    with pytest.raises(llm.InsecureBaseURLError) as e:
        llm.make_http_client(KEY)
    msg = str(e.value)
    assert "gw.example.test" in msg and KEY not in msg and "shared-secret-test-value" not in msg


def test_a_plain_http_anthropic_base_url_warns_once_and_is_refused_only_on_the_opt_in(
        monkeypatch, caplog):
    """D-17: a plain-http ANTHROPIC_BASE_URL (a documented proxy setup) is warned about, not refused,
    unless FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM=1."""
    monkeypatch.setenv(llm.BASE_URL_ENV, "http://plain.example.test:9000")
    llm._warned.clear()
    with caplog.at_level("WARNING", logger=llm.__name__):
        assert llm.make_http_client(KEY)
        assert llm.make_http_client(KEY)
    warnings = [r for r in caplog.records if "unencrypted" in r.getMessage()]
    assert len(warnings) == 1 and "plain.example.test" in warnings[0].getMessage()
    assert KEY not in warnings[0].getMessage()
    monkeypatch.setenv(llm.REQUIRE_TLS_ENV, "1")
    with pytest.raises(llm.InsecureBaseURLError):
        llm.make_http_client(KEY)


def test_make_http_client_builds_for_the_default_host_and_an_internal_gateway(monkeypatch):
    c = llm.make_http_client(KEY)
    assert str(c.base_url).startswith("https://api.anthropic.com") and c.headers["x-api-key"] == KEY
    monkeypatch.setenv(llm.GATEWAY_URL_ENV, "http://forcegw:8009")
    c = llm.make_http_client(KEY)
    assert str(c.base_url).startswith("http://forcegw:8009")
    assert c.headers[llm.PASSTHROUGH_HEADER] == llm.PASSTHROUGH_JUDGE


def test_make_http_client_ignores_environment_proxies(monkeypatch):
    """F-C187-2: with HTTPS_PROXY and HTTP_PROXY set the old callers' clients held 2 proxy mounts."""
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.test:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example.test:3128")
    assert not llm.make_http_client(KEY)._mounts


def test_the_platform_callers_use_the_shared_client_and_none_builds_its_own():
    """A caller that builds its own httpx.Client for the Messages call would bypass both rules."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[3]
    callers = [
        "services/force-gateway/src/force_gateway/hygiene_judge.py",
        "services/conformance-sentinel/src/conformance_sentinel/judge.py",
        "services/compliance-crosswalk/src/compliance_crosswalk/suggestions.py",
    ]
    for rel in callers:
        text = (root / rel).read_text(encoding="utf-8")
        assert "make_http_client(" in text, rel
        assert "httpx.Client(" not in text, rel


@pytest.mark.parametrize("base", [
    "http://134744072/",           # decimal: 8.8.8.8
    "http://0x08080808/",          # hex: 8.8.8.8
    "http://01001001010/",         # octal: 8.4.2.8
])
def test_numeric_spellings_of_a_public_address_are_not_estate_internal(base):
    """C-207 (reviewer C-197 F-C197-1): these passed the single-label-name rule and resolve to a
    public IP, so the key and the platform headers would have gone to it in clear."""
    assert not llm.cleartext_ok(base)


@pytest.mark.parametrize("base", ["http://forcegw/", "http://svc/", "http://db/", "http://10.0.2.10:8009"])
def test_plain_names_and_canonical_internal_addresses_still_pass(base):
    assert llm.cleartext_ok(base)


@pytest.mark.parametrize("base", ["http://0x7f000001/", "http://2130706433/", "http://0x7f.1/", "http://127.1/",
                                  "http://10.1/", "http://0xa000001/", "http://metadata/",
                                  "http://metadata.google.internal/"])
def test_short_spellings_and_metadata_names_are_refused(base):
    """Don's rulings 2026-11-05 (C-880 C1, C3): canonical dotted quad only; metadata names never internal."""
    assert not llm.cleartext_ok(base)


@pytest.mark.parametrize("base", [
    "http://127.0.0.1 .evil.example.com/",    # glibc inet_aton reads "127.0.0.1" and ignores the rest
    "http://10.0.0.1 .evil.example.com/",
    "http://127.1 .evil.example.com/",
    "http://127.0.0.1 evil/",
    "http://0x7f.1 attacker.example.net:8009/",
])
def test_a_numeric_prefix_followed_by_text_is_a_name_not_an_address(base):
    """C-207 follow-up (reviewer C-213 F-C213-1, PROVEN): httpx sees `127.0.0.1%20.evil.example.com`,
    a DNS name; the allow-list must not read the numeric prefix as an internal address."""
    assert not llm.cleartext_ok(base)


@pytest.mark.parametrize("base", ["http://cafe/", "http://beef:8009/", "http://abc/", "http://dead/",
                                  "http://a.internal/", "http://localhost/"])
def test_single_label_names_made_of_hex_letters_are_still_names(base):
    assert llm.cleartext_ok(base)
