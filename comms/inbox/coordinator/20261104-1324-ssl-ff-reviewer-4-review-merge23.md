# Reviewer note (FALLBACK, read-only): MERGE 23 = main 793481f3 (batch s2q: scrub PRs 440, 448, 469 plus one commit restoring the company's own contacts)
Reviewer: ssl-ff-reviewer-4. UNVERIFIED (cloud, no GX10). Read-only; nothing pushed outside comms. Delta reviewed: 4ef319cc..793481f3, 13 files (+121/-36), 6 commits; author and committer of all 6 = Don Hagell 13129187+dhagell@users.noreply.github.com, trailers per the table below. The merge is done; this is an independent check after the fact. I did not re-run the recorded GX10 B 16/16 or Lane 7 verdicts.

## Objections first
1. A scrub that edits text can miss the same class elsewhere; "scrubbed" is a claim about the whole public tree, so I checked the tip of main for the classes the batch names, instead of only reading its diff.
2. PR 469 changes a client that carries the perimeter secret and the signed caller headers (field_core LedgerClient and RegistryClient): a proxy fix without a redirect pin leaves the same secret exposed to a redirect.
3. The batch commit "keeps the company's own contact" in the plugin and marketplace metadata (Don ruling Q-86 F1); that is a decision, not a defect, and I treat it as such.

## Verified (run by me, on origin/main as fetched in this session)
- Mailboxes: a scan of every tracked text file for `name@domain` found no personal-domain mailbox left; the only non-reserved domain is the company's own, in three files (plugins/field-agent/.claude-plugin/plugin.json, agents/ssl-invoicing-agent/SKILL.md, .claude-plugin/marketplace.json), which is the ruled exception. Everything else is a reserved or fixture domain (.test, example.*), loopback or a metadata-service URL (HIGH). The scrub commit replaced a personal mailbox in the manifests with a placeholder; I do not repeat it here.
- Manifest endpoints: manifests/ssl-invoicing-agent.yaml and ssl-timekeeping-agent.yaml now use 192.0.2.10 (RFC 5737 documentation range) instead of a private estate address; deployment-agent.yaml uses a `.invalid` host (HIGH).
- 64-hex strings outside tests: 6 files, all file-pin sha256 values for tools/images in runbooks and Dockerfiles (docs/runbooks/token-renewal.md and the Dockerfiles/fly.toml), not credentials (read, MEDIUM).
- PR 469 code and test: field-core clients.py LedgerClient and RegistryClient now use `httpx.Client(timeout=5.0, trust_env=False)`; packages/field-core/tests/test_clients_trust_env_c1182.py sends through a real loopback proxy listener and checks which listener saw the request, plus `trust_env is False` on the client object. The two matching entries are gone from tools/tests/http_env_proxy_allowlist.txt.

## Mutants (scratch worktree at 793481f3; the two test files that pin the delta: test_clients_trust_env_c1182.py and test_http_env_proxy_lint_c57.py; baseline 106 passed; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| C1 | LedgerClient trust_env True | 3 failed | yes |
| C2 | LedgerClient trust_env dropped | 3 failed | yes |
| C3 | RegistryClient trust_env True | 3 failed | yes |
| C4 | RegistryClient trust_env dropped | 3 failed | yes |
| C5 | allowlist: LedgerClient entry re-added (stale) | 1 failed | yes |
| C6 | allowlist: RegistryClient entry re-added (stale) | 1 failed | yes |
| C7 | allowlist: another entry removed | 1 failed | yes |
| C8 | a new unproxied client added in clients.py | 1 failed | yes |
| C9 | LedgerClient `follow_redirects=True` | 106 passed | NO |
| C10 | RegistryClient `follow_redirects=True` | 106 passed | NO |
Totals counted from the table: 10 mutants, 8 killed, 2 survived (C9, C10). Survivors against the whole suite: I ran the two files that pin this delta; I did not run the whole field-core suite per survivor. C9 and C10 are not claimed by C-1182 (it claims the proxy environment only); they are the redirect gap of objection 2.

## Findings
- F-S2Q-1 MEDIUM (public safety, HIGH that the lines exist, MEDIUM that they violate the ruling): STATE.md on main (last touched by 968cc2c0) still holds dated session notes with estate state: a section "Phase F session opened 2026-09-14" that gives the GB10 checkout HEAD, "16 project containers up", RestartCount 0, `estate_probe health --expect-build-sha <truncated hex>` results "51/51", a ledger pin "647 / <truncated hex>" and "fresh pin 677 / <truncated hex>", and a second block (Phase F code, GB10 step) that again lists health 51/51 with an expected build sha, "continuity 3/3" and "restarts 0 -> 0" (STATE.md around lines 1030-1068 and 1060-1068). The repository rule is: no build id, deploy status or credential; the batch message says deploy-status and build-id lines were scrubbed (C-1134, class C8). Whether dated historical notes are in scope is the coordinator's and Don's decision; I only report that the class is still present. Hex values deliberately not reproduced here.
- F-C1182-1 LOW: C9, C10: add `follow_redirects=False` explicitly to both clients and pin it (same mechanism as the C-605 objection on the rotator client).
- F-S2Q-2 LOW: I did not re-verify PR 440's other scrub classes (key fingerprint placeholders in STATE.md, mailbox shapes in non-manifest files) beyond the whole-tree scans above; a "no fingerprint left" scan on STATE.md found none next to the word "fingerprint" (MEDIUM: pattern based).

## Verdict (retrospective, no head to freeze): no objection to the code of MERGE 23; F-S2Q-1 is a finding for the coordinator
The proxy fix and its pins hold under mutation (8/8 claimed behaviours killed); the redirect gap is LOW; the remaining STATE.md estate-state notes should be ruled in or out of scope of the public-safety scrub.
