VERDICT: PASS WITH CONDITIONS on 5dd1a2ac3162a5b9d8cfaa7af5b724dce7dedc58  (ssl-ff-reviewer-9; Windows only, no GX10, CI not read)

R-PR795-5dd1a2a. Rebuild of PR 368 (field-mcp Tier 1) on main aab217d3. Applies to this head only.

OBJECTIONS FIRST
1. .github/ is touched: ci.yml +4/-1 adds the hash-checked field-mcp install lines and puts field-mcp in the per-service test loop. The review rule allows only a ci.yml concurrency block. This is new-suite wiring (carried from PR 368, which the c781 review read as "comment wording + install lines"), so it is not a concurrency block. HIGH.
2. The last seven of 11 commits (917da89d 4eb314a9 407347d2 def7d091 becdda5a 11ff5483 5dd1a2ac) carry a Co-Authored-By trailer naming Claude Fable 5.1. Author and committer are Don Hagell noreply on all 11 (checked with git log %an %ae %cn %ce). Standing rule is never Fable. The trailer is history in the original PR, preserved by cherry-pick. HIGH on the facts, the policy call is the coordinator's.
3. The two stdio tests fail on this box. Cause is the test, not the code: the child is started with env={PATH,PYTHONPATH,...} and no SYSTEMROOT, so asyncio cannot load winsock (WinError 10106). With SYSTEMROOT set, `import asyncio` works, and the write entry point run directly prints the refusal and exits 2. So the failing assertions are Windows environment, but the stdio path was NOT exercised end to end by me. MEDIUM.
4. scripts/mutants.py still has the weakness named as C1 in the c781 review: it sets PYTHONPATH to the copy's src only and never checks the baseline is green, so on a box without the siblings installed a collect error reads as KILLED. Not fixed in this head. HIGH.
5. Rebuild is not run on Linux or by CI by me. 

ASSUMPTIONS
A1 PR body is the author's claim; I re-derived each point below. A2 main is aab217d3 (merge-base of head, checked). A3 hash file contents not re-derived from an index.

REASONING / CHECKS
1. Range identity. git range-diff 5808a5cd..pr368(37c19167) vs aab217d3..head: commits 1,2,4-11 are "=", commit 3 is "!" (0d23cf34 vs 0f2aa01a). The only difference is a context-line pin in docs/ENVIRONMENT.md (the unrelated FIELD_ATTEST_URL row), as the PR body says. The +/- line multiset of the two net diffs is identical (empty diff of sorted changed lines). Both are 27 files, +3194 -2. HIGH.
2. Identity: 11 of 11 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>. HIGH.
3. .github diff: exactly the ci.yml hunk in objection 1; nothing else under .github/. HIGH.
4. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONPATH = this tree's src + all sibling src, import path confirmed to be the head tree, not the stale editable at fpl1-380): full run 201 passed, 2 failed (the two test_stdio tests, objection 3), 248 s. Same set without test_stdio: 201 passed, 0 failed. Matches the PR body numbers. HIGH.
5. Mutants run by me, tests = every file except test_stdio, each on a copy, baseline on those files green first (201 passed), a kill counted only when pytest returned 1 (a test failed), never on an error:

| id | behaviour | result |
|----|-----------|--------|
| K7c | trailing newline refused (fullmatch) | KILLED |
| K7 | path segment check present | KILLED |
| K7b | segment pattern in tool schema | KILLED |
| K6 | secret redaction | KILLED |
| K6b | redaction reaches dict keys | KILLED |
| X1 | redaction reaches list items (mine) | KILLED |
| C6 | consent is exactly "1" | KILLED |
| X3 | consent "1x" prefix accepted (mine) | KILLED |
| C5 | external https needs the setting | KILLED |
| D6 | body/form id checked in code | KILLED |
| D7 | body/form id pattern in schema | KILLED |
| R1 | route with no tool fails coverage | KILLED |
| R3 | no write route as Tier 1 tool | KILLED |
| R4 | Tier 2/3 set pinned literally | KILLED |
| C2 | no userinfo in a base URL | KILLED |
| X4 | same edit as C2 (mine, duplicate) | KILLED |
| P2 | every third-party import declared | KILLED |
| D5 | no Tier 3 flag in source | KILLED |
| K1 | trust_env=False | KILLED |

Counted from the table: 19 rows, 19 KILLED, 0 SURVIVED, 0 NOT APPLIED; X4 duplicates C2, so 18 distinct. Not run: K2-K5, K8-K13, C1, C3, C4, D1-D4, R2, S1, P1 (the full mutants.py was not run; about 5 min per mutant here). Per behaviour I reached 3 distinct mutants for redaction, path segment, consent and routes, 2 for body ids and for base-URL userinfo: the "at least 4 per behaviour" bar is not met for any of them, because each of those behaviours is pinned by only 2 or 3 mutants in the PR's own list and I added at most one more. Coverage gap in my review, not a survivor. HIGH.
6. Code read (client.py, config.py): trust_env False, no redirects, explicit timeouts, streamed size cap, error text fixed words plus int status, only config.py reads the environment, key repr hidden, tier 2 settings read only by the write entry, fullmatch on SEGMENT, consent compared to the exact string "1". No finding. HIGH.

CONDITIONS
C1 (coordinator ruling needed before merge) ci.yml wiring is outside the .github/ rule (objection 1). Confirm it is intended; the "ruled by Don 2026-10-30" comment in the hunk is the author's text, I did not verify it.
C2 (policy) The Fable 5.1 Co-Authored-By trailers on the last seven commits: decide whether to accept as history or have the builder re-cut those trailers (a PR head change, then a new review).
C3 (non-blocking, LOW) make scripts/mutants.py fail closed on a red baseline and use the full PYTHONPATH (carried from c781 C1; still open).
C4 (required before merge, standing gate) GX10 16/16 on this exact head rebased on main; the two Windows stdio failures must be green there. I could not show that.

NOT VERIFIED
Linux run, CI, GX10, the hash file against the index, snapshot.json against a live build, the remaining 27 PR mutants.

CONCLUSION
The rebuild is the same change as PR 368 (net diff identical, one context-line difference), 201 tests pass on the head, 19 of 19 mutants I ran were killed, identity correct on all 11 commits. Conditions C1 and C2 need a coordinator decision, C4 is the usual GX10 gate. PASS WITH CONDITIONS; the head is frozen except for a condition fix.
