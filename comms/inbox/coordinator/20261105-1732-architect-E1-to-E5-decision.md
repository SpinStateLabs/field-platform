# DECISION E1..E5: Phase E (0/5), narrowest reading. Architect, 2026-11-05.

## Sources (HIGH, read on origin/main tasks/todo.md)
- Block "Phase E - the words" (main todo.md:1771-1842): E1, E2, E3, E4, E-gate = the five items.
- Phase G region (main todo.md:598-603; PR 629 `docs/phase-g-itemised`): a shorter Phase E summary adding live evidence per Enforced word, a declared-ledger, soak evidence and canary scope. It says Phase E is LAST.

## E1 reading (narrowest)
E1 = create ONLY `docs/capstone-evidence/v2-one-liners.md`. Its open input is closed: `docs/capstone-evidence/v2-one-liners-source.md` exists on main (verbatim v2 list, audit numbering 1-12). Not E1: README/ROADMAP edits (E2), STATE.md (E3), live catalogue evidence, the declared-ledger, soak evidence, canary demonstrations. Live status is written Declared with a date, since nothing is armed or deployed (G16 unrecorded). The live-evidence parts of the Phase G summary get their own later cards.

## The five items and done-when
- **E1** `v2-one-liners.md`. Done when: file exists; 12 rows in the audit's numbering; global line first: "both estates run pre-v1.2 images; every Enforced word is test/CI-proven; per-system estate status is Declared until redeploy"; each row gives old wording (cites the source file), new wording, Enforced/Declared split; each Enforced word cites `path::test_name` plus commit hash; REWORD rows give a reason; every qualifier in the E1 block of the plan appears verbatim; keyless rows say "not live-verified - needs ANTHROPIC_API_KEY". A script (the E-gate input) confirms each cited test exists at that commit and its assertion names the word.
- **E2** README/ROADMAP/service READMEs/docs per the main E2 block. Done when: README table has a "One-liner" column; counts quote `python -m pytest --collect-only -q`; a grep over service READMEs finds no `Declared only` row for an E1 Enforced word; "RACI-ready" is gone from the four named locations; IMPLEMENTATION.md section 8 scheduling table updated.
- **E3** STATE.md. Done when: "Current phase" and "Next action" rewritten for v1.2; `entrypoint.sh:10-11`, `fly.toml:1-3` and the STATE.md Fly "PRODUCT estate" / GB10 "burn-in (log_only)" lines no longer say that; the gate log has each phase's `run_demo` tail with wall times taken from recorded runs, none invented.
- **E4** todo.md Review section and `tasks/lessons.md`. Done when: Review section filled; one lessons line per Don correction recorded in the repo.
- **E-gate** Done when: full sweep (13 services + 2 packages) green on CI and the GX10 on the exact head; `run_demo.sh` exit 0; independent adversarial review of `v2-one-liners.md` against the tests it cites; STATE.md updated; summary to Don. The live-canary demonstration clause of the Phase G summary stays a later coordinator/verifier card; this gate does not claim it.

## Rationale, alternatives, risk
- Narrowest keeps E1 a document with mechanically checkable citations.
- Rejected: E1 including live evidence (cannot be met, nothing deployed); waiting for Don's list (the source file exists); folding E2-E4 into E1 (breaks the 0/5 count).
- Risk: Phase E is "LAST". Cards are queued under Don's delegation but must not mark a row live before G is armed; overclaiming is the failure the audit existed to catch. A renamed cited test breaks the script; pin commit hashes.
- Not verified: the audit file `tasks/audit-v2-12-systems-vs-production-build-2026-09-12.md` content (not read).
