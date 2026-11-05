# Review PR #774 (claude-approver: MCP tool named bash/write/edit keeps its own name, S8-17) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `4eac9a7c8c15197cf848463453f612150abceb65` (draft, base main). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 1 commit, 4 files: claude_approver/config.py (+12/-3), core.py (1 line), tests/test_approver_mcp_sandbox_names_s8.py (+71), docs/ENVIRONMENT.md (cite regeneration only: config.py:29-35 to :31-37, consistent with +2 lines in config.py). Nothing under .github/. Author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- `resolve_action(..., event_type=None)`: the sandbox default is skipped only when `event_type == "agent.mcp_tool_use"`. Explicit per-agent and global maps still win. The only production caller (core.py:723) now passes `_get(ev, "type")`; ASK_TYPES is exactly `agent.tool_use` and `agent.mcp_tool_use` (core.py:73).
- Direction is fail-closed (HIGH): an MCP tool named bash/write/edit is no longer authorised under the sandbox scope; it is checked as its own name (sentinel BLOCKs D.scope unless in scope). Nothing became more permissive. Behaviour change to expect: an estate relying on the old mapping gets D.scope BLOCKs (author discloses; estate config not visible to me).
- Tests: tests/test_approver_mcp_sandbox_names_s8.py 11 passed on the head. Full approver suite: my run showed only dots (182 visible in the tail, no F), summary line hidden by my -q -q flags; the PR's "326 passed" is not independently confirmed.

## Mutants (config.py / core.py, one at a time, restored after each)
| # | Mutant | Result |
|---|--------|--------|
| M1 | event_type condition removed | RED |
| M2 | condition flipped (`==`) | RED |
| M3 | core.py stops passing the event type | RED |
| M4 | MCP_TOOL_USE constant set to agent.tool_use | RED |
| M5 | core.py reads the wrong key ("kind") | RED |
| M6 | only `bash` exempted for MCP | RED |
| M7 | exemption only when event_type is None (builtin type also exempt) | RED |
| M8 | explicit per-agent map ignored for MCP | RED |
Totals counted from the table: 8 mutants, 8 RED, 0 SURVIVED.

## LOWs (optional, new PR)
1. Overlap with S2-7 (author did not read it); `event_type` is optional, so existing pins are unaffected.
2. An unknown event type (not in ASK_TYPES) never reaches resolve_action; `something.else` in the direct test is a library-level case only (harmless).
