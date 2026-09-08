"""OPERATOR script — put Spin State's own agents on the GB10 FIELD estate.

Registers ssl-timekeeping-agent and ssl-invoicing-agent, sets their governor
caps from the manifests, mints delegation tokens scoped EXACTLY to each
manifest's ``delegation.scope``, then fires one sentinel /check per scope
action plus one never-granted action per agent so the verdicts land on the
ledger. Idempotent — safe to re-run (re-running mints fresh tokens).

This is the human's side of governance (bootstrap lives outside the agents;
see docs/INTEGRATION.md §3). It is the single-port-proxy analogue of
``_local-test/provision_local.py``.

Run from rog-command (venv C:\\Users\\donal\\.venvs\\field-platform):

    python tools/provision_ssl_agents.py

Env:
    FIELD_PROXY_URL      default http://10.0.0.62:18080  (Caddy path-routed)
    FIELD_SHARED_SECRET  if the estate enforces x-field-auth
    FIELD_TOKENS_FILE    default %USERPROFILE%\\.field-local\\tokens-gb10.json
    FIELD_TOKEN_TTL_DAYS default 30

PREREQUISITE: the two manifests must exist on the estate at
/data/manifests/<agent>.yaml (the sentinel resolves ``manifest_ref`` on ITS
filesystem). See manifests/README.md. Until they do, every /check is an
``I.manifest`` BLOCK — this script prints that plainly instead of hiding it.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

import httpx
import yaml

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
PROXY = os.environ.get("FIELD_PROXY_URL", "http://10.0.0.62:18080").rstrip("/")
REG, LED, DEL, SEN, KIL, GOV = (f"{PROXY}/{p}" for p in
                                ("registry", "ledger", "delegation",
                                 "sentinel", "killswitch", "governor"))
TTL = int(os.environ.get("FIELD_TOKEN_TTL_DAYS", "30")) * 24 * 3600
TOKENS_FILE = pathlib.Path(os.environ.get(
    "FIELD_TOKENS_FILE",
    str(pathlib.Path.home() / ".field-local" / "tokens-gb10.json")))
ESTATE_MANIFEST_DIR = "/data/manifests"      # the sentinel's view, not ours

AGENTS = {
    "ssl-timekeeping-agent": {
        "name": "SSL Time Keeping Agent", "domain": "finance",
        "never": "submit for approval",
    },
    "ssl-invoicing-agent": {
        "name": "SSL Invoicing Agent", "domain": "finance",
        "never": "send invoice email",
    },
}

headers = {}
if os.environ.get("FIELD_SHARED_SECRET"):
    headers["x-field-auth"] = os.environ["FIELD_SHARED_SECRET"]
H = httpx.Client(timeout=20.0, headers=headers)


def manifest(agent_id: str) -> dict:
    path = REPO / "manifests" / f"{agent_id}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def health() -> None:
    bad = []
    for name, base in (("registry", REG), ("ledger", LED), ("delegation", DEL),
                       ("sentinel", SEN), ("killswitch", KIL), ("governor", GOV)):
        try:
            r = H.get(f"{base}/health")
            ok = r.status_code == 200
        except Exception as exc:              # noqa: BLE001 — report, then stop
            ok, r = False, exc
        print(f"  {name:11s} {'OK' if ok else 'FAIL'}  {base}")
        if not ok:
            bad.append(name)
    if bad:
        sys.exit(f"estate not healthy ({', '.join(bad)}) — nothing provisioned")


def upsert(agent_id: str, body: dict) -> str:
    r = H.post(f"{REG}/agents", json=body)
    if r.status_code == 201:
        return "registered"
    r = H.patch(f"{REG}/agents/{agent_id}",
                json={"manifest_ref": body["manifest_ref"], "owner": body["owner"]})
    r.raise_for_status()
    return f"updated ({r.status_code})"


def main() -> int:
    print(f"estate: {PROXY}")
    health()
    tokens: dict[str, str] = {}
    if TOKENS_FILE.exists():
        tokens = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))

    for agent_id, meta in AGENTS.items():
        m = manifest(agent_id)
        assert m["agent"]["name"] == agent_id, f"manifest name mismatch for {agent_id}"
        scope = list(m["delegation"]["scope"])
        principal = m["identity"]["principal"]
        cap = m["enforcement"]["spend_cap"]
        print(f"\n== {agent_id}")

        print("  registry:", upsert(agent_id, {
            "agent_id": agent_id, "name": meta["name"], "owner": principal,
            "domain": meta["domain"],
            "manifest_ref": f"{ESTATE_MANIFEST_DIR}/{agent_id}.yaml"}))

        r = H.put(f"{GOV}/caps/{agent_id}", json={
            "agent_id": agent_id, "limit_cents": int(cap["limit"]) * 100,
            "period": cap["period"], "escalate_at_pct": 80})
        r.raise_for_status()
        print(f"  cap: {cap['currency']} {cap['limit']}/{cap['period']}, escalate at 80%")
        # No usage policy (allowed_models): the Cowork/Claude Code model is not
        # selectable by the agent and no token counts are observable, so an
        # allow-list would be an unverifiable declaration. Stated, not hidden.

        r = H.post(f"{DEL}/tokens", json={
            "agent_id": agent_id, "granted_by": principal, "scope": scope,
            "ttl_seconds": TTL})
        r.raise_for_status()
        tok = r.json()
        tokens[agent_id] = tok["token_id"]
        print(f"  token: minted, expires {tok.get('expires_at', '?')}, "
              f"scope={len(scope)} actions")

        hb = H.get(f"{KIL}/heartbeat/{agent_id}").json()
        print(f"  heartbeat: killed={hb.get('killed')} status={hb.get('status')}")

        for action in scope + [meta["never"]]:
            v = H.post(f"{SEN}/check", json={
                "agent_id": agent_id, "action": action,
                "token_id": tokens[agent_id]}).json()
            wb = (v.get("context") or {}).get("would_be") or {}
            clause = wb.get("clause_id") or v.get("clause_id") or "-"
            tag = "" if action != meta["never"] else "   (never granted — expect D.scope)"
            print(f"    {action:30s} -> {v.get('decision', '?'):8s} {clause}{tag}")

    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    print(f"\ntokens ({TTL // 86400}-day TTL) saved to {TOKENS_FILE}")

    ver = H.get(f"{LED}/verify").json()
    print(f"ledger verify: {ver}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
