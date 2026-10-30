VERDICT: PASS WITH CONDITIONS on 7fc03eb (the carded head, containment as written); FAIL on 8eb5c87205347ff55acfe0ce3f2b6a21da796569 (the PR head now)  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-786, PR 371 (agent-registry id grammar, manifest_ref containment, content-keyed manifest cache; C-635). The card names 7fc03eb. The PR head is now 8eb5c87 (03157d1 tests, 8eb5c87 src): its commit message and comment say absolute refs are no longer confined, because confining them failed 400 tests in six services on the GX10. Each verdict applies to its own SHA only. My probes ran at both.

OBJECTIONS FIRST
1. At 8eb5c87 an absolute manifest_ref anywhere on the server is accepted (api.py, `_ref_is_inside_manifest_dir`: `if target.is_absolute(): return True`). Probe with a valid manifest outside FIELD_MANIFEST_DIR: absolute path ACCEPT at 8eb5c87, REFUSE (missing) at 7fc03eb. So the card's "absolute paths" bypass is open at the head. Confidence HIGH (observed). The change is a stated decision, not an accident (comment, api.py); it still reopens the card's question.
2. At 8eb5c87 the existence oracle that F-C528-4 closed is back for absolute refs: a nonexistent absolute path answers reason "missing", an existing non-manifest file (a system text file) answers "invalid". The distinction tells a caller whether a file exists on the server. Same on origin/main (probe: missing / invalid), so not a new regression against main, but it contradicts the stated purpose of this PR. At 7fc03eb every outside absolute path answers "missing" (probe: nonexistent, an existing system file, /dev/zero all "missing"). Confidence HIGH.
3. New unbounded read. clients.py (this PR) hashes with `path.read_bytes()` before parsing. At 8eb5c87 an absolute ref to a never-ending device file (/dev/zero) ran 7.3 s under a 2 GB address-space limit and raised MemoryError out of the check; on origin/main the same ref answers "invalid" after 3.8 s with no exception. With no limit the process would grow until killed. Registration needs the perimeter key, so this is an authenticated denial of service, not an anonymous one. At 7fc03eb the registration path refuses an absolute outside ref before any read, so the path is closed there; the resolver itself (every reader, stored refs) still has the unbounded read. Confidence HIGH on the behaviour, MEDIUM on the process-level impact (I did not run unlimited).
4. Stored refs are not re-checked ("Refs already stored are not re-checked", api.py comment) and the check is made at registration only, so a symlink changed after registration, or any ref stored before this PR, is read by every service through field_core.clients.ManifestResolver without containment. The resolver itself is not confined. Confidence HIGH that it is unchecked; impact depends on who can write the manifest directory (not in source).
5. Id grammar migration: only NEW ids are checked (models.py comment: "a row written before it keeps working"). Existing ids that the new grammar refuses (trailing or doubled separator, longer than 64) stay valid and are still accepted on every route that takes an id as a path parameter; I did not enumerate which routes validate. Confidence MEDIUM.
6. A refused relative ref is reported as "missing" even when the cause is containment, which is the intended non-oracle; the empty-string ref is ACCEPT (it means "no ref"). Not a defect.

ASSUMPTIONS
A1 Card scope: bypasses in manifest_ref (.., encoded separators, symlinks, absolute paths, drive letters), id edge cases (Unicode, length, case), migration. A2 FIELD_MANIFEST_DIR resolves as the registry process sees it. A3 Linux sandbox; drive-letter paths are ordinary relative names on Linux.

REASONING / CHECKS
- Containment probe at both heads (valid manifest inside and outside the directory, symlinks, via unresolvable_manifest_ref): relative inside, sub/in.yaml, in-directory symlink, "sub/../ok.yaml": ACCEPT at both. "../outside/x", "sub/../../outside/x", symlinked file out, symlinked directory out, "%2e%2e%2f...", "..%2f...", backslash "..\\", "C:\\x.yaml", NUL, "file:///...", "~/x", "//etc/passwd" (7fc03eb: missing; 8eb5c87: invalid because it is absolute and exists), 5000-character name, symlink loop: REFUSE at both (symlink loop "missing" on Python 3.13; older versions raise RuntimeError from resolve(), which the `except (OSError, ValueError)` would not catch: I did not test that; the service requires 3.11+).
- Absolute: inside ACCEPT both; outside valid manifest REFUSE at 7fc03eb, ACCEPT at 8eb5c87.
- Id grammar (AgentCreate, models.py, both heads identical): accept a, a1, a.b, a_b, a-b, a.b-c_d, 1.2.3, 0, exactly 64 characters; refuse a1., a..1, a--b, a-_b, -a, .a, uppercase, é, full-width letters and digits, Arabic-Indic digit, zero-width space, "a\n", NUL, space, slash, "%2e", 65 characters. HIGH.
- Tests at 8eb5c87: agent-registry 339 passed; field-core test_manifest_cache_c635 4 passed.
- Mutants at 8eb5c87 (restored, nothing committed): confusable-id validator off KILLED; max length 65 KILLED; containment check off KILLED; relative_to dropped KILLED; resolve() replaced by absolute() (symlink escape) KILLED; manifest_dir echoed again KILLED; cache returns stale regardless of content KILLED; OSError no longer caught SURVIVED (untested on this interpreter; see above). 
- Commits: 3, author and committer Don Hagell no-reply. Diff scan: no address, flag value, credential or deploy status.

CONDITIONS
C1 (blocking at 8eb5c87) Either confine absolute refs (and migrate the six services' test fixtures, as 03157d1 did for two) or record Don's ruling that absolute refs stay open and drop the claim that containment is closed; with the ruling, objection 2 still needs the "missing" answer for every outside path.
C2 (blocking) Bound the read in the resolver (a size cap and a regular-file check before read_bytes), so /dev/zero and a FIFO cannot reach a read.
C3 (non-blocking) Re-check containment when a stored ref is resolved, or document the registration-time-only check.
C4 (non-blocking) Add a test for the OSError branch or remove it.
C5 (non-blocking) List which routes take an existing id and confirm none now rejects a legacy id.

NOT VERIFIED
GX10 full set, CI by run id, the six services' suites (400 tests said to fail on a confining version), unlimited memory behaviour, FIFO behaviour (not run), Python below 3.13.

CONCLUSION
7fc03eb confines both relative and absolute refs and the id grammar is tight; PASS WITH CONDITIONS there (C3-C5, plus C2 for the new read). 8eb5c87 deliberately leaves absolute refs open, which reopens an existence oracle and, with the new unbounded read, a memory-exhaustion path: FAIL until C1 and C2 are settled. UNVERIFIED.
