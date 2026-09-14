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

import os

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
