VERDICT: PASS WITH CONDITIONS on 6727f5bf1abc2075fc3e747ee3b1ed59ead546be
(Lane 14, cloud, no GX10: UNVERIFIED. PR 378, docs only: docs/capstone-evidence/hardening.md, +6 -3, one commit; author and committer Don Hagell no-reply. CI at this head read by REST: tests (3.12), compose-smoke, compose-upgrade-smoke and fly-image-smoke success; tests (3.11), (3.13), (3.14) queued: NOT confirmed (a docs-only diff).)

OBJECTIONS FIRST
1. The card asks for each dated statement "against git history"; this repository's history cannot answer for August: the clone is SHALLOW (git rev-parse --is-shallow-repository: true; 53 commits; the oldest, 2026-10-29). Every August date below is therefore checked against other documents and the GitHub API, not against commits. MEDIUM confidence on the ones that rest on the project's own notes.
2. A statement dated "historical" is still a claim about the estate in a public repository; dating it does not remove it.
3. The edit dates two sentences; the paragraph and file around them hold other statements that read as current.

ASSUMPTIONS
A1. STATE.md on main is the project's own dated log (self-authored; not independent). A2. The GitHub API's repository, workflow and run timestamps are independent of the docs. A3. "Estate" values = addresses, flag values, build SHAs, deploy status.

REASONING (each dated statement)
1. "Historical statement, 2026-08-08. On that date the full stack was built and run on the DGX Spark" (hardening.md:28-31). Supported, MEDIUM: STATE.md lists "OQ-5 RESOLVED: compose verified on GB10 ... 9 services healthy, governed smoke flow correct, ~4 min" inside its Round-2 summary dated 2026-08-09, so the run could be 08-08 or 08-09 by that line alone; STATE.md also says the oldest active `created_at` on the GB10 is 2026-08-08 (a registry row existed on the GB10 on 2026-08-08), which fits a run on that date. No source I can read gives the compose run's own timestamp. The file's header date is 2026-08-08 and the sentence sits in the first (08-08) part, before the "Round 2 addendum (2026-08-09)" at line 77. F-C874-1.
2. "Historical, 2026-08-09: it was flagged UNTESTED because the repository had no remote then. The repository now has one and the workflow runs on it" (hardening.md:107-109). Supported by the GitHub API (HIGH): the repository was created 2026-08-09, `.github/workflows/ci.yml` as a workflow was created 2026-08-09, the oldest of 806 runs is dated 2026-08-09, and CI runs on this PR's head today. "No remote then" is loose: STATE.md ("Remote (verified 2026-08-09)") says a `gb10` bare-repository remote already existed and `origin` on GitHub was created that day; the accurate wording is "no GitHub remote". STATE.md also says run #2 was green with the x86_64 compose smoke the same day, so "UNTESTED" was true only until run #2. F-C874-2.
3. The nearby "Verified 2026-08-08 and now cited" (hardening.md:44) and "the 2026-08-09 cross-check ... httpx read the ELI URL ... on 2026-09-13" (:111-114) are dated; the 2026-09-13 read is backed by STATE.md's EUR-Lex lines (the EUR-Lex "limit" was the 2026-08-09 agent's fetch tool). Not changed by this PR.
4. STILL READS AS CURRENT, in the same file (not touched): (a) hardening.md:36-37 "x86_64 compose run remains pending (CI candidate)" is inside the paragraph now headed "Historical statement", but the PR's own next sentence at :105-107 says an x86_64 compose smoke exists in CI; and the "Deliberately still open" list (:68-74) still lists "CI matrix incl. an x86_64 compose run", "signing-key rotation/revocation protocol" and "per-caller identity" as open, which the repository now has (CI matrix and compose smoke exist; rotation and operator keys are built). The header "Date: 2026-08-08" and "156 passing" frame the whole file as 08-08, so a careful reader can place them, but an undated "remains pending" next to a dated sentence is the ambiguity the PR set out to remove. F-C874-3 (LOW-MEDIUM).
5. Estate values (the card's second ask): the diff and the file contain NO address, flag value, build SHA, credential or deploy status of a live estate; the only estate-class words are the hardware names ("DGX Spark (aarch64, Ubuntu 24.04, Docker 29 / Compose v5)", "GB10") in a historical, dated sentence, and "all nine services healthy" as a dated result. The present-tense risk is lower after the edit. STATE.md (a separate file, not in this PR) still carries a private home path for the GB10 staging directory and an ssh user at the GB10 (lines near 2113 and 2188) and a note that the stack had exited: not part of this card; flagged only so the coordinator can route it with C-606 (HIGH confidence the strings exist; not printed here).
6. Claims above the evidence: "all nine services healthy, governed smoke flow correct end-to-end ... ~4 min" is a historical result with no artifact in the repository (no log is committed for the GB10 run); STATE.md repeats it. The PR does not add a source. F-C874-4 (LOW).

FINDINGS
F-C874-1 (LOW, MEDIUM confidence): the exact date 2026-08-08 for the GB10 compose run rests on STATE.md and a GB10 row date, not on a timestamped artifact; the repository's history cannot confirm it (shallow clone).
F-C874-2 (LOW): "had no remote" should read "had no GitHub remote" (a `gb10` bare-repository remote existed); run #2 on 2026-08-09 was green.
F-C874-3 (LOW-MEDIUM): :36-37 "x86_64 compose run remains pending" and the :68-74 "still open" list read as current and contradict the CI note added at :105-109.
F-C874-4 (LOW): no artifact for the GB10 result.
F-C874-5 (info): git history here starts 2026-10-29 (shallow); a future date audit needs a full clone.
No estate address, flag value, build SHA or deploy status in the PR: none found.

CONDITIONS
C1 (non-blocking): F-C874-3 date or correct the two undated "open" statements (same file) so the page does not contradict itself.
C2 (non-blocking): F-C874-2 wording.
Not verified: any August date against commits (shallow clone); the GB10 run itself; CI beyond the line above.

CONCLUSION
The edit is accurate on the points I could check independently (the GitHub repository, workflow and first run all date from 2026-08-09, so "UNTESTED then, runs now" is true), adds no estate value, and the GB10 date is plausible but unprovable from this clone. What it leaves is an undated "x86_64 compose run remains pending" and a stale "still open" list in the same file. PASS WITH CONDITIONS (non-blocking) on 6727f5b.
