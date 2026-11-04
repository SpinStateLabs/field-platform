From builder-N4 (Lane R): B-S2-2 spend-governor text bounds, PR 585

Head SHA: 434890dfcacb4e2aef2fc76e8ef330974b7b9b5b (fix/spend-governor-text-bounds-s2-2, draft). UNVERIFIED: no GX10, CI not read.

Claim/dup check: scout evidence true on main (api.py docstring after a statement; fields unbounded) [HIGH]. Part 1 (docstring) is already open PR 566, so NOT done here. Part 2 (bounds) had no PR; PR 555 edits the same two `note:` lines (Utf8Str), so expect a small textual conflict.

Did: max_length on SpendRequest/UsageRequest: note 1000, action 200, model 200, agent_id 128; new tests/test_text_field_bounds.py (6 cases). Red on main (201 == 422), green with change; one mutant (MAX_LABEL_LEN 201) red on 2 cases. spend-governor suite 297 passed; environment_anchors --check clean; four tools tests 260 passed + 1 known c57 baseline.

Deviation: note bound is 1000, not 300: test_usage_55_and_notes.py pins that a 400+ char note is accepted and cut to 300 in the ledger copy.

Not verified: OpenAPI description test (belongs to PR 566); other services' clients that send long notes (not searched).

Decisions needed (Don): the four numbers; whether 566 and 555 land first.
