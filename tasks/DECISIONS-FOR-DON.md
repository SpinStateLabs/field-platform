# DECISIONS-FOR-DON

Don's standing words: "use your recommendations". Entries are PROVISIONAL until Don rules.

## D-1 Integration branch = `main` (2026-10-28, HIGH)
Choice: `main` (the brief left it as a placeholder; HEAD equals origin/main c8ecba7). Alternative: another branch. Reversal: none needed unless Don names another.

## D-2 Coordinator ruling (2026-10-28)
Don: "I coordinate". This session (c6f632) is the field-platform coordinator. Sessions "Force-Field coordinator takeover" and "handoff" run in the Agentic AI and LLMOps at Scale worktrees (another repo, MEDIUM) and verify only.

## D-3 Teammates (2026-10-28, PROVISIONAL, MEDIUM)
Choice (Don, 2026-10-28): reviewers = "FIELD platform adversarial review" (86dc6f) and "Teammate reviewer onboarding" (not in ListAgents, unreachable by me). Builder = "Work queue review" (f77070) until Don names another. Reversal: re-message.

## D-4 Draft PRs #55 #56 #57 stay draft until verified (2026-10-28, HIGH)
Choice: no merge without reviewer PASS plus GX10 run on exact head. Alternative: merge on CI green. Reversal: n/a.

## D-5 #57 persistent post-PROMOTE fault (reviewer Decision C) (2026-10-28, PROVISIONAL, MEDIUM)
Choice: retry cap plus CRITICAL alert before any live use. Alternative: retry forever with hourly keyrotation.failed. Reversal: drop the cap commit (C-15 separate commit).

## D-6 #57 abort refusals halt until R9 acts (reviewer Decision D) (2026-10-28, OPEN, LOW confidence)
Conflicts with P36 unless R9 reconciles automatically. I do not know P36's text. Default: keep halting (fail closed) until Don rules.

## D-7 Cloud reviewer (2026-10-28, PROVISIONAL, HIGH)
Don: "Teammate reviewer onboarding" is a cloud session. Choice: it takes read-only card C-18 from origin/comms (I cannot message cloud sessions); its output is UNVERIFIED until re-run on the GX10. Alternative: bind a local reviewer. Reversal: reassign C-18.

## D-8 Don: "go with recommendations" (2026-10-28)
D-5 (retry cap plus CRITICAL alert) confirmed. D-6 (keep halting, fail closed) confirmed pending a P36 reading.

## D-6 update (2026-10-28, from reviewer C-22, MEDIUM)
P36 (controller project, tasks/DECISIONS-FOR-DON.md:317-321) covers stage gates and alerts, not the rotator: no literal conflict. Your 2026-10-27 ruling "key rotation is continuous machine work" does conflict with "halts until a human acts". Provisional: R9 reconciles automatically where state is provable, halts plus CRITICAL alert only where not (C-29). Until then no live use of the rotator.

## D-9 Unpushed t1 commit recommitted (2026-10-28, HIGH)
Local teammate-don/t1-renew-token-signed (D:/claude-tmp/td-t1) had author donhagell@gmail.com and an empty committer email. Worktree untouched; same tree recommitted as fix/renew-token-signed @8269445 with the repo identity, pushed. Reversal: delete the remote branch.

## D-10 renew_token exit status on a dropped ledger append (2026-10-28, PROVISIONAL, MEDIUM)
Choice: keep exit 0 (unchanged policy; reported in log). Alternative: distinct non-zero exit or the ntfy class from #56, so an unattended renewal with an expired caller key is not silent (reviewer C-19 condition 3). Reversal: add the exit code in a follow-up commit.

## D-11 GB10 catch-up deploy order (2026-10-28, PROVISIONAL, MEDIUM)
Reviewer C-34 found two MEDIUM issues in merged R1/R2 code (break-glass row not forced sealed; observer blind to content-only edits). Choice: no deploy of c8ecba7 to GB10 until C-35 and C-36 land, in any case only with your explicit approval. Alternative: deploy now, fix forward (the operators file is hand-written and root-owned, so exposure needs write access). Reversal: approve a deploy.

## D-12 Perimeter secret is the only control on direct internal-route calls (2026-10-28, OPEN for Don, MEDIUM)
Reviewer C-48: on the compose network the Caddy block is not in the path; canary-agent holds the estate-wide secret and reaches ledger, delegation, killswitch and governor directly. Question: are a separate internal secret (mitigation 2) and per-agent secrets (1) Phase G Stage 2 prerequisites? Provisional: yes for 2 (cheap, default-off compatible, plan is C-54), 1 and 3 await your ruling. Alternative: accept the perimeter secret plus network position until after Stage 2. Reversal: drop C-54.

## D-13 Environment-proxy exposure of secret-bearing HTTP calls (2026-10-28, PROVISIONAL, MEDIUM)
Reviewer C-55: 59 httpx sites plus FieldClient send x-field-auth and the operator key without trust_env=False; a proxy variable on a host or container would receive them in clear (http) . Coordinator read-only check on the GX10 (2026-10-28): no ~/.docker/config.json, no proxy variables in the host environment, none in any running container (MEDIUM: docker exec errors were ignored; Fly and rog-command not checked, I do not know). So not exploitable on the GB10 today. Choice: fix by one shared client constructor (C-56 plan, C-57 lint) rather than 59 ad hoc edits; no deploy urgency. Alternative: set NO_PROXY in compose only. Reversal: drop C-56/C-57.

## D-14 C-7 triage reassigned to the reviewer (2026-10-28, PROVISIONAL, HIGH)
Builder silent for about 3h, reviewer already triaged 4 branches and found each squash-merged. Reversal: hand C-7/C-61 back.

## D-15 Delete 49 stale remote branches (2026-10-28, OPEN for Don, HIGH on evidence)
46 squash-merged (PR tip equals branch tip) plus 3 closed-superseded (reviewer C-61, C-62). Script: comms/inbox/coordinator/20261028-1530-reviewer-c63-delete-branches.sh (dry-run default, deletes only if the remote tip still equals the recorded sha, protects main, comms, #55, #56, #57, fix/renew-token-signed). Coordinator dry run: 49 DRY, 0 moved. Recovery: git push origin <sha>:refs/heads/<branch>. Reviewer suggests archive tags first for pg-s0-guards (MEDIUM). Several local worktrees on this machine sit on some of these branch names (deploy-4194af3, ff-deploy-0ca1d78, fp-caddy); remote deletion does not touch them. Choice: approve, run with DRY=0 after tagging pg-s0-guards. Alternative: leave them.

## D-15 RESULT (2026-10-28, Don approved in chat)
Tag archive/pg-s0-guards pushed at a15e893. C-63 script run with DRY=0: deleted=49 skipped=0 (none moved, none refused). Remote heads now 12: main, comms, feat/machine-verifier-identity, feat/alerts-ntfy, feat/kr-r4a-rotator-core, fix/renew-token-signed and the others the script did not list. Recovery: git push origin <sha>:refs/heads/<branch> (shas in the script). Local worktrees untouched.

## D-16 Second branch delete, six more (2026-10-28, OPEN for Don, HIGH on evidence)
Reviewer C-74: ci/harden-workflows-2026-10-23 (#16), ci/topology-lint-2026-10-23 (#18), feat/phase-g-check-tool (#28), feat/claude-approver-v0 (#35) squash-merged, tips equal PR heads; claude/field-gate-v1-1-integration-7u50hv (#1 merged) and claude/state-field-gate-1-1-0 (ancestor of main, 0 ahead). Script: comms/inbox/coordinator/20261028-1815-reviewer-c74-delete-branches-2.sh, dry-run default, sha-checked, protects the live branches. Needs your approval again; approval for D-15 does not carry over.

## D-9 objection (reviewer C-71, 2026-10-28)
Recommitting the t1 tree under Don Hagell makes agent-written code look personally authored; the repo rule is the committer identity, but for an attribution product the trailer Co-Authored-By is the only trace. Provisional: keep, since every commit carries the Co-Authored-By trailer. Your call whether commits should carry a distinct agent identity instead.

## D-17 ANTHROPIC_BASE_URL over plain http (2026-10-29, PROVISIONAL, MEDIUM)
Reviewer C-58 asked to require https. Existing test test_fourth_reader_real_upstream_ignores_force_gateway_url documents http://proxy.example.test:9000 as an allowed base, so enforcing https would break a documented configuration. Choice (PR 69): log one WARNING (host only) when the key goes over http to a non-private host, scrub the key from replies, keep the behaviour. Alternative: refuse non-https non-private bases. Reversal: a one-line raise in _base_url_warning plus changing that test. Your call.

D-17 update (2026-10-29): reviewer C-104: warn is acceptable; recommends log once per process plus an opt-in FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM=1 refusal (your roadmap choice, default off); card C-112.

## D-18 C-2 condition 1: a verifier-scoped row without the svc-verifier- prefix is an ordinary, unbound row (2026-10-29, OPEN for Don, MEDIUM)
Reviewer C-109 (probe on r2): validate_rows accepts svc-verify-gb10, verifier-gb10, SVC-VERIFIER-gb10 each holding kill, revive, mint_for_others, revoke; list-binding exists only for the exact prefix. The #55 author tested the unprefixed case on purpose ("only narrows"). Options: (a) accept and document: the live operators file is hand-written, root-owned, and Don names the verifier row; add a pre-check line to the runbook (provisional default, no code); (b) refuse in the parser a row holding the verifier scope set (kill, revive, mint, revoke, no mint_for_others, no bypass_operator_list, no "*") whose id lacks the prefix; (c) make list-binding a format-2 row attribute. Merge of PR 71 does not depend on this if you pick (a). Your call.

## D-19 federation-broker authentication and replay (2026-10-29, OPEN for Don, MEDIUM)
Reviewer R-09 (inbound decision path, engine.py:407-488): (1) a contract with no counterparty key authenticates nothing: any caller that names the org and presents a valid manifest with the peer listed gets ALLOW; (2) nothing binds a (manifest, signature) pair to a request or a time, so a captured pair is valid forever. Impact depends on what a caller does with ALLOW (unknown to me). Provisional: no code change; card C-126 asks the reviewer to read the downstream use and propose the smallest control (refuse keyless contracts unless marked unauthenticated; a nonce or timestamp). Your call whether keyless contracts are allowed at all.
