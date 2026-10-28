# C-108 reviewer report: mutation round on packages/field-core/src/field_core/operator_health.py (main 45a36f5; unchanged by 0b44dee)

VERDICT: 65 mutants, 58 killed by the field-core suite, 7 survived. None of the 7 is killed by kill-switch, agent-registry, delegation-authority or lifecycle-manager suites either. Of the 7: 4 are real LOW test gaps, 3 are behaviourally equivalent.

OBJECTIONS FIRST
1. My mutator only generates `if` -> False/True (when the body raises/returns/continues) and single-operator comparison flips; arithmetic, call-argument and boolean-operator mutants are not generated, so "58 of 65" is not a coverage figure.
2. A mutant that survives the suites may still be pinned by an integration test outside the five suites I ran.
3. The first pass ran with the field-core suite only; the service suites were added after.

ASSUMPTIONS
1. Main 45a36f5 (operator_health.py has no diff to a91b819 or to 0b44dee's later base) in `~/ff-work/wt-fieldrev-70`; harness fixed (honours exported PYTHONPATH; see the C-67 report). [HIGH]
2. Pass A: whole file (lines 1-726) with `packages/field-core/tests`; pass B: each surviving line re-run against `services/{kill-switch,agent-registry,delegation-authority,lifecycle-manager}/tests`. [HIGH]

REASONING
1. Pass A: 65 mutants, killed 58, survived 7 (log `~/ff-work/c108.log`). [HIGH]
2. Pass B (log `~/ff-work/c108b.log`): every one of the 7 survives in all four service suites. The four service runs also list extra survivors on the same lines (L165 `if->True`, L531 `if->True`, L699 `if->False/True`): those were killed by field-core in pass A, so they are not new gaps. [HIGH]
3. Survivors, with context (operator_health.py):
   - L165 `if value is None:` -> False in `shown_label`: None becomes NOT_SHOWN instead of None; no test passes a None label. LOW gap (F-C108-1). [HIGH]
   - L174 `len(text) <= MAX_ERROR_LEN` -> `<` in `_clip`: the exact-200-character boundary is unpinned. LOW gap (F-C108-2). [HIGH]
   - L340 `if ledger is None:` -> False in `note_refused`: EQUIVALENT for the counter: with `ledger` None the code reaches `ledger.append` in `_go` (:368), the AttributeError is caught at :369 and `dropped_records` is still incremented; only a warning log and a thread differ. It means the C-52/F-C40-1 explicit branch is redundant, not that a drop goes uncounted. [HIGH]
   - L531 `if not sys.platform.startswith("linux")` -> False: EQUIVALENT on the Linux test host (branch not taken); the non-Linux path (clock-sync None) is unpinned on Windows/macOS. LOW (F-C108-3). [HIGH]
   - L635 `exp < expiry[0]` -> `<=` in `rotation_state`: on equal expiry the reported soonest-expiring operator id changes; ties untested. LOW gap (F-C108-4). [HIGH]
   - L639 `created < oldest` -> `<=`: EQUIVALENT (same value assigned on a tie). [HIGH]
   - L699 `len(body) > MAX_VERIFY_BODY` -> `>=` (MAX_VERIFY_BODY = 1024, :434): a body of exactly 1024 bytes is accepted today and would be 413 under the mutant; boundary untested. LOW gap (F-C108-5). [HIGH]
4. Requested functions: `note_refused` (L329-381 region): killed except the equivalent L340; `_admit_record`: all mutants killed (no survivor in its range); `_record_unauthenticated`, `health_fields`: no survivor reported; `rotation_state`: L635 survives, L639 equivalent. [HIGH on survivor lists, MEDIUM that "no survivor" means well-pinned given objection 1]

CONCLUSION
operator_health.py is well pinned for what the generator can mutate: 58/65 killed, 3 equivalent, 4 LOW boundary/None gaps. Suggested single tests: `shown_label(None)`, `_clip` at 200/201 chars, two operators with equal `key_not_after`, a 1024-byte and 1025-byte verify-hash body. Not done: arithmetic/argument mutants.
