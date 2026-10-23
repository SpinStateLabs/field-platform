"""``python -m deployment_agent plan|run`` - dry-run only; no network, no real provider.

    python -m deployment_agent plan --target fly-app-a [--target ...] [--manifest PATH] [--ttl-days N]
    python -m deployment_agent run  --target fly-app-a --dry-run [--journal-dir DIR] [--manifest PATH]
    python -m deployment_agent run  --no-dry-run --manifest PATH --i-have-a-provider ...   (refuses)

``plan`` prints what a rotation would do per target and what the refuse list says
about each step. ``run --dry-run`` (the default) simulates the whole state machine
against the in-memory FAKE provider and says so; the real world is never touched.
A non-dry run is refused unless a manifest file exists AND ``--i-have-a-provider``
is given, and is then refused anyway: no real provider exists (ADR-0079).
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from . import VERSION
from .actions import ADR_SCOPE, Action, ActionKind as K
from .journal import validate_target
from .manifest import ManifestError, load_manifest
from .provider import ADR_POINTER, FakeProvider
from .refuse import refuse
from .rotation import Rotator
from .states import HAPPY_PATH

EXIT_OK, EXIT_REFUSED = 0, 2
DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / "manifests" / "deployment-agent.yaml"
TTL_PLACEHOLDER = "[placeholder]"


def _targets(value: str) -> str:
    try:
        return validate_target(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="deployment_agent", description=__doc__.splitlines()[0])
    p.add_argument("--version", action="version", version=f"deployment_agent {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run"):
        s = sub.add_parser(name)
        s.add_argument("--target", action="append", type=_targets, default=[], help="credential target (repeatable)")
        s.add_argument("--manifest", type=Path, default=None, help="manifest path (default: manifests/deployment-agent.yaml if present)")
        s.add_argument("--ttl-days", type=int, default=None, help="rotation lifetime, 1-30 (default: placeholder)")
    run = sub.choices["run"]
    run.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True,
                     help="default on; --no-dry-run is refused unless prerequisites exist (and then refused anyway)")
    run.add_argument("--i-have-a-provider", action="store_true",
                     help="declares that a real provider is wired in; does nothing yet beyond a refusal")
    run.add_argument("--journal-dir", type=Path, default=None, help="directory for the simulation's journal (default: a temp dir)")
    return p


def _load_scope(args: argparse.Namespace) -> tuple[frozenset[str], str]:
    path = args.manifest or (DEFAULT_MANIFEST if DEFAULT_MANIFEST.is_file() else None)
    if path is None:
        return ADR_SCOPE, "manifest: none found; using the ADR-0079 scope ceiling"
    m = load_manifest(path)
    return m.scope, f"manifest: {path} (granted_by {m.granted_by!r}, expiry {m.expiry})"


def _ttl(args: argparse.Namespace) -> tuple[str, int]:
    if args.ttl_days is None:
        return TTL_PLACEHOLDER + " (ADR proposes 30 days; the figure is Don's)", 30
    if not 1 <= args.ttl_days <= 30:
        raise ManifestError("--ttl-days must be 1..30")
    return str(args.ttl_days), args.ttl_days


def cmd_plan(args: argparse.Namespace, out) -> int:
    scope, line = _load_scope(args)
    ttl_text, _ = _ttl(args)
    print(line, file=out)
    print(f"ttl_days: {ttl_text}", file=out)
    if not args.target:
        print("no --target given: nothing to plan", file=out)
        return EXIT_OK
    for target in args.target:
        print(f"target {target}:", file=out)
        print("  states: " + " -> ".join(s.value for s in HAPPY_PATH), file=out)
        print("  on failed verification: restore old, revoke new -> rolled_back", file=out)
        print("  on a human revocation or an already-invalid old credential: halted (human clears)", file=out)
        for kind, flags in ((K.MINT_FLY_DEPLOY_TOKEN, {}), (K.WRITE_GITHUB_ENV_SECRET, {}),
                            (K.REVOKE_FLY_DEPLOY_TOKEN, {"replacement_verified": True})):
            verdict = refuse(Action(kind=kind, target=target, scope=scope, **flags))
            print(f"  step {kind.value}: {'allowed' if verdict is None else 'REFUSED ' + verdict}", file=out)
    print("plan only: no provider call was made", file=out)
    return EXIT_OK


def cmd_run(args: argparse.Namespace, out, err) -> int:
    if not args.dry_run:
        manifest = args.manifest
        if manifest is None or not Path(manifest).is_file():
            print("refused: a non-dry run needs --manifest pointing at an existing manifest", file=err)
            return EXIT_REFUSED
        if not args.i_have_a_provider:
            print("refused: a non-dry run needs --i-have-a-provider", file=err)
            return EXIT_REFUSED
        print(f"refused: {ADR_POINTER}", file=err)
        return EXIT_REFUSED
    scope, line = _load_scope(args)
    _, ttl = _ttl(args)
    print("SIMULATION against the in-memory FAKE provider; nothing real is touched", file=out)
    print(line, file=out)
    if not args.target:
        print("no --target given: nothing to simulate", file=out)
        return EXIT_OK
    root = args.journal_dir or Path(tempfile.mkdtemp(prefix="deployment-agent-sim-"))
    provider = FakeProvider()
    rotator = Rotator(provider, root, scope=scope, ttl_days=ttl)
    rc = EXIT_OK
    for target in args.target:
        provider.seed(target)
        res = rotator.rotate(target)
        print(f"target {target}: {res.outcome} ({res.reason})", file=out)
        rc = rc or res.exit_code
    print(f"journal: {rotator.journal_dir}", file=out)
    return rc


def main(argv: list[str] | None = None, out=None, err=None) -> int:
    out, err = out or sys.stdout, err or sys.stderr
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "plan":
            return cmd_plan(args, out)
        return cmd_run(args, out, err)
    except ManifestError as exc:
        print(f"refused: {exc}", file=err)
        return EXIT_REFUSED
