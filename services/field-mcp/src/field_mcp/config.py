"""The one place that reads the process environment (a test greps the package for ``os.environ`` elsewhere).

Per service: ``FFMCP_<SERVICE>_URL`` and ``FFMCP_<SERVICE>_KEY`` (``-`` becomes ``_``). Read once at startup; neither a
URL nor a key ever comes from a tool argument. Tier 2 settings (the write flag and the operator pair) are read ONLY when
the write entry point asks for them, so the read process never loads them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from field_mcp.catalog import SERVICES
from field_mcp.hosts import is_internal_host

ENV_PREFIX = "FFMCP_"
ENV_ENABLE_WRITES = "FFMCP_ENABLE_WRITES"
ENV_ALLOW_EXTERNAL_HTTPS = "FFMCP_ALLOW_EXTERNAL_HTTPS"
ENV_OPERATOR = "FFMCP_OPERATOR"
ENV_OPERATOR_KEY = "FFMCP_OPERATOR_KEY"
ENV_WRITE_RATE = "FFMCP_WRITE_RATE_PER_MIN"
DEFAULT_WRITE_RATE = 10        # proposed default (not measured); Don to set


class ConfigError(Exception):
    """Fixed text naming a variable, never a value."""


def env_name(service: str, what: str) -> str:
    return f"{ENV_PREFIX}{service.replace('-', '_').upper()}_{what}"


@dataclass(frozen=True)
class ServiceConfig:
    base: str
    key: str = field(default="", repr=False)


@dataclass(frozen=True)
class Config:
    tier: int
    services: dict[str, ServiceConfig]
    operator: str = field(default="", repr=False)
    operator_key: str = field(default="", repr=False)
    write_rate_per_min: int = DEFAULT_WRITE_RATE

    def secrets(self) -> tuple[str, ...]:
        return tuple(s for s in [*(c.key for c in self.services.values()), self.operator_key] if s)


def validate_base_url(raw: str, *, allow_external_https: bool = False) -> str:
    """Return the base URL without a trailing slash, or raise ConfigError. A cleartext request that carries a platform
    secret goes only to an internal address (C-488/C-489 rule); https to anything else needs an explicit setting."""
    try:
        parts = urlsplit(raw)
        host, _port = parts.hostname, parts.port
    except ValueError:
        raise ConfigError("base url refused") from None
    if parts.scheme not in ("http", "https") or not host or parts.username or parts.password or parts.query \
            or parts.fragment or any(ord(c) < 33 or ord(c) > 126 for c in raw):
        raise ConfigError("base url refused")
    if not is_internal_host(host):
        if not (parts.scheme == "https" and allow_external_https):
            raise ConfigError("base url refused")
    return raw.rstrip("/")


def load(tier: int = 1, environ: dict[str, str] | None = None) -> Config:
    """Read the configuration for ``tier`` (1 = read process, 2 = write process)."""
    env = os.environ if environ is None else environ
    allow_https = env.get(ENV_ALLOW_EXTERNAL_HTTPS, "") == "1"
    services: dict[str, ServiceConfig] = {}
    for svc in SERVICES:
        url = env.get(env_name(svc, "URL"), "").strip()
        if not url:
            continue
        services[svc] = ServiceConfig(validate_base_url(url, allow_external_https=allow_https),
                                      env.get(env_name(svc, "KEY"), ""))
    operator = operator_key = ""
    rate = DEFAULT_WRITE_RATE
    if tier >= 2:
        if env.get(ENV_ENABLE_WRITES, "") != "1":
            raise ConfigError(f"{ENV_ENABLE_WRITES}=1 is required for the write process")
        operator, operator_key = env.get(ENV_OPERATOR, ""), env.get(ENV_OPERATOR_KEY, "")
        if "sealed-ledger" not in services:
            # every write is recorded on the ledger first; without it nothing may be written
            raise ConfigError(f"{env_name('sealed-ledger', 'URL')} is required for the write process (audit)")
        try:
            rate = int(env.get(ENV_WRITE_RATE, "") or DEFAULT_WRITE_RATE)
        except ValueError:
            raise ConfigError(f"{ENV_WRITE_RATE} must be an integer") from None
        if not 1 <= rate <= 600:
            raise ConfigError(f"{ENV_WRITE_RATE} must be between 1 and 600")
    return Config(tier=tier, services=services, operator=operator, operator_key=operator_key,
                  write_rate_per_min=rate)
