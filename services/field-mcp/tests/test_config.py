"""Credentials and base URL: environment only, one place, internal hosts only. Mutants: C1 predicate swapped for
ipaddress.is_private; C2 userinfo allowed; C3 operator vars read in the read process; C4 key in repr."""
import pathlib
import re

import pytest

from field_mcp import config
from field_mcp.config import ConfigError, load, validate_base_url

BAD = ["http://169.254.169.254", "http://0.0.0.0:80", "http://8.8.8.8", "http://134744072", "http://0x08080808",
       "http://example.com", "http://[::ffff:8.8.8.8]", "http://localhost.evil.test", "http://u:p@127.0.0.1",
       "http://127.0.0.1?x=1", "http://127.0.0.1#f", "ftp://127.0.0.1", "http://", "127.0.0.1", "http://127.1",
       "http://[fe80::1]", "http://198.18.0.1", "http://255.255.255.255", "http://127.0.0.1 .evil.test",
       "https://example.com"]
GOOD = ["http://127.0.0.1:8001", "http://localhost:9", "http://10.1.2.3", "http://192.168.0.5:80/",
        "http://172.16.0.1", "http://[::1]:8000", "http://[fd00::1]"]


@pytest.mark.parametrize("url", BAD)
def test_base_url_refused(url):
    with pytest.raises(ConfigError) as e:
        validate_base_url(url)
    assert url not in str(e.value)


@pytest.mark.parametrize("url", GOOD)
def test_base_url_accepted(url):
    assert validate_base_url(url) == url.rstrip("/")


def test_external_https_needs_the_explicit_setting_and_cleartext_never_passes():
    assert validate_base_url("https://example.com", allow_external_https=True) == "https://example.com"
    with pytest.raises(ConfigError):
        validate_base_url("http://example.com", allow_external_https=True)


def test_load_reads_per_service_variables_and_hides_secrets():
    env = {"FFMCP_KILL_SWITCH_URL": "http://127.0.0.1:1", "FFMCP_KILL_SWITCH_KEY": "k-secret-value",
           "FFMCP_SEALED_LEDGER_URL": "http://127.0.0.1:2"}
    cfg = load(1, env)
    assert set(cfg.services) == {"kill-switch", "sealed-ledger"}
    assert "k-secret-value" not in repr(cfg) and "k-secret-value" not in str(cfg.services)


def test_bad_url_in_the_environment_fails_startup_without_naming_the_value():
    with pytest.raises(ConfigError) as e:
        load(1, {"FFMCP_KILL_SWITCH_URL": "http://8.8.8.8"})
    assert "8.8.8.8" not in str(e.value)


class Watched(dict):
    def __init__(self, *a):
        super().__init__(*a)
        self.read: list[str] = []

    def get(self, k, d=None):
        self.read.append(k)
        return super().get(k, d)


def test_read_process_never_reads_the_operator_pair_or_the_write_flag():
    env = Watched({"FFMCP_OPERATOR": "o", "FFMCP_OPERATOR_KEY": "k", "FFMCP_ENABLE_WRITES": "1"})
    cfg = load(1, env)
    assert not ({"FFMCP_OPERATOR", "FFMCP_OPERATOR_KEY", "FFMCP_ENABLE_WRITES"} & set(env.read))
    assert cfg.operator == "" and cfg.operator_key == ""


W_ENV = {"FFMCP_ENABLE_WRITES": "1", "FFMCP_SEALED_LEDGER_URL": "http://127.0.0.1:1",
         "FFMCP_OPERATOR": "o", "FFMCP_OPERATOR_KEY": "ok-secret"}


def test_write_process_needs_the_flag_and_the_audit_ledger():
    with pytest.raises(ConfigError, match="FFMCP_ENABLE_WRITES"):
        load(2, {"FFMCP_SEALED_LEDGER_URL": "http://127.0.0.1:1"})
    with pytest.raises(ConfigError, match="FFMCP_SEALED_LEDGER_URL"):
        load(2, {"FFMCP_ENABLE_WRITES": "1", "FFMCP_OPERATOR": "o", "FFMCP_OPERATOR_KEY": "ok-secret"})
    cfg = load(2, W_ENV)
    assert cfg.operator == "o" and "ok-secret" not in repr(cfg) and "ok-secret" in cfg.secrets()


@pytest.mark.parametrize("bad", ["x", "0", "601", "-1"])
def test_write_rate_is_a_bounded_integer(bad):
    with pytest.raises(ConfigError):
        load(2, {**W_ENV, "FFMCP_WRITE_RATE_PER_MIN": bad})
    assert load(2, W_ENV).write_rate_per_min == 10 and load(2, {**W_ENV, "FFMCP_WRITE_RATE_PER_MIN": "3"}).write_rate_per_min == 3


def test_read_process_ignores_the_rate_setting():
    env = Watched({"FFMCP_WRITE_RATE_PER_MIN": "x"})
    assert load(1, env).write_rate_per_min == 10 and "FFMCP_WRITE_RATE_PER_MIN" not in env.read


def test_the_environment_is_read_in_config_py_only():
    src = pathlib.Path(config.__file__).parent
    for p in src.glob("*.py"):
        if p.name != "config.py":
            assert not re.search(r"os\.environ|getenv|environ\b", p.read_text()), p.name


def test_no_url_or_credential_is_a_tool_argument():
    from field_mcp.tools import build_specs

    forbidden = {"url", "base_url", "host", "endpoint", "headers", "authorization", "api_key", "key", "secret",
                 "password", "proxy", "operator_key", "x-field-auth"}

    def names(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "properties" and isinstance(v, dict):
                    yield from (n.lower() for n in v)
                yield from names(v)
        elif isinstance(node, list):
            for v in node:
                yield from names(v)

    for s in build_specs(1):
        assert s.input_schema["additionalProperties"] is False, s.name
        assert not (forbidden & set(names(s.input_schema))), s.name


@pytest.mark.parametrize("drop", [("FFMCP_OPERATOR", "FFMCP_OPERATOR_KEY"), ("FFMCP_OPERATOR",), ("FFMCP_OPERATOR_KEY",)])
def test_write_process_refuses_to_start_without_the_whole_operator_pair(drop):
    """A write process with no operator identity would write anonymously (decision, Don 2026-10-31: refuse to start)."""
    env = {k: v for k, v in W_ENV.items() if k not in drop}
    with pytest.raises(ConfigError, match="FFMCP_OPERATOR") as e:
        load(2, env)
    assert "ok-secret" not in str(e.value)


@pytest.mark.parametrize("blank", ["", " ", "\t", "\n"])
@pytest.mark.parametrize("which", ["FFMCP_OPERATOR", "FFMCP_OPERATOR_KEY"])
def test_a_blank_operator_value_counts_as_missing(which, blank):
    with pytest.raises(ConfigError, match="FFMCP_OPERATOR"):
        load(2, {**W_ENV, which: blank})


def test_the_operator_pair_check_comes_before_the_ledger_check_and_never_touches_the_read_process():
    with pytest.raises(ConfigError, match="FFMCP_OPERATOR"):
        load(2, {"FFMCP_ENABLE_WRITES": "1", "FFMCP_SEALED_LEDGER_URL": "http://127.0.0.1:1"})
    assert load(1, {}).operator == ""        # the read process needs no pair
