VERDICT: C-691 PASS WITH FINDINGS on af1e7cc856ecfc6fa4064c7994dc07d34f356f85 (PR 351). Every cited line exists and says what the runbook says it says; nothing is claimed as enforced that is only declared. Two statements are stronger than the code supports and two limits are understated. No estate address, flag value, build SHA or deploy status in the file. Covers C-700 (same text; see 20261104-1830-design-c700-coverage.md). Read-only; UNVERIFIED on any estate.

## Objections first
1. "ITS USE LEAVES NO RECORD" IS TOO STRONG (docs/runbooks/operator-key-limits.md, section 3). The code says the route is never ledgered and never counted as a refusal (operator_health.py:57-63, :484). Whether the service's ordinary request log records the call, or the edge's, I did not check. A break-glass question IS counted (`oa.note_breakglass(used=False)`, operator_health.py:~491, observed), which the runbook states. Reword to "no ledger event and no refusal count". MEDIUM.
2. SECTION 3 DISMISSES THE ORACLE ON HASH ENTROPY ONLY. "A key hash is a SHA-256 of a high-entropy key, so this is not a practical way to recover a key." The oracle also confirms that a candidate KEY (hashed by the caller) is valid, silently, with no refusal count and, as far as I read, no rate limit. That is safe only while keys are high-entropy, which depends on how keys are issued (not checked). The runbook states the entropy as a fact; I could not verify it from the files I read. State the assumption. MEDIUM (reasoned), LOW on exploitability.
3. THE ANSWER DISCLOSES MORE THAN THE RUNBOOK LISTS. The route also returns the registry format, generation and a file-hash prefix (docstring, operator_health.py:467-483). The runbook names only current/next/matchable_now. A reader sizing the exposure of the perimeter secret misses the generation and file-prefix disclosure. LOW-MEDIUM.
4. SECTION 1 UNDERSTATES THE CAP. It says the table is capped at 4096 and the oldest generation dropped first (operator_auth.py:1258-1259, observed), but not the consequence: a dropped retired hash is accepted again if re-presented. It lists restart as the only way a retired key matches again. See my C-690 note, objection 2. MEDIUM.
5. SECTION 1 CONSEQUENCE IS LOOSE. "until a load at a higher generation is seen": the memory learns a hash only from a load at a higher generation that LACKS the hash (operator_auth.py:1247-1257). A higher file that still carries it retires nothing. LOW.
6. SECTION 2 WORDING: "the field is `previous is None` at :411, :452, :466 and :502": the variables are `previous_bg` (:411), `previous` (:452, :502) and `previous_n` (:466); :486 uses a precomputed `startup`. Correct citations, loose wording. LOW.

## Citation check (read at the PR head; grep -n)
| Cited | Found | Match |
|---|---|---|
| operator_auth.py:1212 "Memory resets on a process restart" | :1212 | yes |
| operator_auth.py:1218 MAX_RETIRED_HASHES = 4096 | :1218 | yes |
| operator_auth.py:1258-1260 oldest generations dropped | :1258-1260 (len check, sort, clear) | yes |
| operator_observer.py:13 "startup: true" first observation | :13 | yes |
| operator_observer.py:411, :452, :466, :486, :502 | all five hold a `startup` key | yes (wording, item 6) |
| operator_observer.py:113 MAX_WITNESS_ROWS = 256 and :196 | :113 and :196 (`[:MAX_WITNESS_ROWS]`) | yes; the slice drops rows with no marker (observed) |
| operator_health.py:57-63 verify-hash docs | :57-63 | yes |
| operator_health.py:452-456 internal_routes_enabled | :452-457 | yes |
| operator_health.py:467-500 answer | :467 onward | yes |
| "C-54 proposed, not built" | queue: C-54 CLAIMED plan-only, no PR or main commit | yes at this time |
HIGH on every row (observed).

## Declared versus enforced
Section 1 and 2 describe in-process memory and say "limit, not a defect". Section 3 describes a route that exists and is gated by the perimeter secret only; it says "no further check". Nothing is described as enforced beyond what the code does. The only advice that depends on a facility is "confirm with the verify-hash route that the retired key's hash is no longer `matchable_now`": after a restart the memory is empty, so a restored stale file reports the retired key as matchable, which is the signal the runbook wants. HIGH (reasoned from the docstring, not run).

## Public-safety scan of the added file
Regex for IPv4, 40-hex SHAs, home paths, webmail, and deploy-status phrases: no hits. Only generic "perimeter secret"; no value. HIGH on the scan, MEDIUM on completeness (regex).

## What I did NOT do
- Did not run the service or the verify-hash route.
- Did not read the access-log configuration (objection 1) or how keys are issued (objection 2).
- Did not check cards C-20 and C-34 exist and say what the runbook claims.
