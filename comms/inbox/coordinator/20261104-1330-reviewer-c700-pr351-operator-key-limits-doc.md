VERDICT: PASS WITH CONDITIONS on af1e7cc856ecfc6fa4064c7994dc07d34f356f85 (UNVERIFIED: cloud reviewer, docs read against source at that head; no run, CI not read)

Head matches the card. One commit on main; author and committer are the no-reply identity. One new file: docs/runbooks/operator-key-limits.md (+68). Docs only.

OBJECTIONS FIRST
1. Section 3 says the verify-hash use "leaves no record". Code says the route is never LEDGERED and never counted as a refusal (operator_health.py:57-63, :492-493 docstring). It does not say nothing records it: the break-glass attempt counter is incremented (operator_auth.py:1396-1403 note_breakglass(used=False)) and an HTTP service normally logs the request line. "No ledger record" is source-backed; "no record" is not. LOW-MEDIUM.
2. Section 3 says "a key hash is a SHA-256 of a high-entropy key, so this is not a practical way to recover a key". Nothing I read enforces key entropy: the verifier takes any 64-hex hash and compares SHA-256 of the presented key; I found no minimum length or entropy check in operator_auth.py. The statement is about how keys are generated in practice, not what the code enforces; a runbook that cites lines for every other claim cites none for this one. MEDIUM-LOW (claim above what code enforces).
3. Section 3 says "there is no further check" and "keep the route off the public edge". The shipped edge already refuses these routes from non-loopback clients (the edge block checked by PR 347 and its checker), which is the mitigation the runbook does not mention; the reader is told to do something the shipped proxy config already does, and is not told how to verify it. LOW.
4. The statement that restoring a stale .prev makes the key match "until a load at a higher generation is seen" is imprecise: retirement is learned when a file at a HIGHER generation than the restored one is loaded and lacks the hash, so a restore of the older file means the newer one is not seen again unless it is restored too. The runbook's advice (do not restore, or confirm with verify-hash) is right; the sentence about when the key stops matching is loose. LOW.
5. Section 2's "rows beyond that are dropped without a marker" holds for the own-parse slots event (operator_observer.py:196 slices the list; the payload built at :440-452 carries no total) but not for the health-based registry event, which records a row count (operator_observer.py:164). The runbook states it for "each event". LOW.
6. Line numbers are right "for main at the time of writing" and the doc says to re-grep; good, but the file will drift.

ASSUMPTIONS
A1 "Cites the line that says so" judged by reading each cited line at the PR head (which equals main plus this file). A2 No estate or deployment was consulted. A3 Citing a line "says so" counts only if the line states the claim, not merely nearby code.

REASONING (claim, source, result)
1. Retired-key memory resets on restart: operator_auth.py:1212 reads "Memory resets on a process restart (Declared, design section 11 row 10)". HIGH. "Learns only from loads this process makes": same comment, :1213-1215. HIGH.
2. Cap: MAX_RETIRED_HASHES = 4096 at operator_auth.py:1218. HIGH. "Oldest generations dropped first": operator_auth.py:1258-1261 sorts by generation and keeps the last 4096 (highest generations survive); the cited 1258-1260 is the start of that block. HIGH.
3. A retired hash in a file not above the removing generation is refused alone (403 on that slot): operator_auth.py:1205-1210. HIGH.
4. Observer "startup: true" first observation per ledger process: operator_observer.py:11-13. Cited fields: previous is None at :452 and :502; previous_bg at :411; previous_n at :466; startup at :486; all present as cited (paraphrased: not always literally "previous"). HIGH. Previous values in the observer's own memory: by the structure at :426-456 (self._slots, self._slot_rows). MEDIUM (I did not read the constructor).
5. MAX_WITNESS_ROWS = 256 at operator_observer.py:113 and the slice at :196. HIGH.
6. verify-hash: takes a hash, never a key, answers current/next/matchable_now (operator_health.py:57-63, answer at :466-500); gated by internal_routes_enabled (:452-458: armed layer AND a perimeter secret; otherwise 404); break-glass refused with 403 and counted as an attempt (:493-495, operator_auth.py:1396-1403). HIGH. "Never ledgered and never counted as a refusal": :63 and the verify answer docstring. HIGH.
7. Card C-54 proposes a second internal-only secret and it is not built: a search for FIELD_INTERNAL_SECRET in packages and services finds nothing. HIGH.
8. Diff scan: no estate address, flag value, build SHA, deploy status or credential; no key material; paths are repository paths. HIGH.

CONCLUSION
PASS WITH CONDITIONS. Every limit is real and its citation says what the runbook says, except the two soft claims in section 3 ("no record", "high-entropy") and the loose timing sentence in section 1. Conditions, none blocking merge:
- C1 F-C700-1: change "leaves no record" to "leaves no ledger record (it increments no refusal counter; request logs of the service and proxy are separate)".
- C2 F-C700-2: either cite where key entropy is guaranteed (the generation tool) or say "assuming keys are generated, not chosen".
- C3 F-C700-3/-4/-5: mention the shipped edge block; tighten the restore sentence; qualify the dropped-rows statement to the slots event.

FINDINGS
F-C700-1 LOW-MEDIUM, docs/runbooks/operator-key-limits.md section 3 ("leaves no record"). HIGH (against operator_auth.py:1396-1403 and the request path).
F-C700-2 MEDIUM-LOW, same section ("high-entropy key"): not enforced in operator_auth.py. MEDIUM (I did not read the key-generation tool).
F-C700-3 LOW, same section ("keep the route off the public edge"; omits the shipped edge block). MEDIUM.
F-C700-4 LOW, section 1 (timing of when a restored key stops matching). HIGH.
F-C700-5 LOW, section 2 (rows dropped "without a marker" is true of the slots event only, operator_observer.py:196 versus :164). HIGH.

NOT VERIFIED: the key-generation tool's entropy; the shipped edge configuration (read about, not read); how the service logs requests; CI.
