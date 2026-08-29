"""The deliberately mundane governed agent: reads a timesheet CSV, drafts
invoices — every tool call, dollar, and token behind the field-agent SDK.

Run by ``run_demo.sh`` after the platform is up and the agent is
registered, capped, policied, and holding a delegation token. All data
SYNTHETIC.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from field_agent import (
    ActionBlocked,
    ActionEscalated,
    AgentKilled,
    FieldAgent,
)

AGENT_ID = "invoicing-agent"

# The governed spend is the AGENT'S operating cost (compute, LLM, tooling),
# not the client invoice value. Fixed per-draft cost for determinism:
# 5 drafts × $120 against the manifest's $500/day cap ⇒ the 5th draft
# arrives with the meter at 96% and is escalated to a human.
DRAFT_COST_CENTS = 12_000
# Per-draft LLM usage (synthetic, haiku-priced ≈ $0.0045/draft) folds into
# the SAME cap without moving the 96%-escalation story.
DRAFT_INPUT_TOKENS, DRAFT_OUTPUT_TOKENS = 2_000, 500


def main(timesheet: Path, out_dir: Path, token_id: str) -> int:
    agent = FieldAgent(AGENT_ID, token_id=token_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        agent.ensure_alive()
    except AgentKilled as exc:
        print(f"heartbeat says stop — halting before any work ({exc})")
        return 1

    print("-- reading timesheet (governed) --")
    agent.check("read timesheets")
    rows = list(csv.DictReader(timesheet.open(encoding="utf-8")))
    print(f"   {len(rows)} rows")

    drafted = escalated = 0
    for i, row in enumerate(rows, start=1):
        total_cents = int(row["hours"]) * int(row["rate_cents"])
        try:
            agent.check("draft invoices")
        except ActionEscalated as exc:
            print(f"   INV-{i:03d} {row['client']}: ESCALATED to human queue "
                  f"[{exc.verdict['clause_id']}] — not drafted")
            escalated += 1
            continue
        invoice = out_dir / f"INV-{i:03d}.txt"
        invoice.write_text(
            "DRAFT INVOICE (SYNTHETIC DEMO — pending human review)\n"
            f"Client:  {row['client']}\n"
            f"Project: {row['project']}\n"
            f"Hours:   {row['hours']} @ ${int(row['rate_cents'])/100:.2f}\n"
            f"Total:   ${total_cents/100:.2f}\n",
            encoding="utf-8",
        )
        agent.report_spend(cents=DRAFT_COST_CENTS, actions=1,
                           note=f"draft INV-{i:03d}")
        usage = agent.report_usage(
            "claude-haiku-4-5", DRAFT_INPUT_TOKENS, DRAFT_OUTPUT_TOKENS,
            note=f"draft INV-{i:03d}",
        )
        print(f"   INV-{i:03d} {row['client']}: drafted (${total_cents/100:.2f}), "
              f"LLM usage metered ({usage.status.token_cost_display} cumulative)")
        drafted += 1

    print("-- rogue attempt: transfer funds (never granted) --")
    try:
        agent.check("transfer funds")
        print("   !! ALLOWED — this must never print")
        return 2
    except ActionBlocked as exc:
        print(f"   BLOCKED [{exc.verdict['clause_id']}] as designed")

    print("-- rogue attempt: burning Opus off the Haiku allow-list --")
    rogue = agent.report_usage("claude-opus-4-8", input_tokens=12_000,
                               output_tokens=3_000, note="unapproved model")
    for finding in rogue.rogue:
        print(f"   FLAGGED {finding.kind}: {finding.detail}")

    print(f"-- done: {drafted} drafted, {escalated} escalated --")
    return 0


if __name__ == "__main__":
    sys.exit(
        main(
            timesheet=Path(sys.argv[1]),
            out_dir=Path(sys.argv[2]),
            token_id=sys.argv[3],
        )
    )
