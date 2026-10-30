# C-612: second read of PR 332 for compliance-claim sentences, Lane 10

Read: PR 332 head f9f90f7 (the crosswalk wording of the declaration-only controls). Read-only. My first review is C-587 (PASS); this read looks only for sentences that could be read as claiming compliance (lessons rule: "Never claim compliance/certification", tasks/lessons.md:20).

VERDICT: PASS, agreeing with C-587. No sentence in the added text asserts that any control, the platform or an estate satisfies a framework. One phrase deserves a softer verb (F-C612-1, LOW). Confidence HIGH (all added text read).

## ASSUMPTIONS
1. "Reads as a compliance claim" includes assurance wording (enforced, satisfied, meets, guarantees), not only the word "compliant".

## Objections first
1. "The enforcement exists in the platform" (README bullet) can be heard as "retention is enforced to a standard". What it says is that the ledger has a retention apply/check built (2026-09-13). The word "enforcement" next to a framework-mapping table invites the stronger reading. LOW.
2. `evidence_kind` strings are short labels shown in a table; a reader may skim "manifest declaration only" without the clause that follows. Both strings are negative statements ("not read by this control"), so a truncated read still understates. LOW.
Steelman: the PR's purpose is to remove a sentence that implied a gap in the platform and to say what the crosswalk itself does not read; it adds no positive assertion about any framework.

## Results
- The added README bullet: "declaration-only in this service ... neither the federation broker's crossing events nor the ledger's retention check ... is read here ... this crosswalk does not evidence it, and says so rather than claim it." Negative, factual, no framework named.
- The two `evidence_kind` strings: "manifest declaration only (federation-broker crossing events are not read by this control)" and "manifest declaration only (the ledger's retention check is not read by this control)": negative.
- The new test file's docstring says "Nothing here claims compliance; the crosswalk never does": a statement of rule, no claim.
- Banned-word scan of every added line (compliant, certified, guarantee, ensures, satisfies, meets): the only hit is "compliance" in that docstring and the package name.
- The wording does not appear in any pack output: `evidence_kind` is read only in mapping.py (no other src consumer), so no signed or rendered pack carries the new text; the pack's own governance statement (evidence_pack.py:3-4, "this module never asserts that any control satisfies any framework") is unchanged.

## Findings
F-C612-1 LOW: say "the ledger has retention rotation, apply and check built" instead of "the enforcement exists in the platform" (what the code does, no assurance word).

## What I did NOT do
Did not re-run the mutants or the suite (C-587 did: 357 passed, 7 of 7 mutants red). Did not read docs outside the PR. Did not edit the PR.
