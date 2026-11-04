"""Start a Managed Agents session for one ssl-fp role agent. Needs ANTHROPIC_API_KEY (workspace key) in env."""
import argparse, json, os, sys, urllib.error, urllib.request

AGENTS = {
    "red-team": ("agent_01VfLQMGVpqwF6cnoiEX1wbm", "ssl-fp-red-team"),
    "architect": ("agent_01CFUrUAweLjxSY57cLinFBx", "ssl-fp-architect"),
    "frontdoor-engineer": ("agent_01AthSbHv1rUW7pyVK1TJhVM", "ssl-fp-frontdoor-engineer"),
    "router-engineer": ("agent_01DykU8ZiA3V3HYC3rp5Spii", "ssl-fp-router-engineer"),
    "runtime-engineer": ("agent_01Jo57LEGbYFzEBwUrZjFUx9", "ssl-fp-runtime-engineer"),
}
ENV_ID = "env_01FD7nbGiLfiA4wwj4T3DJjY"


def call(path, payload):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY is not set; nothing sent")
    req = urllib.request.Request(
        "https://api.anthropic.com" + path, method="POST", data=json.dumps(payload).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "anthropic-beta": "managed-agents-2026-04-01", "content-type": "application/json"})
    try:
        # ProxyHandler({}): never read the proxy environment with an API key in the request (C-57)
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:400]}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("role", choices=sorted(AGENTS))
    p.add_argument("session_name", help="unique among live sessions; no personal name")
    p.add_argument("lane", choices=["A", "B"])
    p.add_argument("--budget-cents", default="100")
    a = p.parse_args()
    agent_id, field_id = AGENTS[a.role]
    s = call("/v1/sessions", {
        "agent": agent_id, "environment_id": ENV_ID,
        "budget": {"type": "limit", "max_list_cost": {"amount": a.budget_cents, "currency": "USD"}},
        "metadata": {"field_agent_id": field_id, "role": a.role}})
    text = (f"Session name: {a.session_name}\nLane: {a.lane}\n"
            "Run the ROLE LOOP from your system prompt now and keep running it.")
    call(f"/v1/sessions/{s['id']}/events",
         {"events": [{"type": "user.message", "content": [{"type": "text", "text": text}]}]})
    print(s["id"])


if __name__ == "__main__":
    main()
