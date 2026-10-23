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
themselves errors, so exceptions cannot rot.

Exit status: 0 clean, 1 findings, 2 usage or descriptor error.
Standard library plus PyYAML (already a field-core dependency).
"""

from __future__ import annotations

import argparse
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


def classify_value(raw: object, var: str) -> str:
    """Classify one descriptor value for ``var``. See the module docstring."""
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
    """SafeLoader that accepts compose-only tags (``!override``, ``!reset``)."""


def _any_tag(loader, suffix, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


_ComposeLoader.add_multi_constructor("!", _any_tag)


def _compose_envs(path: Path) -> dict[str, dict[str, object]]:
    """service name -> environment mapping (anchors/merge keys resolved)."""
    try:
        doc = yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader) or {}  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        raise SystemExit(f"topology_lint: cannot parse {path}: {exc}") from exc
    services = doc.get("services") or {}
    out: dict[str, dict[str, object]] = {}
    for name, svc in services.items():
        env = (svc or {}).get("environment") or {}
        if isinstance(env, list):
            parsed: dict[str, object] = {}
            for item in env:
                k, _, v = str(item).partition("=")
                parsed[k] = v if _ else None
            env = parsed
        out[name] = dict(env)
    return out


def analyse_compose(root: Path, topo: Topology) -> dict[str, VarResult]:
    merged: dict[str, dict[str, object]] = {}
    src: dict[tuple[str, str], str] = {}  # (service, var) -> file that last set it
    lines: dict[tuple[str, str], list[int]] = {}  # (file, var) -> lines
    for rel in topo.files:
        path = root / rel
        for svc, env in _compose_envs(path).items():
            merged.setdefault(svc, {})
            for var in VARS:
                if var in env:
                    merged[svc][var] = env[var]
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
        results[var] = VarResult(status, evidence)
    return results


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
        fn = analyse_fly if topo.style == "fly" else analyse_compose
        reports.append(TopologyReport(topo, fn(root, topo)))
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


def evaluate(reports, allowlist, unclassified) -> tuple[list[str], list[str]]:
    """Return (errors, notes)."""
    errors: list[str] = []
    notes: list[str] = []
    allowed = {(e["topology"], e["var"]): e for e in allowlist}
    used: set[tuple[str, str]] = set()
    ids = {r.topology.id for r in reports}
    for path in unclassified:
        errors.append(f"unclassified descriptor {path}: add it to a Topology (demo or deployed) in tools/topology_lint.py")
    for r in reports:
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
    return errors, notes


def render(reports, errors, notes, unclassified) -> str:
    out = ["Deployed-topology lint: fail-open environment variables", ""]
    for r in reports:
        out.append(f"[{r.topology.kind.upper():8}] {r.topology.id}  ({', '.join(r.topology.files)})")
        out.append(f"           {r.topology.evidence}")
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
    errors, notes = evaluate(reports, allowlist, unclassified)
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
