"""The deliberately mundane governed agent: reads a timesheet CSV, drafts
invoices — every tool call behind ``@governed``, every dollar metered.

Run by ``run_demo.sh`` after the platform is up and the agent is
registered, capped, and holding a delegation token. All data SYNTHETIC.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import httpx

from conformance_sentinel.governed import (
    ActionBlocked,
    ActionEscalated,
    Governor,
)

AGENT_ID = "invoicing-agent"
GOVERNOR_URL = os.environ.get("FIELD_GOVERNOR_URL", "http://127.0.0.1:8006")
KILLSWITCH_URL = os.environ.get("FIELD_KILLSWITCH_URL", "http://127.0.0.1:8005")

# The governed spend is the AGENT'S operating cost (compute, LLM, tooling),
# not the client invoice value. Fixed per-draft cost for determinism:
# 5 drafts × $120 against the manifest's $500/day cap ⇒ the 5th draft
# arrives with the meter at 96% and is escalated to a human.
DRAFT_COST_CENTS = 12_000


def heartbeat_ok() -> bool:
    hb = httpx.get(f"{KILLSWITCH_URL}/heartbeat/{AGENT_ID}", timeout=5.0).json()
    return not hb["killed"]


def record_spend(cents: int, note: str) -> None:
    httpx.post(
        f"{GOVERNOR_URL}/spend",
        json={"agent_id": AGENT_ID, "cents": cents, "actions": 1, "note": note},
        timeout=5.0,
    )


def main(timesheet: Path, out_dir: Path, token_id: str) -> int:
    guard = Governor(agent_id=AGENT_ID, token_id=token_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not heartbeat_ok():
        print("heartbeat says killed — halting before any work")
        return 1

    print("-- reading timesheet (governed) --")
    guard.check("read timesheets")
    rows = list(csv.DictReader(timesheet.open(encoding="utf-8")))
    print(f"   {len(rows)} rows")

    drafted = escalated = 0
    for i, row in enumerate(rows, start=1):
        total_cents = int(row["hours"]) * int(row["rate_cents"])
        try:
            guard.check("draft invoices")
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
        record_spend(DRAFT_COST_CENTS, f"draft INV-{i:03d}")
        print(f"   INV-{i:03d} {row['client']}: drafted (${total_cents/100:.2f})")
        drafted += 1

    print("-- rogue attempt: transfer funds (never granted) --")
    try:
        guard.check("transfer funds")
        print("   !! ALLOWED — this must never print")
        return 2
    except ActionBlocked as exc:
        print(f"   BLOCKED [{exc.verdict['clause_id']}] as designed")

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
