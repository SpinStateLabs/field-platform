"""The one place that reads the process environment (a test greps the package for ``os.environ`` elsewhere).

Per service: ``FFMCP_<SERVICE>_URL`` and ``FFMCP_<SERVICE>_KEY`` (``-`` becomes ``_``). Read once at startup; neither a
URL nor a key ever comes from a tool argument. Tier 2 settings (the write flag, the operator pair, the per-service write
keys ``FFMCP_<SERVICE>_WRITE_KEY`` and the write rate) are read ONLY when the write entry point asks for them AND
FFMCP_ENABLE_WRITES is exactly ``1``, so the read process never loads them and a write process without the flag is a
Tier 1 process. ``FFMCP_<SERVICE>_KEY`` is the key for Tier 1 calls (a read key once per-tier keys are in force);
``..._WRITE_KEY`` is the only key a Tier 2 call uses.
"""
from __future__ import annotations

import os
import re
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
DEFAULT_WRITE_RATE = 10        # writes per minute per session (a proposed default; Don sets it)
MAX_WRITE_RATE = 60


class ConfigError(Exception):
    """Fixed text naming a variable, never a value."""


def env_name(service: str, what: str) -> str:
    return f"{ENV_PREFIX}{service.replace('-', '_').upper()}_{what}"


@dataclass(frozen=True)
class ServiceConfig:
    base: str
    key: str = field(default="", repr=False)
    write_key: str = field(default="", repr=False)


@dataclass(frozen=True)
class Config:
    tier: int
    services: dict[str, ServiceConfig]
    operator: str = field(default="", repr=False)
    operator_key: str = field(default="", repr=False)
    write_rate_per_min: int = 0

    def secrets(self) -> tuple[str, ...]:
        keys = [k for c in self.services.values() for k in (c.key, c.write_key)]
        return tuple(s for s in [*keys, self.operator_key] if s)


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
    """Read the configuration for ``tier`` (1 = read process, 2 = write process). The write process is Tier 2 only when
    FFMCP_ENABLE_WRITES is exactly ``1``; without it the result is a Tier 1 configuration and nothing of Tier 2 is read."""
    env = os.environ if environ is None else environ
    allow_https = env.get(ENV_ALLOW_EXTERNAL_HTTPS, "") == "1"
    writes = tier >= 2 and env.get(ENV_ENABLE_WRITES, "") == "1"
    services: dict[str, ServiceConfig] = {}
    for svc in SERVICES:
        url = env.get(env_name(svc, "URL"), "").strip()
        if not url:
            continue
        services[svc] = ServiceConfig(validate_base_url(url, allow_external_https=allow_https),
                                      env.get(env_name(svc, "KEY"), ""),
                                      env.get(env_name(svc, "WRITE_KEY"), "") if writes else "")
    if not writes:
        return Config(tier=1, services=services)
    rate = env.get(ENV_WRITE_RATE)
    if rate is None:
        n = DEFAULT_WRITE_RATE
    elif re.fullmatch(r"[1-9][0-9]?", rate) and int(rate) <= MAX_WRITE_RATE:
        n = int(rate)
    else:                                       # the limit can be tuned, never switched off
        raise ConfigError(f"{ENV_WRITE_RATE} must be an integer from 1 to {MAX_WRITE_RATE}")
    return Config(tier=2, services=services, operator=env.get(ENV_OPERATOR, ""),
                  operator_key=env.get(ENV_OPERATOR_KEY, ""), write_rate_per_min=n)
