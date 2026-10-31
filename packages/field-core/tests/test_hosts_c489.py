"""C-489 (Lane 10 note class A): ONE answer to "is this host estate-internal?".

The set is this repository's own (loopback, RFC 1918, ::1, fc00::/7), never ``ipaddress.is_private``: the
cloud-metadata address, 0.0.0.0/8, the broadcast address, the benchmark range, 192.0.0.0/24, ``::``, 6to4 and
fe80::/10 are refused (Don's ruling on C-488, 2026-11-02).
"""
from __future__ import annotations

import pytest

from field_core.hosts import is_internal_host

IP_ACCEPT = ["127.0.0.1", "10.1.2.3", "172.16.0.1", "172.31.255.255", "192.168.1.1",
             "::1", "fd00::1", "fc00::1", "::ffff:10.0.0.1", "::ffff:127.0.0.1", "::1%25eth0"]
# Don's ruling (2026-11-05, C-880 C1): canonical dotted quad only; every inet_aton short, hex, octal or decimal
# spelling is refused, internal or not.
SHORT_FORM_REFUSE = ["127.1", "127.0.1", "10.1", "10.0.1", "192.168.1", "0x0a.1", "0x7f.1", "0xa000001",
                     "0x7f000001", "2130706433", "017700000001", "010.0.0.1", "0177.0.0.1"]
IP_REFUSE = ["169.254.169.254", "169.254.0.1", "0.0.0.0", "0.1.2.3", "255.255.255.255", "198.18.0.1",
             "198.19.255.255", "192.0.0.1", "::", "2002:808:808::", "fe80::1", "8.8.8.8", "134744072",
             "0x08080808", "01001001010", "172.32.0.1", "172.15.255.255", "::ffff:8.8.8.8", "64:ff9b::808:808",
             "100.64.0.1", "2001:4860:4860::8888", "[2001:4860:4860::8888]", "::ffff:169.254.169.254", "127.0.0.1.", "", None]
NAME_ACCEPT = ["localhost", "LOCALHOST", "forcegw", "svc.internal", "x.local", "db", "dead"]
# Don's ruling (2026-11-05, C-880 C3): cloud-metadata host names are never internal, even with names allowed
METADATA_REFUSE = ["metadata", "METADATA", "metadata.google.internal", "Metadata.Google.Internal"]
# F-C696-1: a non-ASCII dot or digit must not turn a public address into one "single label"
UNICODE_REFUSE = ["8。8。8。8", "8．8．8．8", "8｡8｡8｡8", "８.８.８.８",
                  "127。0。0。1", "svc。example", "café"]
# C-794 objection 4: brackets without a colon and a trailing dot must not pass as names (two survivors)
# C-897 C2: an all-digit single label is read by inet_aton as a number, so it is refused as a name too
NAME_REFUSE = UNICODE_REFUSE + ["10", "0", "1234", "[svc]", "[a]", "[10]", "localhost.", "svc.", "[::1]", "a b", "svc/x", "svc:80", "example.com", "local.evil.com", "127.0.0.1 .evil.test", "a.internal.example.com"]


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


@pytest.mark.parametrize("host", SHORT_FORM_REFUSE + METADATA_REFUSE)
@pytest.mark.parametrize("names", [True, False])
def test_short_forms_and_metadata_names_are_refused(host, names):
    assert is_internal_host(host, allow_names=names) is False


# C-1047 F-C1047-1: the digit-only rule is exactly "inet_aton reads it as a number". "08", "09" and "0999" are
# not valid octal, so inet_aton raises and they stay valid single-label names; the docstring says so.
@pytest.mark.parametrize("host", ["08", "09", "0999"])
def test_a_digit_label_inet_aton_rejects_stays_a_valid_name(host):
    assert is_internal_host(host) is True
    assert is_internal_host(host, allow_names=False) is False


@pytest.mark.parametrize("host", ["10", "1234", "0", "007", "0177"])
def test_a_digit_label_inet_aton_reads_as_a_number_is_refused_as_a_name(host):
    assert is_internal_host(host) is False


def test_the_docstring_names_the_digit_labels_inet_aton_rejects():
    assert "08" in is_internal_host.__doc__ and "0999" in is_internal_host.__doc__


# C-1047 F-C1047-3: ipaddress takes a scope id since Python 3.9, raw and percent-encoded; the answer follows the
# address behind it, on every CI Python (3.11 to 3.14).
@pytest.mark.parametrize("host, internal", [
    ("::1%eth0", True), ("::1%25eth0", True), ("fe80::1%eth0", False), ("fe80::1%25eth0", False),
    ("fd00::1%eth0", True), ("2001:4860:4860::8888%eth0", False),
])
def test_a_scope_id_follows_the_address_behind_it_raw_and_encoded(host, internal):
    assert is_internal_host(host) is internal
    assert is_internal_host(host, allow_names=False) is internal
