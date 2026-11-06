#!/usr/bin/env python3
"""phase_g_stage0_check - read-only Stage 0 record check for Phase G (G16).

    python tools/phase_g_stage0_check.py --base URL [--expect-build-sha SHA]

Stage 0 of the Phase G rollout deploys an image with every operator flag OFF. This tool reads the estate's open
``/health`` of the eight operator-block services (agent-registry, sealed-ledger, delegation-authority, kill-switch,
spend-governor, federation-broker, lifecycle-manager at their proxy prefixes, and the ops-console at ``/health``) and
reports two things, ids and booleans only:

* the image build id every service runs (the first 12 hex of ``build_sha``; with ``--expect-build-sha`` all eight must
  equal it, without it all eight must agree with each other);
* that every FIELD_OPERATOR_* flag is blank, seen from /health: ``operator_mode`` is ``off``, ``identity_present`` is
  false and ``operator_identity_id`` is null. A service that does not report the operator block fails: silence is not
  proof.

It SENDS ONLY ``GET /<prefix>/health`` without credentials, writes nothing, mutates nothing (unlike tools/phase_g_check.py,
which exercises a canary) and prints no key, no key hash, no secret and no value of a /health field other than those
above. The deploy-record template for the result is docs/templates/stage0-deploy-record.md.

Exit status: 0 every check passed, 1 a check failed, 2 usage error. Standard library only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import estate_probe as ep  # noqa: E402

#: (label, path, service name in /health). The console owns the proxy root, so its /health is the bare /health.
OPERATOR_BLOCK_SERVICES = (
    ("registry", "/registry/health", "agent-registry"),
    ("ledger", "/ledger/health", "sealed-ledger"),
    ("delegation", "/delegation/health", "delegation-authority"),
    ("killswitch", "/killswitch/health", "kill-switch"),
    ("governor", "/governor/health", "spend-governor"),
    ("federation", "/federation/health", "federation-broker"),
    ("lifecycle", "/lifecycle/health", "lifecycle-manager"),
    ("console", "/health", "ops-console"),
)
SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SHOWN_SHA = 12


class Report:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, ok: bool, text: str) -> bool:
        print(f"[{'PASS' if ok else 'FAIL'}] {text}")
        self.passed += bool(ok)
        self.failed += not ok
        return ok


def _flags_blank(body: Any) -> tuple[bool, str]:
    """(blank, reason) from the operator block of one /health body. Booleans and fixed words only."""
    if not isinstance(body, dict) or "operator_mode" not in body:
        return False, "the operator block is absent (nothing to prove)"
    if body.get("operator_mode") != "off":
        return False, "operator_mode is not off"
    if body.get("identity_present") is not False:
        return False, "identity_present is not false"
    if body.get("operator_identity_id") not in (None, ""):
        return False, "operator_identity_id is set"
    return True, "operator_mode off, no identity"


def check_estate(estate: Any, expect_sha: str | None) -> int:
    rep = Report()
    seen: dict[str, str] = {}
    for label, path, service in OPERATOR_BLOCK_SERVICES:
        status, body = estate.call("GET", path, auth=False)
        name = body.get("service") if isinstance(body, dict) else None
        if not rep.check(status == 200 and name == service, f"{path} answers 200 as {service} (HTTP {status})"):
            continue
        sha = body.get("build_sha")
        if rep.check(isinstance(sha, str) and SHA.fullmatch(sha) is not None, f"{label}: build_sha is a commit id"):
            seen[label] = sha
            if expect_sha is not None:
                rep.check(sha == expect_sha, f"{label}: build id {sha[:SHOWN_SHA]} equals the expected {expect_sha[:SHOWN_SHA]}")
        ok, why = _flags_blank(body)
        rep.check(ok, f"{label}: every operator flag blank ({why})")
    if expect_sha is None and seen:
        rep.check(len(set(seen.values())) == 1 and len(seen) == len(OPERATOR_BLOCK_SERVICES),
                  f"all {len(OPERATOR_BLOCK_SERVICES)} services run one build id "
                  f"({', '.join(sorted({s[:SHOWN_SHA] for s in seen.values()}))})")
    print(f"\n{rep.passed}/{rep.passed + rep.failed} checks passed")
    return 0 if rep.failed == 0 and rep.passed else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="phase_g_stage0_check", description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", required=True, help="estate base URL, e.g. http://127.0.0.1:18080")
    ap.add_argument("--expect-build-sha", help="the full 40- or 64-hex commit id all services must report")
    args = ap.parse_args(argv)
    if args.expect_build_sha is not None and not SHA.fullmatch(args.expect_build_sha):
        print("error: --expect-build-sha must be a full 40- or 64-hex commit id")
        return 2
    return check_estate(ep.Estate(args.base, None), args.expect_build_sha)


if __name__ == "__main__":
    sys.exit(main())
