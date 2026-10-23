#!/usr/bin/env python3
"""Deployed-topology lint: are the fail-open environment variables armed?

Two controls in this platform are "unset means open":

* ``FIELD_SHARED_SECRET`` unset disables perimeter authentication
  (``packages/field-core/src/field_core/authn.py``: ``if secret and ...``).
* ``FIELD_DOA_ROSTER`` unset skips the grantor, scope and token-TTL checks on
  mint (``services/delegation-authority/.../api.py`` ``if configured:`` and
  ``doa.py`` ``roster_path``), recorded as ``doa_checked: false``.

Both default to empty in the shipped descriptors. That is by design for the
local demo (``authn.py`` calls it "the documented localhost-trust demo mode";
``docker-compose.yml`` says "Blank/default here; set them in the estate .env")
and must not be true of a deployed estate. This tool reads the shipped
descriptors statically (no docker, no network, no secrets) and reports, per
topology and per variable, one of:

``armed``          the descriptor itself guarantees a non-empty value: a
                   literal, a non-empty default, or a required-or-fail
                   reference (``${VAR:?msg}``).
``empty-default``  the descriptor forwards the variable with an empty default
                   (``${VAR:-}``, ``"${VAR:-}"``). Nothing stops an estate
                   starting open.
``operator``       the descriptor only passes the host environment through
                   (``${VAR}``) or does not mention the variable; whether it
                   is set is decided outside the repo and cannot be verified.
                   (A Fly secret is such a case: ``fly secrets set`` is not
                   visible here, and the entrypoint still defaults to empty.)

Each topology is classed ``demo`` (reported, never failing) or ``deployed``
(fails unless ``armed``, or recorded in the allowlist with a reason). Every
compose/Fly descriptor under ``integration/`` must belong to a declared
topology, so a new deployment file cannot slip past by not being classified.
Allowlist entries that no longer match a failing (topology, variable) pair are
themselves errors, so exceptions cannot rot. Every entry also carries
``verified_on`` (ISO date) and ``verified_by``; an entry whose ``verified_on``
is missing, malformed, in the future, or more than ``ALLOWLIST_MAX_AGE_DAYS``
old fails the lint, so an exception expires and forces re-verification.
An entry is also keyed by the weak status and the exact set of services making it
weak (``expected_status``, ``services``): a new weak service, or EMPTY turning
into OPERATOR, stops the waiver applying until the entry is re-verified.

What this is, and is not. This is an ACCIDENT GUARD, not a security boundary: it
catches a deployed descriptor that silently starts open, and it catches the
bypasses that review found. It does not stop a determined author, and it is not
proof that any estate is armed. Treat OK as "no known bypass in the shapes this
lint reads", nothing more.

How armed-ness is decided, per file:

* ``integration/fly/entrypoint.sh`` is established by RUNNING it, not by a parser:
  ``run_entrypoint`` executes the real script under bash with PATH set to a temp
  directory of stub executables ONLY (no host directory on PATH), cwd, HOME and
  TMPDIR in a temp dir, and a hard SIGKILL timeout. Every service the script
  launches (the list is read from the script and pinned in
  ``EXPECTED_FLY_STUBS``) is a stub that records its argv0 and the values it saw;
  external utilities the script uses (``mkdir``, ``touch``, ...) are no-op stubs.
  Nine scenarios run: secret unset / empty, roster unset / empty, both set (with
  sentinel values), roster whitespace-only, and secret whitespace-only / ``null``
  / ``0`` (the last three are documented as weak-but-set, not findings). A variable
  is armed only if, when it is unset or empty, the script exits non-zero before
  any stub starts. With both set every stub must start once with EXACTLY the
  values it was given (a rewrite to ``hunter2``, a space, one character, a
  placeholder or a literal ``${...}`` is a finding), argv0 inside the stub
  directory, and nothing may report ``command not found`` / ``No such file``. A
  roster guard that refuses unset and empty but starts the services with a
  whitespace-only roster is a finding (delegation strips it to unset: gate OFF).
  A different set of launched services than the reviewed one is a finding.
  A script that launches by absolute path, variable or substitution cannot be
  stubbed and is NOT executed (the tripwire reports it). A bash that adds its own
  directories to PATH (Git for Windows' ``bin/bash.exe`` wrapper) is refused;
  ``usr/bin/bash.exe`` is used instead. The lint prints ``entrypoint behavioural
  check: RAN`` or ``SKIPPED (reason)`` plus a loud ``WARN ... NOT RUN`` line, FAILS
  rather than skips when ``CI`` is set and bash is missing, and refuses
  ``TOPOLOGY_LINT_BEHAVIOURAL=0`` (or empty) when ``CI`` is set. The static reading of
  the script is a coarse tripwire (heredocs, eval, source, ``env`` in any spelling,
  ``sh -c``, ``exec -c``, ``printf -v``, ``read``, ``unset``, ``${!X}``, namerefs,
  computed names, startup-hook variables, launches by path or variable;
  continuation lines joined without a space) and the fallback when the script
  cannot be run; it can only add findings, never assure.
* Compose files, ``fly.toml`` and the Dockerfile are read statically (see below).

Known gaps (every one still open unless it says otherwise):

* Live values are invisible: ``.env``, ``fly secrets`` and the host environment
  decide what actually runs. Only an operator check of the running containers
  shows that (presence, not value, is what such a check can safely record).
* The behavioural run exercises ``entrypoint.sh`` only. It does not run the compose
  services, and a stub is not the real service: code inside a real binary that
  unsets the variable, or reads another variable, is out of reach.
* What the run does NOT contain: a launch by absolute path, variable or substitution
  cannot be intercepted (so such a script is not executed at all, and the
  tripwire reports it); builtins run for real (``cd``, ``exec``, redirections such
  as ``> /some/path`` write wherever the script says); network access is not
  blocked by a sandbox, it is only unreachable because no network tool is on PATH.
  The stub list is derived from the script text by a heuristic; a launch it does
  not derive shows up as ``command not found`` or a changed service count, but a
  heuristic miss that happens to be harmless at run time is not seen.
* Environment-gated behaviour is invisible: the run does not set ``FLY_APP_NAME``,
  create ``/data`` or apply fly.toml ``[env]``, so a branch such as ``[ -n
  "$FLY_APP_NAME" ] && ...`` or a guard skipped on Fly would not be seen. The real
  script has no such conditionals today; the check would not notice one being added
  (only the static tripwire's other rules might). Nor does it model time (a launch
  after a long ``sleep`` is stubbed to no-op) or files the stubs do not create.
* Weak-but-set values (whitespace-only or ``null`` or ``0`` secret) are accepted by
  a ``:?`` guard and are documented, not flagged. A secret of 1 character is not
  flagged either.
* The static fallback (used only when bash is unavailable outside CI, or the run
  is disabled outside CI) is weak: in a sweep of 56 entrypoint cases, 24 stayed
  green in static-only mode. Do not rely on it; the lint prints a WARN line.
* Compose is resolved for ``services`` / ``environment`` / ``command`` /
  ``entrypoint`` / ``image`` / ``network_mode`` / ``scale`` / ``deploy.replicas`` and
  the ``!override`` / ``!reset`` tags. ``env_file``, ``extends`` and ``include`` are
  rejected, not followed; ``profiles`` are noted, not evaluated; ``docker compose
  config`` interpolation is approximated. A command or entrypoint that starts with
  ``env``, ``sudo``, ``su``, ``setpriv`` or contains ``env -i`` is a finding, but
  clearing the environment in any other way (a python ``os.environ.pop`` of a
  split name, a wrapper image, an init script baked into the image) is not seen.
  A service with no entry is assumed reachable unless ``network_mode: none``,
  ``scale: 0`` / ``replicas: 0``, or named in ``SERVICE_EXEMPTIONS`` AND matching
  the image or network mode that justifies the exemption.
* The roster consumer is found by ``delegation serve`` / ``delegation-authority`` in
  a command or image; a wrapper script that execs it under another name is missed.
* The Dockerfile is read as an allow-list of shapes (single stage; known COPY, RUN,
  ENV, ARG, ENTRYPOINT forms). Continuation lines are joined without a space and
  ``# escape=`` is honoured; COPY destinations are normalised (``/./``, ``//``,
  ``..``, WORKDIR, ENV expansion) before comparing with ``/entrypoint.sh``. Build
  args, ``.dockerignore``, what is inside the base image (a ``/etc/profile``, an
  ``ENTRYPOINT`` wrapper) and multi-stage tricks are not inspected.
* ``fly.toml`` sections outside a short allow-list are rejected; ``[env]`` values are
  literals (Fly does not interpolate). Overrides applied at deploy time (``fly
  deploy --env``, ``fly machine run``) are invisible.
* The repo-wide scan finds files by name and shape (compose-like YAML, including
  flow style, quoted ``"services":`` and ``.j2`` templates; JSON compose files;
  fly-like TOML; ``Dockerfile*`` and ``Containerfile*``; shell that mentions a
  variable or lives under ``integration/``). Kubernetes manifests, Helm charts,
  Terraform, systemd units, CI/CD deploy steps and any other format are NOT
  scanned; neither are ``.github/workflows`` parsed.
* A literal or placeholder secret is recognised by a short word list and a
  non-empty-literal rule; a weak but unlisted value (``abc123``) is not a finding.
* The allowlist is verified by a coordinator presence check, not by the lint, and
  expires after ``ALLOWLIST_MAX_AGE_DAYS``.

Exit status: 0 clean, 1 findings, 2 usage or descriptor error.
Standard library plus PyYAML (already a field-core dependency).
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

VARS = ("FIELD_SHARED_SECRET", "FIELD_DOA_ROSTER")

ARMED = "armed"
EMPTY = "empty-default"
OPERATOR = "operator"
PLACEHOLDER = "placeholder"  # a well-known public value: as open as empty

_RANK = {ARMED: 0, OPERATOR: 1, EMPTY: 2, PLACEHOLDER: 3}  # larger = weaker

# Literals that are not secrets. Matched case-insensitively against the whole
# value (or the whole default), and only for FIELD_SHARED_SECRET.
PLACEHOLDER_LITERALS = frozenset(
    {"changeme", "change-me", "change_me", "password", "secret", "test", "demo"}
)

# An allowlist exception must have been re-verified within this many days. An
# entry exactly this old still passes; one day older fails. Changing this is a
# reviewed code change on purpose.
ALLOWLIST_MAX_AGE_DAYS = 30

DEMO = "demo"
DEPLOYED = "deployed"


@dataclass(frozen=True)
class Topology:
    id: str
    kind: str  # DEMO or DEPLOYED
    style: str  # "compose" or "fly"
    files: tuple[str, ...]
    evidence: str


# The classification is code, not config, on purpose: moving a topology from
# deployed to demo must be a reviewed change to this file, not to an allowlist.
TOPOLOGIES: tuple[Topology, ...] = (
    Topology(
        id="demo-compose",
        kind=DEMO,
        style="compose",
        files=("integration/demo/docker-compose.yml",),
        evidence=(
            "base compose file alone: the local/CI demo stack and compose-smoke job. "
            "Its header says the operator passthroughs are 'Blank/default here', "
            "authn.py documents unset as the 'localhost-trust demo mode', and "
            "ci.yml compose-smoke runs it with neither variable set."
        ),
    ),
    Topology(
        id="gb10",
        kind=DEPLOYED,
        style="compose",
        files=(
            "integration/demo/docker-compose.yml",
            "integration/demo/docker-compose.gb10.yml",
        ),
        evidence=(
            "base + docker-compose.gb10.yml: the live demo and dogfood estate "
            "for Spin State's own agents (enforce since 2026-09-08, per the "
            "override's header)."
        ),
    ),
    Topology(
        id="fly",
        kind=DEPLOYED,
        style="fly",
        files=("integration/fly/entrypoint.sh", "integration/fly/fly.toml", "integration/fly/Dockerfile"),
        evidence=(
            "Fly.io force-field-sandbox: the public sandbox estate behind "
            "force_https; entrypoint.sh calls itself 'the PRODUCT estate'."
        ),
    ),
)

# Fly runs one container, so its "service set" is this single name.
FLY_SERVICE = "fly-container"

# FIELD_SHARED_SECRET: a compose service that serves HTTP and has no entry for
# it sees the variable unset, which is as open as an empty default. These named
# services are exempt, each with the reason. Code, not config, on purpose.
SERVICE_EXEMPTIONS: dict[tuple[str, str, str], tuple[str, str]] = {
    ("gb10", "FIELD_SHARED_SECRET", "proxy"): (
        "Caddy reverse proxy: it terminates nothing and authenticates nothing; the backends it "
        "forwards to enforce field_core.authn. integration/demo/Caddyfile does not mention the "
        "secret. A 2026-10-23 presence check also found it unset in the live proxy container.",
        "image:caddy",
    ),
    ("gb10", "FIELD_SHARED_SECRET", "manifests-admin"): ("one-shot volume_admin tool, network_mode none, serves no HTTP", "network:none"),
    ("gb10", "FIELD_SHARED_SECRET", "keys-admin"): ("one-shot volume_admin tool (profile admin), network_mode none, serves no HTTP", "network:none"),
    ("gb10", "FIELD_SHARED_SECRET", "attest-keys-admin"): ("one-shot volume_admin tool (profile admin), network_mode none, serves no HTTP", "network:none"),
}


def _exemption_holds(requirement: str, image: str, netmode: str | None) -> bool:
    """A name alone never exempts: the service must also BE what the reason says."""
    if requirement == "image:caddy":
        return image.startswith("caddy")
    if requirement == "network:none":
        return netmode == "none"
    return False

# Environment variables that make a shell, Python or the loader run code, or
# change how a program starts, before the service's own first line.
RISKY_ENV_KEYS = frozenset({
    "BASH_ENV", "ENV", "PROMPT_COMMAND", "BASH_XTRACEFD", "SHELLOPTS", "LD_PRELOAD", "LD_LIBRARY_PATH",
    "PYTHONSTARTUP", "PYTHONPATH", "PYTHONHOME", "NODE_OPTIONS",
})

# Only the compose services that RUN the reader decide a variable's status. They
# are found by what they run (command / entrypoint text, or image name), not by
# the service's name, so renaming a service cannot hide it and naming another one
# `delegation` cannot make it the consumer.
# FIELD_DOA_ROSTER: delegation-authority, per docs/IMPLEMENTATION.md:79 and
# services/delegation-authority/.../doa.py (ROSTER_ENV). Other services restate
# it in compose but never read it (lifecycle-manager reads FIELD_LIFECYCLE_ROSTER).
CONSUMER_PATTERNS: dict[str, tuple[re.Pattern[str], re.Pattern[str]]] = {
    "FIELD_DOA_ROSTER": (
        re.compile(r"(?<![\w-])delegation\s+serve\b|delegation_authority"),
        re.compile(r"delegation[-_]authority"),
    ),
}

# Descriptors that define a topology. Anything matching these globs must be
# listed in some Topology.files, otherwise it is "unclassified" and fails.
DESCRIPTOR_GLOBS = (
    "integration/**/docker-compose*.yml",
    "integration/**/docker-compose*.yaml",
    "integration/**/compose*.yml",
    "integration/**/compose*.yaml",
    "integration/**/fly*.toml",
    "integration/**/entrypoint*.sh",
)


@dataclass
class VarResult:
    status: str
    evidence: list[str] = field(default_factory=list)
    # The services (compose) or the single container (fly) that make the status
    # weaker than armed. Part of an allowlist entry's key, so a new weak service
    # is a new finding rather than being absorbed by an old waiver.
    services: tuple[str, ...] = ()


@dataclass
class TopologyReport:
    topology: Topology
    vars: dict[str, VarResult]
    findings: list[str] = field(default_factory=list)  # structural problems; fail a deployed topology
    notes: list[str] = field(default_factory=list)  # informational (profiles, ...)
    behaviour: str = ""  # fly only: whether the entrypoint was actually run


def _strip_quotes(text: str) -> str:
    text = text.strip()
    while len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def _segments(text: str) -> list[tuple[str, str]] | None:
    """Split into top-level ``("lit", text)`` / ``("sub", inner)`` pieces.

    ``${...}`` is matched by brace depth, so ``${A:-}${B:-}`` is two
    substitutions rather than one with a default of ``}${B:-``. Returns
    ``None`` when braces do not balance.
    """
    out: list[tuple[str, str]] = []
    i, lit = 0, []
    while i < len(text):
        if text.startswith("${", i):
            depth, j = 1, i + 2
            while j < len(text) and depth:
                if text.startswith("${", j):
                    depth, j = depth + 1, j + 2
                    continue
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            if depth:
                return None
            if lit:
                out.append(("lit", "".join(lit)))
                lit = []
            out.append(("sub", text[i + 2 : j - 1]))
            i = j
        else:
            if text[i] == "}":
                return None  # a closing brace with nothing open
            lit.append(text[i])
            i += 1
    if lit:
        out.append(("lit", "".join(lit)))
    return out


def _literal(text: str, var: str) -> str:
    """Classify a plain (non-substitution) value."""
    if text == "":
        return EMPTY
    if var == "FIELD_SHARED_SECRET" and text.lower() in PLACEHOLDER_LITERALS:
        return PLACEHOLDER
    return ARMED


_SUB_BODY = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(:?[-?+=])?(.*)", re.S)


def classify_value(raw: object, var: str, interpolate: bool = True, _outer: str | None = None) -> str:
    """Classify one descriptor value for ``var``. See the module docstring.

    ``interpolate=False`` is for files where nothing expands ``$`` (fly.toml
    ``[env]``): the text is then just a literal.
    """
    outer = _outer or var  # a nested default is judged as the OUTER variable's value
    if raw is PASSTHROUGH:
        return OPERATOR  # `- VAR`: whatever the host env holds, invisible here
    if raw is None or raw is RESET:
        return EMPTY
    text = _strip_quotes(str(raw))
    if text == "":
        return EMPTY
    if not interpolate:
        return _literal(text, outer)
    segs = _segments(text)
    if segs is None:
        return OPERATOR  # unbalanced braces: cannot be read reliably
    subs = [s for k, s in segs if k == "sub"]
    if not subs:
        if "$(" in text or "`" in text or "$" in text:
            return OPERATOR  # $NAME, $(cmd), ...: cannot decide statically
        return _literal(text, outer)
    if len(segs) != 1:
        return OPERATOR  # more than one piece, or text around a substitution
    m = _SUB_BODY.fullmatch(subs[0])
    if not m or m.group(1) != var:
        return OPERATOR  # ${OTHER...}: the value is not this variable's own expansion
    op, rest = m.group(2), m.group(3)
    if op is None:
        return OPERATOR if rest == "" else OPERATOR  # ${VAR} (or ${VAR:0:0} etc.): host-controlled
    if op == ":?":
        return ARMED  # required and non-empty, or the deployment fails
    if op == "?":
        return EMPTY  # required to be SET, but an empty value passes
    if op[-1] in "-=":
        default = _strip_quotes(rest)
        if default.startswith("${"):
            inner = re.match(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", default)
            st = classify_value(default, inner.group(1), True, outer) if inner else OPERATOR
        elif "$" in default or "`" in default:
            st = OPERATOR
        else:
            st = _literal(default, outer)
        if op[0] == ":" or st in (EMPTY, PLACEHOLDER):
            return st
        # no colon: the default only applies when unset, so a host value
        # that is set-but-empty still wins and we cannot tell statically
        return OPERATOR if st == ARMED else st
    return OPERATOR


def literal_default(raw: object, var: str) -> bool:
    """True when ``raw`` is a committed secret: a non-empty literal, or ``${VAR:-literal}``."""
    if raw is None or raw is PASSTHROUGH or raw is RESET:
        return False
    text = _strip_quotes(str(raw))
    if not text:
        return False
    segs = _segments(text)
    if segs is None:
        return False
    if not any(k == "sub" for k, _ in segs):
        return "$" not in text and "`" not in text
    if len(segs) == 1:
        m = _SUB_BODY.fullmatch(segs[0][1])
        if m and m.group(1) == var and m.group(2) in (":-", "-", ":=", "="):
            d = _strip_quotes(m.group(3))
            if d.startswith("${"):
                inner = re.match(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", d)
                return bool(inner) and literal_default(d, inner.group(1))
            return bool(d) and "$" not in d and "`" not in d
    return False


def is_committed_literal(raw: object, var: str = "FIELD_SHARED_SECRET", interpolate: bool = True) -> bool:
    """True for key material committed to the repo (a literal or a literal default)."""
    if not interpolate:
        return raw is not None and bool(_strip_quotes(str(raw)))
    return literal_default(raw, var)


def _weaker(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b


def _lines_mentioning(path: Path, var: str) -> list[int]:
    out = []
    try:
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if var in line and not line.lstrip().startswith("#"):
                out.append(i)
    except OSError:
        pass
    return out


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader that understands compose-only tags (``!override``, ``!reset``)."""


class _Marker:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"<{self.name}>"


RESET = _Marker("!reset")  # compose `!reset`: the key is removed from the merged result
PASSTHROUGH = _Marker("host-passthrough")  # `- VAR` / `VAR:` with no value: taken from the host env


@dataclass(frozen=True)
class _Override:
    """compose `!override`: replaces the value from earlier files instead of merging."""

    value: object


def _compose_tag(loader, suffix, node):
    if node.tag == "!reset":
        return RESET
    if isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node, deep=True)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_scalar(node)
    return _Override(value) if node.tag == "!override" else value


_ComposeLoader.add_multi_constructor("!", _compose_tag)


def _unwrap(value: object) -> object:
    return value.value if isinstance(value, _Override) else value


@dataclass
class _Service:
    env: dict[str, object]
    replace: bool = False  # `environment: !override` / `!reset`: drop what earlier files set
    unsupported: list[str] = field(default_factory=list)  # env_file / extends
    profiles: list[str] = field(default_factory=list)
    network_mode: str | None = None  # None: this file does not set it
    command: str | None = None  # None: this file does not set it
    entrypoint: str | None = None
    image: str | None = None
    mentions: list[tuple[str, str]] = field(default_factory=list)  # (key, var) in command/entrypoint
    wrappers: list[tuple[str, str]] = field(default_factory=list)  # (key, word): env/sudo/su/setpriv/env -i around the process
    disabled: bool | None = None  # scale: 0 / deploy.replicas: 0 (None: this file does not say)


def _as_text(value: object) -> str:
    value = _unwrap(value)
    if value is None or value is RESET:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(_as_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(f"{k} {_as_text(v)}" for k, v in value.items())
    return str(value)


def _compose_services(path: Path) -> tuple[dict[str, _Service], list[str]]:
    """service name -> parsed service, plus file-level findings (``include``)."""
    try:
        doc = yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader) or {}  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        raise SystemExit(f"topology_lint: cannot parse {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise SystemExit(f"topology_lint: {path}: top level must be a mapping")
    findings: list[str] = []
    if doc.get("include"):
        findings.append(f"{path.name} uses top-level include, which this lint does not resolve; inline it or extend the lint")
    services = _unwrap(doc.get("services")) or {}
    if not isinstance(services, dict):
        raise SystemExit(f"topology_lint: {path}: 'services' must be a mapping")
    out: dict[str, _Service] = {}
    for name, svc in services.items():
        svc = _unwrap(svc) or {}
        if not isinstance(svc, dict):
            raise SystemExit(f"topology_lint: {path}: service {name!r} must be a mapping")
        raw = svc.get("environment")
        replace = isinstance(raw, _Override)
        raw = _unwrap(raw)
        if raw is RESET:
            raw, replace = None, True
        env: dict[str, object] = {}
        if raw is None:
            pass
        elif isinstance(raw, list):
            for item in raw:
                k, sep, v = str(item).partition("=")
                env[k] = v if sep else PASSTHROUGH
        elif isinstance(raw, dict):
            env = {str(k): (PASSTHROUGH if v is None else v) for k, v in raw.items()}
        else:
            raise SystemExit(
                f"topology_lint: {path}: service {name!r}: environment must be a mapping or a list, "
                f"got {type(raw).__name__}"
            )
        unsupported = [k for k in ("env_file", "extends") if _unwrap(svc.get(k)) not in (None, RESET, [], {}, "")]
        profiles = _unwrap(svc.get("profiles"))
        # a healthcheck runs beside the service and cannot change its environment, so it is not read
        mentions = [
            (key, var) for key in ("command", "entrypoint") for var in VARS
            if _word(var).search(_as_text(svc.get(key)))
        ]
        wrappers: list[tuple[str, str]] = []
        for key in ("command", "entrypoint"):
            text_ = _as_text(svc.get(key)).strip()
            wm = re.match(r"(env|sudo|su|setpriv)\b", text_)
            if wm:
                wrappers.append((key, wm.group(1)))
            elif re.search(r"\benv\s+-i\b", text_):
                wrappers.append((key, "env -i"))
        zeros = [_unwrap(v) for v in (svc.get("scale"), (_unwrap(svc.get("deploy")) or {}).get("replicas")
                                      if isinstance(_unwrap(svc.get("deploy")), dict) else None)
                 if v is not None and _unwrap(v) is not RESET]
        disabled = None if not zeros else any(str(z).strip() == "0" for z in zeros)
        net = _unwrap(svc.get("network_mode"))
        out[name] = _Service(
            env, replace, unsupported,
            [str(p) for p in profiles] if isinstance(profiles, list) else [],
            network_mode=None if "network_mode" not in svc else ("" if net is RESET else str(net)),
            command=_as_text(svc.get("command")) if "command" in svc else None,
            entrypoint=_as_text(svc.get("entrypoint")) if "entrypoint" in svc else None,
            image=_as_text(svc.get("image")) if "image" in svc else None,
            mentions=mentions,
            wrappers=wrappers,
            disabled=disabled,
        )
    return out, findings


def analyse_compose(root: Path, topo: Topology) -> tuple[dict[str, VarResult], list[str], list[str]]:
    merged: dict[str, dict[str, object]] = {}
    src: dict[tuple[str, str], str] = {}  # (service, var) -> file that last set it
    lines: dict[tuple[str, str], list[int]] = {}  # (file, var) -> lines
    netmode: dict[str, str] = {}
    command: dict[str, str] = {}
    entrypoint: dict[str, str] = {}
    image: dict[str, str] = {}
    disabled: dict[str, bool] = {}
    resets: list[tuple[str, str]] = []
    findings: list[str] = []
    notes: list[str] = []
    for rel in topo.files:
        path = root / rel
        services, file_findings = _compose_services(path)
        findings.extend(file_findings)
        for svc, info in services.items():
            m = merged.setdefault(svc, {})
            if info.network_mode is not None:
                netmode[svc] = info.network_mode  # the last file that sets it wins
            if info.command is not None:
                command[svc] = info.command
            if info.entrypoint is not None:
                entrypoint[svc] = info.entrypoint
            if info.image is not None:
                image[svc] = info.image
            if info.disabled is not None:
                disabled[svc] = info.disabled
            for key, word in info.wrappers:
                findings.append(
                    f"service {svc!r} ({rel}) wraps its {key} in {word}, which can clear or rewrite the environment "
                    "after compose has applied it; this lint does not follow it"
                )
            for key, mvar in info.mentions:
                findings.append(
                    f"service {svc!r} ({rel}) mentions {mvar} in its {key}, which can unset or rewrite it "
                    "after compose has applied the environment; this lint does not read shell inside a command"
                )
            if info.replace:
                for var in VARS:
                    m.pop(var, None)
                    src.pop((svc, var), None)
            for key in sorted(set(info.env) & RISKY_ENV_KEYS):
                findings.append(f"service {svc!r} ({rel}) sets {key}, which runs code or changes loading before the service starts")
            for key in info.unsupported:
                findings.append(f"service {svc!r} ({rel}) uses {key}, which this lint does not resolve; inline it or extend the lint")
            if info.profiles:
                notes.append(f"service {svc} ({rel}) is behind profile(s) {', '.join(info.profiles)}; it only runs when the profile is activated")
            for var in VARS:
                if var not in info.env:
                    continue
                if info.env[var] is RESET:
                    m.pop(var, None)
                    src.pop((svc, var), None)
                    resets.append((var, f"{svc}.{var} removed by !reset in {rel}"))
                    continue
                m[var] = info.env[var]
                if var == "FIELD_SHARED_SECRET" and is_committed_literal(info.env[var], var):
                    findings.append(
                        f"service {svc!r} ({rel}) sets FIELD_SHARED_SECRET to a literal value; "
                        "a committed secret is not a secret, reference ${FIELD_SHARED_SECRET:?...} and keep the value in the estate .env"
                    )
                src[(svc, var)] = rel
                lines[(rel, var)] = _lines_mentioning(path, var)
    results: dict[str, VarResult] = {}
    for var in VARS:
        status = ARMED
        groups: dict[tuple[str, str], list[str]] = {}
        evidence: list[str] = []
        patterns = CONSUMER_PATTERNS.get(var)
        active = [c for c in merged if not disabled.get(c)]  # scale: 0 services never run
        consumers = None
        missing_consumer = False
        if patterns is not None:
            consumers = [
                c for c in active
                if patterns[0].search(entrypoint.get(c, "") + " " + command.get(c, "")) or patterns[1].search(image.get(c, ""))
            ]
            considered = consumers
            ignored = sorted(set(merged) - set(consumers))
            if not consumers:
                missing_consumer = True
                status = _weaker(status, OPERATOR)
                evidence.append(f"no service runs the reader of {var}; cannot show it is armed")
        else:
            considered, ignored = active, []
        absent: list[str] = []
        exempt: list[str] = []
        weak: set[str] = set()
        if missing_consumer:
            weak.add(f"(no {var} consumer)")
        for svc in considered:
            env = merged[svc]
            if var in env:
                st = classify_value(env[var], var)
                status = _weaker(status, st)
                groups.setdefault((st, src[(svc, var)]), []).append(svc)
                if st != ARMED:
                    weak.add(svc)
            elif consumers is not None:
                status = _weaker(status, EMPTY)
                absent.append(svc)
                weak.add(svc)
            elif netmode.get(svc) != "none":
                named = SERVICE_EXEMPTIONS.get((topo.id, var, svc))
                if named and _exemption_holds(named[1], image.get(svc, ""), netmode.get(svc)):
                    exempt.append(f"{svc} ({named[0]})")
                else:
                    if named:
                        evidence.append(f"the exemption named for {svc} does not apply: it is not {named[1]}")
                    status = _weaker(status, EMPTY)
                    absent.append(svc)
                    weak.add(svc)
            else:
                exempt.append(f"{svc} (network_mode none: reachable by nothing)")
        if not groups and not absent and consumers is None:
            status = _weaker(status, OPERATOR)
            weak.add("(no service sets it)")
            evidence.append("not referenced by any service environment")
        for (st, rel), svcs in groups.items():
            ln = ",".join(map(str, lines[(rel, var)]))
            evidence.append(f"{st}: {', '.join(svcs)} ({rel}, mentions at line {ln})")
        if absent:
            evidence.append(
                "no entry (compose forwards no host env, so the variable is unset there): "
                + ", ".join(sorted(absent))
            )
        for e in exempt:
            evidence.append(f"exempt, no entry: {e}")
        if ignored:
            evidence.append(f"ignored, not a consumer of {var}: {', '.join(ignored)}")
        evidence.extend(msg for v, msg in resets if v == var)
        results[var] = VarResult(status, evidence, tuple(sorted(weak)) if status != ARMED else ())
    return results, findings, notes


def strip_trailing_comment(line: str) -> str:
    """Drop a ``# comment`` that is outside quotes and starts a word."""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == "\\" and quote == '"':
                continue
            if ch == quote and not (i and line[i - 1] == "\\" and quote == '"'):
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i].rstrip()
    return line.rstrip()


def _word(var: str) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(var) + r"(?![A-Za-z0-9_])")


# Shell builtins never need a stub; external utilities get a NO-OP logging stub (they
# must not run for real); everything else a script launches is a service and gets a
# stub that records what it saw.
_BUILTINS = frozenset({
    "export", "set", "trap", "echo", "printf", "cd", "umask", "true", "false", "test", "[", "[[", "return",
    "shift", "readonly", "exit", "wait", "kill", "read", "unset", "declare", "typeset", "local", "source",
    "eval", "pwd", ":", "type", "hash", "let", "getopts", "jobs", "fg", "bg", "alias",
})
_EXTERNAL_UTILS = frozenset({
    "mkdir", "cat", "sed", "grep", "date", "rm", "cp", "mv", "ln", "touch", "chmod", "chown", "ls", "head",
    "tail", "tr", "cut", "sort", "id", "dirname", "basename", "sleep", "uname", "tee", "wc", "find", "install",
    "mktemp", "hostname",
})
_SAFE_WORDS = _BUILTINS | _EXTERNAL_UTILS
_KEYWORD_POP = frozenset({"if", "then", "else", "elif", "do", "while", "until", "!", "time"})
_KEYWORD_SKIP = frozenset({"for", "case", "select", "fi", "done", "esac", "in", "function"})
_WRAPPERS = frozenset({"exec", "command", "nohup", "env", "sudo", "time", "xargs", "setsid", "timeout", "nice", "stdbuf"})
_ASSIGN_PREFIX = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=(?:\"[^\"]*\"|'[^']*'|\S*)\s*)+")
_FUNC_NAMES = re.compile(r"(?:^|[;&|{}\n]\s*)(?:function\s+)?([A-Za-z_][\w-]*)\s*\(\s*\)")

# The static reading of entrypoint.sh is a COARSE TRIPWIRE only. Each rule here is
# cheap and sound (a hit means "this text can hide or rewrite an assignment from a
# reader that is not bash"); a miss proves nothing. Whether the script is armed is
# established by RUNNING it (run_entrypoint), not by this parser.
_BANNED = (
    (re.compile(r"<<"), "a heredoc or here-string"),
    (re.compile(r"(?<![\w.-])eval\b"), "eval"),
    (re.compile(r"(?:^|[;&|(]\s*|\bexec\s+|\bcommand\s+)(?:source|\.)\s"), "source / '.'"),
    (re.compile(r"(?<![A-Za-z0-9_])env(?![A-Za-z0-9_])"), "env (incl. /usr/bin/env, command env, \\env)"),
    (re.compile(r"\b(?:sh|bash|dash|zsh|ksh)\b(?:\s+-[A-Za-z-]+)*\s+-[A-Za-z]*c\b"), "sh -c / bash -c"),
    (re.compile(r"\bexec\s+-c\b"), "exec -c"),
    (re.compile(r"\bprintf\s+-v\b"), "printf -v"),
    (re.compile(r"(?:^|[;&|(]\s*)read\b"), "read"),
    (re.compile(r"\$\{![A-Za-z_]"), "indirect expansion ${!NAME}"),
    (re.compile(r"\b(?:declare|typeset|local|export|readonly)\s+-\w*n"), "a nameref"),
    (re.compile(r"\bBASH_ENV\b|\bPROMPT_COMMAND\b|\bBASH_XTRACEFD\b"), "BASH_ENV / PROMPT_COMMAND"),
    (re.compile(r"(?:^|[;&|(]\s*|\bexec\s+)unset\b"), "unset"),
    (re.compile(r"(?:^|[\s;&|(])[A-Za-z_][A-Za-z0-9_]*(?:(?:\"\"|''|\$\{?\w+\}?|\\)[A-Za-z0-9_]*)+="),
     "an assignment to a computed or split variable name"),
)
_DECL_NAME = re.compile(r"\b(?:export|declare|typeset|readonly)\s+(?:-\w+\s+)*([^\s=]*)")


def _logical_lines(text: str) -> list[tuple[int, str]]:
    """Physical lines joined the way the shell joins them: a trailing backslash
    removes the newline and NOTHING is inserted; a backslash inside a trailing
    ``# comment`` is part of the comment and continues nothing."""
    physical = text.splitlines()
    out: list[tuple[int, str]] = []
    k = 0
    while k < len(physical):
        start, buf = k, physical[k]
        while k + 1 < len(physical) and not buf.lstrip().startswith("#"):
            code = strip_trailing_comment(buf)
            if code != buf.rstrip():
                break  # a comment was cut off: its backslash is not a continuation
            m = re.search(r"(\\+)$", code)
            if not m or len(m.group(1)) % 2 == 0:
                break
            buf = code[:-1] + physical[k + 1]
            k += 1
        out.append((start + 1, buf))
        k += 1
    return out


def _mask(s: str) -> str:
    """Same length as ``s`` with quoted text, ``${...}``, ``$(...)`` and the ``&`` of
    redirections blanked, so splitting on operators cannot cut inside them."""
    m = list(s)
    i, quote = 0, ""
    while i < len(s):
        c = s[i]
        if quote:
            m[i] = "x"
            if c == "\\" and quote == '"' and i + 1 < len(s):
                m[i + 1] = "x"
                i += 2
                continue
            if c == quote:
                quote = ""
            i += 1
            continue
        if c in "\"'":
            quote, m[i] = c, "x"
        elif s.startswith("${", i) or s.startswith("$(", i):
            opener, closer = ("{", "}") if s[i + 1] == "{" else ("(", ")")
            depth, j = 0, i + 1
            while j < len(s):
                if s[j] == opener:
                    depth += 1
                elif s[j] == closer:
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            for k in range(i, min(j + 1, len(s))):
                m[k] = "x"
            i = j
        elif c == "&" and ((i and s[i - 1] in "<>") or s[i + 1 : i + 2] == ">"):
            m[i] = "x"
        elif c == "\\":
            m[i] = "x"
        i += 1
    return "".join(m)


@dataclass
class CommandScan:
    services: list[str] = field(default_factory=list)  # stubbed with a recording stub
    utilities: list[str] = field(default_factory=list)  # stubbed as no-ops (never run for real)
    indirect: list[tuple[int, str]] = field(default_factory=list)  # (line, word): path / variable / substitution launches


def scan_commands(text: str) -> CommandScan:
    """Every command the script can start, read from its text: each segment between
    ``; & | && || ( ) { }`` contributes its first word after leading ``VAR=x``, shell
    keywords and wrappers (``exec``, ``env``, ``sudo``, ``xargs``, ``timeout N``, ``command -v X``...).
    A first word that is a path, a variable or a substitution cannot be stubbed and
    is reported in ``indirect``."""
    out = CommandScan()
    funcs = set(_FUNC_NAMES.findall(text))
    for lineno, raw in _logical_lines(text):
        if raw.lstrip().startswith("#"):
            continue
        code = strip_trailing_comment(raw)
        masked = _mask(code)
        pieces, start = [], 0
        for i, ch in enumerate(masked):
            if ch in ";&|(){}":
                pieces.append(code[start:i])
                start = i + 1
        pieces.append(code[start:])
        for seg in pieces:
            words = _ASSIGN_PREFIX.sub("", seg.strip()).strip().split()
            while words and words[0] in _KEYWORD_POP:
                words = words[1:]
            while words and words[0] in _WRAPPERS:
                wrapper = words.pop(0)
                if wrapper == "command" and words and words[0] in ("-v", "-V"):
                    if len(words) > 1 and re.fullmatch(r"[A-Za-z][\w.-]*", words[1]) and words[1] not in _SAFE_WORDS:
                        out.services.append(words[1]) if words[1] not in out.services else None
                    words = []
                    break
                while words and (words[0].startswith("-") or re.fullmatch(r"[A-Za-z_]\w*=\S*", words[0])
                                 or (wrapper in ("timeout", "nice") and re.fullmatch(r"[\d.]+[smhd]?", words[0]))):
                    words = words[1:]
            if not words:
                continue
            first = words[0]
            if first in _KEYWORD_SKIP or first in funcs:
                continue
            if re.fullmatch(r"[A-Za-z][\w.-]*", first):
                if first in _BUILTINS:
                    continue
                bucket = out.utilities if first in _EXTERNAL_UTILS else out.services
                if first not in bucket:
                    bucket.append(first)
            elif first[0] in "/.~$\"'`":
                out.indirect.append((lineno, first[:40]))
    return out


def entrypoint_commands(text: str) -> list[str]:
    """The service commands the script launches (see ``scan_commands``)."""
    return scan_commands(text).services


def parse_entrypoint(text: str, name: str = "integration/fly/entrypoint.sh") -> tuple[dict[str, tuple[str, int]], list[str]]:
    """Coarse tripwire plus a rough static status per variable.

    Findings are the tripwire rules above, a launch by absolute path, variable or
    substitution (it cannot be stubbed), a committed literal ``FIELD_SHARED_SECRET``
    export, and risky startup-hook variables. The returned status (a ``:?`` guard
    seen anywhere, else the first ``export``'s value) is only the fallback when the
    script cannot be run; ``run_entrypoint`` is what decides armed-ness.
    """
    guards: dict[str, int] = {}
    exports: dict[str, tuple[str, int]] = {}
    findings: list[str] = []
    for i, raw in _logical_lines(text):
        if raw.lstrip().startswith("#"):
            continue
        line = strip_trailing_comment(raw)
        stripped = line.strip()
        for pat, what in _BANNED:
            if pat.search(stripped):
                findings.append(f"{name}:{i} uses {what}, which can hide or rewrite an assignment from a static reader")
        for m in _DECL_NAME.finditer(stripped):
            if m.group(1) and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", m.group(1)):
                findings.append(f"{name}:{i} exports a computed or quoted variable name, which this lint cannot read")
        for key in sorted(RISKY_ENV_KEYS):
            if re.search(r"(?<![A-Za-z0-9_])" + key + r"\s*=", stripped):
                findings.append(f"{name}:{i} sets {key}, which runs code or changes loading before the services start")
        for var in VARS:
            if re.search(r":\s+\"?\$\{" + re.escape(var) + r":\?", stripped):
                guards.setdefault(var, i)
            ex = re.match(r"\s*export\s+" + re.escape(var) + r"=(\"(?:[^\"\\]|\\.)*\"|'[^']*'|[^\s;&|]*)", line)
            if ex and var not in exports:
                exports[var] = (ex.group(1), i)
                if var == "FIELD_SHARED_SECRET" and is_committed_literal(ex.group(1), var, interpolate=not ex.group(1).startswith("'")):
                    findings.append(
                        f"{name}:{i} sets {var} to a literal value or a literal default; "
                        "a committed secret is not a secret, keep the value in `fly secrets`"
                    )
    for ln, word in scan_commands(text).indirect:
        findings.append(
            f"{name}:{ln} launches {word!r} by absolute path, variable or substitution; "
            "it cannot be replaced by a stub, so the behavioural run refuses to execute this script"
        )
    out: dict[str, tuple[str, int]] = {}
    for var in VARS:
        if var in guards:
            out[var] = (ARMED, guards[var])
        elif var in exports:
            raw_val, ln = exports[var]
            out[var] = (classify_value(raw_val, var, interpolate=not raw_val.startswith("'")), ln)
    return out, findings


# --- behavioural check: run the real entrypoint.sh under bash with stub services ---

# The reviewed set of services entrypoint.sh launches. A different set (a service
# added, removed or hidden in a loop) is a finding until a reviewer updates this.
EXPECTED_FLY_STUBS = (
    "registry", "ledger", "delegation", "sentinel", "killswitch", "governor", "replay",
    "forcegw", "fedbroker", "console", "crosswalk", "lifecycle", "attest", "caddy",
)
SENTINEL_SECRET = "stub-secret"
SENTINEL_ROSTER = "/run/roster.yaml"


@dataclass
class EntryRun:
    ran: bool
    reason: str = ""  # why it did not run
    refused: bool = False  # not run on purpose (an unstubbable launch); the tripwire already reports it
    status: dict[str, str] = field(default_factory=dict)  # var -> ARMED when the script refuses to start, else EMPTY
    findings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    stubs: list[str] = field(default_factory=list)
    summary: str = ""


def find_bash() -> str | None:
    """A real bash: $TOPOLOGY_LINT_BASH, Git Bash on Windows, then PATH (never WSL's bash.exe)."""
    import shutil

    def plain(path: str) -> str:
        # Git for Windows' bin\bash.exe is a wrapper that PREPENDS /mingw64/bin and /usr/bin
        # to PATH, which would put the real touch/mkdir ahead of the stubs. The sibling
        # usr\bin\bash.exe honours the PATH it is given.
        p = Path(path)
        sibling = p.parent.parent / "usr" / "bin" / "bash.exe"
        return str(sibling) if os.name == "nt" and p.parent.name.lower() == "bin" and sibling.is_file() else path

    env = os.environ.get("TOPOLOGY_LINT_BASH")
    if env:
        return env if Path(env).is_file() else shutil.which(env)
    for cand in (r"d:\Apps\Git\bin\bash.exe", r"C:\Program Files\Git\bin\bash.exe"):
        if os.name == "nt" and Path(cand).is_file():
            return plain(cand)
    found = shutil.which("bash")
    if found and "system32" not in found.lower() and "windowsapps" not in found.lower():
        return plain(found)
    return None


_PATH_PROBE: dict[str, bool] = {}


def _honours_restricted_path(bash: str) -> bool:
    """True when bash keeps PATH exactly as given (so the stub directory contains the run)."""
    if bash not in _PATH_PROBE:
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory(prefix="topology-lint-probe-") as td:
            env = {k: v for k, v in os.environ.items() if k in ("SYSTEMROOT", "SystemRoot", "WINDIR", "COMSPEC", "MSYSTEM")}
            env["PATH"] = Path(td).as_posix()
            try:
                r = subprocess.run([bash, "-c", 'printf %s "$PATH"'], env=env, capture_output=True, text=True, timeout=30, cwd=td)
                _PATH_PROBE[bash] = r.returncode == 0 and len([e for e in r.stdout.split(":") if e]) == 1
            except (OSError, subprocess.SubprocessError):
                _PATH_PROBE[bash] = False
    return _PATH_PROBE[bash]


_STUB = """#!/bin/sh
if [ "${FIELD_SHARED_SECRET+x}" ]; then if [ -n "$FIELD_SHARED_SECRET" ]; then s=set; else s=empty; fi; else s=unset; fi
if [ "${FIELD_DOA_ROSTER+x}" ]; then if [ -n "$FIELD_DOA_ROSTER" ]; then r=set; else r=empty; fi; else r=unset; fi
printf 'started %s argv0=%s S=%s[%s] D=%s[%s]\\n' 'NAME' "$0" "$s" "$FIELD_SHARED_SECRET" "$r" "$FIELD_DOA_ROSTER" >> "$STUB_LOG"
for sl in /bin/sleep /usr/bin/sleep; do [ -x "$sl" ] && exec "$sl" 2; done
"""
_UTILITY_STUB = """#!/bin/sh
printf 'utility %s %s\\n' 'NAME' "$*" >> "$STUB_LOG"
"""
# (label, environment, variables to drop, kind). "refuse" scenarios decide armed-ness;
# "blank" asks whether the script also refuses a whitespace-only roster (delegation
# strips it to unset = gate off); "info" scenarios only document weak-but-set values.
_SCENARIOS = (
    ("secret unset", {"FIELD_DOA_ROSTER": SENTINEL_ROSTER}, "refuse"),
    ("secret empty", {"FIELD_SHARED_SECRET": "", "FIELD_DOA_ROSTER": SENTINEL_ROSTER}, "refuse"),
    ("roster unset", {"FIELD_SHARED_SECRET": SENTINEL_SECRET}, "refuse"),
    ("roster empty", {"FIELD_SHARED_SECRET": SENTINEL_SECRET, "FIELD_DOA_ROSTER": ""}, "refuse"),
    ("both set", {"FIELD_SHARED_SECRET": SENTINEL_SECRET, "FIELD_DOA_ROSTER": SENTINEL_ROSTER}, "set"),
    ("roster blank", {"FIELD_SHARED_SECRET": SENTINEL_SECRET, "FIELD_DOA_ROSTER": " "}, "blank"),
    ("secret blank", {"FIELD_SHARED_SECRET": " ", "FIELD_DOA_ROSTER": SENTINEL_ROSTER}, "info"),
    ("secret null", {"FIELD_SHARED_SECRET": "null", "FIELD_DOA_ROSTER": SENTINEL_ROSTER}, "info"),
    ("secret zero", {"FIELD_SHARED_SECRET": "0", "FIELD_DOA_ROSTER": SENTINEL_ROSTER}, "info"),
)
_STARTED = re.compile(r"^started (\S+) argv0=(\S+) S=(\w+)\[(.*)\] D=(\w+)\[(.*)\]$", re.M)
_RUN_ERRORS = re.compile(r"command not found|No such file or directory|: not found|Permission denied|syntax error")


def _run_scenario(bash: str, text: str, scan: CommandScan, env_vars: dict[str, str], timeout: float):
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory(prefix="topology-lint-") as td_:
        td = Path(td_)
        sdir = td / "stubs"
        sdir.mkdir()
        log = td / "stub.log"
        log.write_text("", encoding="utf-8")
        for name in scan.services:
            f = sdir / name
            f.write_text(_STUB.replace("NAME", name), encoding="utf-8", newline="\n")
            f.chmod(0o755)
        for name in scan.utilities:
            f = sdir / name
            f.write_text(_UTILITY_STUB.replace("NAME", name), encoding="utf-8", newline="\n")
            f.chmod(0o755)
        script = td / "entrypoint.sh"
        script.write_text(text, encoding="utf-8", newline="\n")
        # PATH is the stub directory ONLY: no host binary can be found by name. HOME,
        # TMPDIR and the working directory are the temp dir so a stray write stays there.
        env = {k: v for k, v in os.environ.items()
               if k in ("SYSTEMROOT", "SystemRoot", "WINDIR", "COMSPEC", "MSYSTEM", "LANG", "LC_ALL")}
        env.update(PATH=sdir.as_posix(), STUB_LOG=log.as_posix(), FIELD_DATA_DIR=(td / "data").as_posix(),
                   HOME=td.as_posix(), TMPDIR=td.as_posix(), TMP=td.as_posix(), TEMP=td.as_posix())
        env.update(env_vars)
        kwargs = {"start_new_session": True} if os.name != "nt" else {}
        p = subprocess.Popen([bash, script.as_posix()], env=env, cwd=str(td), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace", **kwargs)
        try:
            _out, err = p.communicate(timeout=timeout)
            rc: object = p.returncode
        except subprocess.TimeoutExpired:
            # SIGKILL only: the script traps TERM and its handler signals every process.
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
            else:
                import signal
                os.killpg(p.pid, signal.SIGKILL)
            p.communicate()
            rc, err = "TIMEOUT", ""
        started = _STARTED.findall(log.read_text(encoding="utf-8", errors="replace"))
        return rc, started, err or "", td.name


_RUN_CACHE: dict[tuple[str, str], EntryRun] = {}


def run_entrypoint(text: str, bash: str | None = None, timeout: float = 30.0) -> EntryRun:
    """Run the script (not a model of it) under bash with stub executables for every
    command it launches, in nine scenarios, in a temp dir with a hard timeout.

    What is and is not contained: PATH is the stub directory only, so a command
    looked up by NAME can only be a stub (services record what they saw; external
    utilities such as ``mkdir`` or ``touch`` are no-op stubs). A launch by absolute
    path, variable or substitution cannot be intercepted, so a script that has one
    is NOT executed (``refused``). Network access is not blocked by the sandbox:
    nothing but stubs and builtins is reachable by name.

    A variable is armed only if, with it unset and with it empty, the script exits
    non-zero and no stub starts. With both set, every stub must start exactly once
    with the values it was GIVEN (not just non-empty ones), argv0 inside the stub
    directory, and nothing may report a missing or unrunnable command."""
    from concurrent.futures import ThreadPoolExecutor

    text = text.replace("\r\n", "\n")
    bash = bash or find_bash()
    if bash is None:
        return EntryRun(False, "no bash found")
    key = (bash, text)
    if key in _RUN_CACHE:
        return _RUN_CACHE[key]
    if not _honours_restricted_path(bash):
        return EntryRun(False, f"{bash} adds its own directories to PATH, so stubs cannot contain the run; "
                               "point TOPOLOGY_LINT_BASH at a plain bash (Git for Windows: usr/bin/bash.exe)")
    scan = scan_commands(text)
    if scan.indirect:
        return EntryRun(False, "not run: the script launches by absolute path, variable or substitution, which cannot be stubbed", refused=True)
    if not scan.services:
        return EntryRun(False, "no service launches found in the script")

    def one(sc):
        label, env_vars, _kind = sc
        return label, _run_scenario(bash, text, scan, env_vars, timeout)

    with ThreadPoolExecutor(len(_SCENARIOS)) as ex:
        results = dict(ex.map(one, _SCENARIOS))
    stubs = scan.services
    res = EntryRun(True, stubs=list(stubs))
    kinds = {lb: k for lb, _e, k in _SCENARIOS}

    def refuses(label: str) -> bool:
        rc, started, _err, _tmp = results[label]
        return not started and rc not in (0, "TIMEOUT")

    for label, (rc, started, err, tmpname) in results.items():
        if rc == "TIMEOUT":
            res.findings.append(f"entrypoint.sh behavioural run '{label}' timed out after {timeout:.0f}s")
        bad = next((ln for ln in err.splitlines() if _RUN_ERRORS.search(ln)), None)
        if bad:
            res.findings.append(
                f"entrypoint.sh scenario '{label}' reported a missing or unrunnable command ({bad.strip()[:140]!r}); "
                "a launch the stubs did not cover ran or failed unseen"
            )
        for g in started:
            if tmpname not in g[1] or "/stubs/" not in g[1].replace("\\", "/"):
                res.findings.append(f"entrypoint.sh scenario '{label}': '{g[0]}' ran from {g[1]}, outside the stub directory")
    for var, labels in (("FIELD_SHARED_SECRET", ("secret unset", "secret empty")), ("FIELD_DOA_ROSTER", ("roster unset", "roster empty"))):
        res.status[var] = EMPTY if any(not refuses(lb) for lb in labels) else ARMED
    rc, started, err, _t = results["both set"]
    for name in stubs:
        lines = [g for g in started if g[0] == name]
        if not lines:
            res.findings.append(
                f"entrypoint.sh with both variables set: service '{name}' never started (exit {rc}); "
                f"something stops the script before it launches it ({err.strip()[:120]!r})"
            )
            continue
        if len(lines) > 1:
            res.findings.append(f"entrypoint.sh with both variables set: service '{name}' started {len(lines)} times")
        for _n, _a0, s, sv, r, dv in lines:
            if (s, sv, r, dv) != ("set", SENTINEL_SECRET, "set", SENTINEL_ROSTER):
                res.findings.append(
                    f"entrypoint.sh with both variables set: service '{name}' saw FIELD_SHARED_SECRET={s}[{sv!r}] "
                    f"FIELD_DOA_ROSTER={r}[{dv!r}] but was given {SENTINEL_SECRET!r} and {SENTINEL_ROSTER!r}; "
                    "something rewrote them after the check"
                )
    unknown = sorted({g[0] for g in results["both set"][1]} - set(stubs))
    if unknown:
        res.findings.append(f"entrypoint.sh started unexpected stubs {unknown}")
    if res.status["FIELD_DOA_ROSTER"] == ARMED and results["roster blank"][1]:
        res.findings.append(
            "entrypoint.sh refuses an unset or empty FIELD_DOA_ROSTER but starts the services with a whitespace-only one; "
            "delegation's roster_path() strips it to unset, so the roster gate is OFF. Refuse blank values too "
            "(for example: [ -n \"${FIELD_DOA_ROSTER// /}\" ] || exit 1)"
        )
    for label in ("secret blank", "secret null", "secret zero"):
        started = results[label][1]
        res.notes.append(f"{label}: {'services started' if started else 'script refused'} (a set but weak value; not a finding)")
    res.summary = f"{len(stubs)} service stubs, {len(_SCENARIOS)} scenarios"
    _RUN_CACHE[key] = res
    return res


def parse_dockerfile(text: str) -> list[tuple[int, str, str]]:
    """(line, INSTRUCTION, rest). Continuation lines are joined WITHOUT inserting a
    space (as Docker does, so ``FIELD_SHARED_\\<newline>SECRET`` is one name), comment
    lines inside a continuation are dropped, and a leading ``# escape=X`` parser
    directive changes the continuation character."""
    esc = "\\"
    lines = text.splitlines()
    for raw in lines:
        m = re.fullmatch(r"#\s*([A-Za-z]+)\s*=\s*(\S+)\s*", raw)
        if not m:
            break
        if m.group(1).lower() == "escape":
            esc = m.group(2)
    out: list[tuple[int, str, str]] = []
    buf, start = "", 0
    for i, raw in enumerate(lines, 1):
        if not buf and (not raw.strip() or raw.lstrip().startswith("#")):
            continue
        if raw.lstrip().startswith("#"):
            continue
        if not buf:
            start = i
        stripped = raw.rstrip()
        cont = stripped.endswith(esc)
        buf += stripped[: -len(esc)] if cont else raw
        if not cont:
            parts = buf.strip().split(None, 1)
            out.append((start, parts[0].upper(), parts[1] if len(parts) > 1 else ""))
            buf = ""
    if buf.strip():
        parts = buf.strip().split(None, 1)
        out.append((start, parts[0].upper(), parts[1] if len(parts) > 1 else ""))
    return out


_DF_INSTRUCTIONS = frozenset(
    {"FROM", "WORKDIR", "COPY", "RUN", "ENV", "EXPOSE", "ARG", "ENTRYPOINT", "LABEL", "USER", "VOLUME", "CMD"}
)
_CRLF_SED = re.compile(r"""sed\s+-i\s+(['"])s/\\r\$//g?\1\s+/entrypoint\.sh""")
_RUN_PIECE_OK = (re.compile(r"pip install\b[^;|&`$]*"), re.compile(r"chmod\b[^;|&`$]*"))
_SHELL_STARTUP = re.compile(r"\bBASH_ENV\b|\bPROMPT_COMMAND\b|\bBASH_XTRACEFD\b")
_ENV_PAIR = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(\"(?:[^\"\\]|\\.)*\"|'[^']*'|\S*)")


def _run_is_known(rest: str) -> bool:
    parts = [p.strip() for p in re.split(r"&&", rest)]
    return bool(parts) and all(
        _CRLF_SED.fullmatch(p) or any(r.fullmatch(p) for r in _RUN_PIECE_OK) for p in parts
    )


def _env_pairs(rest: str) -> list[tuple[str, str]]:
    pairs = _ENV_PAIR.findall(rest)
    if pairs:
        return pairs
    parts = rest.split(None, 1)  # legacy `ENV NAME value`
    return [(parts[0], parts[1])] if len(parts) == 2 else []


def _expand(text: str, env: dict[str, str]) -> str:
    return re.sub(r"\$\{(\w+)\}|\$(\w+)", lambda m: env.get(m.group(1) or m.group(2), ""), text)


def _norm_dst(dst: str, workdir: str, env: dict[str, str]) -> tuple[str, bool]:
    """(normalised absolute destination, destination-is-a-directory)."""
    import posixpath

    d = _expand(dst, env)
    is_dir = d.endswith("/") or d in ("", ".", "..")
    if not d.startswith("/"):
        d = posixpath.join(workdir, d)
    d = re.sub(r"/+", "/", d)
    return posixpath.normpath(d), is_dir


def analyse_dockerfile(text: str, name: str) -> list[str]:
    """Allow-list reading of the Fly image: only the known instruction shapes pass."""
    import posixpath

    findings: list[str] = []
    entrypoint = None
    copied = False
    froms = 0
    workdir = "/"
    env: dict[str, str] = {}
    for ln, instr, rest in parse_dockerfile(text):
        where = f"{name}:{ln} {instr}"
        if instr not in _DF_INSTRUCTIONS:
            findings.append(f"{where} is not an instruction this lint allows (ADD, SHELL, ONBUILD, ... change what runs)")
            continue
        if _SHELL_STARTUP.search(rest):
            findings.append(f"{where} mentions BASH_ENV / PROMPT_COMMAND, which run code before entrypoint.sh's own lines")
        if instr == "ENV":
            for key, val in _env_pairs(rest):
                env[key] = _strip_quotes(val)
                if key in RISKY_ENV_KEYS:
                    findings.append(f"{where} sets {key}, which runs code or changes loading before the service starts")
                if key in VARS and is_committed_literal(val, key):
                    findings.append(f"{where} bakes a literal {key} (or a literal default) into the image layer")
        else:
            for var in VARS:
                if _word(var).search(rest) and instr in ("ARG", "CMD", "RUN", "ENTRYPOINT"):
                    findings.append(f"{where} mentions {var}; the value would no longer come only from entrypoint.sh and the runtime environment")
        if instr == "FROM":
            froms += 1
            if froms > 1:
                findings.append(f"{where}: more than one FROM; this lint reads a single-stage image")
        elif instr == "WORKDIR":
            d = _expand(rest.strip(), env)
            workdir = posixpath.normpath(re.sub(r"/+", "/", d if d.startswith("/") else posixpath.join(workdir, d)))
        elif instr == "ENTRYPOINT":
            entrypoint = (ln, rest)
        elif instr == "RUN":
            if not _run_is_known(rest):
                if "entrypoint.sh" in rest:
                    findings.append(f"{where} touches entrypoint.sh after it is copied, so the analysed file is not what runs")
                else:
                    findings.append(f"{where} is not a known RUN (pip install, chmod, the CRLF sed on entrypoint.sh); review it and extend the lint")
        elif instr == "COPY":
            try:
                args = json.loads(rest) if rest.lstrip().startswith("[") else rest.split()
            except ValueError:
                args = rest.split()
            flags = [str(a) for a in args if str(a).startswith("--")]
            paths = [str(a) for a in args if not str(a).startswith("--")]
            if len(paths) < 2:
                findings.append(f"{where} could not be read (fewer than two paths)")
                continue
            srcs = paths[:-1]
            dst, is_dir = _norm_dst(paths[-1], workdir, env)
            from_flags = [f for f in flags if f.startswith("--from")]
            if from_flags and not (dst == "/usr/bin/caddy" and all(f.startswith("--from=caddy:") for f in from_flags)):
                findings.append(f"{where} uses --from for something other than the caddy binary")
            if dst == "/":
                findings.append(f"{where} copies onto the filesystem root, which could overwrite /entrypoint.sh")
            targets = [dst] if not is_dir and len(srcs) == 1 else [posixpath.join(dst, posixpath.basename(s.rstrip("/"))) for s in srcs]
            if "/entrypoint.sh" in targets:
                if srcs == ["integration/fly/entrypoint.sh"] and not from_flags and dst == "/entrypoint.sh":
                    copied = True
                else:
                    findings.append(f"{where} copies something other than integration/fly/entrypoint.sh to /entrypoint.sh")
    if entrypoint is None:
        findings.append(f"{name}: no ENTRYPOINT; the analysed entrypoint.sh would not be the process that starts")
    else:
        ln, rest = entrypoint
        try:
            argv = json.loads(rest) if rest.lstrip().startswith("[") else None
        except ValueError:
            argv = None
        if argv != ["/entrypoint.sh"]:
            findings.append(f'{name}:{ln} ENTRYPOINT must be exactly the exec form ["/entrypoint.sh"]')
    if not copied and not any("copies something other" in f for f in findings):
        findings.append(f"{name}: no `COPY integration/fly/entrypoint.sh /entrypoint.sh`; the analysed file is not shown to be what runs")
    return findings


# fly.toml tables and [build] keys whose effect this lint understands. Anything
# else (processes, experimental, services, deploy, a prebuilt image, buildpacks)
# can change what runs or how the environment is built.
FLY_TOML_KEYS = frozenset({"app", "primary_region", "kill_signal", "kill_timeout", "build", "env", "http_service", "mounts", "vm"})
FLY_BUILD_KEYS = frozenset({"dockerfile", "args", "ignorefile"})


def _ci() -> bool:
    return os.environ.get("CI", "").strip().lower() in ("1", "true", "yes")


def analyse_fly(root: Path, topo: Topology, behavioural: bool = False, forced_off_in_ci: bool = False) -> tuple[dict[str, VarResult], list[str], str]:
    entry = root / "integration/fly/entrypoint.sh"
    toml = root / "integration/fly/fly.toml"
    entry_text = entry.read_bytes().decode("utf-8").replace("\r\n", "\n")
    from_entry, findings = parse_entrypoint(entry_text)
    run: EntryRun | None = None
    if not behavioural:
        behaviour = "SKIPPED (disabled by TOPOLOGY_LINT_BEHAVIOURAL or by the caller)"
        if forced_off_in_ci:
            findings.append(
                "TOPOLOGY_LINT_BEHAVIOURAL disables the entrypoint behavioural check but CI is set; "
                "the check cannot be turned off in CI. Unset the variable"
            )
    else:
        bash = find_bash()
        if bash is None:
            behaviour = "SKIPPED (no bash found)"
            if _ci():
                findings.append(
                    "the entrypoint behavioural check could not run: bash is missing and CI is set. "
                    "Install bash or set TOPOLOGY_LINT_BASH; the check is never skipped in CI"
                )
        else:
            run = run_entrypoint(entry_text, bash)
            if run.ran:
                behaviour = f"RAN ({run.summary})"
                findings.extend(run.findings)
                if tuple(run.stubs) != EXPECTED_FLY_STUBS:
                    added = sorted(set(run.stubs) - set(EXPECTED_FLY_STUBS))
                    missing = sorted(set(EXPECTED_FLY_STUBS) - set(run.stubs))
                    findings.append(
                        f"entrypoint.sh launches {len(run.stubs)} services, but {len(EXPECTED_FLY_STUBS)} were reviewed "
                        f"(unreviewed: {added}; no longer launched: {missing}); a reviewer must confirm the change "
                        "and update EXPECTED_FLY_STUBS in tools/topology_lint.py"
                    )
            else:
                behaviour = f"SKIPPED ({run.reason})"
                if _ci() and not run.refused:
                    findings.append(f"the entrypoint behavioural check could not run in CI: {run.reason}")
                run = None
    try:
        import tomllib
    except ImportError as exc:  # Python < 3.11: refuse rather than silently skip fly.toml
        raise SystemExit("topology_lint: needs Python 3.11+ (tomllib) to read integration/fly/fly.toml") from exc
    try:
        doc = tomllib.loads(toml.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"topology_lint: cannot parse {toml}: {exc}") from exc
    env_table = doc.get("env") or {}
    if not isinstance(env_table, dict):
        raise SystemExit(f"topology_lint: {toml}: [env] must be a table")
    if is_committed_literal(env_table.get("FIELD_SHARED_SECRET"), interpolate=False):
        findings.append(
            "integration/fly/fly.toml [env] sets FIELD_SHARED_SECRET to a literal value; "
            "fly.toml is committed, use `fly secrets set` instead"
        )
    for key in sorted(set(doc) - FLY_TOML_KEYS):
        findings.append(
            f"integration/fly/fly.toml has an unknown [{key}] section, which can change what runs "
            "or how the environment is built; review it and extend the lint"
        )
    for key in sorted(set(env_table) & RISKY_ENV_KEYS):
        findings.append(f"integration/fly/fly.toml [env] sets {key}, which runs code or changes loading before entrypoint.sh's own lines")
    build = doc.get("build") or {}
    if isinstance(build, dict):
        for key in sorted(set(build) - FLY_BUILD_KEYS):
            findings.append(
                f"integration/fly/fly.toml [build] sets {key}, so the image may not be integration/fly/Dockerfile"
            )
    df_rel = str(build.get("dockerfile", "Dockerfile")) if isinstance(build, dict) else "Dockerfile"
    df = toml.parent / df_rel
    if not df.is_file():
        raise SystemExit(f"topology_lint: fly.toml [build].dockerfile resolves to {df_rel}, which does not exist")
    findings.extend(analyse_dockerfile(df.read_bytes().decode("utf-8").replace("\r\n", "\n"), os.path.relpath(df, root).replace(os.sep, "/")))
    results: dict[str, VarResult] = {}
    for var in VARS:
        evidence: list[str] = []
        toml_status = classify_value(env_table[var], var, interpolate=False) if var in env_table else None
        if toml_status in (ARMED, PLACEHOLDER):
            status = toml_status
            ln = _lines_mentioning(toml, var)
            evidence.append(f"integration/fly/fly.toml:{ln[0] if ln else '?'} [env] sets a {'non-empty' if status == ARMED else 'placeholder'} value")
        elif run is not None:
            status = run.status[var]
            if status == ARMED:
                evidence.append("entrypoint.sh run with stub services: exits non-zero before any service starts when it is unset or empty")
            else:
                evidence.append("entrypoint.sh run with stub services: the services start although it is unset or empty")
                evidence.append(
                    "only an operator action (fly secrets set / [env]) can arm it; "
                    "the entrypoint starts the estate open if that is skipped"
                )
            static = from_entry.get(var)
            if static and static[0] != status:
                evidence.append(f"note: the static reading said {static[0]}; the run decides")
        elif var in from_entry:
            status, ln = from_entry[var]
            evidence.append(f"integration/fly/entrypoint.sh:{ln} {status} (static reading only, not run)")
            if status == EMPTY:
                evidence.append(
                    "only an operator action (fly secrets set / [env]) can arm it; "
                    "the entrypoint starts the estate open if that is skipped"
                )
        else:
            status = OPERATOR
            evidence.append("not referenced by entrypoint.sh or fly.toml [env]")
        results[var] = VarResult(status, evidence, (FLY_SERVICE,) if status != ARMED else ())
    return results, findings, behaviour


def _behavioural_disabled_by_env() -> bool:
    """TOPOLOGY_LINT_BEHAVIOURAL set to 0 / false / no / empty. Unset means enabled."""
    val = os.environ.get("TOPOLOGY_LINT_BEHAVIOURAL")
    return val is not None and val.strip().lower() in ("0", "false", "no", "")


def analyse(root: Path, topologies=TOPOLOGIES, behavioural: bool | None = None) -> list[TopologyReport]:
    forced_off_in_ci = False
    if behavioural is None:
        behavioural = not _behavioural_disabled_by_env()
        forced_off_in_ci = (not behavioural) and _ci()
    reports = []
    for topo in topologies:
        for rel in topo.files:
            if not (root / rel).is_file():
                raise SystemExit(f"topology_lint: declared descriptor missing: {rel} (topology {topo.id})")
        if topo.style == "fly":
            res, findings, behaviour = analyse_fly(root, topo, behavioural, forced_off_in_ci)
            reports.append(TopologyReport(topo, res, findings, behaviour=behaviour))
        else:
            res, findings, notes = analyse_compose(root, topo)
            reports.append(TopologyReport(topo, res, findings, notes))
    return reports


# Files that look like deployment descriptors but are not a topology, each with
# the reason. The bool says whether the file may mention the variables (a demo
# client script legitimately does; an image definition must not).
REVIEWED_NON_TOPOLOGY: dict[str, tuple[str, bool]] = {
    "integration/demo/Dockerfile": ("platform image shared by the compose topologies; sets no secret", False),
    "integration/demo/run_demo.sh": ("local demo runner (local processes, not an estate); mentions neither variable", False),
    "integration/video/stage_scene4.sh": ("video staging script; mentions neither variable", False),
    "packages/field-agent/examples/05_rest_api.sh": ("client example that sends the shared secret; deploys nothing", True),
    "plugins/field-agent/templates/rest_api.sh": ("client template that sends the shared secret; deploys nothing", True),
    "services/delegation-authority/demo.sh": ("local demo script for one service; not a deployed estate", True),
    "services/force-gateway/demo.sh": ("local demo script for one service; not a deployed estate", True),
}

_SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".tox", "site-packages"})
_COMPOSE_LIKE = re.compile(r"(?m)^[\"']?services[\"']?\s*:")
_COMPOSE_JSON = re.compile(r"\"services\"\s*:\s*\{")
_FLY_LIKE = re.compile(
    r"(?m)^(?:\[\[?(?:http_service|build|services|processes|mounts|env|deploy|experimental|vm)(?:\.[\w.-]+)?\]\]?\s*(?:#.*)?"
    r"|(?:app|primary_region)\s*=.*)$"
)
_TEMPLATE_SUFFIX = re.compile(r"\.(?:j2|jinja2?|tpl|template)$")


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return ""


def unclassified_descriptors(root: Path, topologies=TOPOLOGIES) -> list[str]:
    """Deployment-looking files anywhere in the repo that no topology claims.

    Dot-directories are scanned (only VCS, virtualenv and cache directories are
    skipped). A file counts when it is compose-like YAML (a top-level
    ``services:``), a TOML with ``[http_service]`` / ``[build]`` / ``[processes]``,
    a ``Dockerfile*``, a ``compose``/``fly``/``entrypoint`` named descriptor, or a
    shell script that mentions either variable.
    """
    claimed = {f for t in topologies for f in t.files}
    found: set[str] = set()
    for pattern in DESCRIPTOR_GLOBS:
        for p in glob.glob(str(root / pattern), recursive=True):
            found.add(os.path.relpath(p, root).replace(os.sep, "/"))
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            low = _TEMPLATE_SUFFIX.sub("", fn.lower())
            if low.startswith(("dockerfile", "containerfile")) or low.endswith((".dockerfile", ".containerfile")):
                found.add(rel)
            elif low.endswith((".yml", ".yaml")) and _COMPOSE_LIKE.search(_read(full)):
                found.add(rel)
            elif low.endswith(".json") and _COMPOSE_JSON.search(_read(full)):
                found.add(rel)
            elif low.endswith(".toml") and _FLY_LIKE.search(_read(full)):
                found.add(rel)
            elif low.endswith(".sh") and (rel.startswith("integration/") or any(_word(v).search(_read(full)) for v in VARS)):
                found.add(rel)
    out = []
    for rel in sorted(found - claimed):
        if rel in REVIEWED_NON_TOPOLOGY:
            continue
        out.append(rel)
    return out


def reviewed_file_problems(root: Path) -> list[str]:
    """A reviewed non-topology file that must stay free of the variables but now mentions one."""
    out = []
    for rel, (_reason, may_mention) in REVIEWED_NON_TOPOLOGY.items():
        path = root / rel
        if not may_mention and path.is_file() and any(_word(v).search(_read(str(path))) for v in VARS):
            out.append(f"{rel} is a reviewed non-topology file that must not mention the variables, but now does; classify it")
    return out


def load_allowlist(path: Path | None) -> list[dict]:
    if path is None or not path.is_file():
        return []
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = doc.get("exceptions") or []
    if not isinstance(entries, list):
        raise SystemExit(f"topology_lint: {path}: 'exceptions' must be a list")
    for e in entries:
        for key in ("topology", "var", "reason"):
            if not isinstance(e, dict) or not str(e.get(key, "")).strip():
                raise SystemExit(f"topology_lint: {path}: every exception needs topology, var and a non-empty reason: {e!r}")
        if e["var"] not in VARS:
            raise SystemExit(f"topology_lint: {path}: unknown var {e['var']!r}")
        if e.get("expected_status") not in (EMPTY, OPERATOR, PLACEHOLDER):
            raise SystemExit(
                f"topology_lint: {path}: {e['topology']} {e['var']}: expected_status must be one of "
                f"{EMPTY!r}, {OPERATOR!r}, {PLACEHOLDER!r} (the weak status being waived)"
            )
        svcs = e.get("services")
        if not isinstance(svcs, list) or not svcs or not all(isinstance(x, str) and x.strip() for x in svcs):
            raise SystemExit(
                f"topology_lint: {path}: {e['topology']} {e['var']}: services must be a non-empty list of the "
                "services currently making it weak (the lint prints them)"
            )
    seen: set[tuple[str, str]] = set()
    for e in entries:
        key = (e["topology"], e["var"])
        if key in seen:
            raise SystemExit(f"topology_lint: {path}: duplicate exception for {key[0]} {key[1]}; one entry per pair")
        seen.add(key)
    return entries


def _parse_verified_on(raw: object) -> datetime.date | None:
    if isinstance(raw, datetime.datetime):
        return raw.date()
    if isinstance(raw, datetime.date):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.date.fromisoformat(raw.strip())
        except ValueError:
            return None
    return None


def check_verification(entry: dict, today: datetime.date) -> str | None:
    """Return an error message if the entry's verification is missing or expired."""
    name = f"{entry['topology']} {entry['var']}"
    raw = entry.get("verified_on")
    if raw is None or not str(raw).strip():
        return f"allowlist entry {name} has no verified_on date; re-verify it and record the date"
    when = _parse_verified_on(raw)
    if when is None:
        return f"allowlist entry {name} has an unparseable verified_on {raw!r}; use YYYY-MM-DD"
    if not str(entry.get("verified_by", "")).strip():
        return f"allowlist entry {name} has no verified_by"
    age = (today - when).days
    if age < 0:
        return f"allowlist entry {name} verified_on {when} is in the future (today {today})"
    if age > ALLOWLIST_MAX_AGE_DAYS:
        return (f"allowlist entry {name} expired: verified_on {when} is {age} days old "
                f"(max {ALLOWLIST_MAX_AGE_DAYS}); re-verify the live estate and update verified_on")
    return None


def evaluate(reports, allowlist, unclassified, today: datetime.date | None = None) -> tuple[list[str], list[str]]:
    """Return (errors, notes). ``today`` is injectable for tests."""
    today = today or datetime.date.today()
    errors: list[str] = []
    notes: list[str] = []
    allowed = {(e["topology"], e["var"]): e for e in allowlist}
    used: set[tuple[str, str]] = set()
    ids = {r.topology.id for r in reports}
    for path in unclassified:
        errors.append(f"unclassified descriptor {path}: add it to a Topology (demo or deployed) in tools/topology_lint.py")
    for r in reports:
        if r.topology.kind == DEPLOYED:
            for f in r.findings:
                errors.append(f"FAIL {r.topology.id} (deployed) {f}")
        for var, res in r.vars.items():
            if res.status == ARMED or r.topology.kind == DEMO:
                continue
            key = (r.topology.id, var)
            if key in allowed:
                used.add(key)
                entry = allowed[key]
                if res.status != entry["expected_status"] or sorted(res.services) != sorted(entry["services"]):
                    errors.append(
                        f"FAIL {r.topology.id} (deployed) {var} is {res.status} via [{', '.join(sorted(res.services))}], "
                        f"but the allowlist entry expects {entry['expected_status']} via "
                        f"[{', '.join(sorted(entry['services']))}]; re-verify the estate and update the entry"
                    )
                    continue
                notes.append(f"ALLOWED {r.topology.id} {var} is {res.status}: {entry['reason']}")
            else:
                errors.append(f"FAIL {r.topology.id} (deployed) {var} is {res.status}, not armed")
    for key, e in allowed.items():
        if key[0] not in ids:
            errors.append(f"stale allowlist entry: unknown topology {key[0]!r}")
        elif key not in used:
            errors.append(f"stale allowlist entry: {key[0]} {key[1]} is no longer a failing pair; remove it")
        problem = check_verification(e, today)
        if problem:
            errors.append(problem)
    return errors, notes


def render(reports, errors, notes, unclassified) -> str:
    out = ["Deployed-topology lint: fail-open environment variables", ""]
    for r in reports:
        if r.behaviour:
            out.append(f"entrypoint behavioural check: {r.behaviour}")
            if r.behaviour.startswith("SKIPPED"):
                out.append(
                    f"WARN entrypoint behavioural check NOT RUN ({r.behaviour[len('SKIPPED ('):-1]}): "
                    "the entrypoint is only tripwire-checked"
                )
            out.append("")
        out.append(f"[{r.topology.kind.upper():8}] {r.topology.id}  ({', '.join(r.topology.files)})")
        out.append(f"           {r.topology.evidence}")
        for n in r.notes:
            out.append(f"  note: {n}")
        for f in r.findings:
            out.append(f"  finding: {f}")
        for var in VARS:
            res = r.vars[var]
            out.append(f"  {var:20} {res.status}")
            for ev in res.evidence:
                out.append(f"      - {ev}")
        out.append("")
    for n in notes:
        out.append(n)
    for e in errors:
        out.append(e)
    out.append("")
    out.append("RESULT: " + ("FAIL" if errors else "OK") + f" ({len(errors)} finding(s), {len(notes)} allowlisted)")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=here.parent, help="repository root")
    ap.add_argument("--allowlist", type=Path, default=None, help="default: tools/topology_lint_allowlist.yaml under --root")
    ap.add_argument("--today", type=datetime.date.fromisoformat, default=None,
                    help="YYYY-MM-DD override for the allowlist-expiry clock (tests); default: real today")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    allow_path = args.allowlist or root / "tools" / "topology_lint_allowlist.yaml"
    try:
        reports = analyse(root)
        allowlist = load_allowlist(allow_path)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    unclassified = unclassified_descriptors(root)
    errors, notes = evaluate(reports, allowlist, unclassified, args.today)
    errors.extend(reviewed_file_problems(root))
    if args.json:
        print(json.dumps({
            "topologies": [
                {"id": r.topology.id, "kind": r.topology.kind, "behaviour": r.behaviour,
                 "vars": {v: {"status": x.status, "evidence": x.evidence} for v, x in r.vars.items()}}
                for r in reports],
            "errors": errors, "allowlisted": notes}, indent=2))
    else:
        print(render(reports, errors, notes, unclassified))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
