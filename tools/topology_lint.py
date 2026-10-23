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

_RANK = {ARMED: 0, OPERATOR: 1, EMPTY: 2}  # larger = weaker

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


@dataclass
class TopologyReport:
    topology: Topology
    vars: dict[str, VarResult]
    findings: list[str] = field(default_factory=list)  # structural problems; fail a deployed topology
    notes: list[str] = field(default_factory=list)  # informational (profiles, ...)


def classify_value(raw: object, var: str) -> str:
    """Classify one descriptor value for ``var``. See the module docstring."""
    if raw is PASSTHROUGH:
        return OPERATOR  # `- VAR`: whatever the host env holds, invisible here
    if raw is RESET:
        return EMPTY
    if raw is None:
        return EMPTY
    text = str(raw).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    if text == "":
        return EMPTY
    m = re.fullmatch(r"\$\{" + re.escape(var) + r"(:?[-?+=])?(.*)\}", text, re.S)
    if m:
        op, rest = m.group(1), m.group(2)
        if op is None:
            return OPERATOR  # ${VAR}: pass-through from the host
        if op.endswith("?"):
            return ARMED  # required-or-fail
        if op.endswith("-") or op.endswith("="):
            return ARMED if rest.strip() else EMPTY
        return OPERATOR
    if "${" in text or "$(" in text or text.startswith("$"):
        return OPERATOR  # some other substitution: cannot decide statically
    return ARMED


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
        )
    return out, findings


def analyse_compose(root: Path, topo: Topology) -> tuple[dict[str, VarResult], list[str], list[str]]:
    merged: dict[str, dict[str, object]] = {}
    src: dict[tuple[str, str], str] = {}  # (service, var) -> file that last set it
    lines: dict[tuple[str, str], list[int]] = {}  # (file, var) -> lines
    resets: list[tuple[str, str]] = []
    findings: list[str] = []
    notes: list[str] = []
    for rel in topo.files:
        path = root / rel
        services, file_findings = _compose_services(path)
        findings.extend(file_findings)
        for svc, info in services.items():
            m = merged.setdefault(svc, {})
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
                src[(svc, var)] = rel
                lines[(rel, var)] = _lines_mentioning(path, var)
    results: dict[str, VarResult] = {}
    for var in VARS:
        status = ARMED
        groups: dict[tuple[str, str], list[str]] = {}
        absent: list[str] = []
        for svc, env in merged.items():
            if var in env:
                st = classify_value(env[var], var)
                status = _weaker(status, st)
                groups.setdefault((st, src[(svc, var)]), []).append(svc)
            else:
                absent.append(svc)
        evidence: list[str] = []
        if not groups:
            status = OPERATOR
            evidence.append("not referenced by any service environment")
        for (st, rel), svcs in groups.items():
            ln = ",".join(map(str, lines[(rel, var)]))
            evidence.append(f"{st}: {', '.join(svcs)} ({rel}, mentions at line {ln})")
        if groups and absent:
            evidence.append(
                "no entry (compose forwards no host env, so the variable is unset there): "
                + ", ".join(sorted(absent))
            )
        evidence.extend(msg for v, msg in resets if v == var)
        results[var] = VarResult(status, evidence)
    return results, findings, notes


_EXPORT = re.compile(r"^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*?)\s*$")
_REQUIRE = re.compile(r"""^\s*:\s+"?\$\{([A-Za-z_][A-Za-z0-9_]*):\?""")


def analyse_fly(root: Path, topo: Topology) -> dict[str, VarResult]:
    entry = root / "integration/fly/entrypoint.sh"
    toml = root / "integration/fly/fly.toml"
    from_entry: dict[str, tuple[str, int]] = {}
    for i, line in enumerate(entry.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        m = _EXPORT.match(line)
        if m and m.group(1) in VARS:
            from_entry[m.group(1)] = (classify_value(m.group(2), m.group(1)), i)
        r = _REQUIRE.match(line)
        if r and r.group(1) in VARS:
            from_entry[r.group(1)] = (ARMED, i)
    env_table: dict[str, object] = {}
    try:
        try:
            import tomllib  # type: ignore[import-not-found]
        except ModuleNotFoundError:  # pragma: no cover - py<3.11
            tomllib = None  # type: ignore[assignment]
        if tomllib is not None:
            env_table = (tomllib.loads(toml.read_text(encoding="utf-8")).get("env")) or {}
    except (OSError, ValueError) as exc:
        raise SystemExit(f"topology_lint: cannot parse {toml}: {exc}") from exc
    results: dict[str, VarResult] = {}
    for var in VARS:
        evidence: list[str] = []
        if var in env_table and classify_value(env_table[var], var) == ARMED:
            status = ARMED
            ln = _lines_mentioning(toml, var)
            evidence.append(f"integration/fly/fly.toml:{ln[0] if ln else '?'} [env] sets a non-empty value")
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
        results[var] = VarResult(status, evidence)
    return results


def analyse(root: Path, topologies=TOPOLOGIES) -> list[TopologyReport]:
    reports = []
    for topo in topologies:
        for rel in topo.files:
            if not (root / rel).is_file():
                raise SystemExit(f"topology_lint: declared descriptor missing: {rel} (topology {topo.id})")
        if topo.style == "fly":
            reports.append(TopologyReport(topo, analyse_fly(root, topo)))
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
                notes.append(f"ALLOWED {r.topology.id} {var} is {res.status}: {allowed[key]['reason']}")
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
