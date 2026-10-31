# Builder Lane 16: Don's rulings on the three open MCP write-tier decisions (C-902, C-1014, C-775)

Source: Don, in the Lane 16 session, 2026-10-31 (taking the recommendation on each).

1. Write process with no operator pair: REFUSE TO START. PR 380's newest commit already does this; no change needed. Not a reversal of any earlier ruling known to me.
2. FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1: leave unarmed; caller signing in field-mcp stays opt-in (FFMCP_CALLER_ID plus a key file) until the public key is registered in the ledger keyring. Arming and key registration are the coordinator's secret work, not done here.
3. C-775 conditions C2 and C4: DEFERRED until PR 380 merges; then the coordinator cuts a card if they are still wanted.

Coordinator: please record these in the queue next to C-902 and C-1023. Nothing was built or pushed to PR 380 for this note.
