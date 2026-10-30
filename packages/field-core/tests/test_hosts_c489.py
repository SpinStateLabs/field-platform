"""C-489 (Lane 10 note class A): ONE answer to "is this host estate-internal?".

The set is this repository's own (loopback, RFC 1918, ::1, fc00::/7), never ``ipaddress.is_private``: the
cloud-metadata address, 0.0.0.0/8, the broadcast address, the benchmark range, 192.0.0.0/24, ``::``, 6to4 and
fe80::/10 are refused (Don's ruling on C-488, 2026-11-02).
"""
from __future__ import annotations

import pytest

from field_core.hosts import is_internal_host

IP_ACCEPT = ["127.0.0.1", "127.1", "10.1.2.3", "10.1", "0x0a.1", "172.16.0.1", "172.31.255.255", "192.168.1.1",
             "0xa000001", "::1", "fd00::1", "fc00::1", "::ffff:10.0.0.1", "::ffff:127.0.0.1", "::1%25eth0"]
IP_REFUSE = ["169.254.169.254", "169.254.0.1", "0.0.0.0", "0.1.2.3", "255.255.255.255", "198.18.0.1",
             "198.19.255.255", "192.0.0.1", "::", "2002:808:808::", "fe80::1", "8.8.8.8", "134744072",
             "0x08080808", "01001001010", "172.32.0.1", "172.15.255.255", "::ffff:8.8.8.8", "64:ff9b::808:808",
             "100.64.0.1", "2001:4860:4860::8888", "[2001:4860:4860::8888]", "::ffff:169.254.169.254", "127.0.0.1.", "", None]
NAME_ACCEPT = ["localhost", "LOCALHOST", "forcegw", "svc.internal", "x.local"]
# F-C696-1: a non-ASCII dot or digit must not turn a public address into one "single label"
UNICODE_REFUSE = ["8。8。8。8", "8．8．8．8", "8｡8｡8｡8", "８.８.８.８",
                  "127。0。0。1", "svc。example", "café"]
# C-794 objection 4: brackets without a colon and a trailing dot must not pass as names (two survivors)
NAME_REFUSE = UNICODE_REFUSE + ["[svc]", "[a]", "[10]", "localhost.", "svc.", "[::1]", "a b", "svc/x", "svc:80", "example.com", "local.evil.com", "127.0.0.1 .evil.test", "a.internal.example.com"]


@pytest.mark.parametrize("host", IP_ACCEPT + NAME_ACCEPT)
def test_internal_hosts_are_accepted(host):
    assert is_internal_host(host) is True


@pytest.mark.parametrize("host", IP_REFUSE + NAME_REFUSE)
def test_everything_else_is_refused(host):
    assert is_internal_host(host) is False


@pytest.mark.parametrize("host", IP_ACCEPT + ["localhost", "LOCALHOST"])
def test_names_off_still_accepts_addresses_and_localhost(host):
    assert is_internal_host(host, allow_names=False) is True


@pytest.mark.parametrize("host", ["forcegw", "svc.internal", "x.local"] + IP_REFUSE + NAME_REFUSE)
def test_names_off_refuses_every_other_name(host):
    assert is_internal_host(host, allow_names=False) is False
