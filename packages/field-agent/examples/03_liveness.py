"""Sample: hook 3 — LIVENESS. Poll the kill-switch; halt on killed.

Shows: the observer form (heartbeat), the halt gate (ensure_alive), a real
kill propagating into AgentKilled, the unknown-agent fail-closed answer,
and revive. The kill/revive calls are OPERATOR actions, done here over raw
REST to stage the scenario.

Run:  python 03_liveness.py                 (after 04_bootstrap_operator.py)
"""

from __future__ import annotations

import os
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import httpx

from field_agent import AgentKilled, FieldAgent
from field_core.authn import auth_headers

AGENT_ID = "sample-agent"
KILLSWITCH = os.environ.get("FIELD_KILLSWITCH_URL",
                            "http://127.0.0.1:8005").rstrip("/")
OP = {"operator": "CISO on-call (sample)", "reason": "liveness sample"}


def main() -> int:
    agent = FieldAgent(AGENT_ID)

    # Observer form: returns the heartbeat, never raises on killed=true.
    hb = agent.heartbeat()
    print(f"heartbeat: status={hb.status} killed={hb.killed}")

    # Halt gate: raises AgentKilled unless active.
    agent.ensure_alive()
    print("ensure_alive: ok")

    # Operator kills the agent (REST) — the SDK halts on the next gate.
    with httpx.Client(timeout=5.0, headers=auth_headers()) as http:
        http.post(f"{KILLSWITCH}/kill/{AGENT_ID}", json=OP).raise_for_status()
    try:
        agent.ensure_alive()
        print("!! still alive — must never print")
        return 2
    except AgentKilled as exc:
        print(f"halted as designed: {exc}")

    # Unknown agents are told to stop (kill-switch fail-closed).
    try:
        FieldAgent("no-such-agent").ensure_alive()
        return 2
    except AgentKilled as exc:
        print(f"unknown agent halted: status={exc.heartbeat.status}")

    # Revive so later samples keep working.
    with httpx.Client(timeout=5.0, headers=auth_headers()) as http:
        http.post(f"{KILLSWITCH}/revive/{AGENT_ID}", json=OP).raise_for_status()
    print(f"revived: killed={agent.ensure_alive().killed}")

    # Tip: FieldAgent(..., heartbeat_max_age=30.0) makes every check()
    # re-verify liveness when the last confirmation is older than 30s.
    return 0


if __name__ == "__main__":
    sys.exit(main())
