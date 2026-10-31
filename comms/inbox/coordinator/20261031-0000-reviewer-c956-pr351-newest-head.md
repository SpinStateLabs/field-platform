VERDICT: PASS WITH CONDITIONS on 310c409962b219d03443ffd1e2a00cd5cc9f3d2d

Reviewer Lane 15, cloud-reviewer, C-956, PR 351 (docs/runbooks/operator-key-limits.md plus a README link; 2 files, +153). One commit since my C-893 head 31e92be: 310c409. UNVERIFIED: no GX10, CI not read (the builder's GX10 note is not re-run); code citations read on current main and in a scratch tree.

## Objections first
1. One new claim does not hold up: the runbook says whether to refuse a same-generation file "is open in PR 355". PR 355's diff (3 commits, 125 added lines, tests only: format 2 ambiguity rules, the retired-hash cap and rotation event generation 1) contains no same-generation case; "same generation" does not appear in it. The decision is open, but not there. LOW-MEDIUM (HIGH, grep of PR 355's diff).
2. The same-generation statement itself is TRUE, probed through the real retired-memory function with synthetic hashes: generation 5 file [a,b], then a different generation 5 file [c], then generation 5 [a,b] again: nothing refused at any step; a file at the generation of a retirement is refused for that key; a stale generation is refused for retired keys and for hashes absent from the high-water set (HIGH, run). So "treat two files with one generation number as one file" is the right operator advice, and the control does not check it.
3. "Nothing claimed enforced that is only declared": I found no sentence that presents a declared limit as enforced. The new PR 374 sentence says the internal secret exists in that PR and "until that is merged and set nothing requires it" (HIGH: PR 374 defines FIELD_INTERNAL_SECRET and FIELD_INTERNAL_SECRET_SHA256 at operator_health.py:463-470 on its head). It leans on an open PR, so it becomes stale when 374 merges or is dropped (MEDIUM).

## C-893 conditions (mine) and C-845/C-850 residue
- C1 same-generation case declared: CLOSED (objection 2; cites check out: the only-higher-generation learning is operator_auth.py:1252-1256 and the `<` test is :1268 on main).
- C2 link from the field-core README: CLOSED (packages/field-core/README.md:38, a "Runbooks" section) (HIGH, git grep).
- C3 what "off" means and PR 374: CLOSED. The text now says off means no registry file and no true FIELD_OPERATOR_REQUIRE; `mode()` at operator_auth.py:282-288 returns ENFORCE for the flag, LOG_ONLY for a registry path, else OFF; `internal_routes_enabled` (operator_health.py:452-460) returns true only when mode is not OFF and a perimeter secret is set (HIGH, read).
- C4 range nits: not re-run beyond the cites in this delta (earlier C-893 table stands).
- The 404 sentence for the verify route now matches `internal_routes_enabled` (off, or no perimeter secret).

## Safety, authorship, overlap
Added lines: one address-shaped token, a loopback address with a port range placeholder in the Fly in-machine sentence (from the earlier commit, not an estate address); no flag value, build id, deploy status or credential (HIGH, sweep). Author and committer: the no-reply Don Hagell identity. merge-tree: no conflict with PRs 349, 352, 355, 369, 374, 379, 381, 383.

## Conditions
1. Change "open in PR 355" to name the real place (a card or the file itself). Non-blocking.
2. Re-read the PR 374 sentence when 374 lands or is dropped. Non-blocking.

Not verified: CI, the builder's GX10 result, the other cited line ranges beyond this delta.
