# C-209 reviewer report (Lane 5): PR 101 docs/claude-approver-declared-c164 @89122a719610db842cebd6a18fb88f7c5ba9e03f

VERDICT: PASS on the exact head 89122a719610db842cebd6a18fb88f7c5ba9e03f. Both rows match the code: an ALLOW authorizes a tool NAME and `irreversible` is the constant false (core.py:377-383), and `/halt` is guarded by the origin-header marker only (api.py `halt_open_paths` and the handler's `ORIGIN_HEADER` check). Full gx10_verify is green on the head. Two LOW notes.

OBJECTIONS FIRST
1. The card gives the code lines as core.py:379-386 and api.py:34-62. On main the `_check` body is at core.py:377-383 and the halt guard at api.py:31-66; the PR cites the correct (current) lines in its text, not the card's. A reader following the card's numbers lands a few lines off. [HIGH]
2. Docs that say "Declared" are only as good as what they leave out. The ALLOW row says the tool input is "never sent" to the sentinel; the sentinel does receive `context` with the tool NAME, event id, event type, MCP server name and session ids (core.py:629-642). The row's wording ("the tool's input (the command, path, URL or arguments) is never sent") is exact about the input; it does not list those context fields, which a reader might assume are also absent. LOW. [HIGH]
3. I verified by reading the code and by one running test that exists; I did not stand up an approver with a live Managed Agents session. [HIGH]

ASSUMPTIONS
1. main b1872ee (current main 7b54f26 is one PR ahead and touches none of this). PR: one commit, author and committer Don Hagell noreply, one file services/claude-approver/README.md, 2 insertions 1 deletion, merge-base b1872ee. [HIGH]

REASONING
1. Diff: the existing Declared row "The origin header is authentication" gains one sentence ("Only the origin header guards it (`api.py` `halt_open_paths` and the `halt` handler's `ORIGIN_HEADER` check; a marker any caller can send, not authentication)"), and a new Declared row "An ALLOW covers what the tool does". [HIGH, git diff]
2. ALLOW authorizes a tool NAME. `Approver._answer` takes `tool = _get(ev, "name")`, maps it with `config.resolve_action(tool, entry, tmap)` to an action string and calls `_check(entry, estate, action, context)` (core.py:~617-643). `_check` (core.py:372-383) builds `{"agent_id", "action", "token_id", "irreversible": False, "context": context}` and posts it to the sentinel's `/check`. The only call site of `_check` is that one; `irreversible` is the literal `False` there. [HIGH]
3. "The tool's input is never sent": `context` is built from `source`, `console_session_id`, `console_agent_id`, `tool_name`, `event_id`, `event_type`, and optionally `mcp_server_name` and `session_thread_id` (core.py:629-642). No field of the event's `input` is read anywhere in `core.py` (grep for `input` in the module finds none in the answer path). Correct. [HIGH]
4. "The sentinel's irreversible-action rule never fires from this service": in the sentinel, step 6 runs `if req.irreversible:` (conformance_sentinel/engine.py:571-581, `E.irreversible`), so a constant `false` can never reach it. [HIGH]
5. "An ALLOW for `bash` is an ALLOW for every command the session sends under that name": follows from 2 and 3 plus the existing row "A `bash` call is a classified action" (one scope string, "run commands in sandbox"). [HIGH]
6. `/halt` guard. api.py:31-40 `halt_open_paths()` returns `{"/halt/<id>"}` for every usable id in the agent map and is passed to `install_authn(app, open_paths=...)`, so the perimeter secret is NOT required on those paths; the handler (api.py:63-66) returns 403 unless `request.headers.get(ORIGIN_HEADER) == ORIGIN_VALUE` (`x-field-kill-origin: kill-switch`). The only check is a header any caller can send: "a marker, not authentication" is exact. The sentence about computing the paths at app start matches the docstring (api.py:32-37). [HIGH]
7. Running evidence: `test_halt_needs_the_origin_header` (tests/test_approver_api.py:112) and `test_perimeter_exempts_only_mapped_halt_paths` (:192) exist and pass in the full run. [HIGH]
8. Full CI-equivalent run on the exact head (gx10_verify.sh, no --quick, name lane5pr101): core_services 2181 passed 4 skipped; tools 1925 passed 3 skipped; agent-registry 238; sentinel 109; incident-replay 74; crosswalk 160 (1 skipped); gateway 208; lifecycle 185; attestation 66; ops-console 171; approver 101; field-agent 118; topology_lint OK. VERDICT CI-EQUIVALENT STEPS GREEN. A README-only diff; this shows nothing is broken, not that the text is true. [HIGH]
9. Public-repo hygiene: the added text names the service port in the compose network (`approver:8014`, already in the README), no address, secret or flag value. [HIGH]

CONCLUSION
PASS on 89122a7. Optional: in the ALLOW row, add "(its `context` carries the tool name, event id and type, MCP server name and session ids)" so the sentence is complete (objection 2).

What I did NOT do: run an approver against a live session; test a `/halt` with the perimeter secret armed (the repo test does).
