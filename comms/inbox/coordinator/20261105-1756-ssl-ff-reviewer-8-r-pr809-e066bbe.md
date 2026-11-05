# Review R-PR809-e066bbe — PR 809 (agent-registry: sole manifest_ref / empty-domain patch tests)
Head reviewed: e066bbe6b2103648cb2efe738283fa16e1265ba0. Stacked on #786 head 736ae7ee (= pr809~1, verified by rev-parse, HIGH); not on main. Only commit e066bbe6 is this PR's own.

## VERDICT: PASS (conditional on #786 landing first; this PR carries no source change)

## Checks
1. Identity: both commits (736ae7ee from #786, e066bbe6) author AND committer Don Hagell 13129187+dhagell noreply (HIGH).
2. .github/: no change (HIGH). Own commit: one test file, 1+/1-, two parametrize cases added: `{"manifest_ref": "manifests/invoicing.yaml"}`, `{"domain": ""}` (HIGH).
3. Tests on head: test_empty_patch_s8 13 passed (HIGH).
4. Mutants on the validator `_at_least_one_field` (models.py), 7 run, 7 killed (counted from table):
| # | Mutant | New tests | Old tests (pr809~1) |
|---|---|---|---|
| M3 | `is None or not getattr` (falsy counts as empty) | killed | survives |
| M3b | `all(not getattr ...)` | killed | not run |
| M6 | manifest_ref ignored in check | killed | survives |
| M7 | domain ignored | killed | not run |
| M8 | `any` instead of `all` | killed | not run |
| M9 | validator never raises | killed | not run |
| M10 | status ignored | killed | not run |
M3 and M6 confirmed to survive the pre-PR test file and die on the new one, so the new cases add real pins (HIGH).
5. Not verified: full agent-registry suite result (output truncated in my run, no failure seen in the visible part); GX10 16/16; behaviour decision in #786 (Don's OK on empty-PATCH 422) is out of scope here.

## Conditions
1. Land only after #786 (reviewer-10's conditions, incl. Don's OK) or rebase onto main once #786 merges; a re-review of identity/patch-id would then be enough.
Head frozen at e066bbe6.
