"""Signature tables: payload families, agent markers, fetch intermediaries.

These are deliberately small, readable regex tables — a WAF-lite. The
product's claim is not these signatures; it is the sequence clauses
(``clauses.py``) and the evidence trail (``evidence.py``). Every table is
data a customer engagement is expected to tune.

Confidence on the marker and intermediary strings: MEDIUM (vendor-published
user-agent tokens as of training data) and LOW (intermediaries). Re-check
both against the vendors' current documentation before an engagement.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, unquote

# --------------------------------------------------------------- payloads

PAYLOAD_PATTERNS: dict[str, re.Pattern[str]] = {
    "sqli": re.compile(
        r"(?i)("
        r"\bunion\b[\s\S]{0,40}?\bselect\b"
        r"|'\s*(or|and)\s+'?\w*'?\s*=\s*'?\w*"
        r"|\b(or|and)\s+\d+\s*=\s*\d+"
        r"|\bsleep\s*\(\s*\d+\s*\)"
        r"|\bbenchmark\s*\("
        r"|\bwaitfor\s+delay\b"
        r"|;\s*(drop|insert|update|delete|truncate)\s"
        # a SQL line comment right after a quote: '-- or '# followed by space or
        # end of value. Tightened so catalogue text like Soldiers'--Canada and
        # a search for "#1 gift" (apostrophe then #digit) do not trip it.
        r"|'\s*(--|#)(\s|$)"
        r"|\binformation_schema\b"
        r"|\b(extractvalue|updatexml|load_file)\s*\("
        r")"
    ),
    # Every open-ended run ([^>]*, [^}]*) is bounded: an unbounded run between
    # two required tokens is quadratic (or cubic, with two runs) in the input,
    # and a single 8 KB logged URL could stall a scan for seconds. 200 chars is
    # more than any real tag or template expression needs.
    "xss": re.compile(
        r"(?i)("
        r"<\s*script\b"
        r"|javascript\s*:"
        r"|<\s*(img|svg|iframe|body|details|video)\b[^>]{0,200}\bon\w+\s*="
        r"|\bon(error|load|mouseover|focus|toggle)\s*="
        r"|\balert\s*\("
        r"|document\.cookie"
        r")"
    ),
    "ssti": re.compile(
        r"("
        r"\{\{\s*\d+\s*\*\s*\d+\s*\}\}"
        r"|\$\{\s*\d+\s*\*\s*\d+\s*\}"
        r"|<%=?\s*\d+\s*\*\s*\d+\s*%>"
        # "{{ ... <name> ... }}" with no "}" inside: the lookahead first checks,
        # in one bounded pass, that a "}}" closes the expression, so the name
        # scan never runs on an unclosed "{{" (the cubic case).
        r"|\{\{(?=[^}]{0,400}\}\})[^}]{0,200}(__class__|__globals__|config|self)"
        r")"
    ),
    "traversal": re.compile(
        r"(?i)(\.\.[/\\]|\.\.%2f|\.\.%5c|%2e%2e|/etc/passwd|\bwin\.ini\b|\bboot\.ini\b)"
    ),
    # Ampersand is omitted from the leading shell-metachar class on purpose:
    # "dog & cat food" and other natural queries use a bare "&". A shell
    # command injection still needs ; | backtick or $( to chain, which remain.
    "cmdi": re.compile(
        r"(?i)("
        r"[;|]\s*(cat|ls|id|whoami|uname|wget|curl|nc|bash|sh)\s"
        r"|`[^`]{1,80}`"
        r"|\$\(\s*(id|whoami|uname|cat|ls)\b"
        r")"
    ),
}

DEBUG_PATH = re.compile(
    r"(?i)^/("
    r"\.env|\.git(/|$)|\.aws/|\.ssh/|\.ds_store"
    r"|server-status|server-info|phpinfo\.php|info\.php"
    r"|actuator(/|$)|debug(/|$)|_debug|_profiler|console(/|$)"
    r"|admin(/|$)|administrator(/|$)|wp-admin|wp-login\.php"
    r"|config\.(php|json|ya?ml)|web\.config|elmah\.axd|trace\.axd"
    r")"
)
DEBUG_QUERY = re.compile(
    r"(?i)(^|&)(debug|test|trace|verbose|show_errors|xdebug_session_start)"
    r"=(1|true|on|yes)(&|$)"
)

# ------------------------------------------------------- attribution tables

#: Self-declared AI-agent user-agent tokens (substring, case-insensitive) →
#: the operator the token names. A token is a CLAIM made by the client; the
#: report says "marker observed", never "operator did this".
AGENT_MARKERS: dict[str, str] = {
    "gptbot": "OpenAI (GPTBot token)",
    "chatgpt-user": "OpenAI (ChatGPT-User token)",
    "oai-searchbot": "OpenAI (OAI-SearchBot token)",
    "claudebot": "Anthropic (ClaudeBot token)",
    "claude-user": "Anthropic (Claude-User token)",
    "claude-searchbot": "Anthropic (Claude-SearchBot token)",
    "perplexitybot": "Perplexity (PerplexityBot token)",
    "perplexity-user": "Perplexity (Perplexity-User token)",
    "meta-externalagent": "Meta (meta-externalagent token)",
    "meta-externalfetcher": "Meta (meta-externalfetcher token)",
    "mistralai-user": "Mistral (MistralAI-User token)",
    "bytespider": "ByteDance (Bytespider token)",
    "ccbot": "Common Crawl (CCBot token)",
    "amazonbot": "Amazon (Amazonbot token)",
}

#: Automation-library user agents: evidence of automation, not of AI.
AUTOMATION_UA = re.compile(
    r"(?i)(headlesschrome|python-requests|python-urllib|aiohttp|httpx|go-http-client"
    r"|node-fetch|axios/|scrapy|playwright|puppeteer|curl/|wget/|libwww-perl)"
)

#: Fetch intermediaries (web archives, URL scanners). A payload arriving
#: through one means the client IP is the intermediary's, not the agent's.
INTERMEDIARY_UA: dict[str, str] = {
    "archive.org_bot": "Internet Archive",
    "ia_archiver": "Internet Archive / Alexa",
    "wayback": "Wayback-style archive",
    "arquivo": "Arquivo.pt",
    "urlscan": "urlscan.io",
    "urlquery": "urlquery.net",
}


# ------------------------------------------------------------- functions


def _normalise(value: str) -> str:
    value = value.lower()
    value = re.sub(r"\d+", "0", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def fingerprint(value: str) -> str:
    # "replace" so a lone surrogate from a JSON log string cannot raise on encode
    return hashlib.sha256(_normalise(value).encode("utf-8", "replace")).hexdigest()[:16]


#: Each path/value/user-agent is truncated to this before regex matching.
#: Bounds the worst-case regex cost so a single enormous logged URL cannot
#: stall a scan (the signatures look at the head of a target; a payload past
#: 8 KB is not something these patterns were meant to find anyway).
MAX_MATCH_LEN = 8192


def bounded(text: str) -> str:
    """The ONE cap applied to attacker text before any regex in this module
    runs on it. Every public matcher goes through it, so no caller can hand a
    pattern an unbounded string."""
    return text[:MAX_MATCH_LEN]


def _hostile_tokens(query: str) -> list[tuple[str, str]]:
    """(key, value) pairs of the query, each capped."""
    return [(bounded(k), bounded(v)) for k, v in parse_qsl(query, keep_blank_values=True)]


def classify(path: str, query: str) -> tuple[list[str], list[str]]:
    """Return (families, fingerprints) for one request target.

    ``path`` is percent-decoded; ``query`` is the raw query string as logged
    (``parse_qsl`` decodes it once, so a double-encoded ``%252e`` arrives as
    ``%2e`` and the traversal pattern still sees it). Keys and values are both
    tested. A fingerprint is taken per hostile token (or over the path when
    the payload is in the path), so the same payload sent from rotated IPs
    links up.
    """
    families: list[str] = []
    fps: list[str] = []
    path = bounded(unquote(path))  # idempotent for an already-decoded path
    if DEBUG_PATH.search(path) or DEBUG_QUERY.search(bounded(query)):
        families.append("debug_probe")

    values: list[str] = [t for pair in _hostile_tokens(query) for t in pair if t]
    for family, pattern in PAYLOAD_PATTERNS.items():
        hit_value = next((v for v in values if pattern.search(v)), None)
        in_path = pattern.search(path) is not None
        if hit_value is not None or in_path:
            families.append(family)
            fps.append(f"{family}:{fingerprint(hit_value if hit_value is not None else path)}")
    return families, sorted(set(fps))


def markers_for(user_agent: str) -> list[str]:
    ua = user_agent.lower()
    return [label for token, label in AGENT_MARKERS.items() if token in ua]


def intermediary_for(user_agent: str) -> str | None:
    ua = user_agent.lower()
    return next((label for token, label in INTERMEDIARY_UA.items() if token in ua), None)


def is_automation_ua(user_agent: str) -> bool:
    return AUTOMATION_UA.search(bounded(user_agent)) is not None


def hostile_params(query: str) -> set[str]:
    """Names of query parameters whose value (or name) matches a payload
    family. Used by ``S.pivot`` to find the parameter that was tampered."""
    names: set[str] = set()
    for key, value in _hostile_tokens(query):
        if any(p.search(key) or p.search(value) for p in PAYLOAD_PATTERNS.values()):
            names.add(key)
    return names


def param_values(query: str) -> dict[str, str]:
    return {k: v for k, v in parse_qsl(query, keep_blank_values=True)}
