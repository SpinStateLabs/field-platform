# C-542: stale TODO, FIXME and "not yet" comments in packages/ and services/ src (read-only), Lane 10

Scope: `packages/*/src` and `services/*/src`, `.py` and `.sh`, main at the time of writing. Two greps: (1) TODO, FIXME, XXX, HACK, "not yet", NYI, placeholder, "for now", temporary, stub, "follow-up", "future work" and similar (25 hits, raw list in 20261103-0400-design-c542-todo-comments-raw.txt); (2) planned-work phrasing ("not built", "not implemented", "planned", "roadmap", "deferred", version numbers; 17 lines, read). No fix proposed, per the card.

VERDICT: the source is clean of literal markers: 0 TODO, 0 FIXME, 0 XXX, 0 HACK. Of the roughly 40 lines read, 9 are statements about unbuilt or pending work; 1 is STALE, 8 are still true. The rest are ordinary uses of "not yet" or "placeholder" (a state, not a promise). Confidence HIGH for the counts, MEDIUM for the "still true" ones (checked against the README, STATE and the commit that would have made them stale, not against running behaviour).

## ASSUMPTIONS
1. "Stale" = the statement says something is not built, and a merged commit built it. "Still true" = no merged work contradicts it.
2. Commit dates (git) order claims against the work that could invalidate them.

## Objections first (limits of this audit)
1. A grep finds markers, not promises written in prose ("when X lands", a docstring that describes a plan). I read a second pass of planned-work phrasing but cannot prove none was missed.
2. `.md` docs, tests and tools are outside the card; a stale claim in a README that repeats a source comment is reported only where I saw it.
3. "Still true" for a statement about the product (e.g. an unimplemented flag) needs the code path, which I read only where cited below.

## STALE (1)
- services/compliance-crosswalk/src/compliance_crosswalk/mapping.py:279, `evidence_kind="manifest declaration (retention enforcement not built)"` for FC-L-02 (and the same words in services/compliance-crosswalk/README.md:300, "no retention enforcement"). The claim was written 2026-08-08 (ae990ba). Ledger retention by rotation, with apply and check and legal hold, merged 2026-09-13 (700301d: `GET /retention/check`, field-core `LedgerClient.retention_check`, the attestation-reporter and lifecycle-manager consumers). Retention enforcement IS built; what remains true is that the CROSSWALK control still only reads the manifest declaration and does not consult `/retention/check` (engine.py:174 keeps FC-L-02 declaration-only). The sentence misstates where the gap is. HIGH.
- Possibly related, README.md:300 "FC-F-01 ... no federation events until Phase 4": the federation broker is shipped (Phase 4 in ARCHITECTURE); whether the crosswalk reads its events I did not check: LOW confidence it is stale.

## STILL TRUE (8)
- services/compliance-crosswalk/src/compliance_crosswalk/api.py:43-46 ("this service does not yet make that registry-lookup-then-resolve call ... Optionality by agent_id is NOT built ... a plan-assigned D4 deliverable that D4 shipped without — open"). Written 2026-09-12 (f732a09); README:57-58 repeats it; no card in the queue builds it (grep of TASK-QUEUE.md). Still true and an open DECISION (build or move), not a TODO: the text itself says it was put to the plan owner. HIGH.
- services/compliance-crosswalk/src/compliance_crosswalk/mapping.py:160, :284, :297, :329 ("third-party/value-chain articles not yet ingested", "retention duration (Art. 19) not yet ingested", "deployer-obligation articles not yet ingested", "registration articles not yet ingested"): the entries are `pending-*` by design and the README says 16 of 52 entries are cited (README.md:296-297), ISO 42001 entirely pending; no merged card ingests those articles. Still true.
- packages/field-core/src/field_core/operator_health.py:566 ("K4 is not implemented by any merged slice, every expired key is refused (R1), so it is always false here"; `key_grace_active`). Written 2026-10-27 (c8ecba7). K4 appears elsewhere only as a comment (rotation_events.py:100). Still true.
- services/lifecycle-manager/src/lifecycle_manager/api.py:370 ("None ... = the retention policy is not checked. Deliberately not built here from the environment"): a stated design choice, current.

## NOT markers (ordinary language, no action)
`not yet cleared` (compliance-crosswalk cli.py:251, :299: a regwatch state), `ledger not yet written` (sealed-ledger cli.py:99), `written, not yet in the cache` (store.py:1884), `not yet issued`/`not yet expired` (incident-replay engine.py:194, :434), `_walk_placeholders` and `_has_placeholder` (field-core validation.py, crosswalk engine.py: a feature that rejects placeholder values), `placeholder operators file` (sealed-ledger operator_observer.py:15: an attack described), `planned` in claude-approver core.py:675-722 (a local variable), "a later" in kill-switch api.py:529, store.py:902, :1270, :1601 (ordering of events), SDK version strings in claude-approver (v2.3.0 literals: a pinned dependency fact, matches the constraint pin).

## Observation
All real "unbuilt" statements are concentrated in the crosswalk (6 of 9), which is also the service whose README calls itself "Declared only" for mapping correctness: the code is honest about its gaps. The one stale line is a wording error about WHERE the gap is, not a hidden TODO.

## What I did NOT do
Did not scan `.md`, tests, tools, the demo or the Fly files. Did not run any code path. Did not check whether the crosswalk reads federation events (the Phase 4 remark). Did not open a card or edit any file; a builder card for the single stale line (reword FC-L-02's evidence_kind and README:300) is the obvious follow-up.
