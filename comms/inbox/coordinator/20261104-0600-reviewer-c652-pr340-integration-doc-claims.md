VERDICT: PASS WITH CONDITIONS on 1643d20a1fe304750d3cc67e90d83d4d66ac3687 (UNVERIFIED: cloud reviewer, docs read against source at that head; no run, no CI read)

Head matches the card. One commit on main 5808a5c; author and committer are the no-reply identity. One file: docs/INTEGRATION.md, +22 -8. No code changed.

OBJECTIONS FIRST
1. The gateway enforce paragraph cites the module docstring (services/force-gateway/src/force_gateway/api.py:24-40), not the code that enforces. The docstring is right today, but a docstring can drift from code; the code is the handler (api.py:887-899) and _authorize (api.py:555-587).
2. "403 ... body {decision, clause_id, reasons}" is a subset. The code body also carries agent_id and action, an ESCALATE adds a sentence to reasons as well as escalation: true, and a refusal may add retry_after_seconds (api.py:570-584). A reader writing a client against the doc will not expect the extra fields.
3. "503 (the sentinel unreachable, timed out or non-200, or FIELD_SENTINEL_URL unset)" omits two cases the code also refuses 503: a non-JSON body and a body with no verdict (api.py:352-360).
4. "a gateway without ANTHROPIC_API_KEY answers POST /v1/messages with 502" is true only for the real upstream; with the mock upstream switched on (FORCE_GATEWAY_MOCK=1) there is no such answer (api.py:197-202, resolve_upstream). The PR removed the estate wording but made a universal statement.
5. The pre-v1.2 kill-switch claim ("the POST's 405 raises HeartbeatUnreachable") is a claim about an OLDER version's route. field-agent raises HeartbeatUnreachable on any non-200 (packages/field-agent/src/field_agent/liveness.py:60-65) but that an old kill-switch answers 405 is not in the source at this head. 
6. Untouched lines in the same file still carry deploy-flavoured text: line 103-104 ("On the GB10 from v1.2 Phase C that directory is the read-only field-manifests volume") and a real person's name and company in the roster example (line 89). Not in this diff; the card asks for deploy status, so named.

ASSUMPTIONS
A1 Source of truth is the repository at the PR head (5808a5c plus this one commit); no deployed instance consulted. A2 "Estate address, flag value, build SHA, deploy status, credential" judged from the diff and the whole file by pattern; no address-shaped string, SHA or credential found in the diff. A3 Line numbers from `git show` of the PR head.

REASONING (claim by claim, source at file:line)
1. "FIELD_DOA_ROSTER unset: gate off, mint behaves as before v1.2; once set, enforced fail-closed": services/delegation-authority/src/delegation_authority/api.py:192-201 (roster_path(); unreadable roster raises 503 "refusing to mint"; doa_checked set only when a roster is configured; api.py:11 says unset behaves exactly as before, recorded doa_checked false). Variable name at doa.py:40. HIGH.
2. "a value that is neither log_only nor enforce makes the sentinel refuse to start": mode.py:34-49 raises InvalidSentinelMode for any other non-blank value; blank means log_only. Cited range 34-47 stops one line before the end of the raise statement (47-49): trivial. That it makes the SERVICE refuse to start depends on the caller of resolve_mode not catching it; I did not read the caller. MEDIUM.
3. "502 naming the key" api.py:196-203: confirmed, with objection 4.
4. "requires x-field-agent-id and x-field-token; 401 naming both" api.py:887-893; both header names come from field_core.llm (api.py:72). HIGH. "reads x-field-action (default llm.messages)": api.py:896, EGRESS_ACTION. Default string value not read at its definition: MEDIUM.
5. "asks the sentinel; 403 on BLOCK; 403 with escalation true on ESCALATE": api.py:570-586. HIGH (objection 2 on the body).
6. "503 unreachable/timed out/non-200/URL unset; no upstream call in any of them": api.py:555-565 and 352-360; the check runs before the upstream call (api.py:887-900). HIGH.
7. Claims that the gateway meters "except: pass" in the table line were not changed by the PR; not reviewed.
8. Deleting "~30s" from the demo run line removes an unsourced timing; neutral.
9. Estate statements removed: the two "both estates run pre-v1.2 images" and "placing it on the estates is Don's step" lines are gone; "estate" remains as a generic word only (e.g. line 153). The diff adds no address, flag value, build SHA, deploy status or credential. HIGH for the diff.

CONCLUSION
PASS WITH CONDITIONS. The new text matches source at the cited places; no deploy state or estate value was added; the removals are correct. Conditions, none blocking merge:
- C1 F-C652-1/-2/-3 doc precision (cite the handler lines; list the extra response fields; list all 503 causes).
- C2 F-C652-4 add "with the real upstream" to the 502 sentence.
- C3 F-C652-5 reword the pre-v1.2 claim to what the SDK does (any non-200 halts) or source the 405.
- C4 F-C652-6 separate card for lines 89 and 103-104 (outside this diff).

FINDINGS
F-C652-1 LOW, docs/INTEGRATION.md (the new enforce paragraph, ~lines 201-210), cites api.py:24-40 docstring instead of code (api.py:555-587, 887-899). HIGH.
F-C652-2 LOW, same paragraph, 403 body listing incomplete (api.py:570-584). HIGH.
F-C652-3 LOW, same paragraph, 503 causes incomplete (api.py:352-360). HIGH.
F-C652-4 LOW, docs/INTEGRATION.md ~line 186-187, the 502 holds only for the real upstream (api.py:197-202). HIGH.
F-C652-5 LOW-MEDIUM, docs/INTEGRATION.md ~line 222, 405 from an older kill-switch not in source at this head. MEDIUM.
F-C652-6 LOW, docs/INTEGRATION.md:89 (named person and company in a public example) and :103-104 (deploy-flavoured sentence), outside this diff. HIGH that they exist.

NOT VERIFIED: that the sentinel refuses to start (caller of resolve_mode); EGRESS_ACTION literal; kill-switch route set of older versions; rendering of the doc; CI; any deployed behaviour.
