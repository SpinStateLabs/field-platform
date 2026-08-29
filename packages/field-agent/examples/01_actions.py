"""Sample: hook 1 — ACTIONS. Every tool call asks the sentinel first.

Shows: ALLOW (the body runs), out-of-scope BLOCK (the body never runs),
escalation-trigger ESCALATE (a human already has it), and the flags.
Sentinel unreachable ⇒ ActionBlocked — the fail-closed contract is
inherited from the sentinel's own client, re-exported unchanged.

Run:  python 01_actions.py <token_id>      (after 04_bootstrap_operator.py)
"""

from __future__ import annotations

import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from field_agent import ActionBlocked, ActionEscalated, FieldAgent

AGENT_ID = "sample-agent"


def main(token_id: str) -> int:
    agent = FieldAgent(AGENT_ID, token_id=token_id)

    # Imperative form — returns the verdict dict on ALLOW.
    verdict = agent.check("read timesheets")
    print(f"ALLOW: {verdict['decision']} (clause={verdict['clause_id']})")

    # Decorator form — the body is unreachable unless the sentinel allows.
    ran = []

    @agent.governed("transfer funds")          # never granted to this agent
    def exfiltrate():
        ran.append(True)

    try:
        exfiltrate()
    except ActionBlocked as exc:
        print(f"BLOCK: [{exc.verdict['clause_id']}] "
              f"{exc.verdict['reasons'][0]}")
    assert not ran, "blocked body must never run"

    # Escalation triggers put the item in the human queue.
    try:
        agent.check("send invoice email")      # matches trigger "send invoice"
    except ActionEscalated as exc:
        print(f"ESCALATE: [{exc.verdict['clause_id']}] — a human has it")

    # Flags: mark irreversible actions; pass context through to the verdict.
    try:
        agent.check("draft invoices", irreversible=True,
                    context={"batch": "2026-08"})
        print("irreversible draft allowed by policy")
    except (ActionBlocked, ActionEscalated) as exc:
        print(f"irreversible policy said {exc.verdict['decision']}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
