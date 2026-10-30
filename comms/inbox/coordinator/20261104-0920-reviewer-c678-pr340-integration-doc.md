VERDICT: PASS WITH CONDITIONS on 1643d20a1fe304750d3cc67e90d83d4d66ac3687
(Lane 14, cloud, no GX10: UNVERIFIED re-run, docs read against source, nothing executed; CI not read. The PR tip is now 1484aac082305905a77e95c3a8deb7c4b25930df (one more docs commit, 5 lines); I read that delta too and it holds, but this PASS names the card head 1643d20. Both commits: author and committer Don Hagell no-reply. One file, docs/INTEGRATION.md. The service source named below is identical on main and at 1643d20 (no diff in the three services). Independent read: Lane 10 (C-621) and the C-652 reader reached PASS / PASS WITH CONDITIONS on the same head; I re-derived every claim, I did not copy theirs.)

OBJECTIONS FIRST
1. A doc that cites `file:line` is wrong the day the file moves; the PR pins no commit, and a doc about enforcement is read as a contract.
2. "Design facts, not estate deploy state" is the PR's claim; the file still has estate wording outside the diff (below), so the claim is true of the lines changed, not of the file.
3. "Requires x-field-agent-id and x-field-token" omits the self-manifest judge exemption, which could read as a bypass; I checked it is not one for identity.
4. Fail-closed prose invites readers to assume the sentinel is up; a 503 on every call when the sentinel is down is a total LLM outage, and the doc does not say how an operator tells "denied" from "down".

ASSUMPTIONS
A1. "Source" means services/*/src at 1643d20; main is identical for those services. A2. No run: ordering claims (no upstream call) read from the handler body, not exercised. A3. Public repo: no value of any kind quoted here.

REASONING (claim, then the line read)
1. `FIELD_DOA_ROSTER` unset = gate off, claim Declared until set, enforced fail-closed once set. doa.py:40 (ROSTER_ENV), doa.py:15 (fail-closed rule, "ENFORCED"), delegation_authority/api.py:10 ("unset is today's" behaviour). HIGH.
2. A value that is not log_only or enforce makes the sentinel refuse to start. mode.py:34-47 raises InvalidSentinelMode; conformance_sentinel/api.py:74 calls resolve_mode() inside create_app; cli.py:210-216 catches it, prints one line, exits 2, binds nothing. HIGH for the CLI serve path, MEDIUM for any other launcher (the error is raised at app construction). Tip delta: accepted spellings log_only, logonly, enforce, enforcing, enforced; case-insensitive; "-" read as "_"; blank or unset = log-only. mode.py:40-45 matches every word. HIGH.
3. A gateway without ANTHROPIC_API_KEY answers 502 naming the key. force_gateway/api.py:196-202. HIGH; true only on the real-upstream path, not with the mock (F-C678-2).
4. Enforce contract. api.py:24-40 (docstring) and the handler api.py:874-897 read together: with enforce on, missing either header raises 401 whose text names both header names; action = x-field-action stripped, else "llm.messages"; _authorize decides before the passthrough, bypass and upstream branches, so 401/403/503 make no upstream call (the upstream is first called at api.py:915 and later). BLOCK = 403 {decision, clause_id, reasons}; ESCALATE adds escalation: true; sentinel unreachable / timeout / non-200 / FIELD_SENTINEL_URL unset = 503. All match the doc sentence. HIGH.
5. Judge exemption (objection 3): api.py:41-43 and :266-268, handler :908-910: under enforce the x-force-passthrough exemption applies only to three self-manifest ids and only to instrumentation; the identity check above it applies to them too. The doc is not wrong; it is incomplete (F-C678-3).
6. Removed text: "Both estates run pre-v1.2 images with the variable unset ... until Don deploys", "an estate gateway", "pre-v1.2 estate", "(~30s)". All were deploy-state or timing statements; their removal is correct.
7. Public repo scan of the whole file at the tip (283 lines): no address except loopback defaults in a table (lines 32-35, 127.0.0.1 and port numbers, design defaults), no build SHA, no flag value, no credential. Outside the diff, lines 102-105 say "On the GB10 from v1.2 Phase C that directory is the read-only field-manifests volume": that names the estate host class and a deployment fact, which is deploy-state wording (F-C678-1). Line 153 "safe-by-default estates behave this way" and line 274 "a secret estate" are generic. 
8. Mutants: none apply (docs only; no test pins the prose). Probe equivalent: every cited line number opened and read at 1643d20.

FINDINGS
F-C678-1 (LOW-MEDIUM, non-blocking): docs/INTEGRATION.md:102-105, outside this diff. "On the GB10 from v1.2 Phase C that directory is the read-only ... volume" states how one estate is deployed, which is the class the PR title says it removes. Reword to a design statement ("the shipped compose overlay mounts it read-only") if that is what the overlay does (I did not check the overlay). Confidence MEDIUM.
F-C678-2 (LOW): the 502 sentence (cite api.py:196-202) holds only when the real upstream is selected; with the mock upstream the key is never read. Add "with the real upstream". HIGH.
F-C678-3 (LOW): the enforce paragraph does not mention that the three self-manifest agents keep an instrumentation-only passthrough exemption (api.py:41-43); say it holds for instrumentation only, identity still checked. HIGH.
F-C678-4 (LOW): no commit is pinned for the file:line citations; they are exact today because the three services are unchanged on main since the base. 
F-C678-5 (LOW, code not doc): api.py:889 `not x_field_agent_id or not x_field_token` treats a whitespace-only value as present; the doc's "requires" is then read loosely. A transport usually trims header values; not run. Worth a one-line test, not a doc change. MEDIUM-LOW.
No claim in the doc exceeds what the code enforces: none found.

CONDITIONS
C1 (non-blocking): F-C678-1 reword before the doc is used as a public statement of what is deployed.
C2 (non-blocking): F-C678-2/-3 wording.
Not verified: CI at 1643d20 and at 1484aac; the compose overlay behind F-C678-1; full GX10 suites (docs only, none affected); runtime behaviour of any claim (nothing executed).

CONCLUSION
Every behavioural claim the PR adds or changes matches the source at the lines it cites, including the full 401/403/503 contract and the no-upstream-call ordering; the removed text was deploy-state. One pre-existing estate-deployment sentence outside the diff keeps "design facts, not deploy state" from being true of the whole file (F-C678-1). PASS WITH CONDITIONS (non-blocking) on 1643d20; the tip 1484aac delta (accepted spellings) also verified against mode.py:40-45.
