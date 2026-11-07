# Delta review PR 774 (S8-17 claude-approver MCP tool named bash/write/edit keeps its own name) — ssl-ff-builder-7-as-reviewer

**VERDICT: PASS** on head `e66c606029d2e62459b9f8663c6d7260e544fb06` (draft, base main). It is the passed head 4eac9a7c plus a merge of main and the ENVIRONMENT.md anchor refresh; no source change. Standing gate: CI and GX10 on this head (GX10 verifier-5 ran at 4eac9a7c, not here).

Independence: I did not build or fix this PR (2 commits; the merge is builder-8's per its note).

## Checks (HIGH, run by me)
- Identity: both commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; 0 files under .github/.
- Merge shape: parents 4eac9a7c (PR) and ff06b3398 (current origin/main), so the head is not behind main; `git merge-tree` against origin/main is clean (tree id only). PR diff vs main is the same 4 files as at 4eac9a7c: config.py +15/-2 (the MCP_TOOL_USE constant and the `event_type != MCP_TOOL_USE` guard), core.py 1 line (passes `_get(ev, "type")`), the 71-line test file, docs/ENVIRONMENT.md. Source logic identical to what reviewer-10 passed.
- `environment_anchors.py --check`: 0 wrong anchor row(s).
- Tests on the exact head (Windows, py3.14): new file 11 passed; whole `services/claude-approver/tests` 368 passed, 0 failed (84 s).

## Mutants (5, one at a time, files restored and tree verified clean; counted from the table)
| # | mutant | result |
|---|---|---|
| M1 | exemption removed (default applies to MCP too) | KILLED |
| M2 | condition flipped (`==`) | KILLED |
| M3 | core.py stops passing the event type | KILLED |
| M4 | MCP_TOOL_USE constant set to agent.tool_use | KILLED |
| M5 | explicit per-agent map ignored for MCP events | KILLED (`test_the_explicit_maps_still_apply_to_an_mcp_tool`) |
Totals: 5 attempted, 5 killed, 0 survived, 0 not applied.

## Carried forward (not re-opened)
Reviewer-10's behaviour note stands: an estate that relied on the old mapping gets D.scope BLOCKs for such MCP tools (fail-closed direction; estate config not visible to me). Reviewer-10's two LOWs stand as optional follow-ups.

## Not verified
GX10 / Linux; CI; a live Console event.
