"""base_url guard: alternate spellings of the metadata address are refused, ordinary targets still build (S12-1)."""
import ipaddress

import pytest

from field_core import http

BAD = ["http://0xa9fea9fe/", "http://2852039166/", "http://169.254.43518/", "http://0251.0376.0251.0376/",
       "http://[::ffff:169.254.169.254]/"]
GOOD = ["http://169.254.169.254/", "http://svc.internal:8080/", "http://127.0.0.1:8001", "http://10.0.0.5",
        "http://db/"]
FACTORIES = [lambda **k: http.client(**k), lambda **k: http.async_client(**k)]


def _call(f, url):
    return f(timeout=5, base_url=url)


@pytest.mark.parametrize("f", FACTORIES)
@pytest.mark.parametrize("url", BAD + ["http://169.254.169.254/"])
def test_refused_without_echo(f, url):
    with pytest.raises(ValueError) as e:
        _call(f, url)
    host = url.split("//")[1].strip("/")
    assert host not in str(e.value) and "ffff" not in str(e.value)


@pytest.mark.parametrize("f", FACTORIES)
@pytest.mark.parametrize("url", GOOD[1:])
def test_ordinary_targets_build(f, url):
    assert _call(f, url) is not None


def test_mapped_is_unwrapped_explicitly():
    # the unwrap must not depend on the stdlib flagging the mapped form itself
    a = ipaddress.ip_address("::ffff:169.254.169.254")
    assert a.ipv4_mapped.is_link_local
