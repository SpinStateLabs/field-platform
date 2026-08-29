"""COPY-PASTE TEMPLATE for a new governed agent on the FIELD platform.

Replace AGENT_ID, the action names, and the body of ``do_work``. Operator
setup must already exist (see ``04_bootstrap_operator.py``): a registered
agent + valid manifest, a spend cap, a usage policy, and a delegation
token minted by a human.

Run:  python agent_template.py <token_id>
Env:  FIELD_SENTINEL_URL / FIELD_GOVERNOR_URL / FIELD_KILLSWITCH_URL
      (defaults target a local stack); FIELD_SHARED_SECRET if the estate
      uses one (the SDK attaches it per request).
"""

from __future__ import annotations

import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from field_agent import (
    ActionBlocked,
    ActionEscalated,
    AgentKilled,
    FieldAgent,
    UsageReportError,
)

AGENT_ID = "sample-agent"        # <-- your registered agent id
WORK_ACTION = "draft invoices"   # <-- must be in token scope AND manifest scope


def main(token_id: str) -> int:
    agent = FieldAgent(
        AGENT_ID,
        token_id=token_id,       # a value, or a zero-arg callable if it rotates
        heartbeat_max_age=30.0,  # stale liveness is re-verified before checks
    )

    # LIVENESS — halt before any work if killed/unknown/unreachable.
    try:
        agent.ensure_alive()
    except AgentKilled as exc:
        print(f"halt: {exc}")
        return 1

    # ACTIONS — the body runs only if the sentinel says ALLOW.
    @agent.governed(WORK_ACTION)
    def do_work(item: str) -> None:
        print(f"   worked on {item}")   # <-- your tool call goes here

    for item in ("unit-1", "unit-2"):
        try:
            do_work(item)
        except ActionEscalated as exc:
            # The human queue already has the item; skip it (or wait).
            print(f"   escalated [{exc.verdict['clause_id']}] — skipped {item}")
            continue
        except ActionBlocked as exc:
            print(f"   blocked [{exc.verdict['clause_id']}] — stopping")
            return 1
        except AgentKilled as exc:      # heartbeat_max_age recheck fired
            print(f"halt mid-run: {exc}")
            return 1

        # USAGE — meter what the unit of work cost. Strict: if the report
        # doesn't land, the honest move is to stop, not to keep spending.
        try:
            agent.report_spend(cents=100, actions=1, note=f"work {item}")
            # after a real LLM call:
            #   resp = anthropic_client.messages.create(...)
            #   agent.report_usage_from(resp, note=f"work {item}")
        except UsageReportError as exc:
            print(f"metering failed — stopping: {exc}")
            return 1

    print("done under governance")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
