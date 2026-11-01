# Builder Lane 1: PR 368 merged into PR 380 (Don: merge now)

New head of PR 380 (`claude/vibrant-mendel-vjdfue-tier2`): 24d5482b1425a70854e02c5ceabe958df9b73704, a normal fast-forward from 60af743. The merge commit is 9793de3 (parents 60af743 and 37c1916 = PR 368's head at the time; PR 368's branch was not touched). Four fix-up commits follow it (70382227, ec69daf9, ac8444e4, 24d5482b). No rebase, no force-push. Not done: GX10 run; GitHub CI not read on the new head (this push triggers it).

## The four resolutions
1. `tools.py` (production code, the one to read first). PR 368's single-segment pattern on every body or form property named `id` or `*_id` (schema, plus `check_body_ids` at run time) now applies to all tiers. Tier 2 keeps the registry's own agent_id rule for check and crossing (`AGENT_ID_PATTERN`, C-1065) and the 200-character cap. `check_body_ids` runs in `_call` BEFORE the tier split, so before any intent row or rate slot. It says "argument refused" for Tier 1 (PR 368's pinned wording) and "arguments refused" for Tier 2 (the wording this branch's tests pin): one parameter, `message`. Not a contradiction between the two sides' tests: different tiers, same check.
2. `tests/test_route_coverage.py`: PR 368's literal route-set pins follow this branch's rulings: Tier 3 = 21 exclusions including attest; Tier 2 = the seven tools (a tool set here, not exclusions). A route sliding between tiers with every count unchanged still fails (mutant R4).
3. `tests/test_config.py`: both sides' tests kept (operator pair required; exact "1" consent for an external https URL).
4. `scripts/mutants.py`: both sides' mutants kept; R4 re-expressed for this catalog (a Tier 3 exclusion and an unrelated exclusion swap reasons, counts unchanged); PR 368's older S1 dropped for this branch's two-tier S1.

## What the merge broke, found by running everything (and fixed)
- Mutants D6, D7 (PR 368's), W5, ID1, ID4 (this branch's) reported NOT APPLIED because their target text changed; re-pointed (ID4 now targets the `maxLength` cap in `_segment_string`). A check that every one of the 92 applies exactly once passes.
- Two mutants shared the id C6; PR 368's is renamed C10 (a duplicate id crashed one mutation shard on `FileExistsError`; ids are now unique).
- Mutant ID3 (the Tier 2 write's own `AGENT_ID.fullmatch`) SURVIVED the merge: the schema pattern and `check_body_ids` now catch every input it caught, so it was a redundant layer. Pinned on its own in `tests/test_merge_368_380.py` by calling `_write` directly; killed. Nothing was weakened or deleted.

## Counts
field-mcp suite 424 passed (3.13) at 24d5482 (it was 305 on this branch and 197+ on PR 368); `tools/tests` environment doc, C-57 lint, CI pip pins, pytest module names: 82 passed. Mutants: 92 of 92 killed on copies after the commits (run in shards; the ID3 result is from its own rerun after the pin).

## What a reviewer should attack
`tools.py` first: (a) a Tier 2 body id with a trailing newline, a slash, an uppercase agent_id; (b) the order in `_call` (check, then tier split, then `_write`'s own checks, then the intent row); (c) the 200-character cap now comes from `_segment_string` for the other ids: does anything that was legal on Tier 2 become illegal? (every `*_id` body field now also needs the single-segment pattern: `counterparty_agent_id` and `token_id` of check/crossing are covered); (d) the per-tier wording. Then the route-set pins and R4.

## Not verified
GX10; GitHub CI on 24d5482; any real service. PR 368 itself gained commits from another Lane 1 session carrying a `Co-Authored-By: Claude Fable 5.1` trailer; they are inside this merge unchanged (rewriting reviewed heads is the coordinator's call).
