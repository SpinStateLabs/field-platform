"""Sample: hook 2 — USAGE. Meter every LLM call and operating dollar.

Shows: priced usage, extract_usage()/report_usage_from on an Anthropic-
shaped response, non-LLM spend, a rogue-model finding, and the strict
no-cap refusal. Metering is STRICT: a failed report raises — an agent
that cannot meter should not keep spending.

Run:  python 02_usage.py                    (after 04_bootstrap_operator.py)
"""

from __future__ import annotations

import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from field_agent import FieldAgent, NoSpendCapError, extract_usage

AGENT_ID = "sample-agent"


def main() -> int:
    agent = FieldAgent(AGENT_ID)

    # Priced usage — FIELD computes exact integer cost from the dated book.
    report = agent.report_usage("claude-haiku-4-5", input_tokens=42_000,
                                output_tokens=9_000, note="sample call")
    r = report.record
    print(f"priced: {r.model} {r.input_tokens}+{r.output_tokens} tokens = "
          f"{r.cost_units} units ({report.status.token_cost_display} cum)")

    # Straight from an Anthropic Messages response (dict or SDK object).
    fake_response = {"model": "claude-haiku-4-5",
                     "usage": {"input_tokens": 1_200, "output_tokens": 300,
                               "cache_read_input_tokens": 5_000}}
    print(f"extract_usage -> {extract_usage(fake_response)}")
    agent.report_usage_from(fake_response, note="from response")

    # Non-LLM operating cost lands against the SAME cap.
    status = agent.report_spend(cents=250, actions=1, note="tool run")
    print(f"spend: {status.spent_cents}c of "
          f"{status.limit_cents}c cap, state={status.state}")

    # A model off the allow-list is a finding + escalation + ledger event.
    rogue = agent.report_usage("claude-opus-4-8", input_tokens=8_000,
                               output_tokens=2_000, note="unapproved model")
    for finding in rogue.rogue:
        print(f"FLAGGED {finding.kind}: {finding.detail}")

    # No cap ⇒ the governor refuses to meter, and the SDK refuses to hide it.
    try:
        FieldAgent("never-capped-agent").report_usage(
            "claude-haiku-4-5", input_tokens=10, output_tokens=10)
    except NoSpendCapError as exc:
        print(f"refused (as designed): {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
