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
        files=("integration/fly/entrypoint.sh", "integration/fly/fly.toml"),
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
SERVICE_EXEMPTIONS: dict[tuple[str, str, str], str] = {
    ("gb10", "FIELD_SHARED_SECRET", "proxy"): (
        "Caddy reverse proxy: it terminates nothing and authenticates nothing; the backends it "
        "forwards to enforce field_core.authn. integration/demo/Caddyfile does not mention the "
        "secret. A 2026-10-23 presence check also found it unset in the live proxy container."
    ),
    ("gb10", "FIELD_SHARED_SECRET", "manifests-admin"): (
        "one-shot volume_admin tool, network_mode none, serves no HTTP"
    ),
    ("gb10", "FIELD_SHARED_SECRET", "keys-admin"): (
        "one-shot volume_admin tool (profile admin), network_mode none, serves no HTTP"
    ),
    ("gb10", "FIELD_SHARED_SECRET", "attest-keys-admin"): (
        "one-shot volume_admin tool (profile admin), network_mode none, serves no HTTP"
    ),
}

# Only these compose services read the variable, so only they decide its status.
# FIELD_DOA_ROSTER: delegation-authority, per docs/IMPLEMENTATION.md:79 and
# services/delegation-authority/.../doa.py (ROSTER_ENV). Other services restate
# it in compose but never read it (lifecycle-manager reads FIELD_LIFECYCLE_ROSTER).
CONSUMERS: dict[str, tuple[str, ...]] = {"FIELD_DOA_ROSTER": ("delegation",)}

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


def _strip_quotes(text: str) -> str:
    text = text.strip()
    while len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def _literal(text: str, var: str) -> str:
    """Classify a plain (non-substitution) value."""
    if text == "":
        return EMPTY
    if var == "FIELD_SHARED_SECRET" and text.lower() in PLACEHOLDER_LITERALS:
        return PLACEHOLDER
    return ARMED


def classify_value(raw: object, var: str) -> str:
    """Classify one descriptor value for ``var``. See the module docstring."""
    if raw is PASSTHROUGH:
        return OPERATOR  # `- VAR`: whatever the host env holds, invisible here
    if raw is None or raw is RESET:
        return EMPTY
    text = _strip_quotes(str(raw))
    if text == "":
        return EMPTY
    m = re.fullmatch(r"\$\{" + re.escape(var) + r"(:?[-?+=])?(.*)\}", text, re.S)
    if m:
        op, rest = m.group(1), m.group(2)
        if op is None:
            return OPERATOR  # ${VAR}: pass-through from the host
        if op == ":?":
            return ARMED  # required and non-empty, or the deployment fails
        if op == "?":
            return EMPTY  # required to be SET, but an empty value passes
        if op[-1] in "-=":
            default = _strip_quotes(rest)
            if default.startswith("${"):
                inner = re.match(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", default)
                st = classify_value(default, inner.group(1)) if inner else OPERATOR
            else:
                st = _literal(default, var)
            if op[0] == ":" or st in (EMPTY, PLACEHOLDER):
                return st
            # no colon: the default only applies when unset, so a host value
            # that is set-but-empty still wins and we cannot tell statically
            return OPERATOR if st == ARMED else st
        return OPERATOR
    if "${" in text or "$(" in text or text.startswith("$"):
        return OPERATOR  # some other substitution: cannot decide statically
    return _literal(text, var)


def is_committed_literal(raw: object) -> bool:
    """True for a non-empty literal value, i.e. key material committed to the repo."""
    if raw is None or raw is PASSTHROUGH or raw is RESET:
        return False
    text = _strip_quotes(str(raw))
    return bool(text) and "${" not in text and "$(" not in text and not text.startswith("$")


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
    http: bool = False  # published ports, or a `serve` / `--port` command, or a caddy image
    no_network: bool = False  # network_mode: none


def _has(value: object) -> bool:
    value = _unwrap(value)
    return value not in (None, RESET, [], {}, "")


def _serves_http(svc: dict) -> bool:
    if _has(svc.get("ports")) or _has(svc.get("expose")):
        return True
    cmd = _unwrap(svc.get("command"))
    text = " ".join(map(str, cmd)) if isinstance(cmd, list) else ("" if cmd in (None, RESET) else str(cmd))
    if re.search(r"(^|\s)serve(\s|$)", text) or "--port" in text:
        return True
    return str(_unwrap(svc.get("image")) or "").startswith("caddy")


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
        out[name] = _Service(
            env, replace, unsupported,
            [str(p) for p in profiles] if isinstance(profiles, list) else [],
            http=_serves_http(svc),
            no_network=_unwrap(svc.get("network_mode")) == "none",
        )
    return out, findings


def analyse_compose(root: Path, topo: Topology) -> tuple[dict[str, VarResult], list[str], list[str]]:
    merged: dict[str, dict[str, object]] = {}
    src: dict[tuple[str, str], str] = {}  # (service, var) -> file that last set it
    lines: dict[tuple[str, str], list[int]] = {}  # (file, var) -> lines
    http: dict[str, bool] = {}
    no_net: dict[str, bool] = {}
    resets: list[tuple[str, str]] = []
    findings: list[str] = []
    notes: list[str] = []
    for rel in topo.files:
        path = root / rel
        services, file_findings = _compose_services(path)
        findings.extend(file_findings)
        for svc, info in services.items():
            m = merged.setdefault(svc, {})
            http[svc] = http.get(svc, False) or info.http
            no_net[svc] = no_net.get(svc, False) or info.no_network
            if info.replace:
                for var in VARS:
                    m.pop(var, None)
                    src.pop((svc, var), None)
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
                if var == "FIELD_SHARED_SECRET" and is_committed_literal(info.env[var]):
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
        consumers = CONSUMERS.get(var)
        if consumers is not None:
            considered = [c for c in consumers if c in merged]
            for missing in (c for c in consumers if c not in merged):
                status = _weaker(status, OPERATOR)
                evidence.append(f"consumer service {missing!r} not found in this topology; cannot show {var} is armed")
            ignored = sorted(set(merged) - set(consumers))
        else:
            considered, ignored = list(merged), []
        absent: list[str] = []
        exempt: list[str] = []
        weak: set[str] = set()
        weak.update(c for c in (consumers or ()) if c not in merged)
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
            elif http[svc] and not no_net[svc]:
                reason = SERVICE_EXEMPTIONS.get((topo.id, var, svc))
                if reason:
                    exempt.append(f"{svc} ({reason})")
                else:
                    status = _weaker(status, EMPTY)
                    absent.append(svc)
                    weak.add(svc)
            else:
                exempt.append(f"{svc} (does not serve HTTP)")
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


_OPEN_BLOCK = re.compile(r"^(if|case|for|while|until|select)\b|\{\s*$|^[A-Za-z_][A-Za-z0-9_]*\s*\(\)")
_CLOSE_BLOCK = re.compile(r"^(fi|esac|done|\})\s*;?$")


def parse_entrypoint(text: str, name: str = "integration/fly/entrypoint.sh") -> tuple[dict[str, tuple[str, int]], list[str]]:
    """Per variable (status, line) plus findings.

    Exactly one top-level ``export VAR=...`` and at most one top-level
    ``: "${VAR:?...}"`` guard are understood. Any other line that mentions the
    variable (inline assignment, ``env VAR=``, ``declare -x``, ``unset``, a
    conditional or indented re-export, an echo, ...) is a finding, because the
    effective value can no longer be read off the file.
    """
    exports: dict[str, tuple[object, int]] = {}
    guards: dict[str, int] = {}
    findings: list[str] = []
    depth = 0
    for i, raw in enumerate(text.splitlines(), 1):
        if raw.lstrip().startswith("#"):
            continue
        line = strip_trailing_comment(raw)
        stripped = line.strip()
        top = depth == 0 and raw[:1] not in (" ", "\t")
        for var in VARS:
            if not _word(var).search(line):
                continue
            ex = re.fullmatch(r"export\s+" + re.escape(var) + r"=(\"(?:[^\"\\]|\\.)*\"|'[^']*'|[^\s;&|]*)", line) if top else None
            gd = re.fullmatch(r":\s+\"?\$\{" + re.escape(var) + r":\?[^}]*\}\"?", line) if top else None
            if ex:
                if var in exports:
                    findings.append(f"{name}:{i} exports {var} more than once (first at line {exports[var][1]})")
                else:
                    exports[var] = (ex.group(1), i)
            elif gd:
                if var in guards:
                    findings.append(f"{name}:{i} has a second ':?' guard for {var} (first at line {guards[var]})")
                else:
                    guards[var] = i
            else:
                findings.append(
                    f"{name}:{i} mentions {var} outside the single top-level `export {var}=...` "
                    "and one `: \"${" + var + ":?...}\"` guard, so its effective value cannot be read from the file"
                )
        if _CLOSE_BLOCK.match(stripped):
            depth = max(0, depth - 1)
        elif _OPEN_BLOCK.search(stripped):
            depth += 1
    out: dict[str, tuple[str, int]] = {}
    for var in VARS:
        exp = exports.get(var)
        if var in guards:
            st, ln = ARMED, guards[var]
            if exp and exp[1] > guards[var]:
                after = classify_value(exp[0], var)
                if after != ARMED and not re.search(r"\$\{" + re.escape(var), str(exp[0])):
                    st, ln = after, exp[1]  # a literal reassignment after the guard wins
            out[var] = (st, ln)
        elif exp:
            out[var] = (classify_value(exp[0], var), exp[1])
    return out, findings


def parse_dockerfile(text: str) -> list[tuple[int, str, str]]:
    """(line, INSTRUCTION, rest) with backslash continuations joined and comments dropped."""
    out: list[tuple[int, str, str]] = []
    buf, start = "", 0
    for i, raw in enumerate(text.splitlines(), 1):
        if not buf and (not raw.strip() or raw.lstrip().startswith("#")):
            continue
        if raw.lstrip().startswith("#"):
            continue
        if not buf:
            start = i
        cont = raw.rstrip().endswith("\\")
        buf += (raw.rstrip()[:-1] if cont else raw) + " "
        if not cont:
            parts = buf.strip().split(None, 1)
            out.append((start, parts[0].upper(), parts[1] if len(parts) > 1 else ""))
            buf = ""
    if buf.strip():
        parts = buf.strip().split(None, 1)
        out.append((start, parts[0].upper(), parts[1] if len(parts) > 1 else ""))
    return out


def analyse_dockerfile(text: str, name: str) -> list[str]:
    findings: list[str] = []
    entrypoint = None
    copied = False
    for ln, instr, rest in parse_dockerfile(text):
        where = f"{name}:{ln} {instr}"
        for var in VARS:
            if not _word(var).search(rest):
                continue
            if instr == "ENV":
                m = re.search(_word(var).pattern + r"(?:=|\s+)(\"[^\"]*\"|'[^']*'|\S*)", rest)
                if m and is_committed_literal(m.group(1)):
                    findings.append(f"{where} bakes a literal {var} into the image layer")
            elif instr in ("ARG", "CMD", "RUN", "ENTRYPOINT"):
                findings.append(f"{where} mentions {var}; the value would no longer come only from entrypoint.sh and the runtime environment")
        if instr == "ENTRYPOINT":
            entrypoint = (ln, rest)
        elif instr == "RUN" and "entrypoint.sh" in rest and not re.match(r"\s*chmod\b", rest):
            findings.append(f"{where} touches entrypoint.sh after it is copied, so the analysed file is not what runs")
        elif instr == "COPY":
            args = [a for a in rest.split() if not a.startswith("--")]
            if "--from" not in rest and len(args) >= 2 and args[-1] == "/entrypoint.sh":
                if args[:-1] == ["integration/fly/entrypoint.sh"]:
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


def analyse_fly(root: Path, topo: Topology) -> tuple[dict[str, VarResult], list[str]]:
    entry = root / "integration/fly/entrypoint.sh"
    toml = root / "integration/fly/fly.toml"
    from_entry, findings = parse_entrypoint(entry.read_text(encoding="utf-8"))
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
    if is_committed_literal(env_table.get("FIELD_SHARED_SECRET")):
        findings.append(
            "integration/fly/fly.toml [env] sets FIELD_SHARED_SECRET to a literal value; "
            "fly.toml is committed, use `fly secrets set` instead"
        )
    build = doc.get("build") or {}
    df_rel = str(build.get("dockerfile", "Dockerfile")) if isinstance(build, dict) else "Dockerfile"
    df = (toml.parent / df_rel)
    if not df.is_file():
        raise SystemExit(f"topology_lint: fly.toml [build].dockerfile resolves to {df_rel}, which does not exist")
    findings.extend(analyse_dockerfile(df.read_text(encoding="utf-8"), os.path.relpath(df, root).replace(os.sep, "/")))
    results: dict[str, VarResult] = {}
    for var in VARS:
        evidence: list[str] = []
        toml_status = classify_value(env_table[var], var) if var in env_table else None
        if toml_status in (ARMED, PLACEHOLDER):
            status = toml_status
            ln = _lines_mentioning(toml, var)
            evidence.append(f"integration/fly/fly.toml:{ln[0] if ln else '?'} [env] sets a {'non-empty' if status == ARMED else 'placeholder'} value")
        elif var in from_entry:
            status, ln = from_entry[var]
            evidence.append(f"integration/fly/entrypoint.sh:{ln} {status}")
            if status == EMPTY:
                evidence.append(
                    "only an operator action (fly secrets set / [env]) can arm it; "
                    "the entrypoint starts the estate open if that is skipped"
                )
        else:
            status = OPERATOR
            evidence.append("not referenced by entrypoint.sh or fly.toml [env]")
        results[var] = VarResult(status, evidence, (FLY_SERVICE,) if status != ARMED else ())
    return results, findings


def analyse(root: Path, topologies=TOPOLOGIES) -> list[TopologyReport]:
    reports = []
    for topo in topologies:
        for rel in topo.files:
            if not (root / rel).is_file():
                raise SystemExit(f"topology_lint: declared descriptor missing: {rel} (topology {topo.id})")
        if topo.style == "fly":
            res, findings = analyse_fly(root, topo)
            reports.append(TopologyReport(topo, res, findings))
        else:
            res, findings, notes = analyse_compose(root, topo)
            reports.append(TopologyReport(topo, res, findings, notes))
    return reports


def unclassified_descriptors(root: Path, topologies=TOPOLOGIES) -> list[str]:
    claimed = {f for t in topologies for f in t.files}
    found: set[str] = set()
    for pattern in DESCRIPTOR_GLOBS:
        for p in glob.glob(str(root / pattern), recursive=True):
            found.add(os.path.relpath(p, root).replace(os.sep, "/"))
    return sorted(found - claimed)


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
    if args.json:
        print(json.dumps({
            "topologies": [
                {"id": r.topology.id, "kind": r.topology.kind,
                 "vars": {v: {"status": x.status, "evidence": x.evidence} for v, x in r.vars.items()}}
                for r in reports],
            "errors": errors, "allowlisted": notes}, indent=2))
    else:
        print(render(reports, errors, notes, unclassified))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
