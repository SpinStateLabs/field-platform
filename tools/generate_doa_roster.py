#!/usr/bin/env python3
"""generate_doa_roster - build a DOA roster YAML from inputs the operator supplies.

    python tools/generate_doa_roster.py --registry agents.json --manifests DIR \
        --tokens tokens.json --out doa-roster.yaml [--max-ttl-days 30] [--skip-unresolved]

INPUTS, never fetched by this tool (it opens no connection):
  --registry   a JSON list of registry records, e.g. an in-estate
               `GET /registry/agents` saved to a file;
  --manifests  a directory holding the agents' FIELD manifests. A record's
               `manifest_ref` (e.g. /data/manifests/ssl-invoicing-agent.yaml)
               is resolved by its FILE NAME inside this directory, through
               field-core's one resolver, so a manifest that does not validate
               counts as unresolved exactly as it would at mint time;
  --tokens     a JSON list of delegation tokens, e.g. an in-estate
               `GET /delegation/tokens` saved to a file. Optional, but plan J9's
               first row source needs it: without it a grantor string that
               exists only on live tokens is NOT rostered, and the tool says so.

ROWS (v1.2 plan, JUDGEMENT J9 when --tokens is given). Over registered agents
whose status is not `retired`:
  - one row per distinct `granted_by` of a LIVE token (not revoked, not
    expired at generation time) held by such an agent (--tokens);
  - one row per distinct manifest `identity.principal`, and one per distinct
    manifest `delegation.granted_by` (the canary's grantor arrives this way);
  - a row's `allowed_scope` is the ordered union of `delegation.scope` over
    the manifests of every agent it names: as `granted_by` or `principal` in
    the manifest, or as the grantor of a live token that agent holds;
  - `max_ttl_days` is --max-ttl-days (default 30) and `active: true`;
  - `max_spend_usd` is not set (it is recorded, never enforced, at mint).
A live-token grantor that no manifest names is listed on stdout as
"token-only". Tokens held by retired or unregistered agents, and revoked or
expired tokens, contribute nothing.

REFUSALS - exit 2 and NOTHING is written:
  - unreadable or malformed inputs (a --tokens record that is not a delegation
    token included);
  - a registered non-retired agent whose manifest does not resolve (unless
    --skip-unresolved, which names each skipped agent on stderr);
  - a roster with no grantors: `grantors: []` refuses every mint on the estate;
  - a roster that does not validate against delegation_authority.doa's model,
    checked before writing and again by reloading the written file.

LIMITS. The roster is a membership list of STRINGS, not identities. Without
--tokens, grantor strings seen only on live tokens are not rostered. A token
grantor whose holders have no resolvable manifest (possible only with
--skip-unresolved) gets no row, and is named on stderr. The token file is a
snapshot: a token minted after it was saved is not seen. Run `delegation doa
check` for every real renewal before arming. Two agents whose refs share a file
name resolve to the same manifest file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import yaml

from delegation_authority.doa import DoaRoster, DoaRosterError, load_roster
from field_core.clients import resolve_manifest_detail
from field_core.delegation import DelegationToken

EXIT_WRITTEN = 0
EXIT_REFUSED = 2


class Refused(Exception):
    """Nothing is written; the message says why."""


def load_records(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise Refused(f"--registry {path}: not a readable JSON file ({type(exc).__name__})")
    if not isinstance(data, list):
        raise Refused(f"--registry {path}: expected a JSON list of registry records")
    for i, rec in enumerate(data):
        if not isinstance(rec, dict) or not isinstance(rec.get("agent_id"), str) or not rec["agent_id"]:
            raise Refused(f"--registry {path}: record {i} has no agent_id")
    return data


def load_tokens(path: Path) -> list[DelegationToken]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise Refused(f"--tokens {path}: not a readable JSON file ({type(exc).__name__})")
    if not isinstance(data, list):
        raise Refused(f"--tokens {path}: expected a JSON list of delegation tokens")
    tokens = []
    for i, rec in enumerate(data):
        try:
            tokens.append(DelegationToken.model_validate(rec))
        except Exception as exc:  # pydantic ValidationError
            raise Refused(f"--tokens {path}: record {i} is not a delegation token ({type(exc).__name__})")
        naive = [name for name in ("issued_at", "expires_at")
                 if getattr(tokens[-1], name, None) is not None and getattr(tokens[-1], name).tzinfo is None]
        if naive:
            raise Refused(f"--tokens {path}: record {i} has a timezone-naive {', '.join(naive)} "
                          "(expected an ISO-8601 time with an offset, as the delegation service writes)")
    return tokens


def resolve(record: dict, manifest_dir: Path):
    """(FieldManifest | None, reason). Resolution is by file name inside
    --manifests: an estate path like /data/manifests/x.yaml means x.yaml here."""
    ref = record.get("manifest_ref")
    if not ref:
        return None, "no_ref"
    name = PurePosixPath(str(ref).replace("\\", "/")).name
    if not name:
        return None, "missing"
    return resolve_manifest_detail(name, manifest_dir=manifest_dir)


def _add_scope(scopes: dict[str, list[str]], grantor: str, declared: list[str]) -> None:
    union = scopes.setdefault(grantor, [])
    for scope in declared:
        if scope not in union:
            union.append(scope)


def build_roster(records: list[dict], manifest_dir: Path, max_ttl_days: int,
                 skip_unresolved: bool, tokens: list[DelegationToken] | None = None,
                 now: datetime | None = None) -> tuple[DoaRoster, dict]:
    now = now or datetime.now(timezone.utc)
    scopes: dict[str, list[str]] = {}
    retired: list[str] = []
    unresolved: list[tuple[str, str]] = []
    used: list[str] = []
    manifests: dict[str, object] = {}
    registered: set[str] = set()
    for record in sorted(records, key=lambda r: r["agent_id"]):
        registered.add(record["agent_id"])
        if record.get("status") == "retired":
            retired.append(record["agent_id"])
            continue
        manifest, reason = resolve(record, manifest_dir)
        if manifest is None:
            unresolved.append((record["agent_id"], reason))
            continue
        used.append(record["agent_id"])
        manifests[record["agent_id"]] = manifest
        for grantor in (manifest.delegation.granted_by, manifest.identity.principal):
            _add_scope(scopes, grantor, manifest.delegation.scope)
    manifest_named = set(scopes)

    # J9 row source 1: the grantor of every LIVE token held by a registered,
    # non-retired agent, scoped to the union of its holders' manifest scopes.
    token_only: dict[str, list[str]] = {}   # grantor -> holders, when no manifest names it
    token_unscoped: dict[str, list[str]] = {}  # grantor -> holders without a resolvable manifest
    ignored_tokens: list[tuple[str, str]] = []
    retired_ids = set(retired)
    for token in sorted(tokens or [], key=lambda tok: (tok.granted_by, tok.agent_id, tok.token_id)):
        if not token.is_active(now):
            ignored_tokens.append((token.token_id, token.status(now).value))
            continue
        if token.agent_id not in registered:
            ignored_tokens.append((token.token_id, f"holder {token.agent_id} not registered"))
            continue
        if token.agent_id in retired_ids:
            ignored_tokens.append((token.token_id, f"holder {token.agent_id} retired"))
            continue
        manifest = manifests.get(token.agent_id)
        if manifest is None:
            token_unscoped.setdefault(token.granted_by, []).append(token.agent_id)
            continue
        _add_scope(scopes, token.granted_by, manifest.delegation.scope)
        if token.granted_by not in manifest_named:
            holders = token_only.setdefault(token.granted_by, [])
            if token.agent_id not in holders:
                holders.append(token.agent_id)
    token_unscoped = {g: h for g, h in token_unscoped.items() if g not in scopes}

    if unresolved and not skip_unresolved:
        listed = ", ".join(f"{a} ({why})" for a, why in unresolved)
        raise Refused(
            f"{len(unresolved)} registered non-retired agent(s) have no resolvable manifest in "
            f"{manifest_dir}: {listed}. Copy the manifests in, or pass --skip-unresolved to "
            "leave their grantors off the roster deliberately"
        )
    if not scopes:
        raise Refused("no grantors: no registered non-retired agent has a resolvable manifest, "
                      "and `grantors: []` would refuse every mint")

    data = {"grantors": [
        {"grantor": grantor, "allowed_scope": scopes[grantor],
         "max_ttl_days": max_ttl_days, "active": True}
        for grantor in sorted(scopes)
    ]}
    try:
        roster = DoaRoster.model_validate(data)
    except Exception as exc:  # pydantic ValidationError
        raise Refused(f"generated roster does not validate against delegation_authority.doa: {exc}")
    return roster, {"used": used, "retired": retired, "unresolved": unresolved,
                    "token_only": token_only, "token_unscoped": token_unscoped,
                    "ignored_tokens": ignored_tokens}


def write_roster(roster: DoaRoster, out: Path, header: str) -> None:
    """Write to a temp file beside OUT, reload it with the service's own loader,
    and only then replace OUT. A file that would not load is never left behind."""
    body = roster.model_dump(mode="json", exclude_none=True)
    text = header + yaml.safe_dump(body, sort_keys=False, allow_unicode=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        reloaded = load_roster(tmp)
        if reloaded != roster:
            raise Refused("written roster does not reload to the validated roster")
        os.replace(tmp, out)
    except DoaRosterError as exc:
        raise Refused(f"written roster does not load: {exc}")
    finally:
        if tmp.exists():
            tmp.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="generate_doa_roster", description=__doc__.split("\n\n")[0])
    parser.add_argument("--registry", required=True, type=Path, help="JSON list of registry records")
    parser.add_argument("--manifests", required=True, type=Path, help="directory of FIELD manifests")
    parser.add_argument("--tokens", type=Path, default=None,
                        help="JSON list of delegation tokens (a saved GET /delegation/tokens): "
                             "the grantor of every live token held by a registered, non-retired "
                             "agent gets a row (plan J9). Omitted: token-only grantors are NOT rostered")
    parser.add_argument("--out", required=True, type=Path, help="roster YAML to write")
    parser.add_argument("--max-ttl-days", type=int, default=30, help="max_ttl_days on every row (default 30)")
    parser.add_argument("--skip-unresolved", action="store_true",
                        help="leave agents with no resolvable manifest off the roster instead of refusing")
    args = parser.parse_args(argv)

    try:
        if not args.manifests.is_dir():
            raise Refused(f"--manifests {args.manifests}: not a directory")
        records = load_records(args.registry)
        tokens = load_tokens(args.tokens) if args.tokens is not None else None
        roster, info = build_roster(records, args.manifests, args.max_ttl_days, args.skip_unresolved,
                                    tokens=tokens)
        token_source = (
            f"{len(tokens)} token(s) in {args.tokens.name}" if tokens is not None
            else "NO token file (grantors found only on live tokens are not rostered)"
        )
        header = (
            "# DOA roster GENERATED by tools/generate_doa_roster.py "
            f"at {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
            f"# from {len(records)} registry record(s) in {args.registry.name}, the manifests in "
            f"{args.manifests.name}/ (agents used: {', '.join(info['used'])}) and {token_source}.\n"
            "# Review before arming FIELD_DOA_ROSTER: every grantor string below is accepted as\n"
            "# `granted_by` for its allowed_scope. A membership list, not authentication.\n"
        )
        write_roster(roster, args.out, header)
    except Refused as exc:
        print(f"REFUSED (nothing written): {exc}", file=sys.stderr)
        return EXIT_REFUSED

    for agent_id, why in info["unresolved"]:
        print(f"skipped {agent_id}: no resolvable manifest ({why}) - its grantor is NOT rostered", file=sys.stderr)
    if info["ignored_tokens"]:
        print(f"ignored {len(info['ignored_tokens'])} token(s): revoked, expired, or held by a retired "
              "or unregistered agent (they cannot be renewed)")
    if args.tokens is None:
        print("no --tokens given: a grantor string that exists only on live tokens is NOT rostered "
              "(plan J9 row source 1 skipped) - its next renewal will be refused 403 D.grantor",
              file=sys.stderr)
    for grantor, holders in sorted(info["token_unscoped"].items()):
        print(f"live-token grantor {grantor!r} NOT rostered: its holder(s) {', '.join(holders)} "
              "have no resolvable manifest to scope it", file=sys.stderr)
    print(f"wrote {args.out}: {len(roster.grantors)} grantor row(s) from {len(info['used'])} agent(s); "
          f"{len(info['retired'])} retired skipped, {len(info['unresolved'])} unresolved skipped")
    for row in roster.grantors:
        origin = ""
        if row.grantor in info["token_only"]:
            origin = f" [token-only: live token(s) held by {', '.join(info['token_only'][row.grantor])}]"
        print(f"  - {row.grantor}: {len(row.allowed_scope)} scope(s), max_ttl_days={row.max_ttl_days}{origin}")
    return EXIT_WRITTEN


if __name__ == "__main__":
    sys.exit(main())
