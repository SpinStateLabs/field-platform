# Reviewer (lane B, kill-switch): PR 516 (scout P-8) tests pin `_scrub` so URLs with credentials never reach a report or the ledger

**Verdict: PASS WITH CONDITIONS on head `e5baf6e8571e875dd19259bd95b0bc36d00e978d`.** HIGH CARE (credentials, kill path). Head unchanged at start and end; base is current main (diff is the one new file, +77); 1 commit, Don Hagell noreply on author and committer. Tests only, not built by this lane.

Source under test (HIGH, read): `kill_switch/api.py:111` `_URLISH = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://\S+")` and `api.py:309-312` `_scrub(text, limit=200)` = `_URLISH.sub("<endpoint>", str(text))[:limit]`.

## Objections first
1. `_URLISH` needs `://`: a scheme-less `host:port/path?token=...` is not replaced. The PR pins this as a known limit (a test says so) and does not widen it; httpx names a URL with its scheme, so the signal path is covered, but a credential in other free text is not (author's own caveat, accepted).
2. The regex stops at whitespace, so a URL followed by punctuation or inside quotes loses the whole run up to the next space: safe direction (over-redacts).
3. Truncation after substitution is the one ordering that matters: a cut inside `https://` before substitution would leave a fragment; pinned (S4 below).

## Measured (GX10 ~/ff-work/wt-ln516, relative PYTHONPATH incl. sibling service src, own venv, python -B)
New file 10 passed. CI at read: see Conditions. 16-suite not run by me.

## Mutants (25 rows on api.py; source restored, worktree clean)
| Behaviour pinned | Killed | Survived |
|---|---|---|
| S1 every `scheme://` run is replaced wholesale | 5 | 3 (1 equivalent: a lazy-to-whitespace regex; 1 invalid: a no-op `.replace`; 1 gap: a scheme with digits or `+` such as `git+ssh://` or `s3://` is not matched by `[a-z]*` and no test uses one) |
| S2 text with no URL is unchanged | 2 | 2 (gaps: `.strip()` and collapsing double spaces pass; no test has edge whitespace) |
| S3 a non-string is stringified | 4 | 0 |
| S4 truncation happens AFTER substitution | 4 | 0 |
| S5 the 200 limit is honoured | 5 | 0 |
Totals counted from the table: killed 5+2+4+4+5 = 20; survived 3+2+0+0+0 = 5; 25 rows. Of the 5 survivors, 1 is equivalent, 1 is my invalid mutant and 3 are real gaps. S1 and S2 are below the 4-kill bar only because of those.

## Conditions
- C1: CI 7/7 SUCCESS on this exact head (read value is in the line above this report's header command).
- C2: GX10 16-suite 16/16 on a head containing main (tests only; light run acceptable).

## Findings (non-blocking; new PR only)
- F-516-1 LOW: add a `git+ssh://` and an `s3://` string (S1), and leading/trailing and doubled spaces (S2).
- F-516-2 INFO: the scheme-less limit (objection 1) is a decision for the kill-switch owner; the test that pins it will fail if someone widens `_URLISH`, which is the intended signal.
