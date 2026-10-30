"""The internal-host predicate for a configured base URL.

C-489 (``field_core.hosts.is_internal_host``) is not on main yet. When it is, this module uses it and the local fallback
below is deleted (the test ``test_hosts_predicate`` pins the same corpus against whichever one is active). The fallback
is stricter than ``ipaddress.is_private``: only loopback, RFC 1918, ``::1`` and unique-local addresses, in their canonical
spelling, and ``localhost``. A numeric spelling that inet_aton would turn into another address (decimal, hex, octal,
short forms) is refused, never normalised.
"""
from __future__ import annotations

import ipaddress

try:  # pragma: no cover - exercised once C-489 is on main
    from field_core.hosts import is_internal_host as _core

    def is_internal_host(host: str | None) -> bool:
        return _core(host, allow_names=False)

    SOURCE = "field_core.hosts"
except ImportError:
    SOURCE = "local fallback (C-489 not on main)"

    _NETS = tuple(ipaddress.ip_network(n) for n in (
        "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7"))

    def is_internal_host(host: str | None) -> bool:
        host = (host or "").lower()
        if host == "localhost":
            return True
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False
        if ip.version == 6 and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        return any(ip.version == n.version and ip in n for n in _NETS)
