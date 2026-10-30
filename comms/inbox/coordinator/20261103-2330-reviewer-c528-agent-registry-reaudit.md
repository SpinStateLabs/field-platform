VERDICT: PASS WITH CONDITIONS on main 5808a5cd6186566a2233105beaf3913b1ae11e51

C-528 agent-registry standing re-audit (Lane 7). Scope: services/agent-registry api.py, store.py, models.py; the reads conformance-sentinel makes (engine.py:484-497): status, duplicate registration (PR 250: only 400 or 409 confirm a duplicate), and the card's "manifest hash".

CORRECTION TO THE CARD FIRST
There is no manifest hash. The registry stores a manifest_ref (a path) and field-core resolves it by file path with an mtime cache (clients.py:445-493); no hash is computed, stored or compared anywhere in agent-registry, conformance-sentinel or the resolver (grep: the only sha256 is the secret-fingerprint in redaction.py). Any "manifest hash" check named by the card does not exist [HIGH, grep].

OBJECTIONS FIRST
1. A path-plus-mtime reference lets the manifest change under a live agent with no record.
2. Id normalisation by regex only leaves confusable ids that the duplicate check treats as different.
3. A suite can be green while the id grammar is unpinned.

ASSUMPTIONS
A1 Tree = main 5808a5c, clean. A2 Real app via TestClient, temp store and manifest dir, made-up ids, operator layer OFF. A3 Probe results on the mtime cache hold where the filesystem keeps a set mtime (utime).

REASONING / RESULTS
1. Suite: agent-registry 304 passed [HIGH]. 13 hand mutants (12 + one re-run), 10 killed, 3 survive: (a) API-level retired check at api.py:322-328 removed: equivalent, the store enforces the same rule atomically (store.py:229-235) [HIGH]; (b) uppercase ids allowed on AgentCreate (models.py:52): survives, real (F-C528-1); (c) my first uppercase mutant hit AgentRecord only, which is behind AgentCreate: inconclusive, superseded by (b).
2. Killed: duplicate allowed, duplicate answered 422 instead of 409, store reactivation of a retired agent, retired frozen fields off, retired attest allowed, POST ref unchecked, PATCH ref unchecked, "invalid" treated as resolving, id regex unanchored, status change not ledgered.
3. Duplicate contract [HIGH, probe]: exact re-registration 409; re-registering a retired id 409; "A1", "a1 ", "a1\n", full-width, zero-width, "a1/../x", "-a1" are 422, which the PR 250 ruling does NOT count as a duplicate confirmation (correct: they are invalid, not duplicate).
4. F-C528-1 SURVIVOR, id case guard unpinned [HIGH, mutant]: AgentCreate pattern `^[a-z0-9]...` (models.py:52) widened to A-Z keeps 304 green. Without it "A1" and "a1" register as two agents. Severity LOW-MEDIUM. Fix: one test posting "A1".
5. F-C528-2, confusable ids accepted [HIGH, probe; LOW]: "a1." and "a..1" and "a_1" register as distinct from "a1"; a 5000-char id registers (no max_length). Sentinel and ledger key on the id string, so they are distinct identities. Fix: forbid trailing dot/consecutive dots and add max_length.
6. F-C528-3, stale manifest [HIGH, probe]: a manifest rewritten with different delegation scope but its original mtime restored (os.utime) is served from the cache with the OLD scope; a bumped mtime is read fresh (clients.py:475-480). Any tool that preserves mtime (cp -p, rsync -t, tar) leaves registry readers on the old manifest; with no hash there is no second signal. Severity MEDIUM. Fix: cache key on (mtime_ns, size, inode) at least, or store a content hash at registration and compare on read.
7. F-C528-4, manifest_ref may leave manifest_dir [HIGH, probe]: an absolute path and "../outside.yaml" both register (201) when the file is a valid manifest (clients.py:471-473, no containment check). Needs registry write authority, so LOW-MEDIUM; with no hash it also lets a reference point at any file on the host that validates.
8. F-C528-5, refusal body discloses the server path [HIGH, probe]: the 422 for an unresolvable ref echoes manifest_dir (api.py:139) and the ref. Content of an invalid manifest is NOT echoed (probe marker absent). Severity LOW.
9. F-C528-6, PATCH ref check only in ENFORCE [HIGH, probe + code]: with the operator layer OFF a PATCH to a nonexistent ref returns 200 (api.py:296-299 sits inside the enforce branch); README lists this as a LIMIT. Result is an agent whose kill path cannot resolve its manifest. Severity LOW-MEDIUM (documented).
10. Retired [HIGH, probe]: revive of a retired agent 409, rename of a retired agent 200 (name is open by design, models/store comments).

CONCLUSION: the status/duplicate/retired contract the sentinel reads is well pinned; identity grammar and manifest freshness are not. PASS WITH CONDITIONS: pin the id case guard (F-C528-1); decide a content hash or stronger cache key (F-C528-3); contain manifest_ref (F-C528-4).

What I did NOT do: no ENFORCE-mode (operator layer on) run; no /discover audit; no concurrency probe on add/update beyond the suite; no sentinel end to end; no cli.py; no GX10; no whole tools suite.
