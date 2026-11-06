VERDICT: PASS WITH CONDITIONS on 8260a425e4291a478b917b85298874ec3922c650  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). Reviewer-8's three BLOCK items on PR 541 (the address in the manifests, the author name, the conflict) are fixed. I found one required fix (the provisioning tool's default now covers the five new draft agents) and several smaller defects; the workflow and the identity questions of the original review remain Don's.

R-PR857-8260a42, PR 857 (rebuild of PR 541, ssl-fp role agents: five manifests, ten agent files, key_intake.ps1, provisioning entries). Applies to this head only. gh pr view 857 confirms the live head; base 250154d3 = main, 0 behind, `git merge-tree` clean. This repository is public: I name no estate address, environment id or key in this report.

OBJECTIONS FIRST
1. REQUIRED: the provisioning tool's DEFAULT run now covers the five new draft agents. tools/provision_ssl_agents.py builds one AGENTS dict (two SSL agents, now seven) and the main loop provisions every entry unless `--only` is given (`if args.only and agent_id not in args.only: continue`, line 396). The runbooks tell operators to run this tool for the two SSL agents (docs/runbooks/token-renewal.md and v1.2-deploy-rollback.md name it); a bare run now also registers, and mints tokens for, five agents whose own manifests say "DRAFT, not provisioned, not applied" and whose delegation expires on a near date. The tool's comment ("Run with --only: a bare run also re-mints the two above") describes the opposite direction. This is a silent widening of what an existing command does, and it creates authority (scopes including push to the work branch and to comms) that no one approved at run time. MEDIUM, HIGH confidence (read: lines 120 to 135 and 383 to 420). Suggest a separate dict or a `--role-loop` switch, with the default unchanged, and a test of that default.
2. The `--only` behaviour has no test. Mutants O1 (filter removed), O2 (filter inverted), O3 (an unknown id accepted) and O4 (single value, not repeatable) all SURVIVE test_provision_wrapper.py (6 passed each), exactly as in the original review. The only change to that test is the set of AGENTS ids; the content of the new entries (domain, "never") is unpinned too (my O6 domain changed and O7 "never" emptied also survive). MEDIUM, HIGH (measured).
3. Stale identifier introduced by this PR: the PR changes `ENV_ID` in tools/start_role_session.py and the two lines in docs/ROLE-AGENTS-TEAM-ACCESS.md to the new environment id, but all five manifests still cite the OLD environment id in their header comment (line 3 of each: "pattern A, self-hosted GB10 sandbox env_..."). grep over the tree: the old id remains in 5 files, the new one in 2. The files now contradict each other about which environment these agents run in. LOW, HIGH (measured).
4. tools/key_intake.ps1 (new, 96 lines; handles a live API key), read in full, never run (needs a Console key and a clipboard):
   a. The previous key is copied to `<name>.key.prev` (`Copy-Item $dest "$dest.prev" -Force`) BEFORE any ACL is set, and the ACL step (`icacls /inheritance:r /grant:r <user>:(R,W)`) is applied only to `$dest`. The `.prev` copy keeps whatever the key directory's inherited ACL is, so the old key sits in a weaker file than the new one. MEDIUM-LOW (depends on the directory ACL), HIGH on the read.
   b. With `-Replace`, if icacls fails the script does `Remove-Item $dest -Force; throw 'icacls failed; file removed, nothing stored.'`: the live key file has already been truncated by `Set-Content` and is now deleted, the old key survives only in the weakly protected `.prev`, and the message says "nothing stored" and the header says "Nothing changed". A failed rotation therefore deletes the working key. LOW-MEDIUM (an operator-run tool; availability, not disclosure), HIGH on the read.
   c. `-Kind environment` without `-EnvironmentId`: the script sets `$status = 'not verified (no -EnvironmentId)'; $SkipVerify = $true` but the `try { Invoke-RestMethod -Uri $uri ... }` still runs with a null URI, throws, and the catch overwrites the status with "VERIFY FAILED: HTTP 0". The reported status is wrong in that path. LOW.
   d. `$EnvironmentId` is interpolated unvalidated into the verification URL path (the Bearer key goes only to the same api host, so a path trick cannot move the key to another host). LOW.
   e. What I checked and found sound: the key is never an argument or printed; the shape regexes separate admin, environment and workspace keys; an existing clipboard value is baselined and not taken; the clipboard is overwritten after the write; the destination is created empty and ACL'd before the key is written; the output carries a fingerprint, byte count and status only. HIGH on the read.
5. Manifests: the delegation revocation endpoint in all five now points at a documentation-range address, so each manifest declares a revocation route that cannot work; the PR says the sibling manifests do the same. They are marked draft and not provisioned, so this only matters when someone provisions them as written. LOW. The kill-switch endpoint is the internal service name form and unchanged.
6. Unchanged and still Don's (not mine, restated from the original review): permission_policy always_allow with bash, write and edit in each agent.md; the absent workflow (`.github/workflows/ssl-fp-role-session.yml` is deliberately not included; the WIF session path in docs/ROLE-AGENTS-TEAM-ACCESS.md has no workflow until it lands); the platform and workspace identifiers in a public doc (already public on main per the PR); the PR size.
7. All five manifests carry `delegation.expiry` 2026-12-06: they validate as VALID_WITH_WARNINGS ("near-term, within 30 days"), and the delegation service refuses any mint for a manifest whose expiry has passed (RT-MINT-1), so a token cannot be minted for these agents after that date without an edit. LOW (operational).

ASSUMPTIONS
A1 The statement that the PowerShell tool was not run is literal: I read it; I did not execute it (it needs a Console key). A2 "Not provisioned" in the manifest headers means no estate record exists today; I did not check an estate.

REASONING / CHECKS
1. Net-diff identity against PR 541: PR 541 (97dcfec1..65ef4706) = 21 files; PR 857 = 20 files. The file lists differ only by .github/workflows/ssl-fp-role-session.yml; the sorted changed-line sets differ only by the five manifest `endpoint:` lines (the private LAN address replaced by the documentation-range one). So B1 and B3 are fixed with nothing else changed. HIGH.
2. Identity (B2): 1 commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Co-Authored-By Claude Sonnet 5.5 only. Nothing under .github/. HIGH.
3. A scan of the new files for key prefixes, AWS and GitHub token shapes and private keys found only the shape regexes in key_intake.ps1 itself; a scan for IPv4 addresses outside the documentation range found none. HIGH.
4. Validation and tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1): all five manifests validate VALID_WITH_WARNINGS with the one date warning and 0 critical gaps; services/lifecycle-manager test_provision_wrapper 6 passed; tools test_environment_doc + test_start_role_session 67 passed. test_public_safety_c560 is not on main yet (it is PR 851), so the public-files guard did not run on this head. HIGH.
5. Mutants on a copy of the head against test_provision_wrapper.py (-x, a kill = rc 1):

| id | mutation | result |
|----|----------|--------|
| O1 | --only filter removed | SURVIVED |
| O2 | --only filter inverted | SURVIVED |
| O3 | an unknown --only id accepted | SURVIVED |
| O4 | --only not repeatable | SURVIVED |
| O5 | red-team agent id removed from AGENTS | KILLED |
| O6 | architect entry's domain changed | SURVIVED |
| O7 | runtime engineer's "never" emptied | SURVIVED |

Counted from the table: 7 run, 1 KILLED, 6 SURVIVED, 0 NOT APPLIED. The only pin on the new entries is the set of ids. HIGH on the counts.

CONDITIONS
C1 (required before merge) objection 1: keep the default of provision_ssl_agents.py to the two existing agents (separate dict or an explicit opt-in switch), or make the default refuse and require `--only`; add a test for the default and tests for `--only` (kills O1 to O4).
C2 (required, small) objection 3: update the five manifest headers to the new environment id (or drop the id from the comment).
C3 (non-blocking, before the PowerShell tool is used) objections 4a to 4c: ACL the `.prev` file as the new key is, restore the original on an icacls failure, and fix the status override.
C4 (decisions for Don, restated) objection 6, and whether the five draft manifests should carry a documentation-range revocation endpoint.
C5 (standing gate) GX10 16/16 and CI on this exact head, plus PR 851's public-files guard once it lands (this PR adds files that guard will scan); not run by me.

NOT VERIFIED
Execution of key_intake.ps1; any estate state; the agent prompts line by line (I scanned agents/ssl-fp-red-team/agent.md and a pattern scan of all ten files; the others were not read line by line); GX10 / Linux; CI.

CONCLUSION
The three blocking items of the original review are fixed and the rebuild is exactly PR 541 minus the workflow with the address replaced. But merging as it stands would change what the existing provisioning command does (it would also provision five draft agents), the `--only` switch that is meant to prevent that has no test, and the PR leaves two stale environment ids and a key-handling script with a rotation path that can delete the live key. PASS WITH CONDITIONS: C1 and C2 required, C3 before the tool is used, C4 Don's, C5 the gate.
