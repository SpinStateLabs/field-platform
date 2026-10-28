# R-15 reviewer report: attestation-reporter figures recomputed from source (main 444e49b)

VERDICT: every ledger-derived figure and the three token figures I recomputed independently match. Two LOW findings: the conformance percentage rounds half-to-even, and one naive `expires_at` crashes the whole pack.

OBJECTIONS FIRST
1. A differential test against my own reading of the figure definitions can share my misreading; the definitions were taken from the engine's own notes.
2. A synthetic ledger is not the live ledger: the live-estate figures were not recomputed (live estates are out of my remit).
3. I did not recompute the integrity, retention or agent-count figures (they come from other services' answers, not derived here).

ASSUMPTIONS
1. Main 444e49b; probe files in `~/ff-work/r08a/services/attestation-reporter/tests/` (deleted after the run, not committed). [HIGH]
2. Window semantics as documented in `window.py` (both bounds inclusive; quarter = first instant to last microsecond UTC). [HIGH]

REASONING
1. Differential 1, ledger-derived figures: a hand-chained ledger of 400 events (13 event types including noise, agents including both canaries and `None`), timestamps drawn from: 1 microsecond before/at/after the quarter start, 1 microsecond before/at/after the quarter end, random in-window instants, each written as UTC, `Z`, `+01:00/+03:00/+05:00`, `-04:00/-08:00`. Quarter 2026-Q3. I recomputed independently (my own datetime parse, canary exclusion, set sizes): all 15 figures match: ALLOW, BLOCK, ESCALATE, shadow BLOCK, shadow ESCALATE, kill-switch activations, drills, federation allowed/blocked, orphans, re-attestation sweep events and distinct agents, expiring-authority sweep events and distinct tokens, and the canary gate row (sum over both canaries). 0 mismatches over 138 in-window governance events. Boundary and offset handling is correct. [HIGH]
2. Conformance rate: independent value with half-up decimal rounding equalled the reporter's value on this data (15.8). [HIGH]
3. Differential 2, token figures (a fake delegation client returning crafted tokens, `now` fixed): expiring-in-30-days counted exactly `now`, `now+30d`, a `Z`-suffixed expiry; excluded `now-1us`, `now+30d+1us`, a revoked token and a canary token: 3 of 3 as expected; issued 6 (8 crafted minus the naive one minus the canary) and revoked 1 as expected; the canary exclusion is stated in the note. [HIGH]
4. LOW, F-R15-1: `round(100 * allows / total, 1)` (engine.py, conformance rate) is Python's round-half-to-even on a float: 1/16 -> 6.25 -> 6.2 (half-up 6.3), 5/16 -> 31.25 -> 31.2 (31.3), 3/16 -> 18.75 -> 18.8, 7/16 -> 43.75 -> 43.8. The note prints the fraction, so a reader can recompute, but the displayed digit differs from the usual convention on exact ties (error at most 0.05 percentage point). Use `Decimal` with a stated rounding mode. [HIGH on the values]
5. LOW, F-R15-2: a token whose `expires_at` has no offset makes the "Authorities expiring within 30 days" transform raise `TypeError: can't compare offset-naive and offset-aware datetimes`; it is not caught per metric, so the whole `build` fails instead of marking that one metric unavailable. Fails closed (no wrong figure) but one bad token takes down the pack. Whether the delegation service can ever serve a naive `expires_at`: not probed. [HIGH on the crash, LOW on reachability]
6. Not recomputed: integrity (verification answer), retention policy and offending count, agents registered/active/killed, open spend escalations (they are `len()`/pass-through of the other services' lists; the canary exclusion is applied by `_without_canaries`). [HIGH]

CONCLUSION
No wrong figure found. F-R15-1 (tie rounding) and F-R15-2 (naive expiry crash) are LOW. A differential test like this one (400 random boundary events vs an independent recompute) is worth adding to the suite; I can supply the probe.
