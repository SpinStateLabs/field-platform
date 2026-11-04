# Reviewer (read-only, post-merge): batch cb9 = MERGE 5, main b152e955 -> 198c4df2 (PR 322 @1ce17e6, 6 commits)

**Verdict: PASS WITH CONDITIONS (post-merge read) on batch head `198c4df2`** (PR 322 head `1ce17e6cf0efba367d1c0f1819edb309d1b4c144`). No earlier file names cb9 as a batch; this is that file.

## Record checked (HIGH, from git and gh)
- 6 commits (STATUS: 6), a fast-forward, 0 nonconforming identities (Don Hagell noreply on author and committer). PR 322 CLOSED with a pointer comment, CI SUCCESS 7/7.
- Reviewer PASS naming the full head `1ce17e6cf0efba367d1c0f1819edb309d1b4c144`: c957, c960 and c993 (3 files, `VERDICT: PASS on 1ce17e6...`). Verifier A on the batch head: `20261101-0427-gx10-verifier-A-batch-cb9.md`: names 198c4df2fa2961007f304ae233e730f316432412 before and after the run, "16 of 16 suites passed, 0 failed".
- STATUS labels the batch "docs/ENVIRONMENT.md" but the diff is mostly `federation_broker/engine.py` (+178/-45) with a 522-line test; docs/ENVIRONMENT.md changes 2 lines only (LOW: the label names the file group that forced the order, not the content).

## Objections first
1. The change is a SECURITY-relevant org normaliser plus a cross-process uniqueness rule: wrong normalisation merges two different orgs (a contract of one blocks or serves another) or splits one (a duplicate active contract). I attacked both directions with mutants.
2. `normalize_org` drops Unicode Cf and a CHOSEN SUBSET of invisibles; the code says it is a subset and the ruling for Cf is flagged for Don (reviewer C-565 F-C565-5): a decision, not a defect.
3. `for_org` scans all active rows and normalises each in Python ("a handful of rows"): fine now, O(n) per lookup if the table grows (LOW).

## Measured (GX10 ~/ff-work/wt-cb9 at 198c4df2, python -B, own venv)
`tests/test_org_normalise_c483.py`: 83 passed (22 s, the eight-process race test included). The 16-suite is the verifier's report.

## Mutants (41 rows on engine.py; source restored, worktree clean). 2 rows first came out NOMATCH (a bad anchor of mine); I re-ran both with a fixed anchor and both are KILLED, so the table shows them as killed.
| Behaviour | Killed | Survived |
|---|---|---|
| N1 NFKC, casefold, whitespace collapse | 5 | 1 (equivalent for the tests: the second NFKC after casefold only differs for a character whose casefold is not NFKC-stable) |
| N2 Unicode format characters (Cf) are dropped | 5 | 0 |
| N3 the listed invisibles outside Cf are dropped (each range) | 7 | 0 |
| N4 visible marks (Mn, Mc, Me, Cc) are kept | 4 | 0 |
| N5 one active contract per NORMALISED org | 5 | 0 |
| N6 check and insert are one write transaction; upsert, not REPLACE | 5 | 0 |
| N7 migration: duplicates warn, the index is skipped, nothing refused | 5 | 0 |
| N8 a whitespace-only name names no org | 4 | 0 |
Totals counted from the table: killed 5+5+7+4+5+5+5+4 = 40; survived 1+0+0+0+0+0+0+0 = 1; 41 rows. Every behaviour has at least 4 kills.

## Conditions
- C1: none blocking (merged; record complete; mutation-hardened).

## Findings (non-blocking; new PR only)
- F-cb9-1 LOW: one test for a character whose casefold is not NFKC-stable, so the second normalisation is pinned.
- F-cb9-2 LOW: the STATUS batch label (see above).
- F-cb9-3 LOW: `for_org` is O(rows); revisit if contracts grow.
