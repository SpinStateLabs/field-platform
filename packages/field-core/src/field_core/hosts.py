"""The one answer to "is this host estate-internal?" (C-489, design note class A, Don's ruling on C-488).

A cleartext request that carries a platform secret may go only to a host that is a literal address in this
repository's own set, or (when ``allow_names``) a name the estate defines. "Private" is NOT
``ipaddress.is_private``: that accepts the cloud-metadata address (inside 169.254/16), 0.0.0.0/8, the broadcast
address, 198.18.0.0/15, 192.0.0.0/24, ``::``, 6to4 and fe80::/10, all of which are refused here.
"""
from __future__ import annotations

import ipaddress
import re
import socket

_NUMERIC_HOST = re.compile(r"[0-9a-fA-FxX.]+")
_NAME_CHARS = re.compile(r"[a-z0-9._-]+")
METADATA_NAMES = frozenset({"metadata", "metadata.google.internal"})

#: loopback, RFC 1918, ::1, unique-local. Nothing else is internal.
INTERNAL_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7"))


def _address_internal(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip.version == n.version and ip in n for n in INTERNAL_NETWORKS)


def _name_internal(host: str, allow_names: bool) -> bool:
    if not _NAME_CHARS.fullmatch(host):
        return False                      # a bracketed address, a space, a slash: not a host name
    if host == "localhost":
        return True
    if host in METADATA_NAMES:
        return False                      # Don's ruling 2026-11-05 (C-880 C3): never internal, by name either
    return allow_names and ("." not in host or host.endswith((".internal", ".local")))


def is_internal_host(host: str | None, *, allow_names: bool = True) -> bool:
    """True for a loopback / RFC 1918 / ``::1`` / ``fc00::/7`` address (canonical spelling only: an IPv4
    short, hex, octal or decimal form is refused), ``localhost``, and, with ``allow_names``, a single-label name (a compose service), ``.internal`` or
    ``.local``. Everything else, including the empty host and the cloud-metadata names ``metadata`` and
    ``metadata.google.internal``, is False.

    Names are trusted by SHAPE and never resolved (a compose service name is not known statically): a
    single-label name, ``*.internal`` or ``*.local`` that the estate's resolver sends elsewhere would pass.
    That is why the tools and the field-agent client call it with ``allow_names=False``. A numeric-looking
    label that inet_aton rejects (``db``, ``dead``) stays a valid service name on purpose, and so does a digit
    label that is not valid octal (``08``, ``09``, ``0999``); a digit label inet_aton READS as a number
    (``10``, ``1234``, ``0177``) is refused, so name no compose service with such digits. Only the two metadata names are denied by name (``instance-data`` and other aliases are not). Names may use ASCII
    ``[a-z0-9._-]`` only, so a non-ASCII dot or digit cannot turn an address into one label (C-722)."""
    host = (host or "").lower()
    if not host:
        return False
    try:
        return _address_internal(ipaddress.ip_address(host))
    except ValueError:
        pass
    if not _NUMERIC_HOST.fullmatch(host):
        # a name, or something else: glibc inet_aton accepts trailing text ("127.0.0.1 .evil.test"), so it
        # must never see a host with characters outside [0-9a-fx.] (reviewer C-213 F-C213-1).
        return _name_internal(host, allow_names)
    try:
        # inet_aton also reads short (127.1), decimal (134744072), hex (0x08080808) and octal spellings of an
        # IPv4 address (reviewer C-197 F-C197-1). Canonical dotted quad only (Don's ruling 2026-11-05, C-880 C1):
        # whatever inet_aton reads that ip_address did not is refused, internal or not, and never reaches the
        # single-label rule.
        socket.inet_aton(host)
        return False
    except OSError:
        pass
    return _name_internal(host, allow_names)
