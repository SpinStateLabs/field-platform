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
API_BASE = "https://api.anthropic.com"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # a 3xx is an answer, never a hop: the x-api-key header must not travel


# No proxy from the environment and no redirect: this call carries the workspace API key (C-57 lint).
_OPENER = urllib.request.build_opener(_NoRedirect, urllib.request.ProxyHandler({}))


def call(path, payload):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY is not set; nothing sent")
    req = urllib.request.Request(
        API_BASE + path, method="POST", data=json.dumps(payload).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "anthropic-beta": "managed-agents-2026-04-01", "content-type": "application/json"})
    try:
        with _OPENER.open(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        # the status and a fixed phrase: an upstream body is never part of an error message (C-503)
        sys.exit(f"HTTP {e.code}: the API refused the request (body not shown)")
    except (OSError, ValueError) as e:
        # URLError, timeouts and resets are OSError; a reply that is not UTF-8 JSON is a ValueError: the class name
        # only, because the text can carry the URL or part of the reply
        sys.exit(f"request failed: {type(e).__name__}")


MAX_BUDGET_CENTS = 100_000_000      # 1,000,000 USD: a typo guard, not a policy; the workspace budget is the real limit


def _budget_cents(text: str) -> str:
    """A positive integer of at most MAX_BUDGET_CENTS, as text (the API takes the amount as a string)."""
    if not (text.isascii() and text.isdigit()) or not 0 < int(text) <= MAX_BUDGET_CENTS:
        raise argparse.ArgumentTypeError(f"must be a whole number of cents from 1 to {MAX_BUDGET_CENTS}")
    return str(int(text))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("role", choices=sorted(AGENTS))
    p.add_argument("session_name", help="unique among live sessions; no personal name")
    p.add_argument("lane", choices=["A", "B"])
    p.add_argument("--budget-cents", type=_budget_cents, default="100")
    a = p.parse_args()
    agent_id, field_id = AGENTS[a.role]
    s = call("/v1/sessions", {
        "agent": agent_id, "environment_id": ENV_ID,
        "budget": {"type": "limit", "max_list_cost": {"amount": a.budget_cents, "currency": "USD"}},
        "metadata": {"field_agent_id": field_id, "role": a.role}})
    text = (f"Session name: {a.session_name}\nLane: {a.lane}\n"
            "Run the ROLE LOOP from your system prompt now and keep running it.")
    sid = s.get("id") if isinstance(s, dict) else None
    if not isinstance(sid, str) or not sid:
        sys.exit("unexpected reply: no session id; no event sent")
    call(f"/v1/sessions/{sid}/events",
         {"events": [{"type": "user.message", "content": [{"type": "text", "text": text}]}]})
    print(sid)


if __name__ == "__main__":
    main()
