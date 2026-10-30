# C-543: review of PR 317 (attestation conformance rate, half-up), Lane 10

Reviewed: PR 317 head c0f07da (`fix/attestation-rate-halfup-c138`; production change `conformance_percent` in services/attestation-reporter/src/attestation_reporter/engine.py, new test_conformance_rate_c138.py; one commit on a9dc4f3). Probe: 20261103-0200-design-c543-rate-probe-pr317.py (19 cases, a full sweep, error shapes).

VERDICT: PASS on c0f07da. The function is exactly half-up on every input I could construct, the signed pack keeps verifying, and one behaviour change needs a line in the docs (F-C543-1). Confidence HIGH (run, with an independent check).

## ASSUMPTIONS
1. The rate is `100 * ALLOW / (ALLOW + BLOCK + ESCALATE + shadow BLOCK + shadow ESCALATE)`, counts from the ledger (engine.py call site, line 518).
2. "Half up" means ties go to the larger value for non-negative inputs; the ledger cannot hold negative counts.

## Objections first (what could be wrong)
1. A signed figure changes value: for a window whose rate is an exact tie (1/16 = 6.25) a pack generated AFTER the merge says 6.3 where one generated before said 6.2. Both verify under their own signature (the verifier does not re-derive the rate), but a regenerated pack for a past window differs by 0.1 from the earlier one. Of 160 exact ties among all counts up to 200, the old `round()` differed on 80 (half). HIGH (run). Correct by the stated rule, and a documentation point, not a defect.
2. The `note` field, which is inside the signed pack, gains "; rounded half up to one decimal" on every conformance metric. A consumer that parses the note by exact text would break; I found none in the suite or the renderer (the HTML renderer escapes and prints the note, render.py:62), but I did not search consumers outside this service. MEDIUM.
3. Input contract: floats, strings and negative numbers are not validated. `conformance_percent(1.5, 16)` and a string raise TypeError; negatives return negative values (-6.3: half away from zero); `allows > total` returns 150.0. The only call site passes `int(...)` of ledger counts and a sum of them, so none reaches it; LOW.
4. The sentinel's own scorecard prints `f"{x * 100:.1f}%"` (conformance-sentinel measure.py, `_pct`): a float format, which resolves a tie by the binary value (6.25 prints 6.2). That is a different figure (scorecard catch and false-block rates over a seeded corpus), not this ALLOW share, so the two never print the same number for the same quantity: it does not matter to the signed figure. MEDIUM (read the function, not every use). D-31 (Don's call) stands for the display convention across public artefacts; I recommend half up everywhere with the rule printed, consistent with PR 313's reading.
Steelman: Python's `round()` on a float is a documented half-to-even on the binary value, so the old figure was "correct" by its own rule; the change is a convention fix for hand-recomputation (the same reasoning as the cost table).

## Results (the card's questions)
- Exactness: 1/16 gives 6.3, 3/16 18.8, 5/16 31.3, 1/80 1.3, 1/40 2.5, 1/3 33.3, 2/3 66.7, 0/N 0.0, N/N 100.0, huge counts (about 10^30) 100.0 (precision 60 digits is ample for any ledger).
- Independent check (not the PR's own method): integer half-up `(2000a + t) // (2t)` compared with the result for every a<=t<=400: 0 mismatches. A second sweep against a Decimal reference for t<=200: 0 mismatches.
- Zero total (and `None` total) returns None; the metric then shows "n/a — no verdicts in ledger" (read).
- JSON: 6.3 and 33.3 serialise as plain numbers (probe).
- Pack verify of old packs: the attestation-reporter suite (161 passed) includes the pre_f4 fixture verification; `tools/tests/test_environment_doc.py` 43 passed.
- Renderers: the only place the rate is printed is the metric (value and note) through render.py; no other formatter of this rate exists in the service (grep).
- 7 own mutants, each red: half-even (6 failed), half-down (10), precision 3 (5), back to float `round()` (6), zero-total guard removed (3), note text dropped (1), two decimals (16). The builder's 7 were not re-run.

## Findings
F-C543-1 LOW: document the change where the attestation pack is described (README or the pack's own note in the docs): "rates are rounded half up; a window with an exact tie may read 0.1 higher than a pack generated before <this change>". No code change.
F-C543-2 LOW: guard or document the input contract (`allows`, `total` non-negative ints) with a one-line assert or a docstring sentence; no live path reaches the bad shapes.
F-C543-3 INFO: D-31 is Don's: whether the sentinel scorecard should also print half up; it does not affect any signed attestation figure.

## What I did NOT do
Did not search consumers outside services/attestation-reporter for the note text. Did not run the builder's own mutants or the whole tools suite beyond the environment-doc file. Did not regenerate a real pack or run a live window. Did not verify the PDF path (the service renders HTML; no PDF renderer in src). Did not edit the PR.
