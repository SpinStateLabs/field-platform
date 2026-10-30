# C-529 (Lane 9, cloud-reviewer, read-only, no GX10): ADR Pack 02 (Conformance Sentinel) against services/conformance-sentinel/src, main a9dc4f3

VERDICT: of the 27 statements checked, 14 TRUE, 4 PARTLY TRUE, 4 NOT IN CODE (design not built or built elsewhere), 5 UNVERIFIABLE from the repository. The ADR header says "build shipped (deterministic core)"; the ADR 3 retrieval pipeline and the owner notification are not part of that core and are not in the source. No secret read or printed.

OBJECTIONS FIRST: (1) an ADR is a design record; a statement of intent is not a defect, but this one says "Authoritative design record ... build shipped", so a reader takes the whole text as built. (2) I read the source for each claim, I did not run the tests or the sentinel (no GX10). (3) The battery numbers (6.2, 6.3, 6.4, 3.5, 2.4, 8.1) refer to a function battery that is not in the repository as a named file; I matched them to tests by content, not by number. (4) Client-side claims (a caller failing closed when the sentinel is unreachable) live in other packages.

ASSUMPTIONS: main a9dc4f3; ADR file as on main (56 lines, already carrying the 2026-10-29 reviewer notes); "src" is services/conformance-sentinel/src/conformance_sentinel (2,065 lines).

STATEMENT TABLE (ADR line -> source)
TRUE
1. ADR 1: a deterministic engine is primary, the judge only for what rules cannot resolve: judge.py:1-5, engine.py:543-566 (judge consulted only when exact scope membership fails AND routing.py:needs_semantic_judgment fires). HIGH.
2. ADR 1: no training, no self-hosting: judge.py:126 `AnthropicJudgeClient` calls an upstream; no training code anywhere in src. HIGH.
3. ADR 1: judge stateless, version-pinned, recorded: judge.py:28-31 (`JUDGE_MODEL_DEFAULT`), engine.py:340-346 (model in the `sentinel.judge` ledger event), README:110. HIGH.
4. ADR 1: the deterministic engine has no vendor dependency: judge is imported by the engine only for `injection_screen` (engine.py:34); default judge off (judge.py:7, 188-198). HIGH.
5. ADR 2: output allow/block/escalate, each citing a clause: api.py:76-78, engine.py:3-4 ("every BLOCK / ESCALATE cites a clause id from field-core's CLAUSES"). HIGH.
6. ADR 2: structural violations hard-block; semantic fails to escalate; allow only on affirmative conformance: engine.py:472-641 (first failing clause decides; ALLOW only at :641 "all clauses satisfied"); judge failures/uncertainty ESCALATE D.semantic (:285-363). HIGH.
7. ADR 4: semantic path fails to escalate, never silent allow or block: judge.py:7-10, engine.py:285-332 (screen trip, upstream error, parse failure, unmetered, below floor all ESCALATE). HIGH.
8. ADR 4: injection screen runs before any judge call: engine.py:285-289 then the call; judge.py:54-68. HIGH.
9. ADR 4: confidence floor: engine.py:352-363, default 0.8 (:162, judge.py:200). HIGH.
10. ADR 4: one config flag reverts the estate to log-only: mode.py:3-8, api.py:76-84 (FIELD_SENTINEL_MODE; unset means log-only on a served estate). Note: a mistyped value now refuses to start (mode.py:35-47, C-169), which the ADR does not mention. HIGH.
11. ADR 4: the Sentinel cannot modify manifests or its own policy; read-only grounding: self_manifest.py:1-14 (no code path writes its own governance state); self_manifest.yaml scope read/evaluate/append/invoke only (lines 55-60). The route surface is GET /health, GET /clauses, POST /check (api.py:75-92). HIGH.
12. ADR 4: Founder & CTO is the named accountability owner in its own manifest: self_manifest.yaml:3-4, :24, :55. HIGH.
13. ADR 4: ledger-unreachable fails closed: engine.py:479 (L.unreachable BLOCK), api.py:25-52 (health gate: anything but a 200 with ok true and appendable true is False). In ENFORCE an allow whose record the ledger refused becomes BLOCK (engine.py:243-277). HIGH.
14. Gates / scorecard S2: 100 seeds = 40 violations + 53 conforming + 7 ambiguous; gated catch 40/40; structural false-block 0/53; combined false-block 0.1167 (7/60); mode log_only; engine commit d066218: docs/capstone-evidence/sentinel-scorecard-s2.json (scorecard.*). The reviewer note's statement that the scorecard's own gates are 95% and 2% is also TRUE (meta.gates). HIGH.
PARTLY TRUE
15. ADR 2: "Block halts pre-execution": the sentinel returns BLOCK to a caller that must honour it; nothing in the sentinel stops the action. In log-only (the served default) `/check` always returns ALLOW (mode.py:3-5). The ADR's "Block halts" is true for a cooperating enforcement point in enforce mode only. MEDIUM.
16. ADR 4: "every block and escalation is ledgered": engine.py:243-262 says BLOCK/ESCALATE records are best-effort (`except` path), "a block that cannot be recorded is still a block". Ledgered when the ledger takes it; silently not when it does not. MEDIUM.
17. ADR 1: "provider abstraction": judge.py has a mock and one real client behind `resolve_judge` (:188), so the seam exists; there is one provider. MEDIUM.
18. ADR 4: "screen ... confidence floor ... auto-escalates": the screen and floor escalate (rows 7-9), but a judge that says non-conforming at or above the floor BLOCKs D.scope (engine.py:354-358); it does not escalate. MEDIUM.
NOT IN CODE
19. ADR 2/4: "Block ... notifies the owner"; "escalate ... auto-escalates to the named owner": a grep of src for notify, owner routing or alerting finds nothing. A block or escalation is a verdict plus a ledger record (engine.py:240-262). Any notification would be outside this service. HIGH (grep, read).
20. ADR 4: "structural/semantic disagreement auto-escalates": there is no disagreement check. When the judge affirms conformance at the floor after an exact-scope miss, the engine continues ("remaining checks still run", engine.py:549-553) and can ALLOW; no escalation. HIGH (read).
21. ADR 3 as a whole: retrieval over manifests with clause-level chunking, one index per tenant (isolation "a tested property"), re-ranking by action type, a short prompt, "re-index-on-merge": no retrieval, index, chunking, ranking or tenant code in src (grep: retriev, index, chunk, rerank, embedding, tenant: no match). What exists is a per-agent manifest lookup (`ManifestResolver`) and exact scope lists. HIGH. The "tenant isolation tests" are not in services/conformance-sentinel/tests (13 files, none about tenants).
22. ADR 1: "golden-set regression on swap": no golden set or swap test in the sentinel's tests; judge.py:16-18 and README:110 say quality is Declared, not Enforced, until live golden-set evals run. HIGH.
UNVERIFIABLE FROM THE REPOSITORY
23. "136 live verdicts, 73 allow / 63 block, 0 false blocks; blocks = 1 + 57 + 2 + 2 ... fail-closed 9.5 days": the live ledger is not in the repository; the 2026-10-29 reviewer note already shows the block parts sum to 62, not 63. Still unresolved.
24. "Kill drill: 20.45 ms kill, 22.41 ms heartbeat": no artifact in docs/capstone-evidence that holds these. I did not find the source.
25. "Function battery 52/52 PASS" and the case numbers 6.2, 6.3, 6.4, 3.5, 2.4, 8.1: matched by content to test_self_manifest.py, test_judge.py, test_fail_closed_pins_c168.py and test_f2_fail_closed.py, not by number. I did not run them.
26. "$0.34 ledgered over 21 days (~195 verdicts/month)", "s ≈ 15%", "~1,700 tokens/judgment": the scorecard's routing_coverage is 0.15 (15 of 100 seeds routed), which may be the source of 15%; the rest has no artifact.
27. "client-engagement onboarding 2026-09-08 ... skill-agent perimeter honestly documented as cooperative": a statement about the estate; not checkable from source. Contains nothing that reads as a deploy status beyond a date; flag for the coordinator's public-safety call (C-540).

FINDINGS (for cards)
- F-C529-1 MEDIUM (doc): ADR 3 describes a retrieval pipeline that is not built; the header says build shipped. Add a dated note like the C-203 notes (state: not built, the deterministic core uses per-agent manifest lookup) or move ADR 3 to "planned".
- F-C529-2 MEDIUM-LOW (doc): the owner-notification and "structural/semantic disagreement auto-escalates" statements (rows 19, 20) are not in the code; the second is a real behaviour difference (a judge affirmation after a structural miss can ALLOW).
- F-C529-3 LOW (doc): "Block halts pre-execution" and "every block and escalation is ledgered" need the two qualifiers of rows 15 and 16 (cooperating enforcement point in enforce mode; ledger write best-effort).
- F-C529-4 LOW: rows 23, 24, 26 carry figures with no artifact in the repository; label as "owner-reported, not reproducible from the repository" or add the artifact.

CONCLUSION: the sentinel code matches the ADR on the deterministic core, the fail-to-escalate judge, the log-only flag, the self-governance and the scorecard figures (14 of 27 TRUE, HIGH); it does not contain the ADR 3 pipeline, the owner notification or the disagreement escalation (HIGH, by read and grep). Confidence: HIGH for rows 1-14 and 19-22, MEDIUM for 15-18, "I do not know" for 23-27.
