VERDICT: FAIL on 8eb5c87205347ff55acfe0ce3f2b6a21da796569 (same head and same verdict as my C-786; no new commit)  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-807, PR 371 at the narrowed head. The PR head is still 8eb5c87, the SHA I reviewed in C-786 (report reviewer-c786-pr371-manifest-ref-id-grammar.md); `git ls-remote`-equivalent check: the PR head I fetched equals 8eb5c87. So this report adds no new probes; it answers the card's three questions from the C-786 evidence plus the builder note (20261030-2000-builder-lane13-gx10-results-...).

OBJECTIONS FIRST
1. What was cut: the confinement of ABSOLUTE manifest_refs. Head 7fc03eb refused an absolute ref outside FIELD_MANIFEST_DIR; the builder's first GX10 run of 16 suites failed in seven suites (tools, field-agent, conformance-sentinel, delegation-authority, force-gateway, kill-switch, lifecycle-manager) because they register manifests by absolute temp path; the fix was to accept any absolute ref (api.py `_ref_is_inside_manifest_dir`: `if target.is_absolute(): return True`) and confine only relative refs. 8eb5c87's later GX10 line: 16 suites, 0 failed (builder's number; not verified by me). Confidence HIGH on what changed (diff 7fc03eb to 8eb5c87).
2. Does the cut weaken my C-786 findings: yes, it reopens the first two and the third stays: (a) an absolute ref outside the directory to a valid manifest is ACCEPTED (it was refused at 7fc03eb); (b) the existence oracle for absolute paths is back (nonexistent path answers "missing", an existing non-manifest file answers "invalid"; both at 8eb5c87, same as origin/main); (c) the new unbounded `path.read_bytes()` in the resolver is reachable through an absolute ref to a never-ending device file (MemoryError after 7 s under a 2 GB address-space limit; main answers "invalid" after 3.8 s without exception). Nothing since C-786 changes these. Confidence HIGH (observed in C-786).
3. Containment bypasses still open at 8eb5c87 (re-listed from C-786): absolute paths (open, by decision); stored refs not re-checked and checks made at registration only (open); everything else in the card's list is refused: `..` and `sub/../../x`, percent-encoded separators (treated as literal file names, refused as missing), symlinked file or directory pointing out, backslash forms, NUL, `file://`, `~`, a 5,000-character name, a symlink loop. Drive-letter spellings are ordinary relative names on Linux (refused as missing); Windows junctions not probed. Confidence HIGH on Linux.
4. The cut is a stated decision (comment in api.py) "and is a decision, not made here"; the builder did not re-run the Linux symlink mutant on 8eb5c87 (their note says so; I ran a symlink-escape mutant at 8eb5c87 in C-786: `resolve()` replaced by `absolute()` was KILLED).
5. Why the cut was needed is itself a finding for Don: seven suites and about 400 tests depend on registering manifests by absolute path outside the manifest directory; the estate's own form (/data/manifests/<id>.yaml) is absolute. If the estate's manifest directory is the same as FIELD_MANIFEST_DIR, an absolute ref inside it would pass a confining rule; the failures say the suites register outside it (temp directories). Option: confine absolute refs to FIELD_MANIFEST_DIR and move the fixtures (as commit 03157d1 did for two suites). Cost: seven suites' fixtures.

ASSUMPTIONS
A1 The C-786 evidence stands because the SHA is unchanged. A2 The builder note's GX10 numbers are theirs; I did not reproduce them.

REASONING / CHECKS
- Fetched PR 371 head: 8eb5c87 (equals the C-786 SHA). No commit since.
- Verdict logic: the C-786 conditions C1 and C2 (confine absolute refs or record Don's ruling and drop the claim; bound the resolver read) are both still open, so the C-786 FAIL on this head stands.
- No new commits, so no commit-identity or diff-scan change.

CONDITIONS (unchanged from C-786)
C1 (blocking) Confine absolute refs or record a ruling; fix the "missing" oracle for outside paths either way.
C2 (blocking) Bound the resolver read (size cap and regular-file check before read_bytes).
C3 (non-blocking) Re-check containment when a stored ref is resolved; test the OSError branch; list the routes that take an existing id.
C4 (coordinator) Rule on the seven-suite fixture move versus an open absolute rule.

NOT VERIFIED
Everything in C-786's list (GX10 full set, CI, Windows junctions, unlimited memory behaviour, FIFO behaviour, Python below 3.13).

CONCLUSION
The narrowing removed the absolute-path half of the containment and nothing replaced it; the existence oracle and the unbounded read stay reachable through absolute refs. FAIL on 8eb5c87, UNVERIFIED.
