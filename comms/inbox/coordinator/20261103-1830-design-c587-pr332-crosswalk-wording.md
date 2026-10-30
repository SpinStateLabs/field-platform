# C-587: review of PR 332 (crosswalk stale-claim wording, C-558), Lane 10

Reviewed: PR 332 head f9f90f7 (`docs/crosswalk-stale-claims-c558`, builder Lane 1; services/compliance-crosswalk mapping.py (FC-L-02 and FC-F-01 `evidence_kind`), README.md LIMITS bullet, new tests/test_declaration_only_wording_c558.py; 3 files, +57 -4; one commit on b929f12). It closes my C-542 finding (the one stale line).

VERDICT: PASS on f9f90f7. Every new statement is true of the code it names, no compliance claim is added, 7 of 7 mutants of mine go red, and the whole crosswalk suite passes. Confidence HIGH (run).

## ASSUMPTIONS
1. "True of the code" means checkable in `engine.py`, `EvidenceSources`, `LedgerClient.retention_check` and the git history.
2. The `evidence_kind` string is not part of any signed or hashed artifact (checked below).

## Objections first
1. Pinned prose can rot the other way: the tests pin that the evidence sources hold no federation or retention field, so if someone adds collection later the tests force a wording review (intended), but a green test would not notice a README that stays vague. LOW.
2. `evidence_kind` is a long parenthetical now; if a renderer truncates it the nuance is lost. No consumer of `evidence_kind` outside mapping.py in src (grep): LOW.
3. The README says `engine._evidenced` returns "declaration-only control"; the real string is "declaration-only control in v0.1" (engine.py, the end of `_evidenced`). Close enough as a quotation, and the test pins the full string. LOW wording.
Steelman: the previous sentence located the gap wrongly (it said enforcement is not built); this one says enforcement exists in the platform and the crosswalk does not read it.

## Results (the card's questions)
- Retention enforcement exists: ledger retention by rotation, apply, check, legal hold merged 2026-09-13 (commit 700301d); `LedgerClient.retention_check` is in field-core clients.py; the README cites exactly `GET /retention/check` and that method. HIGH.
- `EvidenceSources` fields: `registry_record`, `ledger_verify`, `ledger_event_types`, `tokens`, `governor_cap`: no federation or retention field; so the FC-F-01 text correctly does not claim crossing events. HIGH (read). Test 2 builds sources with every field present, including federation event counts in `ledger_event_types`, and the engine still answers declaration-only for both controls: the claim holds even in the most favourable case.
- Phase 4 phrase: removed ("no federation events until Phase 4" is gone; the federation broker is shipped).
- Compliance word discipline: the added text names no framework as satisfied; the only "compliance" in the diff is the test docstring's sentence "Nothing here claims compliance; the crosswalk never does" and module names. No `certified`, `guarantee`, `ensures`.
- No other stale copy of the old claims in the repository outside comms and lessons (grep for "retention enforcement", "no federation events", "crossing events": only the new text matches).
- `evidence_kind` consumers: none outside mapping.py in `src`; the regwatch hashes (`regwatch.py`) cover fetched source pages, not the mapping, so the wording change moves no signature or fingerprint. HIGH.
- Whole crosswalk suite: 357 passed, 5 skipped (matches the card).
- Mutants of mine, each red (the 4-test file): old FC-L-02 wording back; old FC-F-01 wording back; README naming a wrong route; README claiming the crosswalk evidences it; `EvidenceSources` gaining a retention field; `EvidenceSources` gaining a federation field; the engine's detail string changed. 7 of 7. The builder's 6 were not re-run.

## Findings
F-C587-1 LOW: quote the real string in the README ("declaration-only control in v0.1") or drop the quotation marks, so a reader grepping for it finds it.
No other finding.

## What I did NOT do
Did not run the whole tools suite. Did not check rendered pack output for the new `evidence_kind` text length. Did not re-run the builder's mutants. Did not edit the PR.
