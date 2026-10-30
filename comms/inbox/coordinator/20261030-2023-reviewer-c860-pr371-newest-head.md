VERDICT: FAIL on 8eb5c87205347ff55acfe0ce3f2b6a21da796569 (unchanged head; same verdict as C-786 and C-807)  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-860, PR 371 at its newest head. `git fetch pull/371/head` gives 8eb5c87, the SHA of my C-786 and C-807 reports: no commit since. Nothing in the C-807 list has moved. This report adds one probe, the migration of existing ids that the card asks for. This SHA only.

OBJECTIONS FIRST
1. Every C-807 condition remains open because the head has not changed: absolute manifest_refs are accepted anywhere (api.py `_ref_is_inside_manifest_dir`: `if target.is_absolute(): return True`); the existence oracle ("missing" versus "invalid") is back for absolute paths; the resolver's new `path.read_bytes()` is unbounded (a never-ending device file as an absolute ref ended in MemoryError after 7 s under a 2 GB limit; main answers "invalid"); stored refs are not re-checked. See C-786 and C-807 for the evidence. Confidence HIGH.
2. Migration of existing ids is safe at this head. Probe: eight rows stored the way an older version could have stored them, bypassing validation (ids `a1.`, `a..1`, `a--b`, `a-_b`, a 100-character id, `0`, `a.`, `a_`): GET /agents lists all eight (200), GET /agents/<id> 200 for each, PATCH /agents/<id> 200 for each; the same ids through POST /agents (new registration) answer 422, as does a 65-character id. So existing rows keep working and only new ids face the grammar. The attest route answered 422 to my empty request body for every id; that tells nothing about ids (my body was wrong), so attest was not verified for legacy ids. Confidence HIGH for GET, list and PATCH; not verified for attest.
3. A stored legacy id that collides with a new one under the new grammar (for example a stored `a..1` and a new `a.1`) is distinct in storage; the confusable pair the grammar was written to prevent can still exist through migration. Not probed beyond the reasoning. LOW.

ASSUMPTIONS
A1 The newest head is what GitHub serves now (fetched this session). A2 Legacy rows are inserted by the old model; I constructed them with model_construct.

REASONING / CHECKS
- Head comparison: pr371 head equals 8eb5c87 (the C-786/C-807 SHA). Verdict logic: C-786 conditions C1 (confine absolute refs or record a ruling; fix the oracle) and C2 (bound the resolver read) are open, so FAIL stands.
- C-807 conditions still open: all (as in objection 1). Closed since C-786: none.
- Probe as in objection 2; scratch worktree removed, nothing committed.
- Commits unchanged: 3, author and committer Don Hagell no-reply.

CONDITIONS (unchanged)
C1 (blocking) Confine absolute refs or record Don's ruling, and fix the oracle either way. C2 (blocking) Bound the resolver read. C3 (non-blocking) Re-check stored refs; test the OSError branch; list id routes. C4 (coordinator) Rule on the seven-suite fixture move versus an open absolute rule.

NOT VERIFIED
GX10 full set, CI, attest for legacy ids, Windows junctions.

CONCLUSION
No new commit since C-807: same FAIL. The id migration is safe for existing rows (list, get and patch work; new ids are checked). UNVERIFIED.
