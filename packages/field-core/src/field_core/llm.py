"""Where the platform's own LLM calls go (v1.2 D2e).

Three platform callers make Anthropic Messages calls of their own: the
sentinel's semantic judge, the crosswalk's mapping suggester and the
gateway's sampled hygiene judge. They build their HTTP client from these two
helpers, so an estate routes all of them through force-gateway by setting ONE
variable, ``FORCE_GATEWAY_URL``:

* ``anthropic_base_url()`` = ``FORCE_GATEWAY_URL``, else
  ``ANTHROPIC_BASE_URL``, else ``https://api.anthropic.com``; blank values
  count as unset; trailing slashes are stripped.
* ``anthropic_headers(key)`` = ``x-api-key`` + ``anthropic-version``, and ONLY
  when ``FORCE_GATEWAY_URL`` is the target, the platform headers:
  ``x-force-passthrough: judge`` (the gateway forwards the call uninstrumented,
  so a judge's call is never re-injected, re-sampled or counted as hygiene
  traffic) and ``auth_headers()`` (so a secret estate's gateway accepts it).
  Neither platform header is sent to ``ANTHROPIC_BASE_URL`` or the default
  host: the shared secret must never reach a third party, and there is no way
  to tell whether an ``ANTHROPIC_BASE_URL`` is a gateway.

``FIELD_GATEWAY_URL`` is a different variable with its own meaning: the
``forcegw`` CLI's target (``forcegw telemetry``). The gateway's own upstream
(``force_gateway.api.real_upstream``) deliberately does NOT use this module —
with ``FORCE_GATEWAY_URL`` set estate-wide it would forward to itself.
"""

from __future__ import annotations

import os

from field_core.authn import auth_headers

DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
GATEWAY_URL_ENV = "FORCE_GATEWAY_URL"
BASE_URL_ENV = "ANTHROPIC_BASE_URL"
PASSTHROUGH_HEADER = "x-force-passthrough"
PASSTHROUGH_JUDGE = "judge"


def _env(name: str) -> str | None:
    value = (os.environ.get(name) or "").strip().rstrip("/")
    return value or None


def via_force_gateway() -> bool:
    """True when ``FORCE_GATEWAY_URL`` (non-blank) decides the base URL."""
    return _env(GATEWAY_URL_ENV) is not None


def anthropic_base_url() -> str:
    """``FORCE_GATEWAY_URL`` > ``ANTHROPIC_BASE_URL`` > the default host."""
    return (_env(GATEWAY_URL_ENV) or _env(BASE_URL_ENV)
            or DEFAULT_ANTHROPIC_BASE_URL)


def anthropic_headers(key: str, version: str = ANTHROPIC_VERSION) -> dict[str, str]:
    """Headers for a platform caller's Messages call (read per call, like
    ``auth_headers``). Platform headers ride only to ``FORCE_GATEWAY_URL``."""
    headers = {"x-api-key": key, "anthropic-version": version}
    if via_force_gateway():
        headers[PASSTHROUGH_HEADER] = PASSTHROUGH_JUDGE
        headers.update(auth_headers())
    return headers
