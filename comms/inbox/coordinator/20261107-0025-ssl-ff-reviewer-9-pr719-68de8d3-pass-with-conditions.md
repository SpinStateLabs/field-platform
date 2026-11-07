VERDICT: PASS WITH CONDITIONS on 68de8d3560f3a4e8ee73d563fce783abf868c0e3  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). Re-review of the condition fix for reviewer-7's PASS WITH CONDITIONS on 8ae8dcbd. Their C1 (a halted line corrupted to non-JSON, followed by a valid line, still let the halted run resume) is fixed and pinned. Remaining: two design limits I measured, one unpinned branch, and the standing gate.

R-PR719-68de8d3, PR 719 (S6-19: deployment_agent journal fails closed on a transition with an unreadable state, and now on mid-file damage). Applies to this head only. The fetched pull/719/head is 68de8d35: 6 commits, tools/deployment_agent/journal.py and tools/tests/test_deployment_agent_journal_shape.py only. Base ebb027a2, 74 commits behind main; `git merge-tree --write-tree origin/main <head>` is clean (tree id only). Nothing under .github/.

OBJECTIONS FIRST
1. A halted line that is the FINAL line and torn (a crash during the halt write) is still skipped, so the halt is lost. Reproduction (the real Journal on this head; journal planned, minted, installed, halted; the halted line truncated by 6 bytes): `is_halted()` is False, `pending()` returns the `installed` entry, `torn_lines` 1. This is the documented crash tolerance (the module docstring: a crash leaves at worst a torn final line), and the reader's intended recovery is to resume from the last good state, so it is by design; but the PR's own argument is that the halted line "must stop it", and this is the one way it still does not. MEDIUM-LOW design limit, HIGH on the measurement.
2. The new acknowledgement (`torn_tail_ack`) carries no integrity: a hand-written line `{"event":"torn_tail_ack","damaged_line":4,...}` placed after a corrupted halted line 4 excuses it. Reproduction: halted line (4) truncated, a forged ack appended: `is_halted()` False, `pending()` returns `installed`; without the ack the same journal raises JournalError (measured, "C"). Needs write access to the journal, which a root-owned audit file already assumes, so LOW; but the ack is now the one hand-editable key that silently un-halts, and a human repairing the journal needs to know that.
3. Mutant A2 (an ack lacking `damaged_line` excuses any damaged line: the check `damaged_line in (damaged_at, None)`) SURVIVES the whole new test file (50 passed). A malformed ack with a missing or null `damaged_line` is never tested. LOW (test gap).
4. Behaviour change the builder names: a journal that already has a torn line in the MIDDLE (from a recovery before this change) now raises JournalError on every read, including `clear_halt`, until a human repairs the file; a runbook sentence is a carded follow-up (B-FU-PR719-runbook-repair), and `_locked` still does not convert JournalError into a halted RotationResult. MEDIUM operationally, not a defect of the change.
5. The first version of this fix broke crash recovery (the builder says an existing test failed); the ack mechanism was added to repair that. The recovery path is now: the resumed append writes an ack naming the damaged line, then the new entry; seq values 1,2,4,5 are pinned. I re-ran the two shapes of crash recovery in my mutants (A4 no ack, A5 wrong seq, A6, A7 below): all die. HIGH.

ASSUMPTIONS
A1 The journal is an audit trail on a host the operator owns (not tamper-proof); objection 2 is stated for what a repairer should know, not as an attack by an outsider. A2 I did not run a real rotation.

REASONING / CHECKS
1. Diff read (journal.py): `entries()` numbers physical lines; a non-JSON or non-object line is counted torn and remembered as `damaged_at` (the FIRST such line); if a valid object follows it, the reader raises `JournalError` naming the line, never its content, unless that object is a `torn_tail_ack` whose `damaged_line` equals it; a transition whose state is not exactly a State value raises; `append()` writes an ack before the new entry when it resumes past a torn tail. HIGH.
2. Identity: 6 of 6 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, from tools/): test_deployment_agent_journal_shape.py + test_deployment_agent_rotation.py 390 passed, 0 failed (1,502 s; the builder reports 390). HIGH.
4. Mutants on a copy of the head, the shape test file only, -x, a kill = pytest rc 1:

| id | mutation | result |
|----|----------|--------|
| A1 | an ack excuses any damaged line (no line equality) | KILLED |
| A2 | an ack with no damaged_line excuses any damaged line | SURVIVED |
| A3 | mid-file damage skipped, not raised | KILLED |
| A4 | the ack is never written | KILLED |
| A5 | seq ignores torn lines | KILLED |
| A6 | the ack's seq equals the entry's seq | KILLED |
| A7 | the ack names the wrong line | KILLED |
| A8 | damaged_at keeps the last damaged line, not the first | KILLED |
| A9 | a non-object line is not counted as damaged | KILLED |
| S1 | the bad-state guard removed | KILLED |
| S2 | any string is a readable state | KILLED |
| S3 | the error's line number is zero based | KILLED |
| S4 | state compared case-insensitively | KILLED |

Counted from the table: 13 run, 12 KILLED, 1 SURVIVED, 0 NOT APPLIED (one more edit of mine, S5 on blank-line numbering, did not match the code and is not counted; reviewer-7 pins it by a test). HIGH on the counts.

CONDITIONS
C1 (non-blocking, new PR) pin an ack with a missing or null damaged_line (A2); say in the runbook (the carded B-FU-PR719-runbook-repair) that a hand-written torn_tail_ack un-halts, and that a halted line torn as the FINAL line is lost by design.
C2 (decision for Don) whether a halted record needs a stronger guard than the torn-tail tolerance: for example write the halt line first to a side file, or make `halted` re-derivable from the failure itself on resume; today a crash during the halt write resumes the interrupted run.
C3 (standing gate) GX10 16/16 and CI on this exact head rebased on main; not run by me. After this verdict the head is frozen except a condition fix.

NOT VERIFIED
GX10 / Linux, CI, a real rotation, the rotator's behaviour on a JournalError beyond reading it.

CONCLUSION
reviewer-7's C1 is fixed: a damaged line with a valid line after it now stops the target, and the crash-recovery path it first broke is repaired by an acknowledgement whose line, seq and presence are pinned (A1, A4 to A7 die). 390 tests pass, 12 of 13 mutants die, identity correct, merge clean. Two limits remain by design (a torn FINAL halted line; a hand-forged ack) and one untested malformed-ack case. PASS WITH CONDITIONS: C1 optional, C2 Don's, C3 the gate.
