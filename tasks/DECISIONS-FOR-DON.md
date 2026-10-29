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

## D-19 update (2026-10-29, reviewer C-126, MEDIUM): federation-broker
Today the broker ALLOW is ADVISORY: the only consumer is the field-agent SDK (federation.py), which asks and never relays; nothing issues a token or credential from it. So both findings have LOW present impact; they matter the day an ALLOW gates a real transfer or credential. Whether a live estate holds a keyless contract: not in source, unknown. Recommendations: (1) F-R09-1: in _decide_inbound, BLOCK when the contract has no counterparty key ("inbound crossings require a contract key"), keyless stays valid OUTBOUND; ~6 lines plus tests; the demo (demo.sh:79 registers FED-2026-001 keyless) gains a keygen and sign step; a live keyless contract would start BLOCKing inbound (fail closed). Alternative: an explicit contract field allow_unsigned_inbound, default False. (2) F-R09-2: no code now; add a README Enforced-vs-Declared row (the signature proves the manifests origin, not freshness or the presenter), build signed nonce and issued_at plus a seen-nonce table only when an ALLOW gates a real action. (3) F-R09-3: keep the substring peer rule (a self-declared listing gains nothing from exact match; a test pins the leniency). My provisional default: do (2) the doc row now (card C-129, docs only), hold (1) for your ruling. Your call.

## D-20 defence-shield allowlist can silence the alert exit code (2026-10-29, OPEN for Don, MEDIUM)
Reviewer C-141 F-C141-5: `--allow-ip 0.0.0.0/0` marks every session AUTHORIZED, and `scan` exits 2 only on ESCALATE, so the scheduled alert goes quiet while the report still lists the sessions with `authorized_by`. README says "listed, never suppressed", true of the pack, not of the exit status. Provisional: no code change; C-148 pins the matching behaviour; Choice for you: refuse a catch-all (/0) allowlist, or keep it and exit with a distinct code when anything was allowlisted. Alternative: accept as documented.

## D-21 GB10 restart without its .env starts open (2026-10-29, OPEN for Don, MEDIUM)
Reviewer C-142 item 6: committed compose defaults `FIELD_SHARED_SECRET`, `FIELD_OPERATOR_REQUIRE`, `FIELD_LEDGER_REQUIRE_SIGNING`, `FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE`, `FORCE_GATEWAY_ENFORCE` to empty or 0 (demo mode), so a `docker compose up` on the GB10 without its `.env` starts every service open, silently. Provisional: no change (the demo topology needs the defaults; the topology lint covers deployed estates). Options: (a) accept; (b) a GB10 override file that makes these variables required (`${VAR:?}`) so a missing `.env` aborts the start. Not verified: whether the live GB10 estate runs from a `.env` (I do not know). Your call.

## D-22 A retired agent can be reactivated by PATCH while the operator layer is OFF (2026-10-29, OPEN for Don, MEDIUM; behaviour PROVEN by reviewer C-155)
agent-registry `update_agent` enforces "a decommission is terminal" only when the operator layer is not OFF. With OFF (reviewer: the state of every estate today), `PATCH status=retired` then `PATCH status=active` returns 200 both times, and then `killed` 200. The kill-switch refuses retired -> killed and the drill refuses retired agents (R-11), so the registry PATCH is the way around them; the kill-switch README calls the rule an integrity rule for every identity. The registry's OFF mode is documented as byte-identical to before Phase G, which may be why the guard sits inside the mode check. Provisional (card C-161): apply the 409 in every mode (fail closed; an integrity rule, not an identity decision); update the OFF byte-identity wording. Alternative: keep the exception and document it in both READMEs. Impact: whether any live process reactivates a retired agent: I do not know. Your call.

## D-22 RESULT (2026-10-29, Don ruled in chat: "Yes, every mode")
The retired-is-terminal 409 applies in every operator mode, OFF included (fail closed). Card C-161 is confirmed, no longer provisional. Reversal: drop the C-161 commit.

## D-23 An unrecognised FIELD_SENTINEL_MODE silently disables enforcement (2026-10-29, PROVISIONAL, MEDIUM)
Reviewer C-157 F-C157-3: mode.py resolve_mode maps every unrecognised non-empty value (typo `enfroce`, `on`, `1`, `true`, `off`) to log-only, where every /check returns ALLOW and the would-be verdict is only shadow-ledgered. Deployed descriptors default to enforce (gb10 compose :412, fly entrypoint :110, fly.toml :39, demo compose :100), so a typo in an estate .env turns enforcement off without an error; /health shows the mode. Provisional (card C-169): refuse to start on an unrecognised non-empty value; empty or unset keeps the default. Alternative: keep today's behaviour and log a loud warning. Reversal: drop the C-169 commit. Safe-by-default log-only is a documented choice, so this is yours to confirm.

## D-22 merged (2026-10-29)
PR 91 on main 7b4d6f7. Residual: check-then-write race and no store-level rule (card C-167). Runbook docs/runbooks/v1.2-deploy-rollback.md:1774 already says retired -> active is refused; true in every mode now.

## Rulings 2026-10-29 (Don, answered the coordinator's four questions in chat)
- D-16 RESULT: approved. C-74 script run with DRY=0 after a clean dry run: deleted=6 skipped=0 (ci/harden-workflows-2026-10-23, ci/topology-lint-2026-10-23, feat/phase-g-check-tool, feat/claude-approver-v0, claude/field-gate-v1-1-integration-7u50hv, claude/state-field-gate-1-1-0). Recovery: git push origin <sha>:refs/heads/<branch> (shas in the script). Many merged `-r2`, batch and fix branches remain: card C-174 asks the reviewer for a third delete list (needs your approval again before it runs).
- D-23 RULED: refuse to start on an unrecognised non-empty FIELD_SENTINEL_MODE (card C-169 confirmed, no longer provisional).
- D-19 RULED: block keyless contracts inbound, keyless stays valid outbound (F-R09-1; card C-175). The README Declared row (C-129) stays.
- D-18 RULED: accept and document (option a): no parser change; card C-176 adds the runbook pre-check line.

## D-24 Same rule as D-23 for the force-gateway posture flags (2026-10-29, PROVISIONAL, MEDIUM)
Reviewer C-170 F-C170-1: FORCE_GATEWAY_ENFORCE, FORCE_GATEWAY_TOOL_CHECK and FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM are exact-match `== "1"`; any typo or spelling such as `true`, `yes`, `on`, `enforce` leaves the gateway an observer (or lets the API key travel over plain http with only a warning). You ruled D-23 (refuse to start on an unrecognised sentinel mode). Provisional (card C-180): apply the same rule here, with `1/true/yes/on` and `0/false/no/off` recognised and an unrecognised non-empty value refusing to start; FORCE_GATEWAY_MOCK stays exact-match. Alternative: keep exact-match and document the spelling. Reversal: drop the C-180 commit. Confirm or change.

## D-25 Third branch delete, 38 heads (2026-10-29, OPEN for Don, HIGH on evidence)
Reviewer C-174: 18 heads are ancestors of main (batch a/b, merged -r2 heads, merged originals), 19 have a closed PR superseded by a merged successor (11 merged -r2 PRs, 8 content merged through batch A/B by patch-id), 1 has no PR but adds the same 81-line file as main 0b44dee. Script comms/inbox/coordinator/20261029-2700-reviewer-c174-delete-branches-3.sh: dry-run default, each branch deleted only if its tip still equals the recorded sha, main/comms/open-PR heads refused, recovery `git push origin <sha>:refs/heads/<branch>` (and refs/pull/<n>/head stays on GitHub). Coordinator dry run: 38 DRY, 0 skipped. Needs your approval; earlier approvals do not carry over.

## D-26 `ledger verify --anchors` answers OK for a missing or empty anchors file (2026-10-29, PROVISIONAL, MEDIUM; behaviour PROVEN by reviewer C-186)
A mistyped or deleted anchors path verifies as "OK - 0 anchor(s) hold", exit 0 (anchors.py:95, cli.py:415-428), although anchors exist to defeat a full-history rewrite. witness.py already refuses "nothing witnessed". Provisional (card C-192): when `--anchors` is given, a missing, unreadable or empty file fails with a non-zero exit and a clear message; without `--anchors` nothing changes. Impact on live use: any script that passes `--anchors` to a file that may legitimately not exist yet would start failing (I do not know of one). Alternative: keep OK but print a loud NOTE. Reversal: drop the C-192 commit. Confirm or change.

## D-27 Cleartext rule for the platform's LLM callers (2026-10-29, PROVISIONAL, MEDIUM; PR 96 / C-117)
Reviewer C-187 proved the three platform callers send the Anthropic key, the perimeter secret and the token id in clear when FORCE_GATEWAY_URL is plain http, and honour HTTP(S)_PROXY. PR 96 makes ONE client constructor: trust_env=False always; a plain-http FORCE_GATEWAY_URL outside the estate is refused (allowed: https, loopback, private or link-local IP, localhost, a single-label compose name such as `forcegw`, `.internal`, `.local`); a plain-http ANTHROPIC_BASE_URL stays allowed with one warning (your D-17), refused only on FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM=1. The allow-list is my design: a single-label name is treated as internal because the compose files use `forcegw`, which an https-only rule would break. Alternative: https-only for the gateway URL and change the compose files. Reversal: drop the PR 96 commit. Confirm or change.

## D-25 RESULT (2026-10-29, Don approved in chat)
C-174 script run with DRY=0 after a clean dry run: deleted=38 skipped=0 (none moved, none refused). Remote heads now: main, comms, the open-PR branches and a few merged originals the script did not list (fix/operators-loader-c178, fix/operators-loader-c178-r2, fix/operators-readers-c182, fix/registry-retired-store-guard-c167, test/incident-replay-pins-c137, fix/renew-token-signed). Recovery: git push origin <sha>:refs/heads/<branch> (shas in the script); each merged or closed PR head also stays at refs/pull/<n>/head on GitHub.

## Rulings 2026-10-29 (Don, interview answers)
- D-26: `ledger verify --anchors` fails on a missing, unreadable or empty anchors file (card C-192 confirmed).
- D-27: the cleartext allow-list for the platform LLM callers is confirmed as built in PR 96.
- C-189: read-only estate checks allowed and done; the resulting table is NOT published (open question to Don: the repo is public).

## D-28 Container hardening: stage 1 now, non-root USER as a separate migration (2026-10-29, PROVISIONAL, MEDIUM; PR 108 / C-151)
Reviewer C-142 F-C142-1: containers run as root with a writable root filesystem. Builder Lane 3's PR 108 does stage 1 only in integration/demo/docker-compose.yml (no-new-privileges, cap_drop ALL with DAC_READ_SEARCH added back, read_only with a /tmp tmpfs; the proxy no-new-privileges and cap_drop ALL). A non-root USER is NOT in it: the existing data volumes are root-owned, so it is a migration (a chown job per volume). Provisional: merge stage 1 after the reviewer and compose-smoke pass, open a separate card for the non-root migration, and apply NOTHING to the live estate without your explicit approval (a deploy). Alternative: skip stage 1 and do both together later. Your call.

## D-29 The console sends the shared perimeter secret without the secure-context rule the operator key gets (2026-10-29, PROVISIONAL, MEDIUM; reviewer C-200 F-C200-3)
console.html applies `keyTransportOk()` (https or loopback only) to the stored operator key, but the shared perimeter secret entered in the console is sent without that gate, so over plain http to a non-loopback host it travels in clear. Provisional: record it as a declared limit in the ops-console README now (docs), and gate the secret the same way as a follow-up once you confirm that no operator uses the console over plain http. Alternative: gate it now (an operator on http loses console access until https). Your call.

## Rulings 2026-10-29 (Don, second interview)
- Repo visibility: KEEP PUBLIC for now. Consequence: nothing estate-specific (IPs, flag values, build SHAs, deploy status) and no unfixed-vulnerability specifics beyond the finding id and severity may be pushed to the repo or its comms branch from now on; history already pushed stays public (comms is fast-forward-only). Card C-226 asks a reviewer to inventory what is already exposed so you can judge. The GX10's anonymous fetch keeps working.
- D-28 RULED: stage 1 container hardening now (PR 108 may merge after reviewer, compose-smoke and CI pass); non-root USER is a separate later migration card; nothing applied to the live estate without your approval.
- D-29 RULED: document now, gate later: a README declared-limit line for the console's shared perimeter secret over plain http (card C-228); the gate follows when you confirm no operator uses plain http.
- todo.md C2 RULED: amend the spec to `<stem>.segments.journal` (the code and README already say so); card C-227 amends it and checks C2 off.

## D-30 Edits to a retired agent's record (2026-10-29, PROVISIONAL, MEDIUM; PROVEN by reviewer C-202)
The registry accepts edits of owner, domain, name and manifest_ref on a RETIRED agent, and the spend-governor accepts caps and spend for it. The owner edit has an effect: it rewrites who is "Responsible" in the incident post-mortem of past events. Provisional (card C-229): refuse owner, domain and manifest_ref edits (409) on a retired agent, like the status rule, and leave name and the governor alone (recorded as a declared limit). Alternative: allow edits and have incident-replay read the owner as of each event. Your call.

## D-30 RULED (2026-10-29, Don: option A)
Refuse owner, domain and manifest_ref edits (409) on a RETIRED agent, like the status rule; `name` stays editable; the spend-governor accepting caps and spend for a retired agent is recorded as a declared limit. Card C-229 is confirmed, no longer provisional.

## Ruling 2026-10-29 (Don): light GX10 run for docs-only PRs
Docs-only PRs (*.md, docs/, tasks/) may use a light GX10 run (--quick or core plus the touched suite); CI still runs everything; code and test PRs keep the full run. Rule added to comms/PROTOCOL.md.

## Standing authority (Don, 2026-10-29): "you have the authorization to take your own recommendations"
Design and policy questions no longer wait for Don; the coordinator decides with its recommendation and logs it here. Still reserved for Don (organization rule): deploys, deletes, closes outside the earlier authorization, secrets, and changing repository visibility. Decisions taken under this authority, each reversible by dropping its commit:
- D-17 (ANTHROPIC_BASE_URL over plain http): warn once, refuse only on FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM=1 (as built in PR 69 and PR 96).
- D-20 (defence-shield allowlist `--allow-ip 0.0.0.0/0` silences the alert exit code): refuse a catch-all (/0) allowlist and exit with a distinct code when anything was allowlisted (cards C-148 and a new C-240).
- D-21 (a GB10 compose start without its .env starts open): add a GB10 override that makes the posture variables required (`${VAR:?}`) so a missing .env aborts the start (card C-241); in the repo only, nothing deployed.
- D-24 (force-gateway posture flags exact-match "1"): same rule as D-23: recognise 1/true/yes/on and 0/false/no/off, refuse to start on any other non-empty value; FORCE_GATEWAY_MOCK stays exact-match (card C-180 confirmed).
- D-18, D-19, D-23, D-26, D-27, D-28, D-29, D-30, C2, light GX10 run: already ruled by Don.
