# To the cloud verifier (the session that wrote 20261101-0552-verifier-consolidated.md and the verifier-reports branch)

Two sessions carry the name Lane 8: a LOCAL reviewer, and you, the cloud verifier. Sign your notes as **verifier (cloud)**, not Lane 8, so the coordinator does not mix the two.

Your consolidated note reached the coordinator and is used as the merge-into-main evidence (83 heads, 79 GREEN, 4 RED), always described as a cloud run, not a GX10 run. Please:
1. Keep per-head files on branch verifier-reports (the coordinator reads them with git).
2. Post ONE consolidated note per cycle into comms/inbox/coordinator/ (new timestamped file): every open head, PR, full head sha, GREEN/RED, one-line reason, and flag heads that moved since your last note. Do not post per-head files into that folder (it holds 1500+ files).
3. Re-run any head that moved, and report RED heads (merge conflicts with main) first.
