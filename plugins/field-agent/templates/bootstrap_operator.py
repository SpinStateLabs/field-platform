"""Sample: OPERATOR setup — everything a human does before the agent runs.

Manifest → register → spend cap → usage policy → mint token. The cap and
policy PUTs are raw REST on purpose: they show that the SDK has no private
channel — the governor's own HTTP API is the whole interface (interactive
docs at http://127.0.0.1:8006/docs, and likewise on every service port).

Run:  python 04_bootstrap_operator.py     (prints the token id last)
"""

from __future__ import annotations

import os
import sys
import tempfile

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import httpx
import yaml

from field_agent import BootstrapError, bootstrap
from field_core.authn import auth_headers
from field_core.templates_api import template_data

AGENT_ID = "sample-agent"
SCOPE = ["read timesheets", "draft invoices", "send invoice email"]
GOVERNOR = os.environ.get("FIELD_GOVERNOR_URL", "http://127.0.0.1:8006").rstrip("/")


def write_manifest() -> str:
    data = template_data("default")
    data["agent"]["name"] = AGENT_ID
    data["agent"]["description"] = "SDK examples: governed sample agent"
    data["identity"]["principal"] = "Controller, Spin State Labs"
    data["identity"]["org"] = "Spin State Labs"
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = (
        f"http://127.0.0.1:8005/kill/{AGENT_ID}"
    )
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["enforcement"]["escalation_triggers"] = ["send invoice"]
    data["enforcement"]["spend_cap"] = {"currency": "USD", "limit": 500,
                                        "period": "daily", "on_breach": "halt"}
    data["ledger"]["store"] = "sealed-ledger service (hash-chained JSONL)"
    data["delegation"]["granted_by"] = "Controller, Spin State Labs"
    data["delegation"]["scope"] = list(SCOPE)
    data["delegation"]["expiry"] = "2027-06-30"
    data["delegation"]["revocation"] = {
        "method": "HTTP POST",
        "endpoint": "http://127.0.0.1:8003/tokens/{id}/revoke",
    }
    base = os.environ.get("FIELD_DATA_DIR") or tempfile.mkdtemp()
    path = os.path.join(base, f"{AGENT_ID}.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(yaml.safe_dump(data, sort_keys=False))
    return path


def main() -> int:
    manifest = write_manifest()
    print(f"manifest: {manifest}")

    try:
        rec = bootstrap.register(AGENT_ID, name="Sample Agent",
                                 owner="Controller, Spin State Labs",
                                 domain="finance", manifest_ref=manifest)
        print(f"registered: {rec['agent_id']} status={rec['status']}")
    except BootstrapError as exc:
        if "409" not in str(exc):
            raise
        print("already registered — continuing")

    # Operator REST calls (same thing `governor set-cap` / `set-policy` do).
    with httpx.Client(timeout=5.0, headers=auth_headers()) as http:
        r = http.put(f"{GOVERNOR}/caps/{AGENT_ID}",
                     json={"agent_id": AGENT_ID, "limit_cents": 50_000,
                           "period": "daily", "escalate_at_pct": 80})
        r.raise_for_status()
        print("cap: $500/day, escalate at 80%")
        r = http.put(f"{GOVERNOR}/policies/{AGENT_ID}",
                     json={"agent_id": AGENT_ID,
                           "allowed_models": ["claude-haiku-4-5"],
                           "token_rate_limit": 200_000})
        r.raise_for_status()
        print("policy: haiku only, 200k tokens/h")

    token = bootstrap.mint(AGENT_ID, granted_by="Controller, Spin State Labs",
                           scope=list(SCOPE), ttl_seconds=3600)
    print(f"minted by {token.granted_by}, expires {token.expires_at}")
    print(token.token_id)   # last line: captured by run_all.sh
    return 0


if __name__ == "__main__":
    sys.exit(main())
