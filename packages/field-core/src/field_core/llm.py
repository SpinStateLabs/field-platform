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

Phase F1 — self-agent identity at the egress. An ENFORCING gateway
(``FORCE_GATEWAY_ENFORCE=1``) treats the three platform callers as governed
agents: their judge calls must carry ``x-field-agent-id`` (the caller's
self-manifest id) and ``x-field-token`` (its delegation token id), and the
passthrough exemption is honoured for those three ids only. So, ONLY toward
``FORCE_GATEWAY_URL`` and ONLY when BOTH ``FIELD_SELF_AGENT_ID`` and
``FIELD_SELF_TOKEN_ID`` are set (non-blank), ``anthropic_headers`` adds the
two headers; with either unset it sends neither — exactly D2e — and a
half-configured pair is a misconfiguration made visible, not guessed at.
Under an enforcing gateway a self-agent without them (token-less) gets 401
⇒ the caller's ``JudgeError`` ⇒ in the sentinel a ``D.semantic`` escalation
(fail closed, visible in the ledger); the crosswalk suggester and the
gateway's hygiene judge count the failure in their own gap counters. Neither
header rides to ``ANTHROPIC_BASE_URL`` or the default host: a token id is a
bearer at the egress and must never reach a third party.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import socket
from urllib.parse import urlparse

from field_core.authn import auth_headers

DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
GATEWAY_URL_ENV = "FORCE_GATEWAY_URL"
BASE_URL_ENV = "ANTHROPIC_BASE_URL"
PASSTHROUGH_HEADER = "x-force-passthrough"
PASSTHROUGH_JUDGE = "judge"
#: F1: the egress identity headers an enforcing gateway requires, and the env
#: vars a self-agent's container sets to send them (compose / Fly entrypoint).
AGENT_ID_HEADER = "x-field-agent-id"
TOKEN_HEADER = "x-field-token"
SELF_AGENT_ID_ENV = "FIELD_SELF_AGENT_ID"
SELF_TOKEN_ID_ENV = "FIELD_SELF_TOKEN_ID"
#: F1: the fixed action an enforcing gateway checks when the caller names
#: none (`x-field-action`); manifests that use the gateway list it in
#: ``delegation.scope``.
EGRESS_ACTION = "llm.messages"


def _env(name: str) -> str | None:
    value = (os.environ.get(name) or "").strip().rstrip("/")
    return value or None


def _env_id(name: str) -> str | None:
    """An identifier variable: blank/whitespace counts as unset; no slash
    stripping (an id is not a URL)."""
    value = (os.environ.get(name) or "").strip()
    return value or None


def via_force_gateway() -> bool:
    """True when ``FORCE_GATEWAY_URL`` (non-blank) decides the base URL."""
    return _env(GATEWAY_URL_ENV) is not None


def anthropic_base_url() -> str:
    """``FORCE_GATEWAY_URL`` > ``ANTHROPIC_BASE_URL`` > the default host."""
    return (_env(GATEWAY_URL_ENV) or _env(BASE_URL_ENV)
            or DEFAULT_ANTHROPIC_BASE_URL)


def self_identity_headers() -> dict[str, str]:
    """F1: ``{x-field-agent-id, x-field-token}`` when BOTH
    ``FIELD_SELF_AGENT_ID`` and ``FIELD_SELF_TOKEN_ID`` are set; ``{}`` when
    either is unset or blank (both-or-neither, read per call)."""
    agent_id = _env_id(SELF_AGENT_ID_ENV)
    token_id = _env_id(SELF_TOKEN_ID_ENV)
    if agent_id is None or token_id is None:
        return {}
    return {AGENT_ID_HEADER: agent_id, TOKEN_HEADER: token_id}


def anthropic_headers(key: str, version: str = ANTHROPIC_VERSION) -> dict[str, str]:
    """Headers for a platform caller's Messages call (read per call, like
    ``auth_headers``). Platform headers — passthrough, the F1 self-identity
    pair, the perimeter secret — ride only to ``FORCE_GATEWAY_URL``."""
    headers = {"x-api-key": key, "anthropic-version": version}
    if via_force_gateway():
        headers[PASSTHROUGH_HEADER] = PASSTHROUGH_JUDGE
        headers.update(self_identity_headers())
        headers.update(auth_headers())
    return headers


REQUIRE_TLS_ENV = "FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM"   # the same opt-in the gateway's real_upstream reads
_log = logging.getLogger(__name__)
_NUMERIC_HOST = re.compile(r"[0-9a-fA-FxX.]+")
_warned: set[str] = set()


class InsecureBaseURLError(RuntimeError):
    """The base URL would send the Anthropic key (and, toward a gateway, the perimeter secret and
    the token id) in clear to a host that is not an estate-internal address."""


def cleartext_ok(base: str) -> bool:
    """True when ``base`` is https, or plain http to an estate-internal host: loopback, a private
    or link-local IP, ``localhost``, a single-label name (a compose service such as ``forcegw``),
    or a ``.internal`` / ``.local`` name (Fly private network, mDNS). Anything else over http would
    put the key on a network we do not control. (C-117, reviewer C-187 F-C187-1.)"""
    u = urlparse(base)
    if u.scheme == "https":
        return True
    if u.scheme != "http":
        return False                      # an unrecognised scheme is refused, not guessed at
    host = (u.hostname or "").lower()
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        pass
    if not _NUMERIC_HOST.fullmatch(host):
        # not a numeric spelling: a name (single-label, .internal, .local) or something else.
        # glibc inet_aton accepts trailing whitespace and text ("127.0.0.1 .evil.test"), so it
        # must never see a host with characters outside [0-9a-fx.] (reviewer C-213 F-C213-1).
        return host == "localhost" or "." not in host or host.endswith((".internal", ".local"))
    try:
        # inet_aton also reads decimal (134744072), hex (0x08080808) and octal (01001001010) spellings
        # of an IPv4 address, which the resolver turns into a public address (reviewer C-197
        # F-C197-1): normalise them first, never let them reach the single-label rule below.
        ip = ipaddress.ip_address(socket.inet_ntoa(socket.inet_aton(host)))
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except (OSError, ValueError):
        pass
    return host == "localhost" or "." not in host or host.endswith((".internal", ".local"))


def make_http_client(key: str, *, timeout: float = 30.0):
    """The ONE way a platform caller builds its Messages client (reviewer C-187): refuses a
    cleartext base URL to a non-internal host, and ignores HTTP(S)_PROXY / NO_PROXY
    (``trust_env=False``), so the key and the platform headers go only where
    ``anthropic_base_url()`` says. Raises :class:`InsecureBaseURLError`."""
    import httpx

    base = anthropic_base_url()
    if not cleartext_ok(base):
        u = urlparse(base)
        what = f"{u.scheme or 'an unknown scheme'} to host {u.hostname!r}"
        if via_force_gateway():
            # the platform headers (perimeter secret, token id) ride here: never in clear
            raise InsecureBaseURLError(f"refusing to send the Anthropic key and the platform headers "
                                       f"over {what}: FORCE_GATEWAY_URL must be https or an "
                                       "estate-internal address")
        # ANTHROPIC_BASE_URL over plain http is a documented configuration (D-17): warn once, and
        # refuse only on the opt-in the gateway already offers.
        if os.environ.get(REQUIRE_TLS_ENV, "").strip() == "1":
            raise InsecureBaseURLError(f"{REQUIRE_TLS_ENV}=1: refusing to send the Anthropic key "
                                       f"over {what}")
        if base not in _warned:
            _warned.add(base)
            _log.warning("ANTHROPIC_BASE_URL is plain %s to host %r: the key is sent unencrypted",
                         u.scheme or "unknown", u.hostname)
    return httpx.Client(base_url=base, timeout=timeout, headers=anthropic_headers(key),
                        trust_env=False)
