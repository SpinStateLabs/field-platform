# Delta review PR 511 (agent-registry: blank name/owner/domain is a 422; padding stripped; S-B6) — ssl-ff-builder-7-as-reviewer

**VERDICT: PASS WITH CONDITIONS** on head `023811152a180418ca61005704ee514009522778`. Delta from reviewer-9's 9debfd48 is one commit (models.py +11/-3, tests +35): six more invisible characters join the explicit list and the trailing-trim decision is recorded in the code and pinned by two tests. Reviewer-9's C1 (U+17B4, U+17B5, U+180B) is CLOSED. The remaining conditions are the ones on the record plus one new LOW.
Conditions: C1 (decision for Don, carried) normalise the domain before comparison (card B-FU-PR511-domain-normalise): `finance`, `Finance` and a zero-width-spelled `fin​ance` are still different domains; not changed by this commit. C2 (LOW, carried) the legacy blank-owner row pin (card B-FU-PR511-legacy-row). C3 (LOW, new, below) unassigned default-ignorable code points are still accepted as a blank name. C4 (standing gate) CI and GX10 on a rebased head; the head is 195 commits behind main (a clean merge, see below); not run by me.

Independence: I did not build or fix this PR (4 commits, none mine; builder-8 pushed the fix per its note).

## Checks (HIGH, run by me)
- Identity: 4 of 4 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; 0 files under .github/.
- Shape: the head is 195 commits behind origin/main ccd013d4f; `git merge-tree` against it is clean (tree id only). Diff vs main: models.py +50 and test_blank_fields_sb6.py +167, 2 files, 217 insertions.
- Delta read: `_IGNORABLE_EXTRA` gains U+17B4, U+17B5, U+180B, U+180C, U+180D, U+180F; the comment records the decision "a TRAILING ignorable character is trimmed even when something visible precedes it"; tests add six one-example-per-class rows and two trailing cases (emoji variation selector, right-to-left mark).
- `environment_anchors.py --check`: 0 wrong anchor row(s) (this PR touches no ENVIRONMENT.md row).
- Tests on the exact head (Windows, py3.14, from services/agent-registry): `test_blank_fields_sb6.py` 206 passed (20 s). I did not run the whole agent-registry suite (reviewer-9 ran 491 passed at 9debfd48 in 22 minutes; the concurrency files time out on this box under load, as I reported on PR 862).

## Mutants (9, one at a time, file restored and tree verified clean; counted from the table)
| # | mutant (models.py) | result (first failing test) |
|---|---|---|
| M1 | U+17B4 dropped | KILLED (`..._one_ignorable_class_is_blank[Khmer inherent vowel AQ-name]`) |
| M2 | U+17B5 dropped | KILLED (`[Khmer inherent vowel AA-name]`) |
| M3 | U+180B dropped | KILLED (`[Mongolian FVS one-name]`) |
| M4 | U+180C dropped | KILLED (`[Mongolian FVS two-name]`) |
| M5 | U+180D dropped | KILLED (`[Mongolian FVS three-name]`) |
| M6 | U+180F dropped | KILLED (`[Mongolian FVS four-name]`) |
| M7 | trailing trim removed | KILLED (`test_surrounding_whitespace_is_stripped_on_create`) |
| M8 | leading trim removed | KILLED (same test) |
| M9 | trailing trim only for whitespace (aimed at the new decision) | KILLED: 33 failed, including both new `test_a_trailing_ignorable_character_after_visible_text_is_trimmed_by_decision` cases |
Totals: 9 attempted, 9 killed, 0 survived, 0 not applied.

## New finding C3 (own probe, HIGH on measurement, LOW severity)
Characters that Unicode lists as default-ignorable but that are UNASSIGNED (category Cn) pass as a name: on this head `AgentCreate(name=ch*3)` is ACCEPTED for U+2065, U+FFF0, U+FFF8, U+E0000, U+E0080 and U+E0FFF (measured; Python 3.14's unicodedata). U+180E, U+061C and U+00A0 are refused, and U+17B6 (a vowel sign that draws) is accepted, correctly. The builder says the set stays an explicit list because the standard library has no default-ignorable test; the cheapest closure is to add category Cn to `_IGNORABLE_CATEGORIES`, which also refuses every future unassigned code point, with a test row per range. Same class as reviewer-9's objection 1; a code-point that renders nothing in any font anyway, so impact is cosmetic (an apparently blank name that is not refused).

## Not verified
CI; GX10; Linux; the whole agent-registry suite on this head; rendering in real fonts (a character is "invisible" from its Unicode properties, not from a rendered glyph).
