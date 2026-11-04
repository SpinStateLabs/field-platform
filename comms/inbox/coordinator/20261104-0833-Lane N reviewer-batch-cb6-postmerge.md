# Reviewer (read-only, post-merge): batch cb6 = MERGE 3, main 7de2a064 -> 6a37ae76 (PRs 317 @9cc5221, 331 @543fe63, 332 @0df2259, 333 @f34d092, 337 @72e8fae, 338 @f052a0e; 18 commits)

**Verdict: PASS WITH CONDITIONS (post-merge read) on batch head `6a37ae76`.** Code is mutation-hardened; the RECORD of per-PR reviewer verdicts is incomplete for three PRs (below). No earlier file names cb6 as a batch; this is that file.

## Record checked (HIGH, from git and gh)
- 18 commits (STATUS: 18), a fast-forward, 0 nonconforming identities (Don Hagell noreply, author and committer). PRs 317, 331, 332, 333, 337, 338 CLOSED with a pointer comment each, CI SUCCESS 7/7 on each head.
- Verifier A on the batch head: `20261101-0331-gx10-verifier-A-batch-cb6.md` names 6a37ae76dd1f7207a6eec67ff4ba6d9df1fc61cf before and after the run, "16 of 16 suites passed, 0 failed".
- Reviewer verdicts naming the head, FOUND for 317 (c865, c973), 331 and 333 (c1056). NOT FOUND for 332, 337 and 338 by my search: for 332 only a one-line "PR 332 ... PASS" in an index (`20261101-0618-reviewer-c1082...`, line 160, no sha); for 337 and 338 only verifier GREEN rows and a sweep table (a row says "PASS WITH CONDITIONS on 3b28331 [HEAD MOVED]", a different head). STATUS MERGE 3 asserts "reviewer PASS naming each head": that sentence is not confirmed for these three (MEDIUM: I searched file names containing "review" and the short head sha; a verdict filed under another name would escape this).

## Objections first
1. Four code PRs in one batch: a rounding change, an events-cursor bound, a strict anchors parser with a new floor, and a wording change; each deserves its own mutation check, so I ran them separately.
2. The approver cursor change decides which events a session sees: a bound that is too loose lets one far-future time freeze the session; too tight drops fresh events on a skewed clock. The slack is one minute (author's own C-720 argument, read).
3. `--min-anchors` is only meaningful with the complete off-box anchors file; the code and the CLI now say so (note on every run without a floor).

## Measured (GX10 ~/ff-work/wt-cb6 at 6a37ae76, python -B, own venv)
attestation conformance tests 42 passed; claude-approver cursor and refresh tests 74 passed; sealed-ledger anchors tests 46 passed; crosswalk wording tests 6 passed. The 16-suite is the verifier's report.

## Mutants (62 rows; source restored, worktree clean)
| Behaviour | Killed | Survived |
|---|---|---|
| A1 conformance rate rounds half up, exactly | 6 | 0 |
| A2 the input contract (bool, negative, allows>total, zero total) | 5 | 0 |
| A3 the call site uses it and the note says "rounded half up" | 4 | 0 |
| P1 a future processed_at is never the cursor | 6 | 0 |
| P2 a streak of future values warns once (10) | 4 | 0 |
| P3 the stored cursor is the normalised UTC instant | 5 | 0 |
| P4 a time with no UTC form is counted and skipped | 3 | 1 (gap: the `ValueError` arm of `except (OverflowError, ValueError)` is unpinned) |
| L1 chain_length is a strict non-negative int | 4 | 0 |
| L2 parse_anchors: BOM stripped, split on newline only, strict UTF-8 | 4 | 1 (gap: invalid UTF-8 inside a string value is accepted with `errors="replace"`) |
| L3 anchors in order; same position with different hashes fails | 5 | 0 |
| L4 `--min-anchors` counts signature-verified positions | 5 | 1 (equivalent: with a key present every record is signed, so `len(seen)` equals `len(counted)`) |
| L5 a position-0 anchor needs the genesis hash | 3 | 1 (equivalent: `counted.add(-1)` keeps the set size) |
| W1 declaration-only controls say so | 4 | 0 |
Totals counted from the table: killed 6+5+4+6+4+5+3+4+4+5+5+3+4 = 58; survived 0+0+0+0+0+0+1+0+1+0+1+1+0 = 4; 62 rows. 2 survivors are equivalent and 2 are gaps; every behaviour has at least 3 kills, and 11 of 13 have at least 4.

## Conditions
- C1: confirm or produce reviewer verdicts naming the full heads of PRs 332, 337 and 338 (docs and wording only, low risk); until then the STATUS sentence "reviewer PASS naming each head" is not supported by the files I found for those three.
- C2: none on the code.

## Findings (non-blocking; new PR only)
- F-cb6-1 LOW: tests for the two gaps: a time with a ValueError-only UTC conversion (P4) and invalid UTF-8 inside an anchors string value (L2).
- F-cb6-2 INFO: the "docs: IMPLEMENTATION.md line cite" in `tools/topology_lint.py` now cites a table row instead of a line number: fine.
